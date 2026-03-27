"""Tests for KB (knowledge base) documents and media-related routes."""


class TestKBDocuments:
    def test_list_documents(self, client):
        resp = client.get('/api/kb/documents')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_kb_status(self, client):
        resp = client.get('/api/kb/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)


class TestKBWorkspaces:
    def test_list_workspaces(self, client):
        resp = client.get('/api/kb/workspaces')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_workspace(self, client):
        resp = client.post('/api/kb/workspaces', json={
            'name': 'Test Workspace',
        })
        assert resp.status_code in (200, 201)

    def test_delete_workspace(self, client):
        create = client.post('/api/kb/workspaces', json={'name': 'Delete WS'})
        data = create.get_json()
        if 'id' in data:
            resp = client.delete(f'/api/kb/workspaces/{data["id"]}')
            assert resp.status_code == 200


class TestOCRPipeline:
    def test_ocr_pipeline_status(self, client):
        resp = client.get('/api/kb/ocr-pipeline/status')
        assert resp.status_code == 200

    def test_ocr_pipeline_stop(self, client):
        resp = client.post('/api/kb/ocr-pipeline/stop')
        assert resp.status_code == 200


class TestKiwixCatalog:
    def test_kiwix_catalog(self, client):
        resp = client.get('/api/kiwix/catalog')
        assert resp.status_code == 200

    def test_kiwix_zims(self, client):
        resp = client.get('/api/kiwix/zims')
        assert resp.status_code == 200

    def test_kiwix_check_updates(self, client):
        resp = client.get('/api/kiwix/check-updates')
        assert resp.status_code == 200

    def test_kiwix_wikipedia_options(self, client):
        resp = client.get('/api/kiwix/wikipedia-options')
        assert resp.status_code == 200
