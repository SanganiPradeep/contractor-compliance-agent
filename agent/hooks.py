"""
agent/hooks.py
--------------------------------------------------------------------------
Strands hook provider for ComplianceScout.

Strands' hook system lets you observe (and, if needed, react to) lifecycle
events in the agentic loop without modifying the Agent or tool code
itself. We use it here for two production-readiness requirements called
out by the hackathon rubric:

  1. Transparent decision tracing - every model invocation and tool call
     is logged with enough structure (timing, args, truncated output) to
     reconstruct *why* the agent did what it did, independent of the
     model's own natural-language narration.
  2. A hook point to bridge into Amazon Bedrock AgentCore Observability:
     each event is also emitted as an OpenTelemetry span so it shows up in
     the AgentCore Observability console (CloudWatch GenAI Observability)
     once deployed, in addition to local structured logs.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import logging
import time
from typing import Any

from strands.hooks import (
    AfterInvocationEvent,
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
    MessageAddedEvent,
)

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("contractor-compliance-scout")
    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - OTEL is optional at runtime
    _OTEL_AVAILABLE = False
    _tracer = None

logger = logging.getLogger("compliance_scout.agent")


def _truncate(value: Any, limit: int = 400) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


class ComplianceTraceHooks(HookProvider):
    """Logs and emits OpenTelemetry spans for every model call and tool call.

    Registering this with the Agent (`hooks=[ComplianceTraceHooks()]`)
    gives auditors and the AgentCore Observability dashboard a full trail
    of: what the agent decided to do, which tool it called with which
    arguments, how long each step took, and what came back - which is
    exactly the "flag blockers, ping humans" audit trail a compliance
    tool needs to be trustworthy.
    """

    def __init__(self) -> None:
        self._invocation_start: float | None = None

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeInvocationEvent, self.on_before_invocation)
        registry.add_callback(AfterInvocationEvent, self.on_after_invocation)
        registry.add_callback(BeforeToolCallEvent, self.on_before_tool)
        registry.add_callback(AfterToolCallEvent, self.on_after_tool)
        registry.add_callback(MessageAddedEvent, self.on_message_added)

    # -- Model invocation lifecycle -----------------------------------
    def on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        self._invocation_start = time.perf_counter()
        logger.info("agent_loop_start agent=%s", event.agent.name)
        if _OTEL_AVAILABLE:
            with _tracer.start_as_current_span("compliance_scout.agent_loop") as span:
                span.set_attribute("agent.name", event.agent.name)

    def on_after_invocation(self, event: AfterInvocationEvent) -> None:
        elapsed_ms = None
        if self._invocation_start is not None:
            elapsed_ms = round((time.perf_counter() - self._invocation_start) * 1000, 2)
        logger.info("agent_loop_end agent=%s latency_ms=%s", event.agent.name, elapsed_ms)
        if _OTEL_AVAILABLE:
            with _tracer.start_as_current_span("compliance_scout.agent_loop.complete") as span:
                if elapsed_ms is not None:
                    span.set_attribute("latency_ms", elapsed_ms)

    # -- Tool invocation lifecycle --------------------------------------
    def on_before_tool(self, event: BeforeToolCallEvent) -> None:
        tool_name = event.tool_use.get("name", "unknown_tool")
        tool_input = event.tool_use.get("input", {})
        logger.info(
            "tool_invocation_start tool=%s args=%s",
            tool_name,
            _truncate(tool_input),
        )
        if _OTEL_AVAILABLE:
            with _tracer.start_as_current_span(f"compliance_scout.tool.{tool_name}") as span:
                span.set_attribute("tool.name", tool_name)
                span.set_attribute("tool.input", _truncate(tool_input))

    def on_after_tool(self, event: AfterToolCallEvent) -> None:
        tool_name = event.tool_use.get("name", "unknown_tool")
        status = event.result.get("status") if event.result else None
        latency_ms = round(event.duration * 1000, 2) if event.duration is not None else None
        logger.info(
            "tool_invocation_end tool=%s status=%s latency_ms=%s result=%s exception=%s",
            tool_name,
            status,
            latency_ms,
            _truncate(event.result),
            event.exception,
        )
        if _OTEL_AVAILABLE:
            with _tracer.start_as_current_span(f"compliance_scout.tool.{tool_name}.complete") as span:
                span.set_attribute("tool.name", tool_name)
                span.set_attribute("tool.status", str(status))
                if latency_ms is not None:
                    span.set_attribute("latency_ms", latency_ms)

    # -- Conversation trace ----------------------------------------------
    def on_message_added(self, event: MessageAddedEvent) -> None:
        role = event.message.get("role", "unknown")
        logger.debug("message_added role=%s", role)
