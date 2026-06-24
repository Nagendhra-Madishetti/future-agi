from accounts.authentication import (
    _is_workspace_write_exempt_view,
    workspace_read_only,
)
from tfc.constants.levels import Level


def test_owner_level_maps_to_workspace_admin_label():
    assert Level.to_ws_string(Level.OWNER) == "Workspace Admin"
    assert Level.to_ws_role(Level.OWNER) == "workspace_admin"


class _FakeRequest:
    """Mimics the resolver_match -> func.cls chain Django sets on requests."""

    def __init__(self, view_cls):
        self.resolver_match = type(
            "Match", (), {"func": type("Func", (), {"cls": view_cls})}
        )


def test_workspace_read_only_marks_the_view():
    @workspace_read_only
    class View:
        pass

    assert View.workspace_write_exempt is True


def test_marked_view_is_write_exempt():
    @workspace_read_only
    class View:
        pass

    assert _is_workspace_write_exempt_view(_FakeRequest(View)) is True


def test_unmarked_view_is_not_write_exempt():
    class View:
        pass

    assert _is_workspace_write_exempt_view(_FakeRequest(View)) is False


def test_unresolvable_view_fails_closed():
    class NoMatch:
        resolver_match = None

    assert _is_workspace_write_exempt_view(NoMatch()) is False


def test_read_only_eval_views_are_write_exempt():
    """Every read-only POST view must carry the marker.

    Regression: the ground-truth similarity search was a read-only POST that
    the old path allow-list missed, so viewers got 403 on it. This asserts the
    whole read-only group (including search) is exempt, and fails loudly if a
    future read-only POST view forgets @workspace_read_only.
    """
    from model_hub.views.separate_evals import (
        EvalTemplateListChartsView,
        EvalTemplateListView,
        GetEvalTemplateNameView,
        GetEvalTemplates,
        GroundTruthSearchView,
    )

    for view in (
        GetEvalTemplates,
        GetEvalTemplateNameView,
        EvalTemplateListView,
        EvalTemplateListChartsView,
        GroundTruthSearchView,
    ):
        assert getattr(view, "workspace_write_exempt", False) is True, view.__name__


def test_mutating_eval_views_are_not_write_exempt():
    from model_hub.views.separate_evals import (
        EvalTemplateBulkDeleteView,
        EvalTemplateCreateV2View,
        EvalTemplateUpdateView,
    )

    for view in (
        EvalTemplateCreateV2View,
        EvalTemplateUpdateView,
        EvalTemplateBulkDeleteView,
    ):
        assert getattr(view, "workspace_write_exempt", False) is False, view.__name__
