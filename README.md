# Artefact Music Emporium - Case Study

Customer-service agent prototype for the fictional "Empório da Música Instrumentos Musicais Ltda." — a musical instrument store.

## Documentation

- [Requirements](./docs/REQUIREMENTS.md) - functional and non-functional requirements.
- [Architecture](./docs/ARCHITECTURE.md) — central architecture reference (design, decisions, trade-offs).
- [Open Questions](./docs/OPEN_QUESTIONS.md) — unresolved design decisions.
- [Examples](./examples/) — sample conversations (policy, orders, catalog, returns, out-of-scope).

## Overview

The agent answers recurring customer-service questions for a musical-instrument store: business hours, order status, product price and availability, promotions, payments, shipping, returns, warranty, and privacy. It combines two data sources per turn:

- **Structured operational data** (`products`, `customers`, `orders`, `order_items`, `promotions`, `categories`) exposed to the agent as read-only, typed tools through a dedicated **MCP server**.
- **Unstructured policy data** (`políticas_da_loja.pdf`) chunked by section, embedded with **BGE-M3**, and retrieved from **pgvector** via cosine similarity.

The agent is a **LangGraph ReAct loop**: it decides whether to answer directly, retrieve a policy, call one tool, or call several tools in the same turn. A **LiteLLM** gateway selects the generation model: the recommended default is the hosted `anthropic/claude-haiku-4-5` model (enable it by setting an API key), and the local `ollama/qwen3.5:4b` is the automatic no-key fallback. **Ollama** is always the local runtime for generation fallback and embeddings.

The stack runs behind `docker compose`: `db` (Postgres + pgvector), `ollama`, `ollama-pull` and `ollama-warmup` (one-shot model download and preload), `ingest` (one-shot data materialization), `mcp` (operational-data tools), `backend` (FastAPI agent runtime), and `frontend` (Chainlit chat UI). See [ARCHITECTURE.md](./docs/ARCHITECTURE.md) for details.

## Requirements

- Docker and Docker Compose (v2, invoked as `docker compose`). This is the only supported way to run the full stack. Everything, including Ollama, runs in containers.

For local development of the Python code you additionally need `uv`; see [Local development](#local-development).

## Quick start (Docker)

1. Build and start the whole stack:

   ```bash
   docker compose up --build
   ```

   On the first run the `ollama-pull` service downloads `bge-m3` and `qwen3.5:4b`, `ollama-warmup` preloads them into memory (so the first message is not slowed by a cold start), and `ingest` materializes the CSVs and embeds the policy PDF. This can take several minutes depending on network and hardware. Subsequent runs reuse the `ollama_data` and `db_data` volumes.

2. Open the chat UI at <http://localhost:8001>.

3. The UI signs in automatically as a local admin (identifier `admin`; override with `CHAINLIT_ADMIN_USER`). No password is required. The login is what lets Chainlit persist and resume conversations.

4. In the left sidebar, choose a **Cliente (simulação)**, a **Modelo**, a **Raciocínio** mode, and optionally enable **Modo debug**, then chat. Selecting a new customer or model starts a **fresh conversation**: the current thread is cleared and the new customer is greeted. Changing **Raciocínio** or **Modo debug** applies to the next message without restarting the conversation. Previous conversations appear in the sidebar and can be resumed; reloading the page keeps the current session.

   **Raciocínio** controls the local model's thinking phase per request and is off by default (`Desligado (rápido)`). Enabling it (`Ligado (reflexivo)`) improves tool selection and grounding but is slower on CPU; it does not restart or reload the Ollama model.

   **Modo debug** is on by default so the agent's reasoning is transparent during testing. When enabled, the UI shows the agent's status (`Pensando...`, `Consultando os dados...`) while it works, then each tool call with its arguments and returned result as collapsible steps; the transient status step disappears as soon as the answer starts streaming. Set `SHOW_AGENT_STEPS=false` to make it default to off.

The backend API is exposed at <http://localhost:8000> (`/docs` for OpenAPI). The MCP server is internal-only on the compose network.

> Use `docker compose` (the v2 plugin), not the legacy `docker-compose` v1 binary, which does not support the Compose specification used here.

> Tip: to reuse an Ollama already running on the host instead of the container, set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in a `.env` file and start only the other services (`docker compose up db ingest mcp backend frontend`). You are then responsible for pulling `bge-m3` and `qwen3.5:4b` on the host.

## Stopping and restarting

Stop and remove the containers (volumes with downloaded models, database data, and saved conversations are kept):

```bash
docker compose down
```

Add `-v` (`docker compose down -v`) only when you also want to delete the `db_data` and `ollama_data` volumes; this erases the database and forces the models to be downloaded again on the next start.

Restart with the same configuration:

```bash
docker compose up -d
```

After changing any value in `.env`, recreate the affected service so it picks up the new environment, then refresh the browser:

```bash
docker compose up -d --force-recreate backend frontend
```

Use `docker compose up --build` after changing Python dependencies (`pyproject.toml`/`uv.lock`) or the `Dockerfile`.

## Enabling hosted models (Anthropic)

The recommended default model is hosted `claude-haiku-4-5`. To use it:

1. Copy the example environment file if you have not already: `cp .env.example .env`.
2. Set your key in `.env`, e.g. `ANTHROPIC_API_KEY=sk-ant-...`. Optionally adjust `ANTHROPIC_MODELS`.
3. Recreate the backend (and frontend) so the new environment is read, then refresh the browser:

   ```bash
   docker compose up -d --force-recreate backend frontend
   ```

With a key set, `claude-haiku-4-5` is the default model and the Anthropic models appear in the **Modelo** selector. Without a key, the backend falls back to the first `OLLAMA_MODEL_ALLOWLIST` model (`ollama/qwen3.5:4b`) so the stack still runs out of the box.

## Local development

This runs the Python services from the repository against a containerized Postgres and a host or containerized Ollama. `uv` manages the virtual environment and dependencies; do not install packages into the system Python.

```bash
# 1. Install dependencies (creates a project venv)
uv sync

# 2. Start Postgres, then pull the models on your Ollama and materialize the data
docker compose up -d db
ollama pull bge-m3
ollama pull qwen3.5:4b
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

# 4. Run the frontend on port 8001 (the backend already uses 8000)
BACKEND_URL=http://localhost:8000 \
CHAINLIT_DB_URL=postgresql+asyncpg://emporium:emporium@localhost:5433/emporium \
  uv run chainlit run services/frontend/app.py --port 8001
```

The frontend listens on `8001` to avoid clashing with the backend on `8000`. `SHOW_AGENT_STEPS` defaults to `true`, making the **Modo debug** setting enabled out of the box (a developer aid); set it to `false` to hide the debug steps by default.

## Configuration

Configuration is read from environment variables (or a `.env` file). See [`.env.example`](./.env.example) for the full list. The most important:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://emporium:emporium@db:5432/emporium` | Backend/ingestion database |
| `MCP_DATABASE_URL` | (falls back to `DATABASE_URL`) | Read-only DB for the MCP server |
| `MCP_URL` | `http://mcp:8000/mcp` | MCP server endpoint |
| `MCP_SHARED_SECRET` | `change-me-in-production` | HMAC secret for customer context |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama runtime |
| `EMBEDDING_MODEL` | `bge-m3` | Embedding model (1024-dim) |
| `OLLAMA_NUM_CTX` | `4096` | Context window for the local generation model |
| `OLLAMA_REASONING` | `false` | Default thinking mode for local models: `false` (direct, faster), `true`, `low`/`medium`/`high`, or `none` (model default). Overridable per request from the **Raciocínio** setting |
| `OLLAMA_NUM_PREDICT` | `512` | Upper bound on generated tokens for the local model |
| `DEFAULT_MODEL` | `anthropic/claude-haiku-4-5` | Recommended generation model (hosted). Falls back to the first `OLLAMA_MODEL_ALLOWLIST` entry when no API key is set |
| `OLLAMA_MODEL_ALLOWLIST` | `ollama/qwen3.5:4b` | Local models selectable in the UI and used as the no-key fallback |
| `ANTHROPIC_API_KEY` | (empty) | Enables the Anthropic models below when set |
| `ANTHROPIC_MODELS` | `anthropic/claude-haiku-4-5,anthropic/claude-sonnet-5-5` | Hosted models shown once a key is set |
| `POLICY_SIMILARITY_THRESHOLD` | `0.5` | Minimum cosine similarity for retrieval |
| `SHOW_AGENT_STEPS` | `true` | Default state of the **Modo debug** chat setting |
| `CHAINLIT_DB_URL` | (empty) | Enables thread persistence/resume when set (async SQLAlchemy URL) |
| `CHAINLIT_ADMIN_USER` | `admin` | Identifier used for the automatic local admin sign-in |
| `CHAINLIT_AUTH_SECRET` | `change-me-in-production` | Secret used to sign UI session cookies |

Hosted providers are optional. Setting `ANTHROPIC_API_KEY` adds the configured `ANTHROPIC_MODELS` to the model selector; without a key only local Ollama models are offered. LiteLLM routes `anthropic/*` models through the key.

## Running tests

```bash
# against a running stack (db + ollama required)
docker compose run --rm --profile test test
```

The suite covers CSV ingestion idempotency, referential integrity, customer-scoped tool isolation (no cross-customer leakage), promotion filtering, and policy retrieval.

## Known limitations

- The customer selector is an **admin simulation**, not authentication of the end customer. The UI signs in automatically as a local admin (no password) purely so conversations can be persisted and resumed.
- Complaint registration and human handoff are not wired to a ticketing system; the agent acknowledges complaints and points to human follow-up.
- Raw CSV data may contain contradictions (e.g. order totals vs. item sums); they are preserved, never silently reconciled.
- Prompt-injection defense is lightweight (hardened prompt + read-only tool allowlist + scope guardrails), not a dedicated classifier.
- The MCP server enforces read-only access in code and via a read-only DB role; it is reachable only on the internal compose network.
- Thread persistence uses Chainlit's own tables in the same Postgres database; deleting the `db_data` volume resets both operational data and saved conversations.
- The container uses Python 3.12. Python 3.14 is not usable with Chainlit 2.12: Chainlit calls `nest_asyncio.apply()` and `nest-asyncio` 1.6.0 (unmaintained) breaks `asyncio.current_task()` on 3.14, which makes `anyio.to_thread` fail and prevents the UI's static assets from loading (blank page).
- The no-key local fallback model `qwen3.5:4b` is a *thinking* model; its reasoning phase is disabled by default (`OLLAMA_REASONING=false`) so it answers directly and stays responsive on CPU. It is weaker than the hosted default at tool selection and grounding; re-enabling reasoning improves it but is significantly slower without a GPU.
- Stock is exposed to the agent only as an `in_stock` boolean; exact stock quantities are never returned to the model, so they cannot reach the customer.
- Caching, compression, response validation, and retrieval reranking are deferred extensions.
- The answer is streamed token-by-token exactly as the model emits it (no buffering or rollback), so a model that narrates its plan before calling a tool can show that narration as a leading line in the answer. This is mitigated by the system prompt ("não anuncie que vai usar uma ferramenta") rather than by restructuring the streaming flow.

## Assumptions

- Customer identity: The admin selector can choose one of the customer profiles to use on a testing session. This enables testing that personal customer data is not shared between sessions of different customers, since tools are integrated exclusively using the customer id of the session. A production deployment would require authentication and authorization instead of this trusted admin simulation.
- WhatsApp Numbers: The policy manual lists two different numbers. The number in the company contact block, `(67) 3341-4444`, is treated as the operational company contact. The number in the customer-service section, `(67) 3321-4500`, is treated as the customer-service WhatsApp contact.
- CSV Inconsistencies: CSV content is preserved without correction, even if the source may contain product name/description or specification conflicts and order totals that differ from the sum of order items. These issues are noted but considered out-of-scope for this project, and the agent must not silently invent a reconciliation.
- Signed MCP context: The backend binds the session customer to every MCP call through an HMAC-signed bearer token (`Authorization`) verified by the MCP server. This is the "signed transport mechanism" of the architecture. The MCP server rejects requests without a valid token.
- Fixture customers: The frontend shows a hardcoded list of all 50 fixture customers (there is no customer-listing endpoint). The backend validates the selected `customer_id` against the `customers` table before creating a session.

## Decision rationale

- ReAct instead of intent branches: A fixed policy-versus-database router cannot reliably answer mixed questions. The agent therefore decides whether to answer, retrieve policy, call one tool, or call several tools. An iteration limit protects latency and cost without removing the multi-tool behavior required by `NFR9`.
- Server-bound customer context: Removing customer IDs from tool schemas is stronger than relying on prompts or guardrails. The backend resolves the customer once and the tools use only that trusted context. The local admin selector is for testing by assuming customer identities.
- Policy retrieval: The complete policy manual is ingested uniformly as a RAG source, with no special preprocessing. Persona, tone, scope, lookup rules, escalation, and other behavioral directives are written manually into the versioned system prompt, not extracted from the PDF. The retriever is exposed to the agent as a single `search_knowledge` tool covering any factual store information (address, contact, hours, payments, returns, delivery, promotions, guarantees, privacy). The retriever is designed to rank factual sections above behavioral ones. A preprocessing split will only be reconsidered if testing shows behavioral sections are being surfaced.
- Customer tools: Customer-scoped tools use the session-bound customer internally. `get_customer()` has no parameters, and `get_customer_last_orders(n)` is capped at 10 orders. The agent cannot request another customer's record or provide an order ID to bypass the customer boundary.
- Catalog tool handles: Categories are addressed by name (short and unambiguous), while products are addressed by `product_id`. Catalog product names are long and repetitive (e.g. `Yamaha C40 Nylon Natural`), so a numeric id is a more reliable handle for the follow-up `get_product` call than asking the model to reproduce an exact name. The id appears only in tool results, never as a user-facing value; `status` and `stock_quantity` stay hidden.
- Price ordering and filtering: `list_products_by_category` returns products ordered by price descending, backed by an index on `(category_id, price_brl)`. Both it and `search_products` accept a `max_price` (list-price upper bound) so the agent can answer price-range questions directly, and are paginated (default 30 per page, with a `total` count) so the agent can page through a category instead of only seeing the most expensive items. The trade-off is that `max_price` filters on the list price, not the post-promotion price.
- Model providers: The project is hybrid. The recommended default is the hosted `anthropic/claude-haiku-4-5` model for reliable tool selection and PT-BR grounding; the local `ollama/qwen3.5:4b` is the automatic no-key fallback (`effective_default_model`). Hosted Anthropic models are exposed through LiteLLM only when an API key is configured. A production system would need provider privacy, PII, retention, consent, and contractual controls.
- Customer-name grounding: The backend appends the session customer's first name to the system prompt at request time so the model can address the customer by name without an extra tool call. Only the first name is injected (least privilege); the full profile remains behind the customer-scoped `get_customer` tool.
- Debug tool panes: Each tool call renders as a single collapsible step with PT-BR `Entrada`/`Resultado` labels (the arguments and the returned result), instead of relying on Chainlit's built-in input/output rendering, which cannot be labeled in Portuguese. `search_knowledge` keeps returning prose for model grounding; the debug pane wraps it in a labeled text block rather than changing the model-facing output.
- `get_product` handle: `get_product` accepts a numeric `product_id` and its description explicitly warns the model to use the `product_id` from a prior catalog result and never the `total`/`page`/`limit` numbers, which the local model otherwise confuses with the product id.

## Future

- Caching and semantic caching.
- Chat compression. The complete raw transcript is always persisted; any future compressed context is temporary and is never persisted.
- Response validation.
- Retrieval reranking.
