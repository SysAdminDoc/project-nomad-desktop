"""Notes & journal routes."""

import os

from flask import Blueprint, request, jsonify, Response
from werkzeug.utils import secure_filename

from config import get_data_dir
from db import get_db, log_activity

notes_bp = Blueprint('notes', __name__)


@notes_bp.route('/api/notes')
def api_notes_list():
    db = get_db()
    try:
        notes = db.execute('SELECT * FROM notes ORDER BY pinned DESC, updated_at DESC LIMIT 1000').fetchall()
    finally:
        db.close()
    return jsonify([dict(n) for n in notes])


@notes_bp.route('/api/notes', methods=['POST'])
def api_notes_create():
    data = request.get_json() or {}
    db = get_db()
    try:
        cur = db.execute('INSERT INTO notes (title, content) VALUES (?, ?)',
                         (data.get('title', 'Untitled'), data.get('content', '')))
        db.commit()
        note_id = cur.lastrowid
        note = db.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
        return jsonify(dict(note)), 201
    finally:
        db.close()


@notes_bp.route('/api/notes/<int:note_id>', methods=['PUT'])
def api_notes_update(note_id):
    data = request.get_json() or {}
    db = get_db()
    try:
        current = db.execute('SELECT title, content FROM notes WHERE id = ?', (note_id,)).fetchone()
        if not current:
            return jsonify({'error': 'Not found'}), 404
        title = data.get('title') if data.get('title') is not None else current['title']
        content = data.get('content') if data.get('content') is not None else current['content']
        db.execute('UPDATE notes SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                   (title, content, note_id))
        db.commit()
        note = db.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
        return jsonify(dict(note))
    finally:
        db.close()


@notes_bp.route('/api/notes/<int:note_id>', methods=['DELETE'])
def api_notes_delete(note_id):
    db = get_db()
    try:
        db.execute('DELETE FROM note_tags WHERE note_id = ?', (note_id,))
        db.execute('DELETE FROM note_links WHERE source_note_id = ? OR target_note_id = ?', (note_id, note_id))
        db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        db.commit()
        return jsonify({'status': 'deleted'})
    finally:
        db.close()


# --- Notes Pin/Tag ---

@notes_bp.route('/api/notes/<int:note_id>/pin', methods=['POST'])
def api_notes_pin(note_id):
    data = request.get_json() or {}
    pinned = 1 if data.get('pinned', True) else 0
    db = get_db()
    db.execute('UPDATE notes SET pinned = ? WHERE id = ?', (pinned, note_id))
    db.commit()
    db.close()
    return jsonify({'status': 'ok', 'pinned': pinned})


@notes_bp.route('/api/notes/<int:note_id>/tags', methods=['PUT'])
def api_notes_tags(note_id):
    data = request.get_json() or {}
    tags = data.get('tags', '')
    db = get_db()
    db.execute('UPDATE notes SET tags = ? WHERE id = ?', (tags, note_id))
    db.commit()
    db.close()
    return jsonify({'status': 'ok'})


@notes_bp.route('/api/notes/<int:note_id>/export')
def api_notes_export(note_id):
    """Export a single note as a Markdown file."""
    db = get_db()
    note = db.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
    db.close()
    if not note:
        return jsonify({'error': 'Not found'}), 404
    title = note['title'] or 'Untitled'
    content = note['content'] or ''
    md = f"# {title}\n\n{content}"
    safe_title = secure_filename(title) or 'note'
    return Response(md, mimetype='text/markdown',
                   headers={'Content-Disposition': f'attachment; filename="{safe_title}.md"'})


@notes_bp.route('/api/notes/export-all')
def api_notes_export_all():
    """Export all notes as a ZIP of Markdown files."""
    try:
        import io
        import zipfile as zf
        db = get_db()
        notes = db.execute('SELECT * FROM notes ORDER BY updated_at DESC').fetchall()
        db.close()
        buf = io.BytesIO()
        with zf.ZipFile(buf, 'w', zf.ZIP_DEFLATED) as z:
            for n in notes:
                title = n['title'] or 'Untitled'
                content = n['content'] or ''
                safe = secure_filename(title) or f'note-{n["id"]}'
                md = f"# {title}\n\n{content}"
                z.writestr(f'{safe}.md', md)
        buf.seek(0)
        return Response(buf.read(), mimetype='application/zip',
                       headers={'Content-Disposition': 'attachment; filename="nomad-notes.zip"'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Notes Enhancements (v5.0 Phase 5) ---

@notes_bp.route('/api/notes/tags')
def api_note_tags():
    """List all unique tags with counts."""
    db = get_db()
    try:
        rows = db.execute(
            'SELECT tag, COUNT(*) as count FROM note_tags GROUP BY tag ORDER BY count DESC, tag'
        ).fetchall()
        return jsonify([{'tag': r['tag'], 'count': r['count']} for r in rows])
    finally:
        db.close()


@notes_bp.route('/api/notes/<int:note_id>/tags', methods=['POST'])
def api_note_add_tag(note_id):
    """Add a tag to a note."""
    d = request.json or {}
    tag = d.get('tag', '').strip().lower()
    if not tag:
        return jsonify({'error': 'tag required'}), 400
    db = get_db()
    try:
        db.execute('INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)', (note_id, tag))
        db.commit()
        return jsonify({'status': 'ok'})
    finally:
        db.close()


@notes_bp.route('/api/notes/<int:note_id>/tags/<tag>', methods=['DELETE'])
def api_note_remove_tag(note_id, tag):
    """Remove a tag from a note."""
    db = get_db()
    try:
        db.execute('DELETE FROM note_tags WHERE note_id = ? AND tag = ?', (note_id, tag))
        db.commit()
        return jsonify({'status': 'ok'})
    finally:
        db.close()


@notes_bp.route('/api/notes/<int:note_id>/backlinks')
def api_note_backlinks(note_id):
    """Get all notes that link to this note."""
    db = get_db()
    try:
        rows = db.execute(
            '''SELECT n.id, n.title, n.updated_at FROM notes n
               JOIN note_links l ON l.source_note_id = n.id
               WHERE l.target_note_id = ? ORDER BY n.updated_at DESC''',
            (note_id,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@notes_bp.route('/api/notes/search-titles')
def api_note_search_titles():
    """Search note titles for wiki-link autocomplete."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    db = get_db()
    try:
        rows = db.execute('SELECT id, title FROM notes WHERE title LIKE ? LIMIT 10', (f'%{q}%',)).fetchall()
        return jsonify([{'id': r['id'], 'title': r['title']} for r in rows])
    finally:
        db.close()


@notes_bp.route('/api/notes/templates')
def api_note_templates():
    """List note templates."""
    db = get_db()
    try:
        rows = db.execute('SELECT * FROM note_templates ORDER BY name').fetchall()
        templates = [dict(r) for r in rows]
        # Add built-in templates if table is empty
        if not templates:
            builtins = [
                {'name': 'Incident Report', 'icon': '\ud83d\udea8', 'content': '# Incident Report\n\n**Date:** \n**Location:** \n**Severity:** \n\n## Description\n\n\n## Actions Taken\n\n\n## Follow-up Required\n\n'},
                {'name': 'Patrol Log', 'icon': '\ud83d\udd0d', 'content': '# Patrol Log\n\n**Date:** \n**Route:** \n**Personnel:** \n\n## Observations\n\n\n## Contacts Made\n\n\n## Issues Found\n\n'},
                {'name': 'Comms Log', 'icon': '\ud83d\udce1', 'content': '# Communications Log\n\n**Date:** \n**Operator:** \n**Freq:** \n\n| Time | Callsign | Direction | Message | Signal |\n|------|----------|-----------|---------|--------|\n| | | | | |\n'},
                {'name': 'SITREP', 'icon': '\ud83d\udccb', 'content': '# SITREP\n\n**DTG:** \n**From:** \n**To:** \n\n## 1. SITUATION\n\n## 2. ACTIONS\n\n## 3. REQUIREMENTS\n\n## 4. LOGISTICS\n\n## 5. PERSONNEL\n\n'},
                {'name': 'Meeting Notes', 'icon': '\ud83e\udd1d', 'content': '# Meeting Notes\n\n**Date:** \n**Attendees:** \n\n## Agenda\n\n\n## Discussion\n\n\n## Action Items\n- [ ] \n'},
                {'name': 'Daily Journal', 'icon': '\ud83d\udcd3', 'content': '# Journal Entry\n\n**Weather:** \n**Mood:** \n\n## Today\n\n\n## Accomplishments\n\n\n## Tomorrow\n\n'},
            ]
            for t in builtins:
                db.execute('INSERT INTO note_templates (name, content, icon) VALUES (?, ?, ?)',
                           (t['name'], t['content'], t['icon']))
            db.commit()
            templates = builtins
        return jsonify(templates)
    finally:
        db.close()


@notes_bp.route('/api/notes/journal', methods=['POST'])
def api_note_create_journal():
    """Create a daily journal entry for today."""
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    title = f'Journal \u2014 {today}'
    db = get_db()
    try:
        # Check if today's journal already exists
        existing = db.execute("SELECT id FROM notes WHERE title = ? AND is_journal = 1", (title,)).fetchone()
        if existing:
            return jsonify({'id': existing['id'], 'existed': True})
        content = f'# {title}\n\n**Weather:** \n**Mood:** \n\n## Notes\n\n'
        db.execute('INSERT INTO notes (title, content, is_journal, tags) VALUES (?, ?, 1, ?)', (title, content, 'journal'))
        db.commit()
        note_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.execute('INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)', (note_id, 'journal'))
        db.commit()
        return jsonify({'id': note_id, 'existed': False})
    finally:
        db.close()


# --- Journal (standalone) ---

@notes_bp.route('/api/journal')
def api_journal_list():
    db = get_db()
    rows = db.execute('SELECT * FROM journal ORDER BY created_at DESC LIMIT 100').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@notes_bp.route('/api/journal', methods=['POST'])
def api_journal_create():
    data = request.get_json() or {}
    entry = data.get('entry', '').strip()
    if not entry:
        return jsonify({'error': 'Entry required'}), 400
    db = get_db()
    db.execute('INSERT INTO journal (entry, mood, tags) VALUES (?,?,?)',
               (entry, data.get('mood', ''), data.get('tags', '')))
    db.commit()
    db.close()
    log_activity('journal_entry', detail=entry[:50])
    return jsonify({'status': 'logged'}), 201


@notes_bp.route('/api/journal/<int:jid>', methods=['DELETE'])
def api_journal_delete(jid):
    db = get_db()
    db.execute('DELETE FROM journal WHERE id = ?', (jid,))
    db.commit()
    db.close()
    return jsonify({'status': 'deleted'})


@notes_bp.route('/api/journal/export')
def api_journal_export():
    """Export journal as a text file."""
    db = get_db()
    entries = [dict(r) for r in db.execute('SELECT * FROM journal ORDER BY created_at ASC').fetchall()]
    db.close()
    md = '# N.O.M.A.D. Daily Journal\n\n'
    for e in entries:
        md += f'## {e["created_at"]}\n'
        if e.get('mood'):
            md += f'Mood: {e["mood"]}\n'
        if e.get('tags'):
            md += f'Tags: {e["tags"]}\n'
        md += f'\n{e["entry"]}\n\n---\n\n'
    return Response(md, mimetype='text/markdown',
                   headers={'Content-Disposition': 'attachment; filename="nomad-journal.md"'})


# --- Notes Attachments (v5.0 Phase 5) ---

@notes_bp.route('/api/notes/<int:note_id>/attachments', methods=['GET'])
def api_note_attachments(note_id):
    """List attachments for a note."""
    att_dir = os.path.join(get_data_dir(), 'attachments', 'notes', str(note_id))
    if not os.path.isdir(att_dir):
        return jsonify([])
    files = []
    for f in os.listdir(att_dir):
        fp = os.path.join(att_dir, f)
        files.append({'filename': f, 'size': os.path.getsize(fp), 'path': f'/api/notes/{note_id}/attachments/{f}'})
    return jsonify(files)


@notes_bp.route('/api/notes/<int:note_id>/attachments/<filename>')
def api_note_attachment_serve(note_id, filename):
    """Serve a note attachment file."""
    safe = secure_filename(filename)
    att_dir = os.path.join(get_data_dir(), 'attachments', 'notes', str(note_id))
    full = os.path.join(att_dir, safe)
    if not os.path.normpath(full).startswith(os.path.normpath(att_dir)):
        return jsonify({'error': 'Invalid path'}), 400
    if not os.path.isfile(full):
        return jsonify({'error': 'Not found'}), 404
    from flask import send_file
    return send_file(full)


@notes_bp.route('/api/notes/<int:note_id>/attachments', methods=['POST'])
def api_note_attachment_upload(note_id):
    """Upload an attachment for a note."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'Empty filename'}), 400
    att_dir = os.path.join(get_data_dir(), 'attachments', 'notes', str(note_id))
    os.makedirs(att_dir, exist_ok=True)
    safe = secure_filename(f.filename)
    f.save(os.path.join(att_dir, safe))
    return jsonify({'status': 'ok', 'filename': safe, 'path': f'/api/notes/{note_id}/attachments/{safe}'})
