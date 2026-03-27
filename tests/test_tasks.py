"""Tests for scheduled tasks API routes."""


class TestTasksList:
    def test_list_tasks(self, client):
        resp = client.get('/api/tasks')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_filter_by_category(self, client):
        client.post('/api/tasks', json={'name': 'Check water', 'category': 'maintenance'})
        client.post('/api/tasks', json={'name': 'Radio check', 'category': 'comms'})
        resp = client.get('/api/tasks?category=maintenance')
        data = resp.get_json()
        assert any(t['name'] == 'Check water' for t in data)

    def test_filter_by_assigned(self, client):
        client.post('/api/tasks', json={'name': 'Patrol', 'assigned_to': 'John'})
        resp = client.get('/api/tasks?assigned_to=John')
        data = resp.get_json()
        assert any(t['assigned_to'] == 'John' for t in data)


class TestTasksCreate:
    def test_create_task(self, client):
        resp = client.post('/api/tasks', json={
            'name': 'Rotate food supplies',
            'category': 'maintenance',
            'recurrence': 'monthly',
            'assigned_to': 'Alice',
            'notes': 'Check expiration dates',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Rotate food supplies'
        assert data['recurrence'] == 'monthly'

    def test_create_requires_name(self, client):
        resp = client.post('/api/tasks', json={'category': 'maintenance'})
        assert resp.status_code == 400

    def test_create_defaults(self, client):
        resp = client.post('/api/tasks', json={'name': 'Simple task'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['category'] == 'custom'
        assert data['recurrence'] == 'once'


class TestTasksUpdate:
    def test_update_task(self, client):
        create = client.post('/api/tasks', json={'name': 'Old name'})
        tid = create.get_json()['id']
        resp = client.put(f'/api/tasks/{tid}', json={
            'name': 'New name',
            'notes': 'Updated notes',
        })
        assert resp.status_code == 200
        assert resp.get_json()['name'] == 'New name'

    def test_update_no_fields_rejected(self, client):
        create = client.post('/api/tasks', json={'name': 'Test'})
        tid = create.get_json()['id']
        resp = client.put(f'/api/tasks/{tid}', json={})
        assert resp.status_code == 400


class TestTasksDelete:
    def test_delete_task(self, client):
        create = client.post('/api/tasks', json={'name': 'Delete me'})
        tid = create.get_json()['id']
        resp = client.delete(f'/api/tasks/{tid}')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'


class TestTasksComplete:
    def test_complete_once_task(self, client):
        create = client.post('/api/tasks', json={
            'name': 'One-time task',
            'recurrence': 'once',
            'next_due': '2026-03-20',
        })
        tid = create.get_json()['id']
        resp = client.post(f'/api/tasks/{tid}/complete')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['completed_count'] == 1

    def test_complete_recurring_reschedules(self, client):
        create = client.post('/api/tasks', json={
            'name': 'Daily patrol',
            'recurrence': 'daily',
            'next_due': '2026-03-20',
        })
        tid = create.get_json()['id']
        resp = client.post(f'/api/tasks/{tid}/complete')
        data = resp.get_json()
        assert data['completed_count'] == 1
        assert data['next_due'] is not None

    def test_complete_nonexistent_returns_404(self, client):
        resp = client.post('/api/tasks/99999/complete')
        assert resp.status_code == 404


class TestTasksDue:
    def test_due_tasks(self, client):
        resp = client.get('/api/tasks/due')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)
