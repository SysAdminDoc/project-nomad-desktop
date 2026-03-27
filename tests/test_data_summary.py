"""Tests for data summary and global search API routes."""


class TestDataSummary:
    def test_data_summary(self, client):
        resp = client.get('/api/data-summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'tables' in data
        assert 'total_records' in data
        assert isinstance(data['tables'], list)
        assert isinstance(data['total_records'], int)

    def test_data_summary_table_fields(self, client):
        # Seed some data
        client.post('/api/inventory', json={'name': 'Test Item'})
        resp = client.get('/api/data-summary')
        data = resp.get_json()
        assert data['total_records'] > 0
        for t in data['tables']:
            assert 'table' in t
            assert 'label' in t
            assert 'count' in t
            assert t['count'] > 0


class TestGlobalSearch:
    def test_search_empty_query(self, client):
        resp = client.get('/api/search/all?q=')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)

    def test_search_finds_inventory(self, client):
        client.post('/api/inventory', json={'name': 'UniqueSearchItem123'})
        resp = client.get('/api/search/all?q=UniqueSearchItem123')
        data = resp.get_json()
        assert 'inventory' in data
        assert len(data['inventory']) >= 1

    def test_search_finds_contacts(self, client):
        client.post('/api/contacts', json={'name': 'UniqueContactXYZ789'})
        resp = client.get('/api/search/all?q=UniqueContactXYZ789')
        data = resp.get_json()
        assert 'contacts' in data
        assert len(data['contacts']) >= 1

    def test_search_finds_notes(self, client):
        client.post('/api/notes', json={'title': 'UniqueNoteABC456', 'body': 'test'})
        resp = client.get('/api/search/all?q=UniqueNoteABC456')
        data = resp.get_json()
        assert 'notes' in data
        assert len(data['notes']) >= 1

    def test_search_response_format(self, client):
        client.post('/api/inventory', json={'name': 'FormatTest'})
        resp = client.get('/api/search/all?q=FormatTest')
        data = resp.get_json()
        if data.get('inventory'):
            item = data['inventory'][0]
            assert 'id' in item
            assert 'title' in item
            assert 'type' in item

    def test_search_no_results(self, client):
        resp = client.get('/api/search/all?q=zzz_nonexistent_xyz_99999')
        data = resp.get_json()
        # All categories should be empty
        total = sum(len(v) for v in data.values() if isinstance(v, list))
        assert total == 0
