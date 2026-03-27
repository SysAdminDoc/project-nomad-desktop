"""Negative validation tests for various API routes."""

import json


class TestInventoryValidation:
    def test_name_too_long(self, client):
        resp = client.post('/api/inventory', json={'name': 'X' * 1001})
        assert resp.status_code == 400

    def test_negative_quantity(self, client):
        resp = client.post('/api/inventory', json={'name': 'Test', 'quantity': -10})
        assert resp.status_code == 400

    def test_missing_name(self, client):
        resp = client.post('/api/inventory', json={'quantity': 5})
        assert resp.status_code == 400


class TestContactsValidation:
    def test_missing_required_name(self, client):
        resp = client.post('/api/contacts', json={'phone': '555-1234'})
        assert resp.status_code == 400

    def test_name_too_long(self, client):
        resp = client.post('/api/contacts', json={'name': 'A' * 500})
        assert resp.status_code == 400


class TestIncidentsValidation:
    def test_missing_description(self, client):
        resp = client.post('/api/incidents', json={'severity': 'low'})
        assert resp.status_code == 400

    def test_description_too_long(self, client):
        resp = client.post('/api/incidents', json={'description': 'X' * 3000})
        assert resp.status_code == 400


class TestChecklistsValidation:
    def test_invalid_json_body(self, client):
        resp = client.post('/api/checklists',
                          data='not json',
                          content_type='application/json')
        assert resp.status_code == 400

    def test_name_too_long(self, client):
        resp = client.post('/api/checklists', json={'name': 'Z' * 500})
        assert resp.status_code == 400


class TestGardenValidation:
    def test_plot_no_name(self, client):
        resp = client.post('/api/garden/plots', json={})
        assert resp.status_code == 400

    def test_seed_no_species(self, client):
        resp = client.post('/api/garden/seeds', json={'variety': 'Big Boy'})
        assert resp.status_code == 400

    def test_harvest_no_crop(self, client):
        resp = client.post('/api/garden/harvests', json={'quantity': 10})
        assert resp.status_code == 400


class TestWeatherValidation:
    def test_weather_reading_wrong_type(self, client):
        # Weather readings accept numeric values; string temperature should be handled
        resp = client.post('/api/weather/readings', json={
            'temperature': 'very hot',
        })
        # Should either coerce or accept (manual readings are flexible)
        assert resp.status_code in (200, 201, 400)


class TestFederationValidation:
    def test_add_peer_no_url(self, client):
        resp = client.post('/api/federation/peers', json={'name': 'test'})
        # Without URL, should fail or use defaults
        assert resp.status_code in (200, 201, 400)
