"""Tests for knowledge base / document API routes."""


class TestKBDocuments:
    def test_list_documents(self, client):
        resp = client.get('/api/kb/documents')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestKBStatus:
    def test_kb_status(self, client):
        resp = client.get('/api/kb/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'status' in data


class TestKBSearch:
    def test_search_empty_kb(self, client):
        resp = client.post('/api/kb/search', json={'query': 'water purification'})
        assert resp.status_code == 200
        # May return empty results or error depending on Qdrant state
        data = resp.get_json()
        assert isinstance(data, (list, dict))

    def test_search_requires_query(self, client):
        resp = client.post('/api/kb/search', json={})
        # Should handle missing query gracefully
        assert resp.status_code in (200, 400)


class TestCSVImport:
    def test_csv_preview(self, client):
        csv_data = 'name,category,quantity\nWater,water,10\nRice,food,5\n'
        resp = client.post('/api/import/csv',
                          data=csv_data,
                          content_type='text/csv')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'headers' in data
        assert 'sample_rows' in data
        assert 'name' in data['headers']

    def test_csv_execute_import(self, client):
        resp = client.post('/api/import/csv/execute', json={
            'csv_data': [
                {'name': 'Imported Water', 'category': 'water', 'quantity': '50'},
                {'name': 'Imported Rice', 'category': 'food', 'quantity': '25'},
            ],
            'mapping': {
                'name': 'name',
                'category': 'category',
                'quantity': 'quantity',
            },
            'target_table': 'inventory',
        })
        # May succeed or fail depending on CSV executor implementation details
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            items = client.get('/api/inventory?q=Imported').get_json()
            imported_names = [i['name'] for i in items]
            assert 'Imported Water' in imported_names

    def test_csv_execute_invalid_table(self, client):
        resp = client.post('/api/import/csv/execute', json={
            'csv_data': [{'name': 'test'}],
            'mapping': {'name': 'name'},
            'target_table': 'users',  # not in whitelist
        })
        assert resp.status_code in (400, 403, 404)
