from django.db import migrations


CONFIG_KEY_ALIASES = {
    "compareFilters": "compare_filters",
    "compareDateFilter": "compare_date_filter",
    "extraFilters": "extra_filters",
    "compareExtraFilters": "compare_extra_filters",
    "subTab": "sub_tab",
}


FILTER_CONFIG_KEYS = (
    "filters",
    "compare_filters",
    "extra_filters",
    "compare_extra_filters",
)


FILTER_ITEM_KEY_ALIASES = {
    "columnId": "column_id",
    "displayName": "display_name",
    "outputType": "output_type",
}


FILTER_CONFIG_KEY_ALIASES = {
    "filterType": "filter_type",
    "filterOp": "filter_op",
    "filterValue": "filter_value",
    "colType": "col_type",
}


def _migrate_users_filters_object(config):
    filters = config.get("filters")
    if not isinstance(filters, dict):
        return False

    extra_filters = filters.get("extra_filters", filters.get("extraFilters"))
    if extra_filters is not None and "extra_filters" not in config:
        config["extra_filters"] = extra_filters

    date_filter = filters.get("dateFilter", filters.get("date_filter"))
    if date_filter is not None:
        display = config.get("display")
        if not isinstance(display, dict):
            display = {}
            config["display"] = display
        if "dateFilter" not in display:
            display["dateFilter"] = date_filter

    config.pop("filters")
    return True


def _rename_config_keys(config):
    changed = False
    for old_key, new_key in CONFIG_KEY_ALIASES.items():
        if old_key in config and new_key not in config:
            config[new_key] = config.pop(old_key)
            changed = True
        elif old_key in config:
            config.pop(old_key)
            changed = True
    return changed


def _canonicalize_filter_item(filter_item):
    if not isinstance(filter_item, dict):
        return False

    changed = False
    for old_key, new_key in FILTER_ITEM_KEY_ALIASES.items():
        if old_key in filter_item and new_key not in filter_item:
            filter_item[new_key] = filter_item.pop(old_key)
            changed = True

    config = filter_item.get("filter_config")
    if not isinstance(config, dict) and isinstance(
        filter_item.get("filterConfig"), dict
    ):
        filter_item["filter_config"] = filter_item.pop("filterConfig")
        config = filter_item["filter_config"]
        changed = True

    if isinstance(config, dict):
        for old_key, new_key in FILTER_CONFIG_KEY_ALIASES.items():
            if old_key in config and new_key not in config:
                config[new_key] = config.pop(old_key)
                changed = True

    return changed


def rename_saved_view_config_keys(apps, schema_editor):
    SavedView = apps.get_model("tracer", "SavedView")
    for saved_view in SavedView.objects.iterator(chunk_size=500):
        config = saved_view.config
        if not isinstance(config, dict):
            continue

        changed = _rename_config_keys(config)
        changed = _migrate_users_filters_object(config) or changed
        for key in FILTER_CONFIG_KEYS:
            filters = config.get(key)
            if not isinstance(filters, list):
                continue
            for filter_item in filters:
                changed = _canonicalize_filter_item(filter_item) or changed

        if changed:
            saved_view.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [
        ("tracer", "0078_canonicalize_saved_view_filter_fields"),
    ]

    operations = [
        migrations.RunPython(
            rename_saved_view_config_keys,
            migrations.RunPython.noop,
        ),
    ]
