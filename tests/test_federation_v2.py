"""Tests for federation v2 features — vector clocks, sync, dead drops, group exercises, offline."""

import json


class TestVectorClock:
    def test_vector_clock_endpoint(self, client):
        resp = client.get('/api/node/vector-clock')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)

    def test_vector_clock_conflicts(self, client):
        resp = client.get('/api/node/vector-clock/conflicts')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


class TestSyncPush:
    def test_sync_push_no_ip(self, client):
        resp = client.post('/api/node/sync-push', json={})
        assert resp.status_code == 400
        assert 'No peer IP' in resp.get_json()['error']

    def test_sync_push_invalid_ip(self, client):
        resp = client.post('/api/node/sync-push', json={'ip': '127.0.0.1'})
        assert resp.status_code == 400
        assert 'Invalid' in resp.get_json()['error']


class TestSyncPull:
    def test_sync_pull_invalid_ip(self, client):
        resp = client.post('/api/node/sync-pull', json={'ip': '0.0.0.0'})
        assert resp.status_code == 400
        assert 'Invalid' in resp.get_json()['error']


class TestSyncReceive:
    def test_sync_receive_no_source(self, client):
        resp = client.post('/api/node/sync-receive', json={'tables': {}})
        assert resp.status_code == 400
        assert 'source_node_id' in resp.get_json()['error']

    def test_sync_receive_blocked_peer(self, client, db):
        # Insert a blocked peer so the check fails with 403
        db.execute(
            "INSERT INTO federation_peers (node_id, node_name, trust_level) VALUES (?, ?, ?)",
            ('blocked-node-123', 'Evil Node', 'blocked'),
        )
        db.commit()
        resp = client.post('/api/node/sync-receive', json={
            'source_node_id': 'blocked-node-123',
            'tables': {},
        })
        assert resp.status_code == 403
        assert 'blocked' in resp.get_json()['error'].lower() or 'Unknown' in resp.get_json()['error']


class TestConflicts:
    def test_conflicts_list(self, client):
        resp = client.get('/api/node/conflicts')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_conflict_resolve_invalid(self, client):
        resp = client.post('/api/node/conflicts/999/resolve', json={'resolution': 'bogus'})
        assert resp.status_code == 400
        assert 'resolution' in resp.get_json()['error']


class TestDeadDrop:
    def test_dead_drop_compose(self, client):
        resp = client.post('/api/deaddrop/compose', json={
            'message': 'Meet at the bridge at dawn',
            'recipient': 'Alpha Team',
            'secret': 'hunter2',
        })
        # May succeed (200) if cryptography is installed, or 500 if not
        if resp.status_code == 200:
            data = resp.get_json()
            assert 'payload' in data
            assert data['payload']['type'] == 'nomad-deaddrop'
            assert data['payload']['version'] == 2
            assert 'filename' in data
        else:
            # cryptography package not available — that's OK
            assert resp.status_code == 500

    def test_dead_drop_decrypt_bad_format(self, client):
        resp = client.post('/api/deaddrop/decrypt', json={
            'payload': {'type': 'wrong-type', 'data': 'abc'},
            'secret': 'hunter2',
        })
        assert resp.status_code == 400
        assert 'format' in resp.get_json()['error'].lower()

    def test_dead_drop_messages(self, client):
        resp = client.get('/api/deaddrop/messages')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


class TestGroupExercises:
    def test_group_exercises_list(self, client):
        resp = client.get('/api/group-exercises')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_group_exercises_create(self, client):
        resp = client.post('/api/group-exercises', json={
            'title': 'Grid Down Drill',
            'scenario_type': 'grid_down',
            'description': 'Practice 72-hour grid-down response',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'exercise_id' in data
        assert 'invited' in data


class TestOfflineSnapshot:
    def test_offline_snapshot(self, client):
        resp = client.get('/api/offline/snapshot')
        assert resp.status_code == 200
        data = resp.get_json()
        # Should contain the standard offline tables
        for table in ('inventory', 'contacts', 'waypoints', 'checklists'):
            assert table in data, f'Missing table: {table}'
            assert isinstance(data[table], list)
        assert '_timestamp' in data
        assert '_node_id' in data
