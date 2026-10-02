# Artefact Music Emporium - Case Study

Customer-service agent prototype for the fictional "Empório da Música
Instrumentos Musicais Ltda." — a musical instrument store.

## Documentation

- [Requirements](./docs/REQUIREMENTS.md) - functional and non-functional requirements.
- [Architecture](./docs/ARCHITECTURE.md) — central architecture reference
  (design, decisions, trade-offs).
- [Open Questions](./docs/OPEN_QUESTIONS.md) — unresolved design decisions.
- [Examples](./examples/) — sample conversations (policy, orders, catalog,
  returns, out-of-scope).

## Overview

The agent answers recurring customer-service questions for a musical-instrument
store: business hours, order status, product price and availability, promotions,
payments, shipping, returns, warranty, and privacy. It combines two data sources
per turn:

- **Structured operational data** (`products`, `customers`, `orders`,
  `order_items`, `promotions`, `categories`) exposed to the agent as read-only,
  typed tools through a dedicated **MCP server**.
- **Unstructured policy data** (`políticas_da_loja.pdf`) chunked by section,
  embedded with **BGE-M3**, and retrieved from **pgvector** via cosine
  similarity.

The agent is a **LangGraph ReAct loop**: it decides whether to answer directly,
retrieve a policy, call one tool, or call several tools in the same turn. A
**LiteLLM** gateway selects the generation model (default `ollama/qwen3.5:9b`);
**Ollama** is always the local runtime for generation and embeddings.

Five containerized services run behind `docker compose`: `db` (Postgres +
pgvector), `ollama`, `ingest` (one-shot data materialization), `mcp`
(operational-data tools), `backend` (FastAPI agent runtime), and `frontend`
(Chainlit chat UI). See [ARCHITECTURE.md](./docs/ARCHITECTURE.md) for details.

## Requirements

- Docker and Docker Compose (for the all-in-one stack), or
- `uv` and a local Ollama (for local development).

## Quick start (Docker)

1. Pull the models and build/start the stack:

   ```bash
   docker compose up --build
   ```

   On first run the `ollama-pull` service downloads `bge-m3` and
   `qwen3.5:9b`, and `ingest` materializes the CSVs and embeds the policy PDF.
   This can take several minutes depending on network and hardware.

2. Open the chat UI at <http://localhost:8001>.

3. Use the gear icon to pick a **Cliente (simulação)** and a **Modelo**, then
   chat. Selecting a new customer or model starts a new conversation session.

The backend API is exposed at <http://localhost:8000> (`/docs` for OpenAPI).

> Tip: to reuse an Ollama already running on the host instead of the container,
> set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in a `.env` file and
> start only the other services (`docker compose up db ingest mcp backend frontend`).

## Local development

```bash
# 1. Install dependencies (creates a project venv)
uv sync

# 2. Start Postgres + Ollama (host), then materialize the data
docker compose up -d db
ollama pull bge-m3 qwen3.5:9b
DATABASE_URL=postgresql+asyncpg://emporium:emporium@localhost:5433/emporium \
OLLAMA_BASE_URL=http://localhost:11434 \
  uv run python -m emporium.ingest

# 3. Run the MCP server and backend (separate terminals)
MCP_PORT=8002 MCP_DATABASE_URL=postgresql+asyncpg://readonly:readonly@localhost:5433/emporium \
  uv run python -m emporium.tools.mcp_server
DATABASE_URL=postgresql+asyncpg://emporium:emporium@localhost:5433/emporium \
MCP_URL=http://localhost:8002/mcp \
OLLAMA_BASE_URL=http://localhost:11434 \
  uv run uvicorn emporium.api.app:app --reload --port 8000

# 4. Run the frontend
BACKEND_URL=http://localhost:8000 uv run chainlit run services/frontend/app.py
```

## Configuration

Configuration is read from environment variables (or a `.env` file). See
[`.env.example`](./.env.example) for the full list. The most important:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://emporium:emporium@db:5432/emporium` | Backend/ingestion database |
| `MCP_DATABASE_URL` | (falls back to `DATABASE_URL`) | Read-only DB for the MCP server |
| `MCP_URL` | `http://mcp:8000/mcp` | MCP server endpoint |
| `MCP_SHARED_SECRET` | `change-me-in-production` | HMAC secret for customer context |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama runtime |
| `EMBEDDING_MODEL` | `bge-m3` | Embedding model (1024-dim) |
| `DEFAULT_MODEL` | `ollama/qwen3.5:9b` | Default generation model |
| `MODEL_ALLOWLIST` | `ollama/qwen3.5:9b,ollama/llama3.2` | Models selectable in the UI |
| `POLICY_SIMILARITY_THRESHOLD` | `0.5` | Minimum cosine similarity for retrieval |

Hosted providers can be added to the allowlist (e.g. `openai/gpt-4o-mini` or
`anthropic/claude-...`); LiteLLM routes those through the corresponding provider
API key.

## Running tests

```bash
# against a running stack (db + ollama required)
docker compose run --rm --profile test test
```

The suite covers CSV ingestion idempotency, customer-scoped tool isolation
(no cross-customer leakage), and policy retrieval.

## Known limitations

- The customer selector is an **admin simulation**, not authentication.
- Complaint registration and human handoff are not wired to a ticketing system;
  the agent acknowledges complaints and points to human follow-up.
- Raw CSV data may contain contradictions (e.g. order totals vs. item sums);
  they are preserved, never silently reconciled.
- Prompt-injection defense is lightweight (hardened prompt + read-only tool
  allowlist + scope guardrails), not a dedicated classifier.
- The MCP server enforces read-only access in code and via a read-only DB role;
  it is reachable only on the internal compose network.
- Caching, compression, response validation, and retrieval reranking are
  deferred extensions.

## Assumptions

- Customer identity: The admin selector can choose one of the customers profiles to use on a testing session. This enables for testing how personal customer data is not shared between sessions of different customers, since tools are integrated exclusively using the customer id of the session. A production deployment would require authentication and authorization instead of this trusted admin simulation.
- WhatsApp Numbers: The policy manual lists two different numbers. The number in the company contact block, `(67) 3341-4444`, is treated as the operational company contact. The number in the customer-service section, `(67) 3321-4500`, is treated as the customer-service WhatsApp contact.

- CSV Inconsistencies: CSVs content are preserved without correction, even if the source may contain product name/description or specification conflicts and order totals that differ from the sum of order items. These issues are noted but considered out-of-scope for this project, and the agent must not silently invent a reconciliation.

- Signed MCP context: The backend binds the session customer to every MCP call through an HMAC-signed bearer token (`Authorization`) verified by the MCP server. This is the "signed transport mechanism" of the architecture. The MCP server rejects requests without a valid token.

- Fixture customers: The frontend shows a hardcoded list of fixture customers (there is no customer-listing endpoint). The backend validates the selected `customer_id` against the `customers` table before creating a session.


## Decision rationale

- ReAct instead of intent branches: A fixed policy-versus-database router cannot reliably answer mixed questions. The agent therefore decides whether to answer, retrieve policy, call one tool, or call several tools. An iteration limit protects latency and cost without removing the multi-tool behavior required by `NFR9`.
- Server-bound customer context: Removing customer IDs from tool schemas is stronger than relying on prompts or guardrails. The backend resolves the customer once and the tools use only that trusted context. The local admin selector is for testing by assuming customer identities.
- Policy retrieval: The complete policy manual is ingested uniformly as a RAG source, with no special preprocessing. Persona, tone, scope, lookup rules, escalation, and other behavioral directives are written manually into the versioned system prompt, not extracted from the PDF. The retriever is designed to rank factual sections (hours, payments, returns, delivery, promotions, guarantees, privacy) above behavioral ones. A preprocessing split will only be reconsidered if testing shows behavioral sections are being surfaced.
- Customer tools: Customer-scoped tools use the session-bound customer internally. `get_customer()` has no parameters, and `get_customer_last_orders(n)` is capped at 10 orders. The agent cannot request another customer's record or provide an order ID to bypass the customer boundary.
- Model providers: The project is hybrid. Ollama is the required local runtime for generation and embeddings, while third-party generation providers are supported through LiteLLM. This is acceptable for the study case, but a production system would need provider privacy, PII, retention, consent, and contractual controls.

## Future
- Caching and semantic caching
- Chat compression
  - The complete raw transcript is always persisted, any future compressed context is temporary and is never persisted.
- Response validation
- Retrieval reranking
