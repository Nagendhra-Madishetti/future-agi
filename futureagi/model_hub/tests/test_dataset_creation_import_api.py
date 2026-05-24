import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from accounts.models.workspace import Workspace
from model_hub.models.choices import DataTypeChoices, SourceChoices
from model_hub.models.develop_dataset import Cell, Column, Dataset, Row


class _SuccessfulResourceCallLog:
    status = "created"

    def save(self):
        return None


def _csv_file(name="rows.csv", content=b"input,output\nhello,world\n"):
    return SimpleUploadedFile(name, content, content_type="text/csv")


def _patch_usage(monkeypatch, module_path):
    calls = []

    def record_usage(*args, **kwargs):
        calls.append((args, kwargs))
        return _SuccessfulResourceCallLog()

    monkeypatch.setattr(
        f"{module_path}.log_and_deduct_cost_for_resource_request",
        record_usage,
    )
    return calls


@pytest.mark.django_db
def test_create_empty_dataset_sets_workspace_after_validation(
    auth_client, workspace, monkeypatch
):
    usage_calls = _patch_usage(
        monkeypatch,
        "model_hub.views.datasets.create.empty_dataset",
    )

    response = auth_client.post(
        "/model-hub/develops/create-empty-dataset/",
        {
            "new_dataset_name": "Workspace Empty Dataset",
            "model_type": "GenerativeLLM",
            "row": 0,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    dataset_id = response.json()["result"]["dataset_id"]
    dataset = Dataset.no_workspace_objects.get(id=dataset_id)
    assert dataset.workspace_id == workspace.id
    assert len(usage_calls) == 1


@pytest.mark.django_db
def test_create_empty_dataset_duplicate_name_does_not_charge(
    auth_client, organization, workspace, user, monkeypatch
):
    Dataset.objects.create(
        name="Duplicate Empty Dataset",
        organization=organization,
        workspace=workspace,
        user=user,
    )
    usage_calls = _patch_usage(
        monkeypatch,
        "model_hub.views.datasets.create.empty_dataset",
    )

    response = auth_client.post(
        "/model-hub/develops/create-empty-dataset/",
        {
            "new_dataset_name": "Duplicate Empty Dataset",
            "model_type": "GenerativeLLM",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert usage_calls == []


@pytest.mark.django_db
def test_manual_dataset_sets_workspace_and_does_not_charge_invalid_request(
    auth_client, workspace, monkeypatch
):
    usage_calls = _patch_usage(monkeypatch, "model_hub.views.develop_dataset")

    invalid_response = auth_client.post(
        "/model-hub/develops/create-dataset-manually/",
        {
            "dataset_name": "Invalid Manual Dataset",
            "model_type": "GenerativeLLM",
            "number_of_rows": 0,
            "number_of_columns": 1,
        },
        format="json",
    )
    assert invalid_response.status_code == status.HTTP_400_BAD_REQUEST
    assert usage_calls == []

    response = auth_client.post(
        "/model-hub/develops/create-dataset-manually/",
        {
            "dataset_name": "Workspace Manual Dataset",
            "model_type": "GenerativeLLM",
            "number_of_rows": 2,
            "number_of_columns": 2,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    dataset_id = response.json()["result"]["dataset_id"]
    dataset = Dataset.no_workspace_objects.get(id=dataset_id)
    assert dataset.workspace_id == workspace.id
    assert Row.no_workspace_objects.filter(dataset=dataset, deleted=False).count() == 2
    assert (
        Column.no_workspace_objects.filter(dataset=dataset, deleted=False).count() == 2
    )
    assert len(usage_calls) == 2


@pytest.mark.django_db
def test_create_dataset_from_local_file_sets_workspace_and_progress_scope(
    auth_client, workspace, monkeypatch
):
    usage_calls = _patch_usage(
        monkeypatch,
        "model_hub.views.datasets.create.file_upload",
    )
    queued_tasks = []
    monkeypatch.setattr(
        "model_hub.views.datasets.create.file_upload.upload_file_to_minio",
        lambda file_obj, object_key, org_id=None: f"minio://{object_key}",
    )
    monkeypatch.setattr(
        "model_hub.views.datasets.create.file_upload.process_dataset_from_file.delay",
        lambda *args, **kwargs: queued_tasks.append((args, kwargs)),
    )

    response = auth_client.post(
        "/model-hub/develops/create-dataset-from-local-file/",
        {
            "new_dataset_name": "Workspace Local File Dataset",
            "model_type": "GenerativeLLM",
            "file": _csv_file(),
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_200_OK
    result = response.json()["result"]
    dataset = Dataset.no_workspace_objects.get(id=result["dataset_id"])
    assert dataset.workspace_id == workspace.id
    assert dataset.dataset_config["file_processing_status"] == "queued"
    assert result["estimated_rows"] == 1
    assert result["estimated_columns"] == 2
    assert len(usage_calls) == 2
    assert queued_tasks and queued_tasks[0][0][0] == str(dataset.id)

    progress_response = auth_client.get(
        f"/model-hub/develops/dataset-creation-progress/{dataset.id}/"
    )
    assert progress_response.status_code == status.HTTP_200_OK
    assert progress_response.json()["result"]["processing_status"] == "queued"


@pytest.mark.django_db
def test_create_dataset_from_local_file_duplicate_name_does_not_charge(
    auth_client, organization, workspace, user, monkeypatch
):
    Dataset.objects.create(
        name="Duplicate Local File Dataset",
        organization=organization,
        workspace=workspace,
        user=user,
    )
    usage_calls = _patch_usage(
        monkeypatch,
        "model_hub.views.datasets.create.file_upload",
    )

    response = auth_client.post(
        "/model-hub/develops/create-dataset-from-local-file/",
        {
            "new_dataset_name": "Duplicate Local File Dataset",
            "model_type": "GenerativeLLM",
            "file": _csv_file(),
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert usage_calls == []


@pytest.mark.django_db
def test_add_rows_from_file_rejects_other_workspace_before_usage_charge(
    auth_client, organization, user, monkeypatch
):
    other_workspace = Workspace.objects.create(
        name="Other File Import Workspace",
        organization=organization,
        created_by=user,
    )
    dataset = Dataset.no_workspace_objects.create(
        name="Other Workspace File Import Dataset",
        organization=organization,
        workspace=other_workspace,
        user=user,
    )
    Column.no_workspace_objects.create(
        name="input",
        dataset=dataset,
        data_type=DataTypeChoices.TEXT.value,
        source=SourceChoices.OTHERS.value,
    )
    usage_calls = _patch_usage(monkeypatch, "model_hub.views.develop_dataset")

    response = auth_client.post(
        "/model-hub/develops/add_rows_from_file/",
        {
            "dataset_id": str(dataset.id),
            "file": _csv_file(),
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert usage_calls == []
    assert Row.no_workspace_objects.filter(dataset=dataset, deleted=False).count() == 0
    assert Cell.no_workspace_objects.filter(dataset=dataset, deleted=False).count() == 0
