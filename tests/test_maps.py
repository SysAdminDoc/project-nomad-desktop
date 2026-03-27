"""Tests for maps/waypoints/routes API routes."""

import json


class TestWaypoints:
    def test_list_waypoints(self, client):
        resp = client.get('/api/waypoints')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_waypoint(self, client):
        resp = client.post('/api/waypoints', json={
            'name': 'Rally Point Alpha',
            'lat': 39.7392,
            'lng': -104.9903,
            'category': 'rally',
            'notes': 'Primary assembly area',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Rally Point Alpha'
        assert data['lat'] == 39.7392
        assert data['id'] is not None

    def test_create_waypoint_minimal(self, client):
        resp = client.post('/api/waypoints', json={
            'name': 'Point B',
            'lat': 40.0,
            'lng': -105.0,
        })
        assert resp.status_code == 201

    def test_delete_waypoint(self, client):
        create = client.post('/api/waypoints', json={
            'name': 'Temp WP',
            'lat': 41.0,
            'lng': -106.0,
        })
        wid = create.get_json()['id']
        resp = client.delete(f'/api/waypoints/{wid}')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'

    def test_waypoint_categories(self, client):
        for cat in ['rally', 'water', 'cache', 'shelter', 'hazard', 'medical']:
            resp = client.post('/api/waypoints', json={
                'name': f'{cat} point',
                'lat': 40.0,
                'lng': -105.0,
                'category': cat,
            })
            assert resp.status_code == 201


class TestMapRoutes:
    def test_list_routes(self, client):
        resp = client.get('/api/maps/routes')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_route(self, client):
        # Create waypoints first
        wp1 = client.post('/api/waypoints', json={'name': 'Start', 'lat': 39.0, 'lng': -104.0}).get_json()
        wp2 = client.post('/api/waypoints', json={'name': 'End', 'lat': 39.1, 'lng': -104.1}).get_json()
        resp = client.post('/api/maps/routes', json={
            'name': 'Patrol Route 1',
            'waypoint_ids': json.dumps([wp1['id'], wp2['id']]),
            'terrain_difficulty': 'easy',
            'notes': 'Flat terrain, good visibility',
        })
        assert resp.status_code in (200, 201)
        assert resp.get_json()['id'] is not None

    def test_delete_route(self, client):
        create = client.post('/api/maps/routes', json={'name': 'Temp Route'})
        rid = create.get_json()['id']
        resp = client.delete(f'/api/maps/routes/{rid}')
        assert resp.status_code == 200


class TestElevationProfile:
    def test_elevation_profile_not_found(self, client):
        resp = client.get('/api/maps/elevation-profile/99999')
        assert resp.status_code == 404

    def test_elevation_profile_empty_route(self, client):
        route = client.post('/api/maps/routes', json={
            'name': 'Empty Route',
            'waypoint_ids': json.dumps([]),
        }).get_json()
        resp = client.get(f'/api/maps/elevation-profile/{route["id"]}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['points'] == []
        assert data['total_ascent'] == 0

    def test_elevation_profile_with_waypoints(self, client):
        wp1 = client.post('/api/waypoints', json={
            'name': 'Valley', 'lat': 39.0, 'lng': -104.0,
        }).get_json()
        wp2 = client.post('/api/waypoints', json={
            'name': 'Peak', 'lat': 39.01, 'lng': -104.01,
        }).get_json()
        route = client.post('/api/maps/routes', json={
            'name': 'Elevation Test',
            'waypoint_ids': json.dumps([wp1['id'], wp2['id']]),
        }).get_json()
        resp = client.get(f'/api/maps/elevation-profile/{route["id"]}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'points' in data
        assert 'total_ascent' in data
        assert 'total_descent' in data
        assert 'total_distance_m' in data
