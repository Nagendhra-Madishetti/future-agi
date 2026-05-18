import json

from model_hub.serializers.contracts import (
    ModelHubEmptyRequestSerializer,
    OptimizeDatasetColumnConfigUpdateRequestSerializer,
    OptimizeDatasetKnowledgeBaseRequestSerializer,
    OptimizeDatasetListQuerySerializer,
    OptimizeDatasetMutationRequestSerializer,
    OptimizeDatasetPageRequestSerializer,
)


def test_optimize_dataset_list_query_accepts_canonical_pagination_and_filters():
    serializer = OptimizeDatasetListQuerySerializer(
        data={
            "page": "2",
            "limit": "25",
            "filters": json.dumps(
                [
                    {
                        "key": "status",
                        "operator": "equals",
                        "value": ["completed"],
                    }
                ]
            ),
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["page"] == 2
    assert serializer.validated_data["limit"] == 25
    assert serializer.validated_data["filters"][0]["key"] == "status"


def test_optimize_dataset_list_query_rejects_legacy_aliases():
    serializer = OptimizeDatasetListQuerySerializer(
        data={
            "pageSize": "25",
            "filters": json.dumps(
                [
                    {
                        "filterConfig": {
                            "filter_type": "text",
                            "filter_op": "equals",
                            "filter_value": "completed",
                        }
                    }
                ]
            ),
        }
    )

    assert not serializer.is_valid()
    assert "pageSize" in serializer.errors


def test_optimize_dataset_page_request_rejects_page_number_aliases():
    serializer = OptimizeDatasetPageRequestSerializer(
        data={"page_number": 0, "page_size": 10}
    )

    assert not serializer.is_valid()
    assert "page_number" in serializer.errors
    assert "page_size" in serializer.errors


def test_optimize_dataset_column_config_request_is_exact():
    serializer = OptimizeDatasetColumnConfigUpdateRequestSerializer(
        data={"columns": [{"value": "input", "label": "Input"}]}
    )

    assert serializer.is_valid(), serializer.errors

    serializer = OptimizeDatasetColumnConfigUpdateRequestSerializer(
        data={"columnConfig": [{"value": "input"}]}
    )

    assert not serializer.is_valid()
    assert "columnConfig" in serializer.errors


def test_optimize_dataset_create_rejects_camel_case_fields():
    serializer = OptimizeDatasetMutationRequestSerializer(
        data={
            "startDate": "2026-01-01T00:00:00Z",
            "endDate": "2026-01-02T00:00:00Z",
            "optimizeType": "template",
        }
    )

    assert not serializer.is_valid()
    assert "startDate" in serializer.errors
    assert "endDate" in serializer.errors
    assert "optimizeType" in serializer.errors


def test_optimize_dataset_kb_request_rejects_camel_case_fields():
    serializer = OptimizeDatasetKnowledgeBaseRequestSerializer(
        data={"knowledgeBaseFilters": {"source": "docs"}}
    )

    assert not serializer.is_valid()
    assert "knowledgeBaseFilters" in serializer.errors


def test_empty_request_serializer_rejects_body_fields():
    serializer = ModelHubEmptyRequestSerializer(data={"page": 1})

    assert not serializer.is_valid()
    assert "page" in serializer.errors
