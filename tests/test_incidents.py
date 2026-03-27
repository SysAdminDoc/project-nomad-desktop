"""Tests for incidents API routes."""


class TestIncidentsList:
    def test_list_incidents(self, client):
        resp = client.get('/api/incidents')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_list_with_limit(self, client):
        for i in range(5):
            client.post('/api/incidents', json={'description': f'Incident {i}', 'severity': 'info'})
        resp = client.get('/api/incidents?limit=3')
        assert resp.status_code == 200
        assert len(resp.get_json()) <= 3

    def test_list_filter_by_category(self, client):
        client.post('/api/incidents', json={'description': 'Fire spotted', 'category': 'fire'})
        client.post('/api/incidents', json={'description': 'Medical emergency', 'category': 'medical'})
        resp = client.get('/api/incidents?category=fire')
        data = resp.get_json()
        assert all(i['category'] == 'fire' for i in data)


class TestIncidentsCreate:
    def test_create_incident(self, client):
        resp = client.post('/api/incidents', json={
            'description': 'Perimeter breach at north fence',
            'severity': 'high',
            'category': 'security',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['description'] == 'Perimeter breach at north fence'
        assert data['severity'] == 'high'
        assert data['id'] is not None

    def test_create_requires_description(self, client):
        resp = client.post('/api/incidents', json={'severity': 'low'})
        assert resp.status_code == 400

    def test_create_empty_description_rejected(self, client):
        resp = client.post('/api/incidents', json={'description': '   '})
        assert resp.status_code == 400

    def test_create_defaults(self, client):
        resp = client.post('/api/incidents', json={'description': 'Minor event'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['severity'] == 'info'
        assert data['category'] == 'other'


class TestIncidentsDelete:
    def test_delete_incident(self, client):
        create = client.post('/api/incidents', json={'description': 'Temp incident'})
        iid = create.get_json()['id']
        resp = client.delete(f'/api/incidents/{iid}')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'


class TestIncidentsClear:
    def test_clear_all(self, client):
        client.post('/api/incidents', json={'description': 'Incident 1'})
        client.post('/api/incidents', json={'description': 'Incident 2'})
        resp = client.post('/api/incidents/clear')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'cleared'
        remaining = client.get('/api/incidents').get_json()
        assert len(remaining) == 0
