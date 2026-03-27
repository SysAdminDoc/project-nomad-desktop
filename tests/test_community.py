"""Tests for community resources API routes."""


class TestCommunityList:
    def test_list_community(self, client):
        resp = client.get('/api/community')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestCommunityCreate:
    def test_create_community_resource(self, client):
        resp = client.post('/api/community', json={
            'name': 'Neighbor Ranch',
            'distance_mi': 2.5,
            'skills': ['welding', 'livestock'],
            'equipment': ['tractor'],
            'contact': '555-1234',
            'trust_level': 'trusted',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Neighbor Ranch'
        assert data['id'] is not None

    def test_create_requires_name(self, client):
        resp = client.post('/api/community', json={'distance_mi': 1.0})
        assert resp.status_code == 400

    def test_create_empty_name_rejected(self, client):
        resp = client.post('/api/community', json={'name': ''})
        assert resp.status_code == 400

    def test_create_bad_distance_handled(self, client):
        resp = client.post('/api/community', json={
            'name': 'Bad Distance Place',
            'distance_mi': 'not-a-number',
        })
        assert resp.status_code == 201
        # Should default to 0.0 instead of crashing


class TestCommunityUpdate:
    def test_update_community(self, client):
        create = client.post('/api/community', json={
            'name': 'Update Test',
            'trust_level': 'unknown',
        })
        cid = create.get_json()['id']
        resp = client.put(f'/api/community/{cid}', json={
            'name': 'Updated Name',
            'trust_level': 'trusted',
            'distance_mi': 'bad-value',  # should not crash
        })
        assert resp.status_code == 200


class TestCommunityDelete:
    def test_delete_community(self, client):
        create = client.post('/api/community', json={'name': 'Delete Me'})
        cid = create.get_json()['id']
        resp = client.delete(f'/api/community/{cid}')
        assert resp.status_code == 200
