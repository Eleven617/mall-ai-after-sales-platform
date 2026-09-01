FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app ./app
# Build 22 has two repository-local quality suites: CI's deterministic
# contract_mock and the manually started live-model synthetic suite. Both are
# fixtures, never customer data, and must be present in the runtime image.
COPY evals/quality_agent_cases.v1.json ./evals/quality_agent_cases.v1.json
COPY evals/quality_agent_cases.v2.json ./evals/quality_agent_cases.v2.json
COPY evals/live_model_synthetic_cases.v1.json ./evals/live_model_synthetic_cases.v1.json
COPY evals/rag2_golden_cases.v1.json ./evals/rag2_golden_cases.v1.json

# The local embedding weights and generated Chroma index are deliberately not
# image layers or Git content. `scripts/start-demo.ps1` prepares them from the
# committed policy corpus, then Compose mounts them at runtime. This keeps a
# fresh public clone buildable without publishing model weights or local data.

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
