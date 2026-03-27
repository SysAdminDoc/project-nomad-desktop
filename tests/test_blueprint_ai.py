"""Tests for AI-related routes: memory, training datasets, training jobs."""

import json


class TestAIMemory:
    def test_list_memory_empty(self, client):
        resp = client.get('/api/ai/memory')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'memories' in data

    def test_save_memory(self, client):
        resp = client.post('/api/ai/memory', json={
            'fact': 'The water filter needs replacing every 3 months'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'saved'

    def test_save_and_list_memory(self, client):
        client.post('/api/ai/memory', json={
            'fact': 'Solar panels produce 200W peak'
        })
        resp = client.get('/api/ai/memory')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['memories']) >= 1

    def test_clear_memory(self, client):
        client.post('/api/ai/memory', json={'fact': 'temp fact'})
        resp = client.delete('/api/ai/memory')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'cleared'

    def test_save_memory_no_fact_returns_400(self, client):
        resp = client.post('/api/ai/memory', json={})
        assert resp.status_code == 400

    def test_save_empty_fact_returns_400(self, client):
        resp = client.post('/api/ai/memory', json={'fact': ''})
        assert resp.status_code == 400


class TestAITrainingDatasets:
    def test_list_datasets(self, client):
        resp = client.get('/api/ai/training/datasets')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, (list, dict))

    def test_create_dataset(self, client):
        resp = client.post('/api/ai/training/datasets', json={
            'name': 'Test Dataset',
            'source': 'upload',
        })
        assert resp.status_code in (200, 201)

    def test_list_training_jobs(self, client):
        resp = client.get('/api/ai/training/jobs')
        assert resp.status_code == 200
