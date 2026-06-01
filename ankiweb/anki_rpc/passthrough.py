from __future__ import annotations
import re

# Backend methods the web frontend calls via /_anki/<camel>, served by
# col._backend.<snake>_raw(body). Seeded from mediasrv exposed_backend_list
# (mediasrv.py:659-701); extend per page as needed in later plans.
PASSTHROUGH: set[str] = {
    "latest_progress", "get_custom_colours", "get_deck_names", "i18n_resources",
    "get_field_names", "get_import_anki_package_presets",
    "get_note", "get_notetype_names", "get_change_notetype_info",
    "card_stats", "get_review_logs", "graphs", "get_graph_preferences",
    "set_graph_preferences", "complete_tag", "congrats_info",
    "get_deck_configs_for_update",
    "get_image_occlusion_note", "get_image_occlusion_fields",
    "get_ignored_before_count", "compute_fsrs_params", "evaluate_params_legacy",
    "compute_optimal_retention", "simulate_fsrs_review", "simulate_fsrs_workload",
    "get_retention_workload", "set_wants_abort",
}

_S1 = re.compile(r"(.)([A-Z][a-z]+)")
_S2 = re.compile(r"([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    # keep digit runs attached to the preceding token: i18nResources -> i18n_resources
    return _S2.sub(r"\1_\2", _S1.sub(r"\1_\2", name)).lower()


def snake_to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)
