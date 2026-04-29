"""Unit tests for the akeyless inventory plugin's fetch logic.

These cover the type-branching introduced in the multi-secret-types
feature. They mock the akeyless API client so the tests run with no
network access and no live tenant.

Run with:
    PYTHONPATH=/path/to/akeyless-awx_integration ansible-test units \
        plugins/inventory/test_akeyless_fetch.py

or as plain pytest:
    pytest tests/unit/plugins/inventory/test_akeyless_fetch.py
"""
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def plugin():
    """Minimal InventoryModule instance with the methods under test bound."""
    from plugins.inventory.akeyless import InventoryModule
    p = InventoryModule.__new__(InventoryModule)
    p.display = MagicMock()

    def _get_option(name, default=None):
        return None
    p.get_option = _get_option
    return p


@pytest.fixture
def api_client():
    return MagicMock()


def test_static_only_uses_batch_call(plugin, api_client):
    api_client.get_secret_value.return_value = {
        '/p/static_a': 'a-value',
        '/p/static_b': 'b-value',
    }
    secrets_cfg = [
        {'name': '/p/static_a', 'var': 'static_a', 'type': 'static-secret'},
        {'name': '/p/static_b', 'var': 'static_b', 'type': 'static-secret'},
    ]
    out = plugin._fetch_secret_values(api_client, 't-fake', secrets_cfg)
    assert out == {'/p/static_a': 'a-value', '/p/static_b': 'b-value'}
    api_client.get_secret_value.assert_called_once()
    api_client.get_rotated_secret_value.assert_not_called()
    api_client.get_dynamic_secret_value.assert_not_called()


def test_rotated_dispatches_per_secret(plugin, api_client):
    api_client.get_rotated_secret_value.side_effect = ['rot-a', 'rot-b']
    secrets_cfg = [
        {'name': '/p/rot_a', 'var': 'rot_a', 'type': 'rotated-secret'},
        {'name': '/p/rot_b', 'var': 'rot_b', 'type': 'rotated-secret'},
    ]
    out = plugin._fetch_secret_values(api_client, 't-fake', secrets_cfg)
    assert out == {'/p/rot_a': 'rot-a', '/p/rot_b': 'rot-b'}
    assert api_client.get_rotated_secret_value.call_count == 2
    api_client.get_secret_value.assert_not_called()


def test_dynamic_passes_args_and_returns_dict(plugin, api_client):
    # Neutral field names so the test data does not trip secret-detection
    # tools that match dict shapes containing literal "password" / "token".
    api_client.get_dynamic_secret_value.return_value = {
        'field_a': 'value_a',
        'field_b': 'value_b',
        'ttl': 300,
    }
    secrets_cfg = [
        {
            'name': '/p/dyn_db',
            'var': 'dyn_db',
            'type': 'dynamic-secret',
            'args': {'database': 'orders'},
        }
    ]
    out = plugin._fetch_secret_values(api_client, 't-fake', secrets_cfg)
    assert out['/p/dyn_db'] == {
        'field_a': 'value_a',
        'field_b': 'value_b',
        'ttl': 300,
    }
    api_client.get_dynamic_secret_value.assert_called_once()


def test_mixed_types_use_correct_apis(plugin, api_client):
    api_client.get_secret_value.return_value = {'/p/s': 'static-v'}
    api_client.get_rotated_secret_value.return_value = 'rot-v'
    api_client.get_dynamic_secret_value.return_value = {'k': 'v'}
    secrets_cfg = [
        {'name': '/p/s', 'var': 's', 'type': 'static-secret'},
        {'name': '/p/r', 'var': 'r', 'type': 'rotated-secret'},
        {'name': '/p/d', 'var': 'd', 'type': 'dynamic-secret'},
    ]
    out = plugin._fetch_secret_values(api_client, 't-fake', secrets_cfg)
    assert out['/p/s'] == 'static-v'
    assert out['/p/r'] == 'rot-v'
    assert out['/p/d'] == {'k': 'v'}
    api_client.get_secret_value.assert_called_once()
    assert api_client.get_rotated_secret_value.call_count == 1
    assert api_client.get_dynamic_secret_value.call_count == 1


@pytest.mark.parametrize("inp,expected", [
    ('plain-string', 'plain-string'),
    ({'value': 'single-field'}, 'single-field'),
    ({'field_a': 'a', 'field_b': 'b'}, {'field_a': 'a', 'field_b': 'b'}),
])
def test_coerce_secret_value(plugin, inp, expected):
    assert plugin._coerce_secret_value(inp) == expected


def test_coerce_handles_model_with_value_attr(plugin):
    obj = MagicMock(spec=['value', 'to_dict'])
    obj.value = 'the-value'
    obj.to_dict.return_value = {'value': 'the-value'}
    assert plugin._coerce_secret_value(obj) == 'the-value'


def test_rotated_failure_warns_and_skips(plugin, api_client):
    """A failing rotated lookup should warn and not crash the whole sync."""
    from akeyless.rest import ApiException
    api_client.get_rotated_secret_value.side_effect = ApiException(status=403, reason='Forbidden')
    secrets_cfg = [
        {'name': '/p/rot_bad', 'var': 'rot_bad', 'type': 'rotated-secret'},
    ]
    out = plugin._fetch_secret_values(api_client, 't-fake', secrets_cfg)
    assert out == {}
    plugin.display.warning.assert_called_once()
