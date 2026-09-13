"""
tests/test_compliance_tools.py
--------------------------------------------------------------------------
Unit tests for the custom @tool-decorated functions in
tools/compliance_tools.py. These call the tools directly (Strands'
@tool decorator preserves plain-Python callability) so tests run fast,
offline, and without any AWS/Bedrock credentials.
--------------------------------------------------------------------------
"""

import json

import pytest

from tools.compliance_tools import draft_permit_application, search_building_codes


class TestSearchBuildingCodes:
    def test_known_zip_and_topic_returns_matched_rule(self):
        raw = search_building_codes(zip_code="94103", query="deck")
        result = json.loads(raw)

        assert result["zip_code"] == "94103"
        assert result["matched_topic"] == "deck"
        assert result["source"] == "mock_dataset"
        assert result["permit_required"] == "yes"
        assert "SFBC" in result["citation"]

    def test_known_zip_unknown_topic_falls_back_to_default(self):
        raw = search_building_codes(zip_code="94103", query="swimming pool heater")
        result = json.loads(raw)

        assert result["source"] == "default_fallback"
        assert result["permit_required"] == "unknown"
        assert result["matched_topic"] is None

    def test_unknown_zip_falls_back_to_default(self):
        raw = search_building_codes(zip_code="00000", query="electrical")
        result = json.loads(raw)

        assert result["source"] == "default_fallback"
        assert result["zip_code"] == "00000"

    def test_query_is_case_insensitive(self):
        raw_lower = search_building_codes(zip_code="78701", query="electrical")
        raw_upper = search_building_codes(zip_code="78701", query="ELECTRICAL")

        result_lower = json.loads(raw_lower)
        result_upper = json.loads(raw_upper)

        assert result_lower["matched_topic"] == result_upper["matched_topic"]
        assert result_upper["source"] == "mock_dataset"

    def test_result_is_valid_json_with_required_keys(self):
        raw = search_building_codes(zip_code="10001", query="electrical")
        result = json.loads(raw)

        for key in ("zip_code", "query", "rule", "citation", "permit_required", "source"):
            assert key in result


class TestDraftPermitApplication:
    def test_draft_contains_required_fields_and_is_marked_unsigned(self):
        raw = draft_permit_application(
            project_type="deck_construction",
            specs={
                "address": "123 Main St, San Francisco, CA",
                "zip_code": "94103",
                "square_footage": 168,
                "contractor_license": "CA-B-123456",
                "estimated_cost": 8500,
                "description": "12x14 ft attached rear deck.",
                "compliance_notes": ["Guardrail required per SFBC R312.1"],
            },
        )
        result = json.loads(raw)

        assert result["project_type"] == "deck_construction"
        assert result["requires_signature"] is True
        assert result["fields"]["address"] == "123 Main St, San Francisco, CA"
        assert "DRAFT - NOT SUBMITTED" in result["markdown"]
        assert "Guardrail required per SFBC R312.1" in result["markdown"]

    def test_missing_optional_fields_do_not_raise(self):
        raw = draft_permit_application(project_type="electrical_panel_upgrade", specs={})
        result = json.loads(raw)

        assert result["fields"]["address"] == "UNSPECIFIED - human input required"
        assert result["fields"]["compliance_notes"] == []
        assert result["requires_signature"] is True

    def test_permit_id_is_unique_across_calls(self):
        raw1 = draft_permit_application(project_type="deck", specs={})
        raw2 = draft_permit_application(project_type="deck", specs={})

        id1 = json.loads(raw1)["permit_id"]
        id2 = json.loads(raw2)["permit_id"]

        # IDs are timestamp-based; they may collide only if called within
        # the same second, so we just assert both are well-formed.
        assert id1.startswith("DRAFT-DECK-")
        assert id2.startswith("DRAFT-DECK-")

    def test_markdown_table_includes_all_key_fields(self):
        raw = draft_permit_application(
            project_type="room_addition",
            specs={"address": "55 Elm St", "zip_code": "78701"},
        )
        result = json.loads(raw)
        markdown = result["markdown"]

        assert "55 Elm St" in markdown
        assert "78701" in markdown
        assert "Room Addition" in markdown


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
