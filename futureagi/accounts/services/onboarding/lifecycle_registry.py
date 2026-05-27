from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from django.core.exceptions import ImproperlyConfigured

from accounts.services.onboarding.constants import (
    ACTIVATION_STAGES,
    ONBOARDING_ACTIVATION_EVENTS,
)

CONFIG_PATH = Path(__file__).with_name("lifecycle_campaigns.yml")

REQUIRED_FIELDS = (
    "campaign_key",
    "template_key",
    "template_version",
    "campaign_group",
    "primary_path",
    "entry_stages",
    "wait_window_minutes",
    "priority",
    "target_action_id",
    "target_success_event",
    "route_strategy",
    "dry_run_flag",
    "send_flag",
    "frequency_cap_key",
    "sample_policy",
    "owner",
    "qa_fixture",
)

ROUTE_STRATEGIES = {
    "activation_recommendation",
    "home_choose_goal",
    "sample_project",
    "artifact_deep_link",
    "daily_quality",
}

SAMPLE_POLICIES = {"real_only", "sample_only", "allow_sample"}


def _config_error(message: str) -> ImproperlyConfigured:
    return ImproperlyConfigured(
        f"Invalid onboarding lifecycle campaign config: {message}"
    )


def _mapping(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise _config_error(f"{path} must be a mapping.")
    return value


def _sequence(value: Any, path: str) -> list:
    if not isinstance(value, list):
        raise _config_error(f"{path} must be a list.")
    return value


def _required_text(mapping: dict, key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _config_error(f"{path}.{key} must be a non-empty string.")
    return value


def _required_positive_int(mapping: dict, key: str, path: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or value < 0:
        raise _config_error(f"{path}.{key} must be a positive integer.")
    return value


def _load_config_file() -> dict:
    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _config_error(f"{CONFIG_PATH.name} could not be read.") from exc
    except yaml.YAMLError as exc:
        raise _config_error(f"{CONFIG_PATH.name} is not valid YAML.") from exc
    return _mapping(raw, CONFIG_PATH.name)


def _validate_campaign(campaign: dict, path: str) -> None:
    for field in REQUIRED_FIELDS:
        if field not in campaign:
            raise _config_error(f"{path}.{field} is required.")

    _required_text(campaign, "campaign_key", path)
    template_key = _required_text(campaign, "template_key", path)
    if not template_key.endswith("_v1"):
        raise _config_error(f"{path}.template_key must include a version suffix.")
    _required_text(campaign, "template_version", path)
    _required_text(campaign, "campaign_group", path)
    _required_text(campaign, "primary_path", path)
    _required_positive_int(campaign, "wait_window_minutes", path)
    _required_positive_int(campaign, "priority", path)
    _required_text(campaign, "target_action_id", path)
    if campaign["target_success_event"] not in ONBOARDING_ACTIVATION_EVENTS:
        raise _config_error(f"{path}.target_success_event is not supported.")
    if campaign["route_strategy"] not in ROUTE_STRATEGIES:
        raise _config_error(f"{path}.route_strategy is not supported.")
    _required_text(campaign, "dry_run_flag", path)
    _required_text(campaign, "send_flag", path)
    _required_text(campaign, "frequency_cap_key", path)
    if campaign["sample_policy"] not in SAMPLE_POLICIES:
        raise _config_error(f"{path}.sample_policy is not supported.")
    _required_text(campaign, "owner", path)
    _required_text(campaign, "qa_fixture", path)

    stages = _sequence(campaign.get("entry_stages"), f"{path}.entry_stages")
    if not stages:
        raise _config_error(f"{path}.entry_stages cannot be empty.")
    for stage in stages:
        if stage not in ACTIVATION_STAGES:
            raise _config_error(f"{path}.entry_stages contains unknown stage.")


def _validate_config(config: dict) -> None:
    _required_text(config, "schema_version", CONFIG_PATH.name)
    campaigns = _sequence(config.get("campaigns"), "campaigns")
    seen = set()
    for index, campaign in enumerate(campaigns):
        campaign = _mapping(campaign, f"campaigns.{index}")
        _validate_campaign(campaign, f"campaigns.{index}")
        key = campaign["campaign_key"]
        if key in seen:
            raise _config_error(f"Duplicate campaign_key: {key}.")
        seen.add(key)


@lru_cache(maxsize=1)
def get_lifecycle_registry_config() -> dict:
    config = _load_config_file()
    _validate_config(config)
    return config


def lifecycle_campaigns() -> tuple[dict, ...]:
    return tuple(deepcopy(get_lifecycle_registry_config()["campaigns"]))


def lifecycle_campaign_by_key(campaign_key: str) -> dict | None:
    for campaign in lifecycle_campaigns():
        if campaign["campaign_key"] == campaign_key:
            return campaign
    return None
