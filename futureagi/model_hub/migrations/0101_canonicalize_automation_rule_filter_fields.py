from django.db import migrations


FIELD_ID_ALIASES = {
    "traceId": "trace_id",
    "traceName": "trace_name",
    "nodeType": "node_type",
    "userId": "user_id",
    "projectName": "project_name",
    "totalCost": "total_cost",
    "startTime": "start_time",
    "endTime": "end_time",
    "agentDefinition": "agent_definition",
    "callType": "call_type",
    "datasetName": "dataset_name",
    "createdAt": "created_at",
}

FILTER_CONFIG_KEY_ALIASES = {
    "colType": "col_type",
    "filterType": "filter_type",
    "filterOp": "filter_op",
    "filterValue": "filter_value",
}


def _canonical_field_id(value):
    return FIELD_ID_ALIASES.get(value, value)


def _canonical_filter(filter_item):
    if not isinstance(filter_item, dict):
        return filter_item, False

    changed = False
    next_item = dict(filter_item)
    if "columnId" in next_item and "column_id" not in next_item:
        next_item["column_id"] = next_item.pop("columnId")
        changed = True

    if "filterConfig" in next_item and "filter_config" not in next_item:
        next_item["filter_config"] = next_item.pop("filterConfig")
        changed = True

    if "column_id" in next_item:
        column_id = _canonical_field_id(next_item["column_id"])
        if column_id != next_item["column_id"]:
            next_item["column_id"] = column_id
            changed = True

    config = next_item.get("filter_config")
    if isinstance(config, dict):
        next_config = dict(config)
        for old_key, new_key in FILTER_CONFIG_KEY_ALIASES.items():
            if old_key in next_config and new_key not in next_config:
                next_config[new_key] = next_config.pop(old_key)
                changed = True
        if next_config != config:
            next_item["filter_config"] = next_config

    return next_item, changed


def _canonical_rule(rule):
    if not isinstance(rule, dict):
        return rule, False

    next_rule = dict(rule)
    field = next_rule.get("field")
    canonical_field = _canonical_field_id(field)
    if canonical_field != field:
        next_rule["field"] = canonical_field
        return next_rule, True
    return next_rule, False


def _canonical_conditions(conditions):
    if not isinstance(conditions, dict):
        return conditions, False

    changed = False
    next_conditions = dict(conditions)

    for key in ("filter", "filters"):
        filters = next_conditions.get(key)
        if not isinstance(filters, list):
            continue
        next_filters = []
        filters_changed = False
        for filter_item in filters:
            next_item, item_changed = _canonical_filter(filter_item)
            next_filters.append(next_item)
            filters_changed = filters_changed or item_changed
        if filters_changed:
            next_conditions[key] = next_filters
            changed = True

    rules = next_conditions.get("rules")
    if isinstance(rules, list):
        next_rules = []
        rules_changed = False
        for rule in rules:
            next_rule, rule_changed = _canonical_rule(rule)
            next_rules.append(next_rule)
            rules_changed = rules_changed or rule_changed
        if rules_changed:
            next_conditions["rules"] = next_rules
            changed = True

    return next_conditions, changed


def canonicalize_automation_rule_filters(apps, schema_editor):
    AutomationRule = apps.get_model("model_hub", "AutomationRule")
    for rule in AutomationRule.objects.all().only("id", "conditions").iterator():
        next_conditions, changed = _canonical_conditions(rule.conditions or {})
        if changed:
            rule.conditions = next_conditions
            rule.save(update_fields=["conditions"])


class Migration(migrations.Migration):
    dependencies = [
        ("model_hub", "0100_score_queue_scoped_uniqueness"),
    ]

    operations = [
        migrations.RunPython(canonicalize_automation_rule_filters, migrations.RunPython.noop),
    ]
