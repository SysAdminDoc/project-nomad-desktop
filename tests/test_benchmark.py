"""Tests for benchmark API routes."""


class TestBenchmarkStatus:
    def test_benchmark_status(self, client):
        resp = client.get('/api/benchmark/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'status' in data


class TestBenchmarkHistory:
    def test_benchmark_history(self, client):
        resp = client.get('/api/benchmark/history')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestBenchmarkResults:
    def test_results_empty(self, client):
        resp = client.get('/api/benchmark/results')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_results_with_type_filter(self, client):
        resp = client.get('/api/benchmark/results?type=storage')
        assert resp.status_code == 200

    def test_results_with_limit(self, client):
        resp = client.get('/api/benchmark/results?limit=5')
        assert resp.status_code == 200


class TestStorageBenchmark:
    def test_storage_benchmark(self, client):
        resp = client.post('/api/benchmark/storage')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'read_mbps' in data
        assert 'write_mbps' in data
        assert data['read_mbps'] > 0
