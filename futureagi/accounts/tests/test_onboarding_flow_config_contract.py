from copy import deepcopy
from dataclasses import fields

import pytest
from django.core.exceptions import ImproperlyConfigured

from accounts.services.onboarding.flow_config import (
    _validate_config,
    get_activation_flow_config,
)
from accounts.services.onboarding.signal_contract import (
    SUPPORTED_ONBOARDING_STAGE_RULE_SIGNALS,
)
from accounts.services.onboarding.signal_resolver import OnboardingSignals


def _valid_activation_flow_config():
    return deepcopy(get_activation_flow_config())


def _configured_stage_rule_signals(condition):
    names = set()
    for key in ("signal", "signal_not"):
        if key in condition:
            names.add(condition[key])
    for key in ("all", "any"):
        for nested in condition.get(key, []):
            names |= _configured_stage_rule_signals(nested)
    if "not" in condition:
        names |= _configured_stage_rule_signals(condition["not"])
    return names


def test_activation_flow_rejects_duplicate_activation_event_names():
    config = _valid_activation_flow_config()
    event_name = config["activation_events"]["names"][0]
    config["activation_events"]["names"].append(event_name)

    with pytest.raises(ImproperlyConfigured):
        _validate_config(config)


@pytest.mark.parametrize("route_field", ("route_key", "fallback_route_key"))
def test_activation_flow_rejects_unknown_action_route_keys(route_field):
    config = _valid_activation_flow_config()
    config["actions"]["create_prompt"][route_field] = "missing_route"

    with pytest.raises(ImproperlyConfigured):
        _validate_config(config)


def test_activation_flow_rejects_unknown_stage_rule_feature_flags():
    config = _valid_activation_flow_config()
    config["stage_rules"][0]["when"] = {
        "flag_enabled": "onboarding_flag_that_does_not_exist",
    }

    with pytest.raises(ImproperlyConfigured):
        _validate_config(config)


@pytest.mark.parametrize("condition_key", ("signal", "signal_not"))
def test_activation_flow_rejects_unknown_stage_rule_signals(condition_key):
    config = _valid_activation_flow_config()
    config["stage_rules"][0]["when"] = {
        condition_key: "signal_that_does_not_exist",
    }

    with pytest.raises(ImproperlyConfigured):
        _validate_config(config)


def test_stage_rule_signal_contract_matches_signal_state_fields():
    available_fields = {field.name for field in fields(OnboardingSignals)}

    assert SUPPORTED_ONBOARDING_STAGE_RULE_SIGNALS <= available_fields


def test_configured_stage_rule_signals_are_supported():
    config = _valid_activation_flow_config()
    configured_signals = set()
    for rule in config["stage_rules"]:
        configured_signals |= _configured_stage_rule_signals(rule["when"])

    assert configured_signals <= SUPPORTED_ONBOARDING_STAGE_RULE_SIGNALS
