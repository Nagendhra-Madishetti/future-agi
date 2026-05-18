"""Tests for the eval context map and mapping resolver in xl.py.

Covers:
- _resolve_persona_for_call: picks the Persona used for a given CallExecution.
- _flatten_persona / _flatten_persona_for_resolver: build the persona.* namespace.
- _build_simulation_context_map: full context map assembly.
- _translate_mapping_value: resolver branches including scenario.<column_name>.
"""

import pytest

from model_hub.models.choices import DatasetSourceChoices, SourceChoices, StatusType

# These exercise the resolver against a real DB graph (Persona, Scenarios,
# Dataset, CallExecution) — integration scope, not pure unit. Per the
# project convention these live in @pytest.mark.integration.
pytestmark = pytest.mark.integration
from model_hub.models.develop_dataset import Cell, Column, Dataset, Row
from simulate.models import AgentDefinition, Persona, Scenarios
from simulate.models.run_test import RunTest
from simulate.models.simulator_agent import SimulatorAgent
from simulate.models.test_execution import CallExecution, TestExecution


# ---------------------------------------------------------------------------
# Test helpers — module-scope factories. Kept in this file (not conftest) so
# the persona/simulator coverage doesn't bleed into unrelated suites.
# ---------------------------------------------------------------------------


def _make_persona(organization, workspace, **overrides):
    """Create a Persona row with sane defaults; overrides win."""
    defaults = dict(
        name="Test Persona",
        organization=organization,
        workspace=workspace,
        persona_type=Persona.PersonaType.WORKSPACE,
    )
    defaults.update(overrides)
    return Persona.objects.create(**defaults)


def _make_agent_definition(organization, workspace):
    return AgentDefinition.objects.create(
        agent_name="Test Agent",
        agent_type=AgentDefinition.AgentTypeChoices.VOICE,
        inbound=True,
        description="Test agent",
        organization=organization,
        workspace=workspace,
        languages=["en"],
    )


def _make_dataset_with_columns(organization, workspace, user, column_specs):
    """Create a Dataset with the named columns and a single Row.

    `column_specs` is a list of (column_name, cell_value) tuples. Returns
    (dataset, row, columns_by_name).
    """
    dataset = Dataset.no_workspace_objects.create(
        name="Test Dataset",
        organization=organization,
        workspace=workspace,
        user=user,
        source=DatasetSourceChoices.SCENARIO.value,
    )
    columns_by_name = {}
    column_order = []
    for col_name, _ in column_specs:
        col = Column.objects.create(
            dataset=dataset,
            name=col_name,
            data_type="text",
            source=SourceChoices.OTHERS.value,
        )
        columns_by_name[col_name] = col
        column_order.append(str(col.id))
    dataset.column_order = column_order
    dataset.save()

    row = Row.objects.create(dataset=dataset, order=0)
    for col_name, cell_value in column_specs:
        Cell.objects.create(
            dataset=dataset,
            column=columns_by_name[col_name],
            row=row,
            value=cell_value,
        )
    return dataset, row, columns_by_name


def _make_scenario(
    organization, workspace, agent_definition, dataset=None, metadata=None
):
    return Scenarios.objects.create(
        name="Test Scenario",
        description="Test scenario description",
        source="Test source",
        scenario_type=Scenarios.ScenarioTypes.DATASET,
        organization=organization,
        workspace=workspace,
        dataset=dataset,
        agent_definition=agent_definition,
        status=StatusType.COMPLETED.value,
        metadata=metadata or {},
    )


def _make_run_test(organization, workspace, agent_definition, simulator_agent, scenario):
    rt = RunTest.objects.create(
        name="Test Run",
        description="Test run description",
        agent_definition=agent_definition,
        simulator_agent=simulator_agent,
        organization=organization,
        workspace=workspace,
    )
    rt.scenarios.add(scenario)
    return rt


def _make_call_execution(test_execution, scenario, row_id=None, row_data=None):
    call_metadata = {}
    if row_id is not None:
        call_metadata["row_id"] = str(row_id)
    if row_data is not None:
        call_metadata["row_data"] = row_data
    return CallExecution.objects.create(
        test_execution=test_execution,
        scenario=scenario,
        phone_number="+1234567890",
        status=CallExecution.CallStatus.COMPLETED,
        call_metadata=call_metadata,
    )


# ---------------------------------------------------------------------------
# Task 1.1 — _resolve_persona_for_call
# ---------------------------------------------------------------------------


@pytest.fixture
def persona_setup(db, organization, workspace, user):
    """Bootstraps the dependency graph: AgentDefinition → Scenario → RunTest
    → TestExecution. Returns a closure that builds a CallExecution with
    arbitrary scenario_metadata / row_data.
    """
    agent_def = _make_agent_definition(organization, workspace)
    simulator = SimulatorAgent.objects.create(
        name="Sim",
        prompt="You are a simulator",
        voice_provider="elevenlabs",
        voice_name="marissa",
        model="gpt-4",
        organization=organization,
        workspace=workspace,
    )

    def _build(scenario_metadata=None, row_data=None):
        scenario = _make_scenario(
            organization,
            workspace,
            agent_def,
            metadata=scenario_metadata or {},
        )
        rt = _make_run_test(organization, workspace, agent_def, simulator, scenario)
        te = TestExecution.objects.create(
            run_test=rt,
            status=TestExecution.ExecutionStatus.COMPLETED,
            simulator_agent=simulator,
            agent_definition=agent_def,
        )
        return _make_call_execution(te, scenario, row_data=row_data)

    return _build


@pytest.mark.django_db
def test_resolve_persona_prefers_row_data_persona_id(
    persona_setup, organization, workspace
):
    from simulate.temporal.activities.xl import _resolve_persona_for_call

    persona_a = _make_persona(organization, workspace, name="A")
    persona_b = _make_persona(organization, workspace, name="B")

    call = persona_setup(
        scenario_metadata={"persona_ids": [str(persona_a.id), str(persona_b.id)]},
        row_data={"persona": str(persona_b.id)},
    )

    resolved = _resolve_persona_for_call(call)

    assert resolved is not None
    assert resolved.id == persona_b.id


@pytest.mark.django_db
def test_resolve_persona_falls_back_to_first_in_metadata(
    persona_setup, organization, workspace
):
    from simulate.temporal.activities.xl import _resolve_persona_for_call

    persona_a = _make_persona(organization, workspace, name="A")
    persona_b = _make_persona(organization, workspace, name="B")

    call = persona_setup(
        scenario_metadata={"persona_ids": [str(persona_a.id), str(persona_b.id)]},
        row_data={},
    )

    resolved = _resolve_persona_for_call(call)

    assert resolved is not None
    assert resolved.id == persona_a.id


@pytest.mark.django_db
def test_resolve_persona_returns_none_when_no_persona_ids(persona_setup):
    from simulate.temporal.activities.xl import _resolve_persona_for_call

    call = persona_setup(scenario_metadata={}, row_data={})

    assert _resolve_persona_for_call(call) is None
