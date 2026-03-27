"""Tests for maps/waypoints/routes blueprint routes."""

import json


class TestWaypointCRUD:
    def test_list_waypoints(self, client):
        resp = client.get('/api/waypoints')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_waypoint(self, client):
        resp = client.post('/api/waypoints', json={
            'name': 'Observation Post',
            'lat': 38.8977,
            'lng': -77.0365,
            'category': 'rally',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['id'] is not None
        assert data['name'] == 'Observation Post'

    def test_create_waypoint_minimal(self, client):
        resp = client.post('/api/waypoints', json={
            'name': 'Minimal WP',
            'lat': 40.0,
            'lng': -105.0,
        })
        assert resp.status_code == 201

    def test_delete_waypoint(self, client):
        create = client.post('/api/waypoints', json={
            'name': 'Temp WP Delete',
            'lat': 39.5,
            'lng': -105.5,
        })
        wid = create.get_json()['id']
        resp = client.delete(f'/api/waypoints/{wid}')
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'

    def test_waypoint_categories(self, client):
        for cat in ['water', 'cache', 'shelter', 'hazard']:
            resp = client.post('/api/waypoints', json={
                'name': f'Cat {cat}',
                'lat': 39.0,
                'lng': -104.0,
                'category': cat,
            })
            assert resp.status_code == 201


class TestMapRoutes:
    def test_list_routes(self, client):
        resp = client.get('/api/maps/routes')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_route(self, client):
        wp1 = client.post('/api/waypoints', json={
            'name': 'Route Start', 'lat': 39.0, 'lng': -104.0
        }).get_json()
        wp2 = client.post('/api/waypoints', json={
            'name': 'Route End', 'lat': 39.1, 'lng': -104.1
        }).get_json()
        resp = client.post('/api/maps/routes', json={
            'name': 'Supply Route',
            'waypoint_ids': json.dumps([wp1['id'], wp2['id']]),
            'terrain_difficulty': 'moderate',
        })
        assert resp.status_code in (200, 201)
        assert resp.get_json()['id'] is not None

    def test_delete_route(self, client):
        create = client.post('/api/maps/routes', json={'name': 'Temp Route'})
        rid = create.get_json()['id']
        resp = client.delete(f'/api/maps/routes/{rid}')
        assert resp.status_code == 200


class TestElevationProfile:
    def test_elevation_profile_empty_route(self, client):
        route = client.post('/api/maps/routes', json={
            'name': 'Empty Elevation',
            'waypoint_ids': json.dumps([]),
        }).get_json()
        resp = client.get(f'/api/maps/elevation-profile/{route["id"]}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['points'] == []

    def test_elevation_profile_not_found(self, client):
        resp = client.get('/api/maps/elevation-profile/99999')
        assert resp.status_code == 404


class TestWaypointDistances:
    def test_distances_endpoint(self, client):
        client.post('/api/waypoints', json={'name': 'D1', 'lat': 39.0, 'lng': -104.0})
        client.post('/api/waypoints', json={'name': 'D2', 'lat': 39.1, 'lng': -104.1})
        resp = client.get('/api/waypoints/distances')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'points' in data
        assert 'matrix' in data
