"""
agent/compliance_agent.py
--------------------------------------------------------------------------
Core agent logic for ComplianceScout (Agents for Humans Hackathon,
Professional Agents track).

This module:
  1. Builds a Strands Agent backed by Amazon Bedrock (Claude Sonnet).
  2. Wires in the custom municipal-compliance tools + tracing hooks.
  3. Applies Strands execution limits (conversation window + tool
     concurrency) so the agent loop stays bounded and observable.
  4. Exposes an Amazon Bedrock AgentCore Runtime entrypoint (`app`) so the
     exact same agent object can be deployed serverlessly via the
     `agentcore` CLI, with AgentCore Memory wired in for session
     persistence across multi-step contractor conversations.
  5. Provides a `--serve` mode (used by the Dockerfile) and a safe,
     no-AWS-credentials-required local CLI runner for quick iteration.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from typing import Any

from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import BedrockModel
from strands.tools.executors import SequentialToolExecutor

from agent.hooks import ComplianceTraceHooks
from agent.prompts import SYSTEM_PROMPT
from tools.compliance_tools import draft_permit_application, search_building_codes

# ---------------------------------------------------------------------------
# Logging: structured, INFO by default, overridable via LOG_LEVEL env var.
# This is what ComplianceTraceHooks writes to; in AgentCore Runtime, stdout
# logs are automatically captured by CloudWatch and correlated with the
# OpenTelemetry traces emitted by the same hooks.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("compliance_scout")

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
# Claude Sonnet on Amazon Bedrock is the default model provider for this
# agent. The model id is read from an env var so the same code can target
# a regional inference profile without a code change (recommended for
# on-demand throughput with Claude models on Bedrock).
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def build_model() -> BedrockModel:
    """Construct the Bedrock-backed Claude Sonnet model client."""
    return BedrockModel(
        model_id=BEDROCK_MODEL_ID,
        region_name=AWS_REGION,
        temperature=0.2,  # Compliance work rewards low-variance, grounded output
        max_tokens=4096,
    )


def build_agent(session_id: str | None = None) -> Agent:
    """Construct a fully-wired ComplianceScout Agent instance.

    Args:
        session_id: Optional identifier used to scope AgentCore Memory
            retrieval/storage for this conversation (see
            `agentcore_app.py` for how this is populated per-request in
            deployed AgentCore Runtime sessions).
    """
    # Execution limit #1: bound the conversation window so a long-running,
    # multi-turn contractor session can't silently grow the prompt (and
    # cost/latency) without limit. Older turns are summarized/pruned.
    conversation_manager = SlidingWindowConversationManager(
        window_size=40,
    )

    agent = Agent(
        name="ComplianceScout",
        model=build_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[search_building_codes, draft_permit_application],
        hooks=[ComplianceTraceHooks()],
        conversation_manager=conversation_manager,
        # Execution limit #2: force sequential tool execution so that when
        # the agent calls multiple tools in one turn (e.g. two code
        # lookups), the calls -- and the trace/log events emitted by
        # ComplianceTraceHooks for each -- stay strictly ordered and easy
        # for a human auditor to follow, rather than interleaving.
        tool_executor=SequentialToolExecutor(),
        trace_attributes={
            "hackathon.track": "professional-agents",
            "app.name": "contractor-compliance-scout",
            "session.id": session_id or "local-session",
        },
    )
    return agent


# ---------------------------------------------------------------------------
# Amazon Bedrock AgentCore Runtime entrypoint
# ---------------------------------------------------------------------------
# BedrockAgentCoreApp turns this module into an HTTP service compatible
# with AgentCore Runtime's contract (POST /invocations, GET /ping) when
# run via `agentcore launch` / `agentcore deploy`, and lets `agentcore
# invoke` call it locally or remotely with the same payload shape.
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    from bedrock_agentcore.memory import MemoryClient

    app = BedrockAgentCoreApp()
    _memory_client: "MemoryClient | None" = None

    def _get_memory_client() -> "MemoryClient":
        global _memory_client
        if _memory_client is None:
            _memory_client = MemoryClient(region_name=AWS_REGION)
        return _memory_client

    @app.entrypoint
    def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """AgentCore Runtime entrypoint.

        Expected payload shape:
            {
              "prompt": "I want to build a 12x14 deck at 123 Main St, 94103",
              "session_id": "contractor-42-session-1"   # optional
            }

        AgentCore Memory is used to persist and recall prior turns for the
        same session_id, so a contractor can come back a day later and
        continue the same permit conversation without repeating context.
        """
        prompt = payload.get("prompt", "")
        session_id = payload.get("session_id") or str(uuid.uuid4())

        memory = _get_memory_client()
        memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "compliance-scout-memory")

        # Retrieve prior conversation turns for this contractor/session from
        # AgentCore Memory, so multi-step interactions (e.g. "continue
        # drafting that deck permit") persist across separate invocations
        # of this otherwise-stateless runtime. get_last_k_turns already
        # groups raw events into USER/ASSISTANT turns for us.
        try:
            prior_turns = memory.get_last_k_turns(
                memory_id=memory_id,
                actor_id=session_id,
                session_id=session_id,
                k=10,
            )
        except Exception as exc:  # noqa: BLE001 - memory is best-effort
            logger.warning("agentcore_memory_read_failed error=%s", exc)
            prior_turns = []

        scout = build_agent(session_id=session_id)

        # Hydrate agent conversation history from memory before answering.
        for turn in prior_turns:
            for message in turn:
                role = message.get("role", "USER")
                content = message.get("content", {}).get("text", "")
                if content:
                    scout.messages.append(
                        {"role": role.lower(), "content": [{"text": content}]}
                    )

        result = scout(prompt)
        response_text = str(result)

        # Persist this turn to AgentCore Memory for future invocations.
        try:
            memory.create_event(
                memory_id=memory_id,
                actor_id=session_id,
                session_id=session_id,
                messages=[(prompt, "USER"), (response_text, "ASSISTANT")],
            )
        except Exception as exc:  # noqa: BLE001 - memory is best-effort
            logger.warning("agentcore_memory_write_failed error=%s", exc)

        return {
            "session_id": session_id,
            "response": response_text,
        }

    _AGENTCORE_AVAILABLE = True

except ImportError:  # pragma: no cover - allows local dev without the SDK
    _AGENTCORE_AVAILABLE = False
    app = None
    logger.info(
        "bedrock_agentcore SDK not installed; AgentCore entrypoint disabled "
        "(fine for local/offline testing, required for `agentcore launch`)."
    )


# ---------------------------------------------------------------------------
# Safe local runner
# ---------------------------------------------------------------------------
def run_local_cli() -> None:
    """Interactive terminal loop for local testing, no AgentCore required.

    Requires valid AWS credentials with Bedrock model-invoke permissions
    in the target region. Type 'exit' or Ctrl-D to quit.
    """
    print("ComplianceScout (local mode) - type 'exit' to quit.\n")
    session_id = f"local-{uuid.uuid4().hex[:8]}"
    scout = build_agent(session_id=session_id)

    while True:
        try:
            user_input = input("Contractor> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting ComplianceScout.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Exiting ComplianceScout.")
            break

        try:
            result = scout(user_input)
            print(f"\nComplianceScout> {result}\n")
        except Exception as exc:  # noqa: BLE001 - surface errors, don't crash loop
            logger.exception("agent_invocation_failed")
            print(f"\n[error] ComplianceScout hit an issue: {exc}\n")


def run_smoke_test() -> None:
    """Non-interactive smoke test that exercises both tools directly.

    Useful in CI or a sandbox without Bedrock credentials configured -
    it calls the tool functions directly rather than through the LLM.
    """
    print("Running ComplianceScout offline smoke test (tools only)...\n")

    code_result = search_building_codes(zip_code="94103", query="deck")
    print("search_building_codes ->\n", code_result, "\n")

    permit_result = draft_permit_application(
        project_type="deck_construction",
        specs={
            "address": "123 Main St, San Francisco, CA",
            "zip_code": "94103",
            "square_footage": 168,
            "contractor_license": "CA-B-123456",
            "estimated_cost": 8500,
            "description": "12x14 ft attached rear deck, 34 inches above grade.",
            "compliance_notes": ["Guardrail required per SFBC R312.1"],
        },
    )
    print("draft_permit_application ->\n", permit_result, "\n")
    print("Smoke test complete. Tools are wired correctly.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ComplianceScout locally.")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Serve the AgentCore-compatible HTTP app (used by the Dockerfile).",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run an offline tool smoke test with no AWS credentials required.",
    )
    args = parser.parse_args()

    if args.serve:
        if not _AGENTCORE_AVAILABLE:
            logger.error(
                "Cannot --serve: bedrock_agentcore SDK is not installed. "
                "Run `pip install -r requirements.txt`."
            )
            sys.exit(1)
        # BedrockAgentCoreApp.run() starts the HTTP server AgentCore
        # Runtime expects (0.0.0.0:8080, /invocations, /ping).
        app.run()
    elif args.smoke_test:
        run_smoke_test()
    else:
        run_local_cli()


if __name__ == "__main__":
    main()
