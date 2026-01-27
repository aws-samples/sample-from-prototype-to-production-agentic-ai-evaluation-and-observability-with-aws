# Dockerfile for AgentCore Runtime agents with OTEL observability
# This Dockerfile uses opentelemetry-instrument to automatically instrument the agent

FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
ARG AGENT_FILE=product_agent.py
COPY ${AGENT_FILE} agent.py

# Expose port 8080 (AgentCore Runtime default)
EXPOSE 8080

# Use opentelemetry-instrument to wrap the Python execution
# This automatically enables OTEL tracing for CloudWatch GenAI Observability
CMD ["opentelemetry-instrument", "python", "agent.py"]
