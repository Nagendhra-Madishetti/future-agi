import json

import pytest
from rest_framework import status

from model_hub.serializers.contracts import LegacyKnowledgeBaseTableQuerySerializer


class TestKnowledgeBaseTableContracts:
    def test_knowledge_base_table_query_accepts_canonical_sort_and_pagination(self):
        serializer = LegacyKnowledgeBaseTableQuerySerializer(
            data={
                "search": "docs",
                "sort": json.dumps(
                    [{"column_id": "updated_at", "type": "descending"}]
                ),
                "page_number": "1",
                "page_size": "25",
            }
        )

        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["page_number"] == 1
        assert serializer.validated_data["sort"][0]["column_id"] == "updated_at"

    def test_knowledge_base_table_query_rejects_legacy_pagination_aliases(self):
        serializer = LegacyKnowledgeBaseTableQuerySerializer(
            data={
                "pageNumber": "1",
                "pageSize": "25",
            }
        )

        assert not serializer.is_valid()
        assert "pageNumber" in serializer.errors
        assert "pageSize" in serializer.errors


@pytest.mark.integration
@pytest.mark.api
def test_knowledge_base_table_api_rejects_legacy_pagination_aliases(auth_client):
    response = auth_client.get(
        "/model-hub/knowledge-base/get/",
        {"pageNumber": "1", "pageSize": "25"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
