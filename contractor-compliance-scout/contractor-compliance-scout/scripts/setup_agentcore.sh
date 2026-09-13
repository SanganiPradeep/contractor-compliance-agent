#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/setup_agentcore.sh
#
# Configures and deploys ComplianceScout to Amazon Bedrock AgentCore Runtime
# using the `agentcore` CLI (from bedrock-agentcore-starter-toolkit), driven
# by the declarative settings in agentcore.json.
#
# Usage:
#   ./scripts/setup_agentcore.sh configure   # one-time: register the agent
#   ./scripts/setup_agentcore.sh deploy      # build + deploy to AWS
#   ./scripts/setup_agentcore.sh deploy-local  # run the container locally
#   ./scripts/setup_agentcore.sh invoke '{"prompt": "..."}'
#   ./scripts/setup_agentcore.sh memory-create  # create the AgentCore Memory
#
# Requires: `agentcore` CLI on PATH (pip install -r requirements.txt),
# AWS credentials with Bedrock + AgentCore permissions, and `jq`.
# ---------------------------------------------------------------------------
set -euo pipefail

CONFIG_FILE="$(dirname "$0")/../agentcore.json"
cd "$(dirname "$0")/.."

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required (brew install jq / apt-get install jq)." >&2
  exit 1
fi

PROJECT_NAME=$(jq -r '.project_name' "$CONFIG_FILE")
ENTRYPOINT=$(jq -r '.runtime.entrypoint' "$CONFIG_FILE")
REGION=$(jq -r '.runtime.region' "$CONFIG_FILE")
REQUIREMENTS_FILE=$(jq -r '.runtime.requirements_file' "$CONFIG_FILE")
PROTOCOL=$(jq -r '.runtime.protocol' "$CONFIG_FILE")
MEMORY_NAME=$(jq -r '.memory.memory_name' "$CONFIG_FILE")

cmd="${1:-}"
shift || true

case "$cmd" in
  configure)
    echo "==> Registering ${PROJECT_NAME} with AgentCore (region: ${REGION})"
    agentcore configure \
      --create \
      --entrypoint "${ENTRYPOINT}" \
      --name "${PROJECT_NAME}" \
      --requirements-file "${REQUIREMENTS_FILE}" \
      --protocol "${PROTOCOL}" \
      --region "${REGION}" \
      --non-interactive
    ;;

  memory-create)
    echo "==> Creating AgentCore Memory resource: ${MEMORY_NAME}"
    agentcore memory create "${MEMORY_NAME}" \
      --region "${REGION}" \
      --description "Session + summary memory for contractor permit conversations" \
      --strategies '[{"summaryMemoryStrategy": {"name": "ComplianceSummaries"}}]' \
      --wait
    echo "Copy the returned memoryId into AGENTCORE_MEMORY_ID (.env / agentcore.json)."
    ;;

  deploy)
    echo "==> Deploying ${PROJECT_NAME} to Bedrock AgentCore Runtime (cloud build)"
    agentcore deploy --agent "${PROJECT_NAME}"
    ;;

  deploy-local)
    echo "==> Building and running ${PROJECT_NAME} locally via AgentCore"
    agentcore deploy --agent "${PROJECT_NAME}" --local
    ;;

  invoke)
    payload="${1:-'{"prompt": "I want to add a 12x14 deck at 123 Main St, zip 94103"}'}"
    echo "==> Invoking ${PROJECT_NAME} with payload: ${payload}"
    agentcore invoke --agent "${PROJECT_NAME}" "${payload}"
    ;;

  status)
    agentcore status --agent "${PROJECT_NAME}"
    ;;

  *)
    echo "Usage: $0 {configure|memory-create|deploy|deploy-local|invoke|status}"
    exit 1
    ;;
esac
