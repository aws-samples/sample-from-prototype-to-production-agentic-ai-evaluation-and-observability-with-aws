# Dockerfile for Product Catalog Agent - AgentCore Runtime
# ARM64 architecture required by AgentCore Runtime

FROM --platform=linux/arm64 python:3.11-slim

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY product_catalog_agent.py /app/agent.py

# Create non-root user for security
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

# AgentCore Runtime expects the server on port 8080
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run with OpenTelemetry instrumentation for observability
CMD ["opentelemetry-instrument", "python", "-m", "agent"]
