"""Tests for notes API routes."""


class TestNotesList:
    def test_list(self, client):
        resp = client.get('/api/notes')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_list_returns_created_notes(self, client):
        client.post('/api/notes', json={'title': 'First', 'content': 'aaa'})
        client.post('/api/notes', json={'title': 'Second', 'content': 'bbb'})
        resp = client.get('/api/notes')
        data = resp.get_json()
        titles = [n['title'] for n in data]
        assert 'First' in titles
        assert 'Second' in titles


class TestNotesCreate:
    def test_create_note(self, client):
        resp = client.post('/api/notes', json={
            'title': 'Patrol Log',
            'content': '## 0600 — All clear'
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['title'] == 'Patrol Log'
        assert data['content'] == '## 0600 — All clear'
        assert data['id'] is not None

    def test_create_with_defaults(self, client):
        resp = client.post('/api/notes', json={})
        assert resp.status_code == 201
        assert resp.get_json()['title'] == 'Untitled'


class TestNotesUpdate:
    def test_update_content(self, client):
        create = client.post('/api/notes', json={'title': 'Log', 'content': 'v1'})
        nid = create.get_json()['id']
        resp = client.put(f'/api/notes/{nid}', json={'content': 'v2 updated'})
        assert resp.status_code == 200
        assert resp.get_json()['content'] == 'v2 updated'
        assert resp.get_json()['title'] == 'Log'  # unchanged

    def test_update_nonexistent(self, client):
        resp = client.put('/api/notes/99999', json={'title': 'Ghost'})
        assert resp.status_code == 404


class TestNotesDelete:
    def test_delete_note(self, client):
        create = client.post('/api/notes', json={'title': 'DeleteMeNote'})
        nid = create.get_json()['id']
        resp = client.delete(f'/api/notes/{nid}')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'
        # Verify this specific note is gone
        notes = client.get('/api/notes').get_json()
        assert not any(n['id'] == nid for n in notes)


class TestNotesPin:
    def test_pin_note(self, client):
        create = client.post('/api/notes', json={'title': 'Important'})
        nid = create.get_json()['id']
        resp = client.post(f'/api/notes/{nid}/pin', json={'pinned': True})
        assert resp.status_code == 200
        assert resp.get_json()['pinned'] == 1

    def test_pinned_notes_first(self, client):
        n1 = client.post('/api/notes', json={'title': 'Regular Note ZZZ'}).get_json()
        n2 = client.post('/api/notes', json={'title': 'Pinned Note ZZZ'}).get_json()
        client.post(f'/api/notes/{n2["id"]}/pin', json={'pinned': True})
        notes = client.get('/api/notes').get_json()
        titles = [n['title'] for n in notes]
        pinned_idx = titles.index('Pinned Note ZZZ')
        regular_idx = titles.index('Regular Note ZZZ')
        assert pinned_idx < regular_idx


class TestNotesTags:
    def test_set_tags(self, client):
        create = client.post('/api/notes', json={'title': 'Tagged'})
        nid = create.get_json()['id']
        resp = client.put(f'/api/notes/{nid}/tags', json={'tags': 'medical,urgent'})
        assert resp.status_code == 200


class TestNotesJournal:
    def test_create_journal_entry(self, client):
        resp = client.post('/api/notes/journal')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['id'] is not None
        assert data['existed'] is False

    def test_journal_idempotent(self, client):
        first = client.post('/api/notes/journal').get_json()
        second = client.post('/api/notes/journal').get_json()
        assert first['id'] == second['id']
        assert second['existed'] is True


class TestNotesExport:
    def test_export_markdown(self, client):
        create = client.post('/api/notes', json={'title': 'Export Me', 'content': 'Hello world'})
        nid = create.get_json()['id']
        resp = client.get(f'/api/notes/{nid}/export')
        assert resp.status_code == 200
        assert b'Export Me' in resp.data
        assert b'Hello world' in resp.data

    def test_export_nonexistent(self, client):
        resp = client.get('/api/notes/99999/export')
        assert resp.status_code == 404
