"""
tools/compliance_tools.py
--------------------------------------------------------------------------
Custom tools for ComplianceScout, exposed to the Strands Agent via the
@tool decorator. Each tool is intentionally deterministic and side-effect
free (besides logging) so it is easy to unit test and easy for the agent
to reason about when deciding when to call it again.

`search_building_codes` simulates a municipal zoning/code lookup. In a real
production deployment, swap the `_MOCK_CODE_DB` lookup for a call to an
AgentCore Gateway target that fronts a real municipal permitting API
(e.g. Accela, CitizenServe, or a city Open Data zoning endpoint).

`draft_permit_application` performs no network calls - it is a pure
transformation from structured contractor input into a permit-ready
document, returned as both JSON (for programmatic use / AgentCore Memory)
and Markdown (for human review before signature).
--------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from strands import tool

logger = logging.getLogger("compliance_scout.tools")

# ---------------------------------------------------------------------------
# Simulated municipal code database.
# Keyed by ZIP code -> topic keyword -> rule text + citation.
# Replace with a real data source (AgentCore Gateway -> city GIS/zoning API)
# for production use; the tool's input/output contract stays identical.
# ---------------------------------------------------------------------------
_MOCK_CODE_DB: Dict[str, Dict[str, Dict[str, str]]] = {
    "94103": {
        "deck": {
            "rule": "Decks over 30 inches above grade require a building "
                    "permit and guardrails at least 36 inches high per "
                    "San Francisco Building Code Sec. R312.",
            "citation": "SFBC R312.1",
            "permit_required": "yes",
        },
        "electrical": {
            "rule": "Any new circuit or panel upgrade requires an electrical "
                    "permit and inspection by SF DBI prior to close-in.",
            "citation": "SFBC Ch. 13A / NEC 2020 adoption",
            "permit_required": "yes",
        },
        "setback": {
            "rule": "Rear yard accessory structures must maintain a minimum "
                    "4 ft setback from the property line in RH-1 zones.",
            "citation": "SF Planning Code Sec. 136",
            "permit_required": "conditional",
        },
    },
    "78701": {
        "deck": {
            "rule": "Decks attached to the primary structure require a "
                    "residential building permit; detached decks under "
                    "200 sq ft and under 30 inches high are exempt.",
            "citation": "Austin Residential Code R105.2",
            "permit_required": "conditional",
        },
        "electrical": {
            "rule": "Service panel upgrades above 200A require an electrical "
                    "permit and City of Austin inspection.",
            "citation": "Austin Electrical Code Sec. 12-1",
            "permit_required": "yes",
        },
    },
    "10001": {
        "electrical": {
            "rule": "All electrical work in NYC requires a licensed master "
                    "electrician to file and pull an NYC DOB electrical "
                    "permit (PW1) prior to work starting.",
            "citation": "NYC Admin Code Title 27 / DOB Electrical Bulletins",
            "permit_required": "yes",
        },
    },
}

_DEFAULT_RULE = {
    "rule": "No specific local ordinance found in the reference dataset for "
            "this ZIP code / topic combination. Default to International "
            "Residential Code (IRC) baseline requirements and flag for "
            "manual verification with the local building department.",
    "citation": "IRC (baseline, unconfirmed local override)",
    "permit_required": "unknown",
}


@tool
def search_building_codes(zip_code: str, query: str) -> str:
    """Look up municipal building/zoning code requirements relevant to a project.

    Use this tool whenever the project description touches a structural,
    electrical, plumbing, or zoning element (e.g. "deck", "electrical",
    "setback", "addition") so the agent can ground its compliance analysis
    in the applicable local code before drafting any permit paperwork.

    Args:
        zip_code: The 5-digit ZIP code of the project site (e.g. "94103").
        query: A short keyword describing the code topic to search for,
            e.g. "deck", "electrical", "setback", "fence height".

    Returns:
        A JSON string with keys: zip_code, query, rule, citation,
        permit_required ("yes" | "no" | "conditional" | "unknown"), and
        source ("mock_dataset" | "default_fallback") so the agent can tell
        callers/humans whether this result should be double-checked.
    """
    normalized_zip = zip_code.strip()
    normalized_query = query.strip().lower()

    logger.info(
        "tool_call=search_building_codes zip=%s query=%s",
        normalized_zip,
        normalized_query,
    )

    zone_rules = _MOCK_CODE_DB.get(normalized_zip, {})
    match = None
    for topic, details in zone_rules.items():
        if topic in normalized_query or normalized_query in topic:
            match = details
            matched_topic = topic
            break

    if match is None:
        result = {
            "zip_code": normalized_zip,
            "query": query,
            "matched_topic": None,
            **_DEFAULT_RULE,
            "source": "default_fallback",
        }
    else:
        result = {
            "zip_code": normalized_zip,
            "query": query,
            "matched_topic": matched_topic,
            **match,
            "source": "mock_dataset",
        }

    return json.dumps(result, indent=2)


@tool
def draft_permit_application(project_type: str, specs: dict) -> str:
    """Compile contractor-provided project data into a structured permit draft.

    This produces a ready-for-review permit application: a machine-readable
    JSON payload (useful for filing systems / AgentCore Memory) plus a
    human-readable Markdown form the contractor or homeowner can review and
    sign. This tool never submits anything - it only drafts. Actual
    submission to a municipal portal always requires an explicit human
    decision/signature outside of this tool.

    Args:
        project_type: Category of work, e.g. "deck_construction",
            "electrical_panel_upgrade", "room_addition".
        specs: Dictionary of project-specific fields. Common keys include
            "address", "zip_code", "square_footage", "contractor_license",
            "estimated_cost", "description", and any compliance notes
            gathered from search_building_codes.

    Returns:
        A JSON string with keys: permit_id, generated_at, project_type,
        fields (the normalized specs), markdown (the rendered draft
        document), and requires_signature (always true) to make clear a
        human must review and approve before filing.
    """
    logger.info(
        "tool_call=draft_permit_application project_type=%s fields=%s",
        project_type,
        list(specs.keys()),
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    permit_id = f"DRAFT-{project_type[:4].upper()}-{int(datetime.now().timestamp())}"

    normalized_specs: Dict[str, Any] = {
        "address": specs.get("address", "UNSPECIFIED - human input required"),
        "zip_code": specs.get("zip_code", "UNSPECIFIED"),
        "square_footage": specs.get("square_footage"),
        "contractor_license": specs.get("contractor_license", "UNSPECIFIED"),
        "estimated_cost": specs.get("estimated_cost"),
        "description": specs.get("description", ""),
        "compliance_notes": specs.get("compliance_notes", []),
    }

    markdown = f"""# Permit Application Draft

**Permit ID (draft):** {permit_id}
**Generated:** {generated_at}
**Project Type:** {project_type.replace('_', ' ').title()}

| Field | Value |
|---|---|
| Site Address | {normalized_specs['address']} |
| ZIP Code | {normalized_specs['zip_code']} |
| Square Footage | {normalized_specs['square_footage'] or 'N/A'} |
| Contractor License # | {normalized_specs['contractor_license']} |
| Estimated Cost | {normalized_specs['estimated_cost'] or 'N/A'} |

## Project Description
{normalized_specs['description'] or '_No description provided._'}

## Compliance Notes
{chr(10).join(f"- {note}" for note in normalized_specs['compliance_notes']) or '_None recorded._'}

---
**STATUS: DRAFT - NOT SUBMITTED.**
A licensed contractor or property owner must review this draft, confirm
all fields, and provide a signature before it is filed with the local
building department. ComplianceScout will not submit this on your behalf.
"""

    result = {
        "permit_id": permit_id,
        "generated_at": generated_at,
        "project_type": project_type,
        "fields": normalized_specs,
        "markdown": markdown,
        "requires_signature": True,
    }

    return json.dumps(result, indent=2)
