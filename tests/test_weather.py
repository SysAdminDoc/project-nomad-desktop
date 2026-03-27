"""Tests for weather API routes including Zambretti prediction."""


class TestWeatherLog:
    def test_empty_list(self, client):
        resp = client.get('/api/weather')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create_reading(self, client):
        resp = client.post('/api/weather', json={
            'pressure_hpa': 1013.25,
            'temp_f': 72,
            'wind_dir': 'NW',
            'wind_speed': '10',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['pressure_hpa'] == 1013.25
        assert data['temp_f'] == 72

    def test_list_with_limit(self, client):
        for i in range(5):
            client.post('/api/weather', json={'pressure_hpa': 1010 + i, 'temp_f': 70})
        resp = client.get('/api/weather?limit=3')
        assert len(resp.get_json()) == 3


class TestWeatherReadings:
    def test_add_reading(self, client):
        resp = client.post('/api/weather/readings', json={
            'source': 'manual',
            'pressure_hpa': 1015.0,
            'temp_f': 68,
            'humidity': 55,
        })
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'ok'

    def test_get_readings(self, client):
        client.post('/api/weather/readings', json={'pressure_hpa': 1013, 'temp_f': 70})
        resp = client.get('/api/weather/readings?hours=24')
        assert resp.status_code == 200


class TestWeatherTrend:
    def test_trend_returns_valid_response(self, client):
        resp = client.get('/api/weather/trend')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'trend' in data

    def test_trend_with_data(self, client):
        # Add multiple readings to establish trend
        for pressure in [1010, 1012, 1014, 1016, 1018]:
            client.post('/api/weather', json={'pressure_hpa': pressure, 'temp_f': 70})
        resp = client.get('/api/weather/trend')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'trend' in data


class TestZambrettiPredict:
    def test_predict_insufficient_data(self, client):
        resp = client.get('/api/weather/predict')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'forecast' in data or 'trend' in data

    def test_predict_with_rising_pressure(self, client):
        # Seed weather_readings with rising pressure pattern
        for i, pressure in enumerate([1005, 1008, 1010, 1013, 1016, 1018]):
            client.post('/api/weather/readings', json={
                'pressure_hpa': pressure,
                'temp_f': 65,
                'source': 'test',
            })
        resp = client.get('/api/weather/predict')
        assert resp.status_code == 200
        data = resp.get_json()
        # Rising pressure should predict fair/improving weather
        assert 'forecast' in data

    def test_predict_with_falling_pressure(self, client):
        for pressure in [1025, 1022, 1018, 1014, 1010, 1005]:
            client.post('/api/weather/readings', json={
                'pressure_hpa': pressure,
                'temp_f': 60,
                'source': 'test',
            })
        resp = client.get('/api/weather/predict')
        data = resp.get_json()
        assert 'forecast' in data
