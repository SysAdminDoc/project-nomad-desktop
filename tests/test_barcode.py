"""Tests for barcode/UPC lookup and scan-to-inventory API routes."""

import json


class TestBarcodeLookup:
    def test_barcode_lookup_found(self, client):
        """Seeded Spam UPC should be in the database."""
        resp = client.get('/api/barcode/lookup/037600215114')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['found'] is True
        assert data['upc'] == '037600215114'
        assert data['name']  # should have a non-empty name

    def test_barcode_lookup_not_found(self, client):
        resp = client.get('/api/barcode/lookup/000000000000')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['found'] is False

    def test_barcode_lookup_invalid_format(self, client):
        resp = client.get('/api/barcode/lookup/abc')
        assert resp.status_code == 400
        assert 'Invalid UPC' in resp.get_json()['error']


class TestBarcodeAdd:
    def test_barcode_add(self, client):
        resp = client.post('/api/barcode/add', json={
            'upc': '123456789012',
            'name': 'Test Item',
            'category': 'Food',
            'brand': 'TestBrand',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'saved'
        assert data['upc'] == '123456789012'
        assert data['name'] == 'Test Item'

    def test_barcode_add_duplicate(self, client):
        client.post('/api/barcode/add', json={
            'upc': '111111111111',
            'name': 'First Entry',
        })
        # Adding the same UPC again should succeed (INSERT OR REPLACE)
        resp = client.post('/api/barcode/add', json={
            'upc': '111111111111',
            'name': 'Updated Entry',
        })
        assert resp.status_code == 201
        assert resp.get_json()['name'] == 'Updated Entry'


class TestBarcodeScanToInventory:
    def test_barcode_scan_to_inventory(self, client):
        # First add a known UPC to the database
        client.post('/api/barcode/add', json={
            'upc': '222222222222',
            'name': 'Canned Beans',
            'category': 'Food',
            'brand': 'BrandX',
            'unit': 'can',
            'default_shelf_life_days': 730,
        })
        # Now scan it into inventory
        resp = client.post('/api/barcode/scan-to-inventory', json={
            'upc': '222222222222',
            'quantity': 5,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'added'
        assert data['item']['name'] == 'Canned Beans'
        assert data['item']['quantity'] == 5

    def test_barcode_scan_unknown(self, client):
        resp = client.post('/api/barcode/scan-to-inventory', json={
            'upc': '999999999999',
        })
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()


class TestBarcodeDatabase:
    def test_barcode_database_stats(self, client):
        resp = client.get('/api/barcode/database/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total' in data
        assert 'categories' in data
        assert isinstance(data['categories'], list)

    def test_barcode_database_has_seeds(self, client):
        """The UPC database should be pre-seeded with common items."""
        resp = client.get('/api/barcode/database/stats')
        data = resp.get_json()
        assert data['total'] >= 50, f'Expected at least 50 seeded UPCs, got {data["total"]}'

    def test_barcode_upc_validation(self, client):
        """Various invalid UPC formats should return 400."""
        for bad_upc in ['', '12345', '12345678901234567890']:
            resp = client.post('/api/barcode/add', json={'upc': bad_upc, 'name': 'X'})
            assert resp.status_code == 400, f'Expected 400 for UPC: {bad_upc!r}'
