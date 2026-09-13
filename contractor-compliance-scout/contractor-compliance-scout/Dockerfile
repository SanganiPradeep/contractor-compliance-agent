# ---------------------------------------------------------------------------
# ComplianceScout - Agents for Humans Hackathon (Professional Agents track)
#
# This image is built to run standalone (docker run) AND to be pushed to ECR
# for deployment behind Amazon Bedrock AgentCore Runtime, which expects an
# HTTP server exposing POST /invocations and GET /ping on port 8080.
# ---------------------------------------------------------------------------
FROM public.ecr.aws/docker/library/python:3.11-slim AS base

# AgentCore Runtime executes on linux/arm64 by default - build multi-arch if
# you plan to run locally on a different architecture:
#   docker buildx build --platform linux/arm64 -t contractor-compliance-scout .
ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System deps kept minimal for a small, fast-starting image
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/
COPY tools/ ./tools/
COPY agentcore.json ./agentcore.json
COPY README.md ./README.md

# Non-root user for production hardening
RUN useradd --create-home --shell /bin/bash scout \
    && chown -R scout:scout /app
USER scout

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AWS_REGION=us-east-1 \
    LOG_LEVEL=INFO \
    OTEL_SERVICE_NAME=contractor-compliance-scout

EXPOSE 8080

# Health check hits the AgentCore-style /ping endpoint exposed by
# BedrockAgentCoreApp inside agent/compliance_agent.py
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# When running under AgentCore Runtime, `agentcore launch` builds this same
# Dockerfile and drives the entrypoint below automatically.
CMD ["python", "-m", "agent.compliance_agent", "--serve"]
