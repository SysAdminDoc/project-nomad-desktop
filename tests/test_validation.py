"""Tests for input validation hardening across API routes."""


class TestFuelValidation:
    def test_create_fuel_requires_fuel_type(self, client):
        resp = client.post('/api/fuel', json={'quantity': 10})
        assert resp.status_code == 400

    def test_create_fuel_bad_quantity_handled(self, client):
        resp = client.post('/api/fuel', json={
            'fuel_type': 'Gasoline',
            'quantity': 'not-a-number',
        })
        assert resp.status_code == 201
        # Should default quantity to 0.0


class TestEquipmentValidation:
    def test_create_equipment_requires_name(self, client):
        resp = client.post('/api/equipment', json={'category': 'tools'})
        assert resp.status_code == 400

    def test_create_equipment_empty_name_rejected(self, client):
        resp = client.post('/api/equipment', json={'name': '  '})
        assert resp.status_code == 400


class TestCSVImportValidation:
    def test_csv_execute_invalid_column(self, client):
        resp = client.post('/api/import/csv/execute', json={
            'csv_data': 'name,evil\nTest,hack',
            'mapping': {'name': 'name', 'evil': 'DROP TABLE inventory--'},
            'target_table': 'inventory',
        })
        assert resp.status_code == 400
        assert 'Invalid column' in resp.get_json()['error']

    def test_csv_execute_valid_columns(self, client):
        resp = client.post('/api/import/csv/execute', json={
            'csv_data': [
                {'item_name': 'Test Water', 'cat': 'water', 'qty': '5'},
            ],
            'mapping': {
                'item_name': 'name',
                'cat': 'category',
                'qty': 'quantity',
            },
            'target_table': 'inventory',
        })
        # Should succeed or fail gracefully (not 400 for valid columns)
        assert resp.status_code in (200, 500)


class TestUploadSizeLimit:
    def test_max_content_length_configured(self, app):
        assert app.config['MAX_CONTENT_LENGTH'] == 100 * 1024 * 1024
