"""Federation, sync, node discovery, and dead drop routes."""

import json
import logging
import platform
import time
import threading
import uuid as _uuid

from flask import Blueprint, request, jsonify, Response

from config import Config
from db import get_db, get_db_path, log_activity
from web.state import _discovered_peers, broadcast_event

log = logging.getLogger('nomad.web')

federation_bp = Blueprint('federation', __name__)


# ─── Version (read from app module at import time if possible) ──────
def _get_version():
    try:
        from web.app import VERSION
        return VERSION
    except Exception:
        return '0.0.0'


# ─── Node Identity Helpers ──────────────────────────────────────────

def _get_node_id():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'node_id'").fetchone()
    if row and row['value']:
        db.close()
        return row['value']
    node_id = str(_uuid.uuid4())[:8]
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('node_id', ?)", (node_id,))
    db.commit()
    db.close()
    return node_id


def _get_node_name():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'node_name'").fetchone()
    db.close()
    return (row['value'] if row and row['value'] else platform.node()) or 'NOMAD Node'


def _vc_dominates(a, b):
    """Check if vector clock a dominates b (a >= b for all keys, a > b for at least one)."""
    all_keys = set(list(a.keys()) + list(b.keys()))
    if not all_keys:
        return False
    at_least_one_greater = False
    for k in all_keys:
        av = a.get(k, 0)
        bv = b.get(k, 0)
        if av < bv:
            return False
        if av > bv:
            at_least_one_greater = True
    return at_least_one_greater


def _check_origin(req):
    """Block cross-origin state-changing requests (CSRF protection)."""
    origin = req.headers.get('Origin', '')
    if origin and not origin.startswith(('http://localhost:', 'http://127.0.0.1:')):
        from flask import abort
        abort(403, 'Cross-origin request blocked')


# ─── Node Identity ──────────────────────────────────────────────────

@federation_bp.route('/api/node/identity')
def api_node_identity():
    return jsonify({'node_id': _get_node_id(), 'node_name': _get_node_name(), 'version': _get_version()})


@federation_bp.route('/api/node/identity', methods=['PUT'])
def api_node_identity_update():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if name:
        db = get_db()
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('node_name', ?)", (name,))
        db.commit()
        db.close()
    return jsonify({'status': 'updated', 'node_name': name})


# ─── UDP Discovery ──────────────────────────────────────────────────

@federation_bp.route('/api/node/discover', methods=['POST'])
def api_node_discover():
    """Broadcast UDP to find other NOMAD Field Desk nodes on the LAN."""
    import socket
    _discovered_peers.clear()
    node_id = _get_node_id()
    node_name = _get_node_name()
    msg = json.dumps({'type': 'nomad_discover', 'node_id': node_id, 'node_name': node_name, 'port': Config.APP_PORT}).encode()

    discovery_port = Config.DISCOVERY_PORT
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(3)
        sock.sendto(msg, ('<broadcast>', discovery_port))

        end_time = time.time() + 3
        while time.time() < end_time:
            try:
                data, addr = sock.recvfrom(1024)
                peer = json.loads(data.decode())
                if peer.get('type') == 'nomad_announce' and peer.get('node_id') != node_id:
                    _discovered_peers[peer['node_id']] = {
                        'node_id': peer['node_id'], 'node_name': peer.get('node_name', 'Unknown'),
                        'ip': addr[0], 'port': peer.get('port', 8080), 'version': peer.get('version', '?'),
                    }
            except socket.timeout:
                break
            except Exception:
                continue
        sock.close()
    except Exception as e:
        log.warning(f'Discovery broadcast failed: {e}')

    return jsonify({'peers': list(_discovered_peers.values()), 'self': {'node_id': node_id, 'node_name': node_name}})


@federation_bp.route('/api/node/peers')
def api_node_peers():
    return jsonify(list(_discovered_peers.values()))


@federation_bp.route('/api/node/announce', methods=['POST'])
def api_node_announce():
    """Respond to a discovery broadcast (called by peers via HTTP as fallback)."""
    return jsonify({
        'type': 'nomad_announce', 'node_id': _get_node_id(),
        'node_name': _get_node_name(), 'port': 8080, 'version': _get_version(),
    })


# ─── Sync Push/Pull/Receive ────────────────────────────────────────

@federation_bp.route('/api/node/sync-push', methods=['POST'])
def api_node_sync_push():
    """Push data TO a peer node."""
    data = request.get_json() or {}
    peer_ip = data.get('ip')
    peer_port = data.get('port', 8080)
    if not peer_ip:
        return jsonify({'error': 'No peer IP'}), 400
    import ipaddress as _ipa
    try:
        ip_obj = _ipa.ip_address(peer_ip)
        if ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_unspecified:
            return jsonify({'error': 'Invalid peer IP address'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid IP address format'}), 400

    import requests as req
    SYNC_TABLES = ['inventory', 'contacts', 'checklists', 'notes', 'incidents', 'waypoints']
    node_id = _get_node_id()
    node_name = _get_node_name()

    db = get_db()
    payload = {'source_node_id': node_id, 'source_node_name': node_name, 'tables': {}}
    total_items = 0
    for table in SYNC_TABLES:
        try:
            rows = db.execute(f'SELECT * FROM {table}').fetchall()
            table_data = [dict(r) for r in rows]
            for row in table_data:
                row.pop('id', None)
                row['_source_node'] = node_id
            payload['tables'][table] = table_data
            total_items += len(table_data)
            import hashlib
            for row in table_data:
                row_key = hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:16]
                existing = db.execute('SELECT clock FROM vector_clocks WHERE table_name = ? AND row_hash = ?', (table, row_key)).fetchone()
                clock = json.loads(existing['clock']) if existing else {}
                clock[node_id] = clock.get(node_id, 0) + 1
                db.execute('INSERT OR REPLACE INTO vector_clocks (table_name, row_hash, clock, last_node, updated_at) VALUES (?, ?, ?, ?, datetime("now"))',
                           (table, row_key, json.dumps(clock), node_id))
            db.commit()
        except Exception as e:
            log.error('Sync push failed for table %s: %s', table, e)

    vc_rows = db.execute('SELECT table_name, row_hash, clock FROM vector_clocks').fetchall()
    payload['vector_clocks'] = {r['table_name']: {} for r in vc_rows}
    for r in vc_rows:
        payload['vector_clocks'][r['table_name']][r['row_hash']] = json.loads(r['clock'] or '{}')
    db.close()

    try:
        r = req.post(f'http://{peer_ip}:{peer_port}/api/node/sync-receive',
                    json=payload, timeout=30)
        result = r.json()
        db = get_db()
        db.execute('INSERT INTO sync_log (direction, peer_node_id, peer_name, peer_ip, tables_synced, items_count, status) VALUES (?,?,?,?,?,?,?)',
                   ('push', result.get('node_id', ''), result.get('node_name', ''), peer_ip,
                    json.dumps({t: len(d) for t, d in payload['tables'].items()}), total_items, 'success'))
        db.commit()
        db.close()
        return jsonify({'status': 'pushed', 'items': total_items, 'peer': result.get('node_name', peer_ip)})
    except Exception as e:
        log.error('Sync push to peer failed: %s', e)
        return jsonify({'error': 'Push to peer failed'}), 500


@federation_bp.route('/api/node/sync-receive', methods=['POST'])
def api_node_sync_receive():
    """Receive data FROM a peer node (merge mode)."""
    data = request.get_json() or {}
    source_node = data.get('source_node_id', '')
    source_name = data.get('source_node_name', '')
    tables = data.get('tables', {})

    if not source_node:
        return jsonify({'error': 'source_node_id required'}), 400
    db_check = get_db()
    peer = db_check.execute("SELECT trust_level FROM federation_peers WHERE node_id = ?", (source_node,)).fetchone()
    db_check.close()
    if not peer or peer['trust_level'] == 'blocked':
        return jsonify({'error': 'Unknown or blocked peer'}), 403

    ALLOWED = {'inventory', 'contacts', 'checklists', 'notes', 'incidents', 'waypoints'}
    db = get_db()
    imported = {}
    total = 0
    for tname, rows in tables.items():
        if tname not in ALLOWED:
            continue
        schema_cols = {r[1] for r in db.execute(f"PRAGMA table_info({tname})").fetchall()}
        count = 0
        for row in rows[:10000]:
            row.pop('id', None)
            row.pop('created_at', None)
            row.pop('updated_at', None)
            row.pop('_source_node', None)
            safe_row = {k: v for k, v in row.items() if k in schema_cols}
            if not safe_row:
                continue
            cols = list(safe_row.keys())
            vals = list(safe_row.values())
            placeholders = ','.join(['?'] * len(cols))
            try:
                db.execute(f'INSERT INTO {tname} ({",".join(cols)}) VALUES ({placeholders})', vals)
                count += 1
            except Exception:
                pass
        imported[tname] = count
        total += count
    db.commit()

    incoming_clocks = data.get('vector_clocks', {})
    conflicts = []
    for tname, hashes in incoming_clocks.items():
        for row_hash, incoming_clock in hashes.items():
            local_row = db.execute('SELECT clock FROM vector_clocks WHERE table_name = ? AND row_hash = ?', (tname, row_hash)).fetchone()
            if local_row:
                local_clock = json.loads(local_row['clock'] or '{}')
                if not _vc_dominates(local_clock, incoming_clock) and not _vc_dominates(incoming_clock, local_clock) and local_clock != incoming_clock:
                    conflicts.append({'table': tname, 'row_hash': row_hash, 'local_clock': local_clock, 'incoming_clock': incoming_clock, 'resolution': 'last-write-wins'})
            merged = dict(local_clock) if local_row else {}
            for node, val in incoming_clock.items():
                merged[node] = max(merged.get(node, 0), val)
            db.execute('INSERT OR REPLACE INTO vector_clocks (table_name, row_hash, clock, last_node, updated_at) VALUES (?, ?, ?, ?, datetime("now"))',
                       (tname, row_hash, json.dumps(merged), source_node))
    db.commit()

    db.execute('INSERT INTO sync_log (direction, peer_node_id, peer_name, peer_ip, tables_synced, items_count, status, conflicts_detected, conflict_details) VALUES (?,?,?,?,?,?,?,?,?)',
               ('receive', source_node, source_name, request.remote_addr or '',
                json.dumps(imported), total, 'success', len(conflicts), json.dumps(conflicts)))
    db.commit()
    db.close()

    log_activity('sync_received', detail=f'From {source_name} ({source_node}): {total} items')
    return jsonify({'status': 'received', 'imported': imported, 'total': total,
                   'node_id': _get_node_id(), 'node_name': _get_node_name()})


@federation_bp.route('/api/node/sync-pull', methods=['POST'])
def api_node_sync_pull():
    """Pull data FROM a peer node."""
    data = request.get_json() or {}
    peer_ip = data.get('ip')
    peer_port = data.get('port', 8080)
    if not peer_ip:
        return jsonify({'error': 'No peer IP'}), 400
    import ipaddress as _ipa
    try:
        ip_obj = _ipa.ip_address(peer_ip)
        if ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_unspecified:
            return jsonify({'error': 'Invalid peer IP address'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid IP address format'}), 400

    import requests as req

    try:
        r = req.post(f'http://{peer_ip}:{peer_port}/api/node/sync-push',
                    json={'ip': request.host.split(':')[0], 'port': 8080}, timeout=30)
        return jsonify({'status': 'pull_requested', 'peer': peer_ip})
    except Exception as e:
        return jsonify({'error': f'Pull failed: {e}'}), 500


# ─── Vector Clock / Conflicts ───────────────────────────────────────

@federation_bp.route('/api/node/vector-clock')
def api_node_vector_clock():
    """Get the current vector clock state for all tracked tables."""
    db = get_db()
    rows = db.execute('SELECT table_name, row_hash, clock, last_node, updated_at FROM vector_clocks ORDER BY table_name').fetchall()
    db.close()
    clocks = {}
    for r in rows:
        tname = r['table_name']
        if tname not in clocks:
            clocks[tname] = []
        clocks[tname].append({'row_hash': r['row_hash'], 'clock': json.loads(r['clock'] or '{}'), 'last_node': r['last_node'], 'updated_at': r['updated_at']})
    return jsonify(clocks)


@federation_bp.route('/api/node/vector-clock/conflicts')
def api_node_vector_clock_conflicts():
    """Get recent sync conflicts."""
    db = get_db()
    rows = db.execute("SELECT * FROM sync_log WHERE conflicts_detected > 0 ORDER BY created_at DESC LIMIT 50").fetchall()
    db.close()
    result = []
    for r in rows:
        entry = dict(r)
        entry['conflict_details'] = json.loads(entry.get('conflict_details') or '[]')
        result.append(entry)
    return jsonify(result)


@federation_bp.route('/api/node/conflicts')
def api_node_conflicts():
    """Get unresolved sync conflicts for the three-way merge UI."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM sync_log WHERE conflicts_detected > 0 AND (resolved IS NULL OR resolved = 0) ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    result = []
    for r in rows:
        entry = dict(r)
        entry['conflict_details'] = json.loads(entry.get('conflict_details') or '[]')
        for conflict in entry['conflict_details']:
            tname = conflict.get('table', '')
            row_hash = conflict.get('row_hash', '')
            if tname and row_hash:
                vc_row = db.execute('SELECT * FROM vector_clocks WHERE table_name = ? AND row_hash = ?', (tname, row_hash)).fetchone()
                if vc_row:
                    conflict['local_node'] = vc_row['last_node']
                    conflict['local_updated'] = vc_row['updated_at']
        result.append(entry)
    db.close()
    return jsonify(result)


@federation_bp.route('/api/node/conflicts/<int:conflict_id>/resolve', methods=['POST'])
def api_node_conflict_resolve(conflict_id):
    """Resolve a sync conflict."""
    _check_origin(request)
    data = request.get_json() or {}
    resolution = data.get('resolution', '')
    if resolution not in ('local', 'remote', 'merged'):
        return jsonify({'error': 'resolution must be one of: local, remote, merged'}), 400

    db = get_db()
    row = db.execute('SELECT * FROM sync_log WHERE id = ?', (conflict_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({'error': 'Conflict not found'}), 404

    conflicts = json.loads(row['conflict_details'] or '[]')

    if resolution == 'remote':
        tables_synced = json.loads(row['tables_synced'] or '{}')
        for conflict in conflicts:
            tname = conflict.get('table', '')
            incoming_clock = conflict.get('incoming_clock', {})
            row_hash = conflict.get('row_hash', '')
            if tname and row_hash:
                db.execute(
                    'INSERT OR REPLACE INTO vector_clocks (table_name, row_hash, clock, last_node, updated_at) VALUES (?, ?, ?, ?, datetime("now"))',
                    (tname, row_hash, json.dumps(incoming_clock), row['peer_node_id'])
                )
    elif resolution == 'merged':
        merged_data = data.get('merged_data', {})
        if not merged_data:
            db.close()
            return jsonify({'error': 'merged_data required for merged resolution'}), 400
        import re as _re
        MERGE_ALLOWED = {'inventory', 'contacts', 'checklists', 'notes', 'incidents', 'waypoints'}
        for tname, rows_to_merge in merged_data.items():
            if tname not in MERGE_ALLOWED:
                continue
            schema_cols = {r[1] for r in db.execute(f"PRAGMA table_info({tname})").fetchall()}
            for merge_row in (rows_to_merge if isinstance(rows_to_merge, list) else [rows_to_merge]):
                safe_row = {k: v for k, v in merge_row.items() if k in schema_cols and _re.match(r'^[a-zA-Z_]\w*$', k)}
                if not safe_row:
                    continue
                if 'id' in safe_row:
                    row_id = safe_row.pop('id')
                    if safe_row:
                        set_clause = ', '.join(f'{k} = ?' for k in safe_row.keys())
                        db.execute(f'UPDATE {tname} SET {set_clause} WHERE id = ?', list(safe_row.values()) + [row_id])
                else:
                    cols = list(safe_row.keys())
                    placeholders = ','.join(['?'] * len(cols))
                    db.execute(f'INSERT INTO {tname} ({",".join(cols)}) VALUES ({placeholders})', list(safe_row.values()))

    db.execute('UPDATE sync_log SET resolved = 1, resolution = ? WHERE id = ?', (resolution, conflict_id))
    db.commit()
    db.close()
    log_activity('conflict_resolved', detail=f'Sync conflict #{conflict_id} resolved as {resolution}')
    return jsonify({'status': 'resolved', 'resolution': resolution})


@federation_bp.route('/api/node/sync-log')
def api_node_sync_log():
    db = get_db()
    rows = db.execute('SELECT * FROM sync_log ORDER BY created_at DESC LIMIT 50').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ─── Sneakernet Sync ────────────────────────────────────────────────

@federation_bp.route('/api/sync/export', methods=['POST'])
def api_sync_export():
    """Export selected data as a portable content pack ZIP."""
    data = request.get_json() or {}
    ALLOWED_SYNC_TABLES = {'inventory', 'contacts', 'checklists', 'notes', 'incidents', 'waypoints'}
    include = [t for t in data.get('include', list(ALLOWED_SYNC_TABLES)) if t in ALLOWED_SYNC_TABLES]
    import io
    import zipfile as zf
    buf = io.BytesIO()
    db = get_db()
    VERSION = _get_version()
    with zf.ZipFile(buf, 'w', zf.ZIP_DEFLATED) as z:
        manifest = {'version': VERSION, 'exported_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'tables': []}
        for table in include:
            try:
                rows = db.execute(f'SELECT * FROM {table}').fetchall()
                table_data = [dict(r) for r in rows]
                z.writestr(f'{table}.json', json.dumps(table_data, indent=2, default=str))
                manifest['tables'].append({'name': table, 'count': len(table_data)})
            except Exception:
                pass
        z.writestr('manifest.json', json.dumps(manifest, indent=2))
    db.close()
    buf.seek(0)
    fname = f'nomad-sync-{time.strftime("%Y%m%d-%H%M%S")}.zip'
    return Response(buf.read(), mimetype='application/zip',
                   headers={'Content-Disposition': f'attachment; filename="{fname}"'})


@federation_bp.route('/api/sync/import', methods=['POST'])
def api_sync_import():
    """Import a content pack ZIP (merge mode)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    import zipfile as zf
    import io
    file = request.files['file']
    db = None
    try:
        with zf.ZipFile(io.BytesIO(file.read())) as z:
            if 'manifest.json' not in z.namelist():
                return jsonify({'error': 'Invalid sync file (no manifest)'}), 400
            manifest = json.loads(z.read('manifest.json'))
            db = get_db()
            imported = {}
            for table_info in manifest.get('tables', []):
                tname = table_info['name']
                if tname not in ('inventory', 'contacts', 'checklists', 'notes', 'incidents', 'waypoints'):
                    continue
                fname = f'{tname}.json'
                if fname not in z.namelist():
                    continue
                rows = json.loads(z.read(fname))
                schema_cols = {row[1] for row in db.execute(f"PRAGMA table_info({tname})").fetchall()}
                count = 0
                for row in rows:
                    row.pop('id', None)
                    row.pop('created_at', None)
                    row.pop('updated_at', None)
                    safe_row = {k: v for k, v in row.items() if k in schema_cols}
                    if not safe_row:
                        continue
                    cols = list(safe_row.keys())
                    vals = list(safe_row.values())
                    placeholders = ','.join(['?'] * len(cols))
                    try:
                        db.execute(f'INSERT INTO {tname} ({",".join(cols)}) VALUES ({placeholders})', vals)
                        count += 1
                    except Exception:
                        pass
                imported[tname] = count
            db.commit()
            return jsonify({'status': 'imported', 'tables': imported})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        if db:
            try: db.close()
            except Exception: pass


# ─── Federation Peers CRUD ──────────────────────────────────────────

@federation_bp.route('/api/federation/peers')
def api_federation_peers():
    db = get_db()
    rows = db.execute('SELECT * FROM federation_peers ORDER BY last_seen DESC').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@federation_bp.route('/api/federation/peers', methods=['POST'])
def api_federation_peer_add():
    data = request.get_json() or {}
    node_id = data.get('node_id', '').strip()
    if not node_id:
        return jsonify({'error': 'node_id required'}), 400
    db = get_db()
    db.execute('INSERT OR REPLACE INTO federation_peers (node_id, node_name, trust_level, ip, port, lat, lng) VALUES (?,?,?,?,?,?,?)',
               (node_id, data.get('node_name', ''), data.get('trust_level', 'observer'),
                data.get('ip', ''), data.get('port', 8080),
                data.get('lat'), data.get('lng')))
    db.commit()
    db.close()
    return jsonify({'status': 'added'})


@federation_bp.route('/api/federation/peers/<node_id>/trust', methods=['PUT'])
def api_federation_peer_trust(node_id):
    data = request.get_json() or {}
    trust = data.get('trust_level', 'observer')
    if trust not in ('observer', 'member', 'trusted', 'admin'):
        return jsonify({'error': 'Invalid trust level'}), 400
    db = get_db()
    db.execute('UPDATE federation_peers SET trust_level = ? WHERE node_id = ?', (trust, node_id))
    db.commit()
    db.close()
    return jsonify({'status': 'updated'})


@federation_bp.route('/api/federation/peers/<node_id>', methods=['DELETE'])
def api_federation_peer_remove(node_id):
    db = get_db()
    db.execute('DELETE FROM federation_peers WHERE node_id = ?', (node_id,))
    db.commit()
    db.close()
    return jsonify({'status': 'removed'})


# ─── Supply Chain GeoJSON ───────────────────────────────────────────

@federation_bp.route('/api/federation/supply-chain')
def api_federation_supply_chain():
    """Return federation peers, offers, and requests as GeoJSON for map visualization."""
    db = get_db()
    peers = db.execute('SELECT * FROM federation_peers WHERE lat IS NOT NULL AND lng IS NOT NULL').fetchall()
    offers = db.execute("SELECT * FROM federation_offers WHERE status = 'active'").fetchall()
    requests_rows = db.execute("SELECT * FROM federation_requests WHERE status = 'active'").fetchall()
    db.close()

    peer_map = {}
    features = []
    trust_colors = {'observer': '#888', 'member': '#5b9fff', 'trusted': '#4caf50', 'admin': '#ffc107'}

    for p in peers:
        d = dict(p)
        peer_map[d['node_id']] = d
        p_offers = [dict(o) for o in offers if o['node_id'] == d['node_id']]
        p_requests = [dict(r) for r in requests_rows if r['node_id'] == d['node_id']]
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [d['lng'], d['lat']]},
            'properties': {
                'type': 'peer', 'node_id': d['node_id'], 'name': d.get('node_name', d['node_id']),
                'trust_level': d.get('trust_level', 'observer'),
                'color': trust_colors.get(d.get('trust_level', 'observer'), '#888'),
                'offers': [{'item': o['item_type'], 'qty': o['quantity']} for o in p_offers],
                'requests': [{'item': r['item_type'], 'qty': r['quantity'], 'urgency': r.get('urgency', 'normal')} for r in p_requests],
            }
        })

    peer_ids = list(peer_map.keys())
    for i, pid1 in enumerate(peer_ids):
        for pid2 in peer_ids[i+1:]:
            p1_offers = {o['item_type'] for o in offers if o['node_id'] == pid1}
            p2_requests = {r['item_type'] for r in requests_rows if r['node_id'] == pid2}
            p2_offers = {o['item_type'] for o in offers if o['node_id'] == pid2}
            p1_requests = {r['item_type'] for r in requests_rows if r['node_id'] == pid1}
            matches = (p1_offers & p2_requests) | (p2_offers & p1_requests)
            if matches:
                features.append({
                    'type': 'Feature',
                    'geometry': {'type': 'LineString', 'coordinates': [
                        [peer_map[pid1]['lng'], peer_map[pid1]['lat']],
                        [peer_map[pid2]['lng'], peer_map[pid2]['lat']]
                    ]},
                    'properties': {
                        'type': 'trade_route',
                        'from': peer_map[pid1].get('node_name', pid1),
                        'to': peer_map[pid2].get('node_name', pid2),
                        'matched_items': list(matches),
                        'match_count': len(matches),
                    }
                })

    return jsonify({'type': 'FeatureCollection', 'features': features})


# ─── Federation Offers/Requests ─────────────────────────────────────

@federation_bp.route('/api/federation/offers')
def api_federation_offers():
    db = get_db()
    rows = db.execute("SELECT * FROM federation_offers WHERE status = 'active' ORDER BY created_at DESC").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@federation_bp.route('/api/federation/offers', methods=['POST'])
def api_federation_offer_create():
    data = request.get_json() or {}
    db = get_db()
    db.execute('INSERT INTO federation_offers (item_type, item_id, quantity, node_id, notes) VALUES (?,?,?,?,?)',
               (data.get('item_type', ''), data.get('item_id'), data.get('quantity', 0),
                data.get('node_id', ''), data.get('notes', '')))
    db.commit()
    db.close()
    return jsonify({'status': 'created'})


@federation_bp.route('/api/federation/requests')
def api_federation_requests():
    db = get_db()
    rows = db.execute("SELECT * FROM federation_requests WHERE status = 'active' ORDER BY urgency DESC, created_at DESC").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@federation_bp.route('/api/federation/requests', methods=['POST'])
def api_federation_request_create():
    data = request.get_json() or {}
    db = get_db()
    db.execute('INSERT INTO federation_requests (item_type, description, quantity, urgency, node_id) VALUES (?,?,?,?,?)',
               (data.get('item_type', ''), data.get('description', ''), data.get('quantity', 0),
                data.get('urgency', 'normal'), data.get('node_id', '')))
    db.commit()
    db.close()
    return jsonify({'status': 'created'})


# ─── Mutual Aid Agreements ──────────────────────────────────────────

@federation_bp.route('/api/federation/mutual-aid')
def api_mutual_aid_list():
    db = get_db()
    rows = db.execute('SELECT * FROM mutual_aid_agreements ORDER BY updated_at DESC').fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        for k in ('our_commitments', 'their_commitments'):
            try: d[k] = json.loads(d[k] or '[]')
            except (json.JSONDecodeError, TypeError): d[k] = []
        result.append(d)
    return jsonify(result)


@federation_bp.route('/api/federation/mutual-aid', methods=['POST'])
def api_mutual_aid_create():
    data = request.get_json() or {}
    if not data.get('title'):
        return jsonify({'error': 'Title required'}), 400
    db = get_db()
    cur = db.execute(
        'INSERT INTO mutual_aid_agreements (peer_node_id, peer_name, title, description, '
        'our_commitments, their_commitments, status, effective_date, expiry_date) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (data.get('peer_node_id', ''), data.get('peer_name', ''), data['title'],
         data.get('description', ''),
         json.dumps(data.get('our_commitments', [])),
         json.dumps(data.get('their_commitments', [])),
         data.get('status', 'draft'),
         data.get('effective_date', ''), data.get('expiry_date', '')))
    db.commit()
    aid = cur.lastrowid
    db.close()
    log_activity('mutual_aid_create', 'federation', f'Agreement "{data["title"]}" created')
    return jsonify({'id': aid, 'status': 'created'}), 201


@federation_bp.route('/api/federation/mutual-aid/<int:aid>', methods=['PUT'])
def api_mutual_aid_update(aid):
    data = request.get_json() or {}
    db = get_db()
    fields, vals = [], []
    for k in ('title', 'description', 'status', 'effective_date', 'expiry_date', 'peer_name'):
        if k in data:
            fields.append(f'{k} = ?')
            vals.append(data[k])
    for k in ('our_commitments', 'their_commitments'):
        if k in data:
            fields.append(f'{k} = ?')
            vals.append(json.dumps(data[k]))
    if 'signed_by_us' in data:
        fields.append('signed_by_us = ?')
        vals.append(1 if data['signed_by_us'] else 0)
    if fields:
        fields.append("updated_at = datetime('now')")
        vals.append(aid)
        db.execute(f'UPDATE mutual_aid_agreements SET {", ".join(fields)} WHERE id = ?', vals)
        db.commit()
    db.close()
    return jsonify({'status': 'updated'})


@federation_bp.route('/api/federation/mutual-aid/<int:aid>', methods=['DELETE'])
def api_mutual_aid_delete(aid):
    db = get_db()
    db.execute('DELETE FROM mutual_aid_agreements WHERE id = ?', (aid,))
    db.commit()
    db.close()
    return jsonify({'status': 'deleted'})


@federation_bp.route('/api/federation/mutual-aid/<int:aid>/sign', methods=['POST'])
def api_mutual_aid_sign(aid):
    """Mark agreement as signed by us, update status to active if both signed."""
    db = get_db()
    db.execute("UPDATE mutual_aid_agreements SET signed_by_us = 1, updated_at = datetime('now') WHERE id = ?", (aid,))
    row = db.execute('SELECT signed_by_us, signed_by_peer FROM mutual_aid_agreements WHERE id = ?', (aid,)).fetchone()
    if row and row['signed_by_us'] and row['signed_by_peer']:
        db.execute("UPDATE mutual_aid_agreements SET status = 'active', updated_at = datetime('now') WHERE id = ?", (aid,))
    db.commit()
    db.close()
    log_activity('mutual_aid_sign', 'federation', f'Agreement #{aid} signed')
    return jsonify({'status': 'signed'})


# ─── Sit Board / Network Map ───────────────────────────────────────

@federation_bp.route('/api/federation/sitboard')
def api_federation_sitboard():
    """Aggregated situation from all peers."""
    db = get_db()
    rows = db.execute('SELECT * FROM federation_sitboard ORDER BY updated_at DESC').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@federation_bp.route('/api/federation/network-map')
def api_federation_network_map():
    """Returns all known nodes with positions for map overlay."""
    db = get_db()
    peers = [dict(r) for r in db.execute('SELECT node_id, node_name, trust_level, last_seen, ip FROM federation_peers').fetchall()]
    for p in peers:
        wp = db.execute("SELECT lat, lng FROM waypoints WHERE name LIKE ? OR notes LIKE ?",
                        (f'%{p["node_name"]}%', f'%{p["node_id"]}%')).fetchone()
        p['lat'] = wp['lat'] if wp else None
        p['lng'] = wp['lng'] if wp else None
    db.close()
    return jsonify(peers)


# ─── Dead Drop Encrypted Messaging ─────────────────────────────────

@federation_bp.route('/api/deaddrop/compose', methods=['POST'])
def api_deaddrop_compose():
    """Compose an encrypted message for dead drop exchange."""
    import hashlib, base64, os as _os
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    recipient = data.get('recipient', '').strip()
    secret = data.get('secret', '').strip()
    if not message or not secret:
        return jsonify({'error': 'Message and shared secret are required'}), 400
    salt = _os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', secret.encode(), salt, 100000)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = _os.urandom(12)
        aesgcm = AESGCM(key)
        encrypted = aesgcm.encrypt(nonce, message.encode('utf-8'), None)
        enc_data = base64.b64encode(salt + nonce + encrypted).decode()
    except ImportError:
        return jsonify({'error': 'cryptography package not installed \u2014 run: pip install cryptography'}), 500
    payload = {
        'version': 2,
        'type': 'nomad-deaddrop',
        'from_node': _get_node_id(),
        'from_name': _get_node_name(),
        'recipient': recipient,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'data': enc_data,
        'checksum': hashlib.sha256(message.encode()).hexdigest()[:16]
    }
    return jsonify({'payload': payload, 'filename': f'deaddrop-{_get_node_id()[:4]}-{int(time.time())}.json'})


@federation_bp.route('/api/deaddrop/decrypt', methods=['POST'])
def api_deaddrop_decrypt():
    """Decrypt a dead drop message."""
    import hashlib, base64
    data = request.get_json() or {}
    payload = data.get('payload', {})
    secret = data.get('secret', '').strip()
    if not payload or not secret:
        return jsonify({'error': 'Payload and shared secret are required'}), 400
    if payload.get('type') != 'nomad-deaddrop':
        return jsonify({'error': 'Invalid dead drop message format'}), 400
    try:
        raw = base64.b64decode(payload['data'])
        version = payload.get('version', 1)
        if version >= 2:
            salt = raw[:16]
            key = hashlib.pbkdf2_hmac('sha256', secret.encode(), salt, 100000)
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                nonce = raw[16:28]
                ciphertext = raw[28:]
                aesgcm = AESGCM(key)
                decrypted = aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
            except ImportError:
                return jsonify({'error': 'cryptography package not installed \u2014 run: pip install cryptography'}), 500
        else:
            key = hashlib.sha256(secret.encode()).digest()
            decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode('utf-8')
        expected = hashlib.sha256(decrypted.encode()).hexdigest()[:16]
        if expected != payload.get('checksum', ''):
            return jsonify({'error': 'Wrong secret or corrupted message'}), 400
        return jsonify({'message': decrypted, 'from_node': payload.get('from_node'), 'from_name': payload.get('from_name'), 'timestamp': payload.get('timestamp')})
    except Exception:
        return jsonify({'error': 'Decryption failed \u2014 wrong secret or corrupted data'}), 400


@federation_bp.route('/api/deaddrop/messages')
def api_deaddrop_messages():
    """List received dead drop messages."""
    db = get_db()
    rows = db.execute('SELECT * FROM dead_drop_messages ORDER BY created_at DESC LIMIT 100').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@federation_bp.route('/api/deaddrop/import', methods=['POST'])
def api_deaddrop_import():
    """Import a dead drop JSON file and store it."""
    data = request.get_json() or {}
    payload = data.get('payload', {})
    if payload.get('type') != 'nomad-deaddrop':
        return jsonify({'error': 'Invalid dead drop format'}), 400
    db = get_db()
    db.execute('INSERT INTO dead_drop_messages (from_node_id, from_name, recipient, encrypted_data, checksum, message_timestamp) VALUES (?,?,?,?,?,?)',
               (payload.get('from_node', ''), payload.get('from_name', ''), payload.get('recipient', ''),
                payload.get('data', ''), payload.get('checksum', ''), payload.get('timestamp', '')))
    db.commit()
    db.close()
    log_activity('deaddrop_import', 'comms', f'Imported message from {payload.get("from_name", "unknown")}')
    return jsonify({'status': 'imported'})
