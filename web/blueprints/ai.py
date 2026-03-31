"""AI chat, conversations, and model management routes."""

import json
import os
import time
import threading
import logging

from flask import Blueprint, request, jsonify, Response, stream_with_context
from werkzeug.utils import secure_filename

from db import get_db, get_db_path, log_activity
from config import get_data_dir
from services import ollama, qdrant
from services.manager import format_size
from web.state import _pull_queue, _pull_queue_lock
from web.validation import validate_json
from web.sql_safety import safe_columns
import web.state as _state

log = logging.getLogger('nomad.web')

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/api/ai/models')
def api_ai_models():
    if not ollama.is_installed() or not ollama.running():
        return jsonify([])
    return jsonify(ollama.list_models())

@ai_bp.route('/api/ai/pull', methods=['POST'])
def api_ai_pull():
    data = request.get_json() or {}
    model_name = data.get('model', ollama.DEFAULT_MODEL)

    def do_pull():
        ollama.pull_model(model_name)

    threading.Thread(target=do_pull, daemon=True).start()
    return jsonify({'status': 'pulling', 'model': model_name})

@ai_bp.route('/api/ai/pull-queue', methods=['POST'])
def api_ai_pull_queue():
    """Queue multiple models for sequential download."""
    data = request.get_json() or {}
    models = data.get('models', [])
    if not models:
        return jsonify({'error': 'No models specified'}), 400
    # Filter out already-installed models
    try:
        installed = set(m['name'] for m in ollama.list_models())
    except Exception:
        installed = set()
    to_pull = [m for m in models if m not in installed]
    if not to_pull:
        return jsonify({'status': 'all_installed', 'count': 0})
    with _pull_queue_lock:
        if _state._pull_queue_active:
            return jsonify({'error': 'A download queue is already running. Wait for it to finish.'}), 409
        _pull_queue.clear()
        _pull_queue.extend(to_pull)
        _state._pull_queue_active = True

    def do_queue():
        try:
            for i, model_name in enumerate(to_pull):
                ollama._pull_progress = {
                    'status': 'pulling', 'model': model_name, 'percent': 0,
                    'detail': f'Queue: {i+1}/{len(to_pull)} — Starting {model_name}...',
                    'queue_pos': i + 1, 'queue_total': len(to_pull),
                }
                ollama.pull_model(model_name)
                # Wait for pull to finish
                for _ in range(7200):
                    p = ollama.get_pull_progress()
                    if p.get('status') in ('complete', 'error', 'idle'):
                        break
                    time.sleep(1)
        finally:
            with _pull_queue_lock:
                _pull_queue.clear()
                _state._pull_queue_active = False

    threading.Thread(target=do_queue, daemon=True).start()
    return jsonify({'status': 'queued', 'count': len(to_pull), 'models': to_pull})

@ai_bp.route('/api/ai/pull-progress')
def api_ai_pull_progress():
    progress = ollama.get_pull_progress()
    progress['queue'] = list(_pull_queue)
    progress['queue_active'] = _state._pull_queue_active
    return jsonify(progress)

@ai_bp.route('/api/ai/delete', methods=['POST'])
def api_ai_delete():
    data = request.get_json() or {}
    model_name = data.get('model')
    if not model_name:
        return jsonify({'error': 'No model specified'}), 400
    success = ollama.delete_model(model_name)
    if not success:
        return jsonify({'error': 'Failed to delete model'}), 500
    return jsonify({'status': 'deleted'})

def _safe_json_list(val, default=None):
    """Parse a JSON string, returning default on failure."""
    if default is None:
        default = []
    try:
        return json.loads(val or '[]')
    except (json.JSONDecodeError, TypeError):
        return default

def build_situation_context(db) -> list[str]:
    """Build rich situation context from DB for AI consumption.
    Returns a list of context section strings."""
    ctx_parts = []

    # Inventory with burn rates
    inv = db.execute('SELECT name, quantity, unit, category, daily_usage, min_quantity, expiration FROM inventory ORDER BY category, name LIMIT 200').fetchall()
    if inv:
        inv_lines = []
        for r in inv:
            line = f'{r["name"]}: {r["quantity"]} {r["unit"]} ({r["category"]})'
            if r['daily_usage'] and r['daily_usage'] > 0:
                days = round(r['quantity'] / r['daily_usage'], 1)
                line += f' — {days} days supply at {r["daily_usage"]}/day'
            if r['min_quantity'] and r['quantity'] <= r['min_quantity']:
                line += ' [LOW STOCK]'
            if r['expiration']:
                line += f' expires {r["expiration"]}'
            inv_lines.append(line)
        ctx_parts.append('INVENTORY:\n' + '\n'.join(inv_lines))

    # Contacts with skills and roles
    contacts = db.execute('SELECT name, role, skills, phone, callsign, blood_type FROM contacts LIMIT 50').fetchall()
    if contacts:
        c_lines = [f'{c["name"]} — {c["role"] or "unassigned"}' +
                   (f', skills: {c["skills"]}' if c.get('skills') else '') +
                   (f', callsign: {c["callsign"]}' if c.get('callsign') else '') +
                   (f', blood: {c["blood_type"]}' if c.get('blood_type') else '')
                   for c in contacts]
        ctx_parts.append('TEAM CONTACTS:\n' + '\n'.join(c_lines))

    # Patients with medical details
    patients = db.execute('SELECT name, age, weight_kg, blood_type, allergies, conditions, medications FROM patients LIMIT 20').fetchall()
    if patients:
        p_lines = []
        for p in patients:
            line = f'{p["name"]}'
            if p['age']: line += f', age {p["age"]}'
            if p['blood_type']: line += f', blood {p["blood_type"]}'
            allg = _safe_json_list(p['allergies'])
            if allg: line += f', ALLERGIES: {", ".join(allg)}'
            cond = _safe_json_list(p['conditions'])
            if cond: line += f', conditions: {", ".join(cond)}'
            meds = _safe_json_list(p['medications'])
            if meds: line += f', meds: {", ".join(meds)}'
            p_lines.append(line)
        ctx_parts.append('PATIENTS:\n' + '\n'.join(p_lines))

    # Fuel storage
    fuel = db.execute('SELECT fuel_type, quantity, unit, location FROM fuel_storage LIMIT 100').fetchall()
    if fuel:
        ctx_parts.append('FUEL: ' + ', '.join(f'{f["fuel_type"]}: {f["quantity"]} {f["unit"]} at {f["location"]}' for f in fuel))

    # Ammo
    ammo = db.execute('SELECT caliber, quantity, location FROM ammo_inventory LIMIT 100').fetchall()
    if ammo:
        ctx_parts.append('AMMO: ' + ', '.join(f'{a["caliber"]}: {a["quantity"]} rounds ({a["location"]})' for a in ammo))

    # Equipment
    equip = db.execute("SELECT name, status, next_service FROM equipment_log WHERE next_service != '' ORDER BY next_service LIMIT 10").fetchall()
    if equip:
        ctx_parts.append('EQUIPMENT: ' + ', '.join(f'{e["name"]}: {e["status"]}, service due {e["next_service"]}' for e in equip))

    # Active alerts
    alerts = db.execute('SELECT title, severity, message FROM alerts WHERE dismissed = 0 LIMIT 10').fetchall()
    if alerts:
        ctx_parts.append('ACTIVE ALERTS:\n' + '\n'.join(f'[{a["severity"]}] {a["title"]}: {a["message"][:100]}' for a in alerts))

    # Weather
    wx = db.execute('SELECT * FROM weather_log ORDER BY created_at DESC LIMIT 1').fetchone()
    if wx:
        ctx_parts.append(f'WEATHER: {dict(wx)}')

    # Power
    pwr = db.execute('SELECT * FROM power_log ORDER BY created_at DESC LIMIT 1').fetchone()
    if pwr:
        ctx_parts.append(f'POWER: Battery {pwr["battery_soc"] or "?"}%, Solar {pwr["solar_watts"] or 0}W, Load {pwr["load_watts"] or 0}W')

    # Recent incidents
    incidents = db.execute("SELECT severity, category, description FROM incidents WHERE created_at >= datetime('now', '-24 hours') ORDER BY created_at DESC LIMIT 5").fetchall()
    if incidents:
        ctx_parts.append('RECENT INCIDENTS (24h): ' + ' | '.join(f'[{r["severity"]}] {r["category"]}: {r["description"][:60]}' for r in incidents))

    return ctx_parts

def get_ai_memory_text() -> str:
    """Load AI memory facts from settings, return formatted string or empty."""
    try:
        mem_db = get_db()
        try:
            mem_row = mem_db.execute("SELECT value FROM settings WHERE key = 'ai_memory'").fetchone()
        finally:
            mem_db.close()
        if mem_row and mem_row['value']:
            memories = json.loads(mem_row['value'])
            if memories:
                lines = '\n'.join(f'- {m["fact"] if isinstance(m, dict) else m}' for m in memories)
                return f'\n\n--- OPERATOR NOTES ---\n{lines}\n--- END NOTES ---'
    except Exception:
        pass
    return ''


@ai_bp.route('/api/ai/chat', methods=['POST'])
def api_ai_chat():
    data = request.get_json() or {}
    model = data.get('model', ollama.DEFAULT_MODEL)
    messages = data.get('messages', [])
    system_prompt = data.get('system_prompt', '')
    use_kb = data.get('knowledge_base', False)

    if not ollama.running():
        return jsonify({'error': 'Ollama is not running'}), 503

    # Situation-aware context injection
    use_situation = data.get('situation_context', False)
    if use_situation:
        db_ctx = None
        try:
            db_ctx = get_db()
            sit_parts = []
            # Inventory summary
            inv_rows = db_ctx.execute('SELECT category, SUM(quantity) as qty, COUNT(*) as cnt FROM inventory GROUP BY category').fetchall()
            if inv_rows:
                sit_parts.append('SUPPLY INVENTORY: ' + ', '.join(f'{r["category"]}: {r["cnt"]} items ({r["qty"]} total)' for r in inv_rows))
            # Low stock
            low = db_ctx.execute('SELECT name, quantity, unit, category FROM inventory WHERE quantity <= min_quantity AND min_quantity > 0 LIMIT 10').fetchall()
            if low:
                sit_parts.append('LOW STOCK ALERTS: ' + ', '.join(f'{r["name"]} ({r["quantity"]} {r["unit"]})' for r in low))
            # Burn rate
            burn = db_ctx.execute('SELECT name, quantity, daily_usage, category FROM inventory WHERE daily_usage > 0 LIMIT 10').fetchall()
            if burn:
                sit_parts.append('BURN RATES: ' + ', '.join(f'{r["name"]}: {round(r["quantity"]/max(r["daily_usage"],0.001),1)} days left' for r in burn))
            # Contacts count
            ct_count = db_ctx.execute('SELECT COUNT(*) as c FROM contacts').fetchone()['c']
            if ct_count:
                sit_parts.append(f'TEAM: {ct_count} contacts registered')
            # Recent incidents
            incidents = db_ctx.execute("SELECT severity, category, description FROM incidents WHERE created_at >= datetime('now', '-24 hours') ORDER BY created_at DESC LIMIT 5").fetchall()
            if incidents:
                sit_parts.append('RECENT INCIDENTS (24h): ' + ' | '.join(f'[{r["severity"]}] {r["category"]}: {r["description"][:60]}' for r in incidents))
            # Situation board
            settings_row = db_ctx.execute("SELECT value FROM settings WHERE key = 'sit_board'").fetchone()
            if settings_row:
                try:
                    sit = json.loads(settings_row['value'] or '{}')
                    sit_parts.append('SITUATION STATUS: ' + ', '.join(f'{k}: {v}' for k, v in sit.items()))
                except (json.JSONDecodeError, TypeError): pass
            # Weather
            wx = db_ctx.execute('SELECT pressure_hpa, temp_f, created_at FROM weather_log WHERE pressure_hpa IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()
            if wx:
                sit_parts.append(f'WEATHER: {wx["pressure_hpa"]} hPa, {wx["temp_f"]}F (as of {wx["created_at"]})')
            # Active alerts
            alerts = db_ctx.execute('SELECT title, severity FROM alerts WHERE dismissed = 0 ORDER BY severity DESC LIMIT 5').fetchall()
            if alerts:
                sit_parts.append('ACTIVE ALERTS: ' + ' | '.join(f'[{a["severity"]}] {a["title"]}' for a in alerts))
            # Power status
            pwr = db_ctx.execute('SELECT battery_soc, solar_watts, load_watts FROM power_log ORDER BY created_at DESC LIMIT 1').fetchone()
            if pwr:
                sit_parts.append(f'POWER: Battery {pwr["battery_soc"] or "?"}%, Solar {pwr["solar_watts"] or 0}W, Load {pwr["load_watts"] or 0}W')
            # Patients with conditions
            patients = db_ctx.execute('SELECT name, allergies, conditions FROM patients LIMIT 5').fetchall()
            if patients:
                def _safe_json(val):
                    try: return json.loads(val or '[]')
                    except (json.JSONDecodeError, TypeError): return []
                pt_str = ', '.join(f'{p["name"]} (allergies: {_safe_json(p["allergies"])}, conditions: {_safe_json(p["conditions"])})' for p in patients)
                sit_parts.append(f'PATIENTS: {pt_str}')
            # Garden/harvest
            harvest_count = db_ctx.execute('SELECT COUNT(*) as c FROM harvest_log').fetchone()['c']
            if harvest_count:
                sit_parts.append(f'GARDEN: {harvest_count} harvests logged')
            if sit_parts:
                ctx = '\n'.join(sit_parts)
                system_prompt = (system_prompt + '\n\n' if system_prompt else '') + \
                    f'You have access to the user\'s current preparedness data. Use this to give specific, actionable advice based on their actual situation:\n\n--- Current Situation ---\n{ctx}\n--- End Situation ---'
        except Exception as e:
            log.warning(f'Situation context injection failed: {e}')
        finally:
            if db_ctx:
                try: db_ctx.close()
                except Exception: pass

    # RAG: inject knowledge base context if enabled, with source citations
    _rag_citations = []
    if use_kb and qdrant.running() and messages:
        last_user_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), '')
        if last_user_msg:
            try:
                from web.blueprints.kb import embed_text as _embed_text
                vectors = _embed_text([last_user_msg], prefix='search_query: ')
                if vectors:
                    results = qdrant.search(vectors[0], limit=6)
                    if results:
                        context_parts = []
                        seen_files = set()
                        for r in results:
                            if r.get('score', 0) <= 0.3:
                                continue
                            payload = r.get('payload', {})
                            text = payload.get('text', '')
                            filename = payload.get('filename', 'Unknown')
                            doc_id = payload.get('doc_id')
                            if text:
                                context_parts.append(f'[Source: {filename}]\n{text}')
                                if filename not in seen_files:
                                    seen_files.add(filename)
                                    _rag_citations.append({
                                        'filename': filename,
                                        'doc_id': doc_id,
                                        'score': round(r.get('score', 0), 3),
                                        'excerpt': text[:150] + ('...' if len(text) > 150 else ''),
                                    })
                        if context_parts:
                            kb_context = '\n\n---\n\n'.join(context_parts[:4])
                            system_prompt = (system_prompt + '\n\n' if system_prompt else '') + \
                                f'Use the following knowledge base context to help answer the question. Cite sources by mentioning the document name when relevant. If the context is not relevant, ignore it.\n\n--- Knowledge Base ---\n{kb_context}\n--- End Knowledge Base ---'
            except Exception as e:
                log.warning(f'RAG context injection failed: {e}')

    # AI Memory: inject persistent facts the user has stored
    try:
        mem_db = get_db()
        try:
            mem_row = mem_db.execute("SELECT value FROM settings WHERE key = 'ai_memory'").fetchone()
        finally:
            mem_db.close()
        if mem_row and mem_row['value']:
            memories = json.loads(mem_row['value'])
            if memories:
                mem_text = '\n'.join(f'- {m["fact"] if isinstance(m, dict) else m}' for m in memories)
                system_prompt = (system_prompt + '\n\n' if system_prompt else '') + \
                    f'Important context the user has asked you to remember:\n{mem_text}'
    except Exception as e:
        log.warning(f'AI memory injection failed: {e}')

    if system_prompt:
        messages = [{'role': 'system', 'content': system_prompt}] + messages

    def generate():
        try:
            # Send RAG citations as first chunk if available
            if _rag_citations:
                yield json.dumps({'citations': _rag_citations}) + '\n'
            for line in ollama.chat(model, messages, stream=True):
                if line:
                    yield line.decode('utf-8') + '\n'
        except Exception as e:
            yield json.dumps({'error': str(e)}) + '\n'

    return Response(generate(), mimetype='text/event-stream')

@ai_bp.route('/api/ai/quick-query', methods=['POST'])
def api_ai_quick_query():
    """Answer a focused question using real data without full chat context.
    Designed for the dashboard copilot widget."""
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'error': 'No question'}), 400
    if not ollama.running():
        return jsonify({'error': 'AI service not running'}), 503

    # Build rich data context from DB using shared helper
    db = get_db()
    try:
        ctx_parts = build_situation_context(db)
    finally:
        db.close()

    context = '\n\n'.join(ctx_parts) if ctx_parts else 'No data has been entered yet.'
    memory_text = get_ai_memory_text()

    system = f"""You are the NOMAD Survival Operations Copilot — an AI embedded in a desktop-first preparedness and field-operations workspace. Your role is to provide actionable intelligence based on the operator's REAL supply data, team roster, medical records, and equipment status.

RULES:
- Answer using ONLY the data below. Never fabricate items, quantities, or people.
- Use exact names, quantities, and numbers from the data.
- If a supply has daily_usage, calculate and report days remaining.
- Flag anything critical: items below 7 days supply, expired items, overdue equipment.
- Keep responses concise (2-4 sentences). Be direct — this is an ops brief, not a conversation.
- If asked about something not in the data, say "No data available for that" — don't guess.

--- OPERATOR'S LIVE DATA ---
{context}
--- END DATA ---{memory_text}"""

    try:
        model = data.get('model', ollama.DEFAULT_MODEL)
        result = ollama.chat(model, [{'role': 'system', 'content': system}, {'role': 'user', 'content': question}], stream=False)
        response_text = result.get('message', {}).get('content', '') if isinstance(result, dict) else ''
        return jsonify({'answer': response_text.strip(), 'data_sources': list(set(p.split(':')[0] for p in ctx_parts))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@ai_bp.route('/api/ai/suggested-actions')
def api_ai_suggested_actions():
    """Generate suggested actions based on current alerts and data state."""
    db = get_db()
    try:
        suggestions = []
        from datetime import datetime, timedelta
        today = datetime.now().strftime('%Y-%m-%d')
        soon7 = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        soon30 = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

        # Low stock items
        low = db.execute('SELECT name, quantity, unit FROM inventory WHERE quantity <= min_quantity AND min_quantity > 0 LIMIT 3').fetchall()
        for r in low:
            suggestions.append({'type': 'warning', 'action': f'Restock {r["name"]} — only {r["quantity"]} {r["unit"]} remaining', 'module': 'inventory'})

        # Expiring items (7 days)
        expiring = db.execute("SELECT name, expiration FROM inventory WHERE expiration != '' AND expiration <= ? AND expiration >= ? LIMIT 3", (soon7, today)).fetchall()
        for r in expiring:
            suggestions.append({'type': 'urgent', 'action': f'Rotate {r["name"]} — expires {r["expiration"]}', 'module': 'inventory'})

        # Equipment overdue
        overdue = db.execute("SELECT name, next_service FROM equipment_log WHERE next_service != '' AND next_service <= ? LIMIT 3", (today,)).fetchall()
        for r in overdue:
            suggestions.append({'type': 'warning', 'action': f'Service {r["name"]} — overdue since {r["next_service"]}', 'module': 'equipment'})

        # Unresolved critical alerts
        crit = db.execute("SELECT title FROM alerts WHERE dismissed = 0 AND severity = 'critical' LIMIT 3").fetchall()
        for r in crit:
            suggestions.append({'type': 'critical', 'action': f'Resolve alert: {r["title"]}', 'module': 'alerts'})

        # Fuel expiring
        fuel_exp = db.execute("SELECT fuel_type, expires FROM fuel_storage WHERE expires != '' AND expires <= ? LIMIT 2", (soon30,)).fetchall()
        for r in fuel_exp:
            suggestions.append({'type': 'warning', 'action': f'Rotate {r["fuel_type"]} fuel — expires {r["expires"]}', 'module': 'fuel'})

        return jsonify({'suggestions': suggestions[:8]})
    finally:
        db.close()

@ai_bp.route('/api/ai/recommended')
def api_ai_recommended():
    return jsonify(ollama.RECOMMENDED_MODELS)

# ─── Conversation Branching (v5.0 Phase 1) ──────────────────────

@ai_bp.route('/api/conversations/<int:cid>/branch', methods=['POST'])
def api_conversation_branch(cid):
    """Fork a conversation from a specific message index."""
    d = request.json or {}
    msg_idx = d.get('message_index', 0)
    db = get_db()
    try:
        convo = db.execute('SELECT * FROM conversations WHERE id = ?', (cid,)).fetchone()
        if not convo:
            return jsonify({'error': 'Conversation not found'}), 404
        messages = json.loads(convo['messages'] or '[]')
        # Keep messages up to and including the branch point
        branched = messages[:msg_idx + 1]
        db.execute(
            'INSERT INTO conversation_branches (conversation_id, parent_message_idx, messages) VALUES (?, ?, ?)',
            (cid, msg_idx, json.dumps(branched))
        )
        branch_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.execute('UPDATE conversations SET branch_count = branch_count + 1 WHERE id = ?', (cid,))
        db.commit()
        return jsonify({'branch_id': branch_id, 'messages': branched})
    finally:
        db.close()

@ai_bp.route('/api/conversations/<int:cid>/branches')
def api_conversation_branches(cid):
    """List all branches of a conversation."""
    db = get_db()
    try:
        rows = db.execute(
            'SELECT id, parent_message_idx, created_at FROM conversation_branches WHERE conversation_id = ? ORDER BY created_at DESC',
            (cid,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@ai_bp.route('/api/conversations/branches/<int:bid>')
def api_conversation_branch_get(bid):
    """Get a specific conversation branch."""
    db = get_db()
    try:
        row = db.execute('SELECT * FROM conversation_branches WHERE id = ?', (bid,)).fetchone()
        if not row:
            return jsonify({'error': 'Branch not found'}), 404
        return jsonify(dict(row))
    finally:
        db.close()

@ai_bp.route('/api/conversations/branches/<int:bid>', methods=['PUT'])
def api_conversation_branch_update(bid):
    """Update branch messages (append new messages to branch)."""
    d = request.json or {}
    db = get_db()
    try:
        db.execute('UPDATE conversation_branches SET messages = ? WHERE id = ?',
                   (json.dumps(d.get('messages', [])), bid))
        db.commit()
        return jsonify({'status': 'ok'})
    finally:
        db.close()

# ─── AI Image Input / Multimodal (v5.0 Phase 1) ─────────────────

@ai_bp.route('/api/ai/chat-with-image', methods=['POST'])
def api_ai_chat_image():
    """Send a message with an image to a multimodal model (llava, gemma3, etc.)."""
    if 'image' not in request.files and 'image_base64' not in (request.form or {}):
        return jsonify({'error': 'No image provided'}), 400

    model = request.form.get('model', '')
    message = request.form.get('message', 'Describe this image.')

    # Get image as base64
    import base64
    if 'image' in request.files:
        img_data = base64.b64encode(request.files['image'].read()).decode('utf-8')
    else:
        img_data = request.form.get('image_base64', '')

    if not model:
        return jsonify({'error': 'model required'}), 400

    try:
        import requests as _req
        resp = _req.post('http://localhost:11434/api/chat', json={
            'model': model,
            'messages': [{
                'role': 'user',
                'content': message,
                'images': [img_data]
            }],
            'stream': False
        }, timeout=120)
        if resp.ok:
            data = resp.json()
            answer = data.get('message', {}).get('content', 'No response')
            return jsonify({'answer': answer, 'model': model})
        return jsonify({'error': f'Model returned {resp.status_code}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_bp.route('/api/conversations')
def api_conversations_list():
    db = get_db()
    try:
        convos = db.execute('SELECT id, title, model, created_at, updated_at, branch_count FROM conversations ORDER BY updated_at DESC').fetchall()
    finally:
        db.close()
    return jsonify([dict(c) for c in convos])

@ai_bp.route('/api/conversations', methods=['POST'])
def api_conversations_create():
    data = request.get_json() or {}
    db = get_db()
    try:
        cur = db.execute('INSERT INTO conversations (title, model, messages) VALUES (?, ?, ?)',
                         (data.get('title', 'New Chat'), data.get('model', ''), '[]'))
        db.commit()
        cid = cur.lastrowid
        convo = db.execute('SELECT * FROM conversations WHERE id = ?', (cid,)).fetchone()
    finally:
        db.close()
    return jsonify(dict(convo)), 201

@ai_bp.route('/api/conversations/<int:cid>')
def api_conversations_get(cid):
    db = get_db()
    try:
        convo = db.execute('SELECT * FROM conversations WHERE id = ?', (cid,)).fetchone()
    finally:
        db.close()
    if not convo:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(convo))

@ai_bp.route('/api/conversations/<int:cid>', methods=['PUT'])
def api_conversations_update(cid):
    data = request.get_json() or {}
    db = get_db()
    try:
        update_data = {}
        if 'title' in data:
            update_data['title'] = data['title']
        if 'model' in data:
            update_data['model'] = data['model']
        if 'messages' in data:
            update_data['messages'] = json.dumps(data['messages'])
        filtered = safe_columns(update_data, ['title', 'model', 'messages'])
        if filtered:
            set_clause = ', '.join(f'{col} = ?' for col in filtered)
            vals = list(filtered.values())
            vals.append(cid)
            db.execute(f'UPDATE conversations SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?', vals)
        db.commit()
    finally:
        db.close()
    return jsonify({'status': 'saved'})

@ai_bp.route('/api/conversations/<int:cid>', methods=['PATCH'])
def api_conversation_rename(cid):
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'error': 'Title required'}), 400
    db = get_db()
    try:
        db.execute('UPDATE conversations SET title = ? WHERE id = ?', (title, cid))
        db.commit()
    finally:
        db.close()
    return jsonify({'status': 'renamed'})

@ai_bp.route('/api/conversations/<int:cid>', methods=['DELETE'])
def api_conversations_delete(cid):
    db = get_db()
    try:
        db.execute('DELETE FROM conversations WHERE id = ?', (cid,))
        db.commit()
    finally:
        db.close()
    return jsonify({'status': 'deleted'})

@ai_bp.route('/api/conversations/all', methods=['DELETE'])
def api_conversations_delete_all():
    db = get_db()
    try:
        db.execute('DELETE FROM conversations')
        db.commit()
    finally:
        db.close()
    return jsonify({'status': 'deleted'})

@ai_bp.route('/api/conversations/search')
def api_conversations_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    # Escape LIKE wildcard characters to prevent unintended pattern matching
    q_escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    db = get_db()
    try:
        rows = db.execute(
            "SELECT id, title, model, created_at FROM conversations WHERE title LIKE ? ESCAPE '\\' OR messages LIKE ? ESCAPE '\\' ORDER BY updated_at DESC LIMIT 20",
            (f'%{q_escaped}%', f'%{q_escaped}%')
        ).fetchall()
    finally:
        db.close()
    return jsonify([dict(r) for r in rows])

@ai_bp.route('/api/conversations/<int:cid>/export')
def api_conversations_export(cid):
    db = get_db()
    try:
        convo = db.execute('SELECT * FROM conversations WHERE id = ?', (cid,)).fetchone()
    finally:
        db.close()
    if not convo:
        return jsonify({'error': 'Not found'}), 404
    messages = json.loads(convo['messages'] or '[]')
    md = f"# {convo['title']}\n\n"
    md += f"*Model: {convo['model'] or 'Unknown'} | {convo['created_at']}*\n\n---\n\n"
    for m in messages:
        role = 'You' if m['role'] == 'user' else 'AI'
        md += f"**{role}:**\n\n{m.get('content', '')}\n\n---\n\n"
    safe_title = ''.join(c for c in (convo['title'] or 'export') if c.isalnum() or c in ' _-').strip() or 'export'
    return Response(md, mimetype='text/markdown',
                   headers={'Content-Disposition': f'attachment; filename="{safe_title}.md"'})

@ai_bp.route('/api/ai/auto-setup', methods=['POST'])
def api_ai_auto_setup():
    """Auto-pull default model. Called after wizard installs Ollama."""
    if not ollama.is_installed():
        return jsonify({'error': 'Ollama not installed'}), 400

    def do_setup():
        # Wait for Ollama to be ready
        for _ in range(30):
            if ollama.running():
                break
            time.sleep(1)
        if ollama.running():
            log.info('Auto-pulling default model llama3.2:3b...')
            log_activity('auto_model_pull', 'ollama', 'llama3.2:3b')
            ollama.pull_model('llama3.2:3b')

    threading.Thread(target=do_setup, daemon=True).start()
    return jsonify({'status': 'started'})

@ai_bp.route('/api/library/upload-pdf', methods=['POST'])
def api_library_upload_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'error': 'Invalid filename'}), 400
    pdf_dir = os.path.join(get_data_dir(), 'library')
    os.makedirs(pdf_dir, exist_ok=True)
    filepath = os.path.join(pdf_dir, filename)
    file.save(filepath)
    return jsonify({'status': 'uploaded', 'filename': filename, 'size': os.path.getsize(filepath)}), 201

@ai_bp.route('/api/library/pdfs')
def api_library_pdfs():
    pdf_dir = os.path.join(get_data_dir(), 'library')
    if not os.path.isdir(pdf_dir):
        return jsonify([])
    files = []
    for f in os.listdir(pdf_dir):
        if f.lower().endswith(('.pdf', '.epub', '.txt', '.md')):
            fp = os.path.join(pdf_dir, f)
            files.append({'filename': f, 'size': format_size(os.path.getsize(fp)), 'type': f.rsplit('.', 1)[-1].lower()})
    return jsonify(sorted(files, key=lambda x: x['filename']))

@ai_bp.route('/api/library/serve/<path:filename>')
def api_library_serve(filename):
    pdf_dir = os.path.join(get_data_dir(), 'library')
    safe = os.path.normpath(os.path.join(pdf_dir, secure_filename(filename)))
    if not safe.startswith(os.path.normpath(pdf_dir)) or not os.path.isfile(safe):
        return jsonify({'error': 'Not found'}), 404
    from flask import send_file
    return send_file(safe)

@ai_bp.route('/api/library/delete/<path:filename>', methods=['DELETE'])
def api_library_delete(filename):
    pdf_dir = os.path.join(get_data_dir(), 'library')
    safe = os.path.normpath(os.path.join(pdf_dir, secure_filename(filename)))
    if not safe.startswith(os.path.normpath(pdf_dir)):
        return jsonify({'error': 'Invalid'}), 400
    if os.path.isfile(safe):
        os.remove(safe)
    return jsonify({'status': 'deleted'})

# ─── AI Chat File Upload (drag/drop) ──────────────────────────────

@ai_bp.route('/api/ai/upload-context', methods=['POST'])
def api_ai_upload_context():
    """Upload a file and extract text for AI chat context."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    content = ''
    if ext == 'pdf':
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(file)
            content = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except Exception as e:
            return jsonify({'error': f'PDF read failed: {e}'}), 400
    elif ext in ('txt', 'md', 'csv', 'log', 'json', 'xml', 'html'):
        content = file.read().decode('utf-8', errors='ignore')
    else:
        return jsonify({'error': f'Unsupported file type: {ext}'}), 400
    # Truncate to ~4000 words to fit in context
    words = content.split()
    if len(words) > 4000:
        content = ' '.join(words[:4000]) + '\n\n[... truncated, file too large for full context ...]'
    return jsonify({'filename': filename, 'content': content, 'words': len(words)})

# ─── Comms Log API ─────────────────────────────────────────────────


@ai_bp.route('/api/ai/model-info/<model_name>')
def api_ai_model_info(model_name):
    """Get detailed model info for model cards."""
    try:
        import requests as _req
        r = _req.get(f'http://localhost:11434/api/show', json={'name': model_name}, timeout=5)
        if r.ok:
            data = r.json()
            details = data.get('details', {})
            model_info = data.get('model_info', {})
            # Extract key metrics
            params = details.get('parameter_size', 'Unknown')
            quant = details.get('quantization_level', 'Unknown')
            family = details.get('family', 'Unknown')
            fmt = details.get('format', '')
            # Estimate RAM from parameter count
            param_num = 0
            if isinstance(params, str):
                p = params.lower().replace('b', '').replace(' ', '')
                try:
                    param_num = float(p)
                except Exception:
                    pass
            ram_est = f'~{max(1, round(param_num * 0.6))} GB' if param_num > 0 else 'Unknown'
            return jsonify({
                'name': model_name,
                'parameters': params,
                'quantization': quant,
                'family': family,
                'format': fmt,
                'ram_estimate': ram_est,
                'size_bytes': model_info.get('general.file_size', 0),
            })
        return jsonify({'name': model_name, 'error': 'Could not fetch model info'}), 404
    except Exception as e:
        return jsonify({'name': model_name, 'error': str(e)}), 500

# ─── Media Metadata Editor (v5.0 Phase 6) ───────────────────────


@ai_bp.route('/api/ai/training/datasets')
def api_training_datasets():
    db = get_db()
    rows = db.execute('SELECT * FROM training_datasets ORDER BY created_at DESC LIMIT 50').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@ai_bp.route('/api/ai/training/datasets', methods=['POST'])
def api_training_datasets_create():
    """Create a training dataset from conversation history or uploaded JSONL."""
    data = request.get_json() or {}
    name = (data.get('name', '') or 'Training Dataset').strip()[:200]
    source = data.get('source', 'conversations')  # 'conversations' or 'upload'
    base_model = data.get('base_model', '')

    db = get_db()
    records = []
    if source == 'conversations':
        # Extract Q&A pairs from conversation history (messages stored as JSON array in conversations.messages)
        convos = db.execute('SELECT messages FROM conversations ORDER BY updated_at DESC LIMIT 20').fetchall()
        for c in convos:
            try:
                msgs = json.loads(c['messages'] or '[]')
            except (json.JSONDecodeError, TypeError):
                continue
            for i in range(len(msgs) - 1):
                if isinstance(msgs[i], dict) and isinstance(msgs[i+1], dict) and msgs[i].get('role') == 'user' and msgs[i+1].get('role') == 'assistant':
                    records.append({'instruction': (msgs[i].get('content', '') or '')[:2000], 'output': (msgs[i+1].get('content', '') or '')[:2000]})

    # Save dataset file
    ds_dir = os.path.join(get_data_dir(), 'training_datasets')
    os.makedirs(ds_dir, exist_ok=True)
    import re as _re
    safe_name = _re.sub(r'[^a-z0-9_-]', '', name.replace(' ', '_').lower())[:100] or 'dataset'
    ds_file = os.path.join(ds_dir, f'{safe_name}_{int(time.time())}.jsonl')
    with open(ds_file, 'w') as f:
        for rec in records:
            f.write(json.dumps(rec) + '\n')

    db.execute('INSERT INTO training_datasets (name, description, format, record_count, file_path, base_model, status) VALUES (?,?,?,?,?,?,?)',
               (name, data.get('description', ''), 'jsonl', len(records), ds_file, base_model, 'ready'))
    db.commit()
    did = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.close()
    log_activity('training_dataset_created', 'ai', f'Dataset "{name}" with {len(records)} records')
    return jsonify({'id': did, 'records': len(records)}), 201

@ai_bp.route('/api/ai/training/jobs')
def api_training_jobs():
    db = get_db()
    rows = db.execute('SELECT j.*, d.name as dataset_name FROM training_jobs j LEFT JOIN training_datasets d ON j.dataset_id = d.id ORDER BY j.created_at DESC LIMIT 50').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@ai_bp.route('/api/ai/training/jobs', methods=['POST'])
def api_training_jobs_create():
    """Create a training job. Generates an Ollama Modelfile for the custom model."""
    data = request.get_json() or {}
    dataset_id = data.get('dataset_id')
    import re as _re
    base_model = _re.sub(r'[^a-zA-Z0-9._:-]', '', data.get('base_model', 'llama3.2'))[:100] or 'llama3.2'
    output_model = _re.sub(r'[^a-zA-Z0-9_-]', '', data.get('output_model', f'nomad-custom-{int(time.time())}'))[:100] or f'nomad-custom-{int(time.time())}'
    epochs = min(max(int(data.get('epochs', 3)), 1), 20)
    lr = float(data.get('learning_rate', 0.0002))

    db = get_db()
    ds = db.execute('SELECT * FROM training_datasets WHERE id = ?', (dataset_id,)).fetchone() if dataset_id else None

    # Generate Ollama Modelfile
    modelfile_dir = os.path.join(get_data_dir(), 'modelfiles')
    os.makedirs(modelfile_dir, exist_ok=True)
    modelfile_path = os.path.join(modelfile_dir, f'{output_model}.Modelfile')

    system_prompt = "You are NOMAD, a survival and preparedness AI assistant. You provide practical, actionable advice for emergency preparedness, off-grid living, and disaster response."
    if ds:
        # Read sample records for system prompt enhancement
        try:
            with open(ds['file_path'], 'r') as f:
                samples = [json.loads(line) for line in f.readlines()[:5]]
            if samples:
                topics = ', '.join(set(s.get('instruction', '')[:50] for s in samples[:3]))
                system_prompt += f" Your training focused on: {topics}."
        except Exception as e:
            log.warning(f'Could not read training dataset samples: {e}')

    with open(modelfile_path, 'w') as f:
        f.write(f'FROM {base_model}\n')
        f.write(f'SYSTEM """{system_prompt}"""\n')
        f.write(f'PARAMETER temperature 0.7\n')
        f.write(f'PARAMETER top_p 0.9\n')
        f.write(f'PARAMETER num_ctx 4096\n')

    db.execute('INSERT INTO training_jobs (dataset_id, base_model, output_model, method, epochs, learning_rate, status, log_text) VALUES (?,?,?,?,?,?,?,?)',
               (dataset_id, base_model, output_model, 'modelfile', epochs, lr, 'ready',
                f'Modelfile created at {modelfile_path}\nBase model: {base_model}\nRun: ollama create {output_model} -f {modelfile_path}'))
    db.commit()
    jid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.close()
    log_activity('training_job_created', 'ai', f'Job for {output_model} from {base_model}')
    return jsonify({'id': jid, 'output_model': output_model}), 201

@ai_bp.route('/api/ai/training/jobs/<int:jid>/run', methods=['POST'])
def api_training_jobs_run(jid):
    """Execute training job — runs ollama create with the Modelfile."""
    db = get_db()
    job = db.execute('SELECT * FROM training_jobs WHERE id = ? AND status = ?', (jid, 'ready')).fetchone()
    if not job:
        db.close()
        return jsonify({'error': 'Job not found or not in ready state'}), 404

    db.execute("UPDATE training_jobs SET status = 'running', started_at = datetime('now') WHERE id = ?", (jid,))
    db.commit()
    db.close()

    def do_train():
        try:
            import requests as req
            # Use Ollama create API
            modelfile_path = os.path.join(get_data_dir(), 'modelfiles', f'{job["output_model"]}.Modelfile')
            with open(modelfile_path, 'r') as f:
                modelfile_content = f.read()
            resp = req.post(f'http://localhost:{ollama.OLLAMA_PORT}/api/create',
                           json={'name': job['output_model'], 'modelfile': modelfile_content},
                           timeout=300)
            db2 = get_db()
            if resp.status_code == 200:
                db2.execute("UPDATE training_jobs SET status = 'completed', progress = 100, completed_at = datetime('now'), log_text = log_text || ? WHERE id = ?",
                           (f'\nModel {job["output_model"]} created successfully!', jid))
            else:
                db2.execute("UPDATE training_jobs SET status = 'failed', log_text = log_text || ? WHERE id = ?",
                           (f'\nFailed: {resp.text[:500]}', jid))
            db2.commit()
            db2.close()
        except Exception as e:
            try:
                db2 = get_db()
                db2.execute("UPDATE training_jobs SET status = 'failed', log_text = log_text || ? WHERE id = ?",
                           (f'\nError: {str(e)[:500]}', jid))
                db2.commit()
                db2.close()
            except Exception:
                pass

    t = threading.Thread(target=do_train, daemon=True)
    t.start()
    return jsonify({'status': 'running'})
