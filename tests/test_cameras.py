"""Tests for security cameras API routes."""


class TestCamerasList:
    def test_list_cameras(self, client):
        resp = client.get('/api/security/cameras')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestCamerasCreate:
    def test_create_camera(self, client):
        resp = client.post('/api/security/cameras', json={
            'name': 'Front Gate Camera',
            'url': 'http://192.168.1.100/stream',
            'stream_type': 'mjpeg',
            'location': 'Front gate',
            'zone': 'perimeter',
        })
        assert resp.status_code == 201
        assert resp.get_json()['status'] == 'created'

    def test_create_requires_name_and_url(self, client):
        resp = client.post('/api/security/cameras', json={'name': 'No URL'})
        assert resp.status_code == 400
        resp = client.post('/api/security/cameras', json={'url': 'http://x'})
        assert resp.status_code == 400


class TestCamerasDelete:
    def test_delete_camera(self, client):
        client.post('/api/security/cameras', json={
            'name': 'Temp Camera',
            'url': 'http://x',
        })
        cameras = client.get('/api/security/cameras').get_json()
        temp = next((c for c in cameras if c['name'] == 'Temp Camera'), None)
        assert temp is not None
        resp = client.delete(f'/api/security/cameras/{temp["id"]}')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'
