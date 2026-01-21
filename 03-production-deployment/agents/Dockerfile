# Dockerfile for AgentCore Runtime agents
# ARM64 architecture required by AgentCore Runtime

FROM --platform=linux/arm64 python:3.11-slim

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code (will be overridden by build arg)
ARG AGENT_FILE=order_agent.py
COPY ${AGENT_FILE} /app/agent.py

# AgentCore Runtime expects the server on port 8080
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the agent with uvicorn
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]
