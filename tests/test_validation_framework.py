"""Tests for the validation framework."""
import pytest
import json


class TestValidateJson:
    def test_missing_required_field(self, client):
        # POST to inventory without required 'name'
        resp = client.post('/api/inventory',
                          data=json.dumps({'quantity': 5}),
                          content_type='application/json')
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'name' in str(data.get('details', []))

    def test_valid_payload_passes(self, client):
        resp = client.post('/api/inventory',
                          data=json.dumps({'name': 'Water', 'quantity': 10, 'category': 'water'}),
                          content_type='application/json')
        # Should not be a 400 validation error
        assert resp.status_code != 400 or 'Validation' not in resp.get_json().get('error', '')

    def test_string_too_long(self, client):
        resp = client.post('/api/inventory',
                          data=json.dumps({'name': 'X' * 1001, 'quantity': 1}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_negative_quantity(self, client):
        resp = client.post('/api/inventory',
                          data=json.dumps({'name': 'Water', 'quantity': -5}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_invalid_json_body(self, client):
        resp = client.post('/api/inventory',
                          data='not json',
                          content_type='application/json')
        assert resp.status_code == 400

    def test_non_json_content_type(self, client):
        resp = client.post('/api/inventory',
                          data='name=Water',
                          content_type='application/x-www-form-urlencoded')
        assert resp.status_code == 400


class TestValidateDataUnit:
    """Unit tests for _validate_data function directly."""

    def test_required_field_missing(self):
        from web.validation import _validate_data
        errors = _validate_data({}, {'name': {'type': str, 'required': True}})
        assert len(errors) == 1
        assert 'required' in errors[0]

    def test_type_mismatch(self):
        from web.validation import _validate_data
        errors = _validate_data({'age': 'not a number'}, {'age': {'type': int}})
        assert len(errors) == 1
        assert 'int' in errors[0]

    def test_int_accepted_as_float(self):
        from web.validation import _validate_data
        errors = _validate_data({'rate': 5}, {'rate': {'type': float}})
        assert errors == []

    def test_max_length(self):
        from web.validation import _validate_data
        errors = _validate_data({'name': 'X' * 300}, {'name': {'type': str, 'max_length': 200}})
        assert len(errors) == 1

    def test_min_value(self):
        from web.validation import _validate_data
        errors = _validate_data({'qty': -1}, {'qty': {'type': int, 'min': 0}})
        assert len(errors) == 1

    def test_choices(self):
        from web.validation import _validate_data
        errors = _validate_data({'status': 'evil'}, {'status': {'choices': ['active', 'inactive']}})
        assert len(errors) == 1

    def test_pattern(self):
        from web.validation import _validate_data
        errors = _validate_data({'code': 'ABC123'}, {'code': {'type': str, 'pattern': r'^[a-z]+$'}})
        assert len(errors) == 1

    def test_valid_data_no_errors(self):
        from web.validation import _validate_data
        errors = _validate_data(
            {'name': 'Water', 'qty': 10, 'cat': 'supply'},
            {'name': {'type': str, 'required': True, 'max_length': 200},
             'qty': {'type': int, 'min': 0},
             'cat': {'type': str, 'choices': ['supply', 'food', 'medical']}}
        )
        assert errors == []

    def test_optional_field_skipped(self):
        from web.validation import _validate_data
        errors = _validate_data({}, {'notes': {'type': str, 'max_length': 1000}})
        assert errors == []
