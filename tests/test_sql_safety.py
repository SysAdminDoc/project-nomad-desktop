"""Tests for SQL safety helpers."""
import pytest
from web.sql_safety import safe_table, safe_columns, build_update, build_insert


class TestSafeTable:
    def test_valid_table(self):
        assert safe_table('inventory', {'inventory', 'contacts'}) == 'inventory'

    def test_invalid_table(self):
        with pytest.raises(ValueError, match='not in allowed set'):
            safe_table('evil_table', {'inventory', 'contacts'})

    def test_sql_injection_attempt(self):
        with pytest.raises(ValueError):
            safe_table('inventory; DROP TABLE users', {'inventory'})


class TestSafeColumns:
    def test_filters_to_allowed(self):
        result = safe_columns({'name': 'X', 'evil': 'Y', 'qty': 1}, ['name', 'qty'])
        assert result == {'name': 'X', 'qty': 1}

    def test_rejects_bad_identifiers(self):
        result = safe_columns({'name': 'X', 'a; DROP': 'Y'}, ['name', 'a; DROP'])
        assert result == {'name': 'X'}

    def test_empty_dict(self):
        assert safe_columns({}, ['name']) == {}

    def test_no_matching_columns(self):
        assert safe_columns({'a': 1}, ['b', 'c']) == {}


class TestBuildUpdate:
    def test_basic_update(self):
        sql, params = build_update('inventory', {'name': 'Water', 'qty': 10},
                                   ['name', 'qty', 'category'], where_val=5)
        assert sql == 'UPDATE inventory SET name = ?, qty = ? WHERE id = ?'
        assert params == ['Water', 10, 5]

    def test_filters_invalid_columns(self):
        sql, params = build_update('inventory', {'name': 'X', 'evil': 'Y'},
                                   ['name', 'qty'], where_val=1)
        assert 'evil' not in sql
        assert params == ['X', 1]

    def test_no_valid_columns_raises(self):
        with pytest.raises(ValueError, match='No valid columns'):
            build_update('inventory', {'evil': 'Y'}, ['name'], where_val=1)

    def test_custom_where_column(self):
        sql, params = build_update('contacts', {'name': 'A'}, ['name'],
                                   where_col='callsign', where_val='K1ABC')
        assert 'WHERE callsign = ?' in sql

    def test_invalid_where_column(self):
        with pytest.raises(ValueError, match='Invalid WHERE column'):
            build_update('t', {'a': 1}, ['a'], where_col='id; DROP', where_val=1)


class TestBuildInsert:
    def test_basic_insert(self):
        sql, params = build_insert('inventory', {'name': 'Water', 'qty': 10},
                                   ['name', 'qty', 'category'])
        assert sql == 'INSERT INTO inventory (name, qty) VALUES (?, ?)'
        assert params == ['Water', 10]

    def test_filters_invalid_columns(self):
        sql, params = build_insert('inventory', {'name': 'X', 'evil': 'Y'},
                                   ['name', 'qty'])
        assert 'evil' not in sql

    def test_no_valid_columns_raises(self):
        with pytest.raises(ValueError, match='No valid columns'):
            build_insert('inventory', {'evil': 'Y'}, ['name'])
