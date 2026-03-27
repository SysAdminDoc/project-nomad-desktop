"""Tests for encrypted vault API routes."""


class TestVaultList:
    def test_list_vault(self, client):
        resp = client.get('/api/vault')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_list_does_not_expose_encrypted_data(self, client):
        client.post('/api/vault', json={
            'title': 'Secret',
            'encrypted_data': 'abc123encrypted',
            'iv': 'iv123',
            'salt': 'salt456',
        })
        items = client.get('/api/vault').get_json()
        secret = next((v for v in items if v['title'] == 'Secret'), None)
        assert secret is not None
        assert 'encrypted_data' not in secret


class TestVaultCreate:
    def test_create_vault_entry(self, client):
        resp = client.post('/api/vault', json={
            'title': 'WiFi Passwords',
            'encrypted_data': 'enc_data_here',
            'iv': 'init_vector_here',
            'salt': 'salt_here',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['id'] is not None
        assert data['status'] == 'saved'

    def test_create_requires_encrypted_data(self, client):
        resp = client.post('/api/vault', json={
            'title': 'Missing fields',
            'iv': 'iv',
            'salt': 'salt',
        })
        assert resp.status_code == 400

    def test_create_requires_iv(self, client):
        resp = client.post('/api/vault', json={
            'title': 'Missing IV',
            'encrypted_data': 'data',
            'salt': 'salt',
        })
        assert resp.status_code == 400

    def test_create_requires_salt(self, client):
        resp = client.post('/api/vault', json={
            'title': 'Missing salt',
            'encrypted_data': 'data',
            'iv': 'iv',
        })
        assert resp.status_code == 400


class TestVaultGet:
    def test_get_vault_entry(self, client):
        create = client.post('/api/vault', json={
            'title': 'Get Test',
            'encrypted_data': 'enc_data',
            'iv': 'iv_val',
            'salt': 'salt_val',
        })
        eid = create.get_json()['id']
        resp = client.get(f'/api/vault/{eid}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['encrypted_data'] == 'enc_data'
        assert data['iv'] == 'iv_val'
        assert data['salt'] == 'salt_val'

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get('/api/vault/99999')
        assert resp.status_code == 404


class TestVaultUpdate:
    def test_update_vault_entry(self, client):
        create = client.post('/api/vault', json={
            'title': 'Old',
            'encrypted_data': 'old_data',
            'iv': 'old_iv',
            'salt': 'old_salt',
        })
        eid = create.get_json()['id']
        resp = client.put(f'/api/vault/{eid}', json={
            'title': 'Updated',
            'encrypted_data': 'new_data',
            'iv': 'new_iv',
            'salt': 'new_salt',
        })
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'saved'
        # Verify
        get = client.get(f'/api/vault/{eid}').get_json()
        assert get['encrypted_data'] == 'new_data'


class TestVaultDelete:
    def test_delete_vault_entry(self, client):
        create = client.post('/api/vault', json={
            'title': 'Delete me',
            'encrypted_data': 'x',
            'iv': 'y',
            'salt': 'z',
        })
        eid = create.get_json()['id']
        resp = client.delete(f'/api/vault/{eid}')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'
