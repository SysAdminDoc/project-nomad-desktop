"""Tests for timers API routes."""


class TestTimersList:
    def test_list_timers(self, client):
        resp = client.get('/api/timers')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestTimersCreate:
    def test_create_timer(self, client):
        resp = client.post('/api/timers', json={
            'name': 'Cooking Timer',
            'duration_sec': 600,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Cooking Timer'
        assert data['duration_sec'] == 600
        assert data['id'] is not None

    def test_create_timer_defaults(self, client):
        resp = client.post('/api/timers', json={})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Timer'
        assert data['duration_sec'] == 300

    def test_create_invalid_duration(self, client):
        resp = client.post('/api/timers', json={
            'name': 'Bad Timer',
            'duration_sec': 'not-a-number',
        })
        assert resp.status_code == 400

    def test_timer_remaining_computed(self, client):
        client.post('/api/timers', json={
            'name': 'Running Timer',
            'duration_sec': 3600,
        })
        timers = client.get('/api/timers').get_json()
        running = next((t for t in timers if t['name'] == 'Running Timer'), None)
        assert running is not None
        assert 'remaining_sec' in running
        assert 'done' in running
        assert running['remaining_sec'] > 0
        assert running['done'] is False


class TestTimersDelete:
    def test_delete_timer(self, client):
        create = client.post('/api/timers', json={'name': 'Delete Me', 'duration_sec': 60})
        tid = create.get_json()['id']
        resp = client.delete(f'/api/timers/{tid}')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'
