"""Render the ComplianceScout architecture Mermaid diagram as a PNG.

Uses kroki.io as the rendering service. Falls back to a direct
mermaid-cli approach if available.
"""
import base64
import json
import urllib.request
import zlib
import sys
import os

DIAGRAM = r"""flowchart LR
    U["User / Contractor\nProject Prompt"] --> SA

    subgraph SA["Strands Agent Harness & Loop"]
        direction TB
        SYS["System Prompt\n(ComplianceScout persona)"]
        LOOP["Agent Loop\n(SlidingWindowConversationManager\n+ SequentialToolExecutor)"]
        HOOKS["ComplianceTraceHooks\n(decision + tool tracing)"]
        SYS --> LOOP
        LOOP -. emits .-> HOOKS
    end

    SA <--> BR["Amazon Bedrock\nClaude Sonnet (model provider)"]

    LOOP --> T1["Tool: search_building_codes\n(zip_code, query)"]
    LOOP --> T2["Tool: draft_permit_application\n(project_type, specs)"]
    T1 --> MUNI["Municipal Zoning / Building\nCode APIs (or reference dataset)"]

    subgraph ACR["Amazon Bedrock AgentCore"]
        direction TB
        RUNTIME["AgentCore Runtime\n(serverless HTTP host)"]
        MEM["AgentCore Memory\n(session + summary persistence)"]
        OBS["AgentCore Observability\n(OpenTelemetry traces & logs)"]
    end

    SA --> RUNTIME
    RUNTIME <--> MEM
    HOOKS -. OTEL spans .-> OBS
    RUNTIME -. "CloudWatch GenAI\nObservability" .-> OBS

    T2 --> DRAFT["Permit Draft\n(JSON + Markdown,\nrequires human signature)"]
    DRAFT --> HUMAN["Human Contractor\nreview & sign-off"]
"""

out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "architecture_diagram.png")

# Kroki accepts POST with JSON body
payload = json.dumps({"diagram_source": DIAGRAM, "diagram_type": "mermaid", "output_format": "png"}).encode("utf-8")

url = "https://kroki.io/mermaid/png"

print("Fetching diagram from kroki.io ...")
try:
    req = urllib.request.Request(
        url,
        data=DIAGRAM.encode("utf-8"),
        headers={"Content-Type": "text/plain", "Accept": "image/png"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    with open(out_path, "wb") as f:
        f.write(data)
    print(f"Saved: {out_path}  ({len(data):,} bytes)")
except Exception as e:
    print(f"kroki.io failed: {e}", file=sys.stderr)
    sys.exit(1)
