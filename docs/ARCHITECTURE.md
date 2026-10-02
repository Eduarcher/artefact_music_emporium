# Architecture

This document describes the system design of the Artefact Music Emporium customer-service agent: how its components are organized, how they interact, and why each technology was chosen. The requirements that motivate these decisions live in [REQUIREMENTS.md](./REQUIREMENTS.md) and are referenced here by identifier (`FR1`, `NFR4`, and so on). Unresolved decisions are tracked in [OPEN_QUESTIONS.md](./OPEN_QUESTIONS.md).

## 1. Scope

This document covers system design only: component boundaries, the request lifecycle, the data layer, and the technology choices. It does not restate the business problem or the requirements. Trade-offs are called out inline where a decision was made over an alternative.

## 2. System overview

The system is a set of five containerized services behind `docker compose`.

- The **frontend** is a Chainlit application. It contains no agent logic; it renders the chat, forwards user messages to the backend over HTTP, and renders the streamed response. Its only state is presentation-scoped (for example, runtime model selection exposed through the Chainlit settings panel).
- The **backend** is a FastAPI service that owns all intelligence: the LangGraph agent, the RAG pipeline, guardrails, caching, and prompt resolution. It hosts the MCP client that binds the database tools into the agent. It exposes a JSON/SSE API so any client can drive the agent; Chainlit is the reference UI, not a hard dependency.
- The **mcp-server** is the agent's only access path to structured operational data. It exposes read-only tools (product, order, customer, promotion lookups) over the Model Context Protocol and queries Postgres on the backend's behalf.
- **Postgres** (with the pgvector extension) is the single datastore, holding the relational operational data, the vector embeddings of the policy manual, and persisted chat sessions.
- **Ollama** runs the local models used by default for generation and embeddings. When configured, requests can instead route to hosted providers (Claude, OpenAI) through LiteLLM.

## 3. Technology stack

Each choice below records its rationale and, where relevant, the requirement it addresses.

### 3.1 Orchestration — LangGraph

LangGraph models the agent as a state machine: a typed state object, a set of nodes (functions that read and mutate state), and conditional edges that route between nodes. This is the mechanism behind `FR2`. Two capabilities in particular justify the dependency over hand-rolling orchestration:

- **Checkpointing.** Every state transition is persisted through a checkpointer. Keyed by `thread_id` (mapped from our `session_id`), this provides per-session memory (`FR5`) and strict isolation between clients (`NFR3`). We use the Postgres checkpointer so session state lives in the same database as the rest of the system.
- **Tool routing.** The graph binds tools and lets the model decide when to invoke them, feeding results back into the graph — the control loop we would otherwise have to write ourselves.

### 3.2 Model access — LiteLLM

LiteLLM is pinned as the single gateway to every provider. It normalizes the chat-completions interface, so moving between Ollama, Claude, and OpenAI is a configuration change rather than a code change. This is what makes the hybrid strategy inexpensive: the default path is a local Ollama model (no API keys, works offline — `NFR5`), and hosted providers are used only when their keys are present. LiteLLM also surfaces per-call cost metadata, which supports the cost-efficiency requirement.

The trade-off is accepting a large dependency that abstracts away provider specifics; that is acceptable because writing and maintaining per-provider connectors is not worth the effort for this project.

### 3.3 Backend service — FastAPI

FastAPI is the service layer. It runs async (asyncio) end to end, satisfying `NFR2`: the event loop serves concurrent conversations without blocking, and streaming responses use Server-Sent Events. Each request carries a `session_id` that the backend passes to LangGraph as `thread_id`, so client state never crosses conversations (`NFR3`).

### 3.4 Frontend — Chainlit

Chainlit provides the chat UI, streaming rendering, and a settings panel. Runtime model selection is exposed through the settings panel and forwarded to the backend. The frontend is fully decoupled from the backend and communicates only over the HTTP API.

### 3.5 Data storage — Postgres + pgvector, SQLAlchemy

Postgres is the single datastore. Relational tables hold the operational data; the pgvector extension adds the vector type and HNSW index for policy embeddings; and persisted chat sessions live here as well. Consolidating onto one database avoids running a separate vector store (`NFR5`, simpler deployment). SQLAlchemy (async, with asyncpg) is the ORM used for session persistence and for the read-only operational queries exposed by the MCP server (`NFR7`, `NFR8`).

### 3.6 Tool access — MCP

The structured-data tools are exposed through the Model Context Protocol rather than as backend-local functions. A dedicated `mcp-server` service defines the read-only tools (section 4.3) with typed schemas and serves them over Streamable HTTP; the backend hosts the MCP client and binds those tools into the LangGraph graph via the LangChain MCP adapter. This keeps tool definitions self-describing and discoverable, decouples data access from the agent, and makes the MCP server the enforcement point for read-only access (`FR4`, `NFR7`, `NFR8`). The trade-off is an extra service and one more network hop per tool call, which is acceptable at this scale for the clarity and separation it buys.

### 3.7 Guardrails

Two layers bound the agent's behavior: an input guardrail (scope and prompt-injection detection) and an output guardrail (tone, policy compliance, safety). They implement `NFR4`, `NFR7`, and part of `NFR8`, and are detailed in section 4.

### 3.8 Caching

Two caches reduce redundant work: a TTL cache in front of tool results (product/stock/promo lookups) so repeated questions do not re-hit the database (`NFR6`), and an optional semantic answer cache for near-duplicate questions. See section 8.

### 3.9 Prompt versioning

Prompts are plain files under `prompts/<version>/`, loaded by a small registry keyed by an explicit version. This keeps prompt changes reviewable in git without an external tool.

## 4. Agent workflow

This section describes the LangGraph graph in detail.

### 4.1 State

The graph state is a `TypedDict` holding the current message, the resolved `session_id`, the intent classification, retrieved context, tool results, the accumulated (or compressed) message history, and the final response. Only the graph mutates state; nodes are functions of that state.

### 4.2 Nodes and routing

The graph is mostly linear, with one branch:

1. **Input guardrail.** The first node classifies the message as in-scope, out-of-scope, or injection. Out-of-scope and injection short-circuit to a refusal branch that returns a polite, policy-compliant response without touching the database or invoking the full generation model beyond a cheap local classifier (`NFR4`, `NFR7`).
2. **Intent router.** For in-scope messages, a second node classifies intent — policy question, product lookup, order inquiry, promotion, or general. This determines what work is actually needed and prevents unnecessary retrieval or tool calls (`NFR5`, `NFR6`).
3. **Resolve.** Depending on intent, the graph either retrieves policy sections through the RAG pipeline (section 6) or invokes one or more tools (section 4.3). Tool results are cached.
4. **Assemble.** Retrieved context, tool results, the versioned system prompt, and the (possibly compressed) history are assembled into the model call.
5. **Generate.** The model call runs through LiteLLM with the selected provider and model.
6. **Output guardrail.** The generated answer is checked for tone, policy compliance, and safety before being returned; failures trigger a corrective pass.
7. **Persist.** The turn is written to the session store and the response streamed back over SSE.

### 4.3 Tools

Structured-data access is handled by tools, which are defined and served by the `mcp-server` over the Model Context Protocol and consumed by the backend's MCP client. Each tool is a read-only, parameterized SQL query with a typed input schema the model can fill. The set: `get_order_by_id`, `get_orders_by_customer`, `check_stock`, `get_product`, `search_products`, `get_promotions`, `get_customer`. Because the agent can only invoke these whitelisted tools — never issue SQL directly — the MCP server is the enforcement point for read-only access (`NFR7`, `NFR8`). The model receives only the columns needed to answer a question, never raw tables.

## 5. Project structure

```
app/
  agent/     # graph definition, state, nodes, guardrails
  api/       # FastAPI routes, SSE streaming, settings
  mcp/       # MCP client: connects to mcp-server, loads tools into the graph
  db/        # session/chat persistence models
  rag/       # PDF extraction, chunking, embedding, pgvector store, retriever
  llm/       # LiteLLM wrapper, model registry, cost logging
  cache/     # TTL tool cache and answer cache
prompts/     # versioned prompt files
mcp_server/  # MCP server service: read-only operational-data tools (Streamable HTTP)
ingest/      # CLI: seed CSVs and preprocess/chunk/embed the PDF
frontend/    # Chainlit application (separate service)
tests/
examples/
docs/
docker-compose.yml
README.md
```

`app/agent` depends on `app/mcp`, `app/rag`, `app/llm`, and `app/cache`; `app/api` depends only on `app/agent`. `mcp_server` is a separate service with its own access to Postgres and no dependency on the backend.

## 6. RAG pipeline

The policy manual is the retrieval target. The pipeline has four stages: extraction and preprocessing, chunking, embedding and indexing, and retrieval.

**Extraction and preprocessing.** Text is extracted from the PDF and normalized. Preprocessing is where editorial decisions are applied before anything is embedded, so the model never sees content we have decided is out of scope. Concretely, the ingest job drops the duplicate WhatsApp number (keeping the one in the company contact block; this assumption is documented in the README) and removes the directives about customer-service tone, which describe how *staff* should behave and would otherwise leak into answers as policy. Running this at ingest time — once, rather than at query time — keeps the stored chunks clean.

**Chunking.** The manual is organized into numbered sections and sub-sections, so chunks follow those boundaries (header-aware splitting) rather than fixed token windows. Each chunk carries metadata — section number and title — used later for filtering and for citing the source in the answer.

**Embedding and indexing.** Chunks are embedded with the local embedding model by default (nomic-embed-text, 768 dimensions; bge-m3 as a multilingual alternative), with a hosted fallback through LiteLLM. Embeddings are stored in a pgvector column with an HNSW index using cosine distance, alongside the section metadata.

**Retrieval.** At query time the question is embedded with the same model, and the top-k chunks are retrieved by cosine similarity, optionally constrained to a section by metadata filter. Retrieved chunks are injected into context with their section titles so the answer can cite the policy. An optional reranking step is tracked as a stretch goal in OPEN_QUESTIONS.md.

## 7. Data layer

Operational data is seeded from `data/raw/*.csv` into relational tables — `categories`, `products`, `customers`, `orders`, `order_items`, `promotions` — by an idempotent ingest step that runs at backend startup. Raw files are never modified; materialization happens only in the database. The operational tables are read exclusively through the MCP server; the backend and its agent never issue SQL against them directly.

Policy content lives in a vector table: chunk id, text, embedding, and section metadata.

Data-quality issues observed in the raw files are tracked separately and are intentionally not addressed in this document.

## 8. Cross-cutting concerns

- **Async and isolation.** The backend is async end to end; `session_id` maps one-to-one to the LangGraph `thread_id`, so no state is shared across clients (`NFR3`).
- **Caching.** Tool results are memoized with a short TTL so repeated or follow-up questions do not re-query Postgres (`NFR6`). An optional semantic answer cache (embed the query, reuse a similar past answer) is a stretch goal.
- **Session persistence and compression.** Sessions and messages are stored in Postgres (`DR1`). When history exceeds a token budget, older turns are summarized and the summary replaces the full history (`DR2`).
- **Cost.** Local models by default, minimal context injection, a cheap local model for the guardrail and router, tool caching, and LiteLLM cost logging (`NFR5`).
- **Grounding.** The model is instructed to answer only from retrieved context and tool results; prices, stock, and deadlines are never answered from memory (`NFR8`).

## 9. Security

- The MCP server exposes only read-only, parameterized tools; the agent cannot issue SQL directly (no arbitrary SQL, no writes, no exfiltration).
- Prompt-injection detection at the input guardrail.
- Output guardrail enforces scope, tone, and policy.
- Secrets are injected through environment variables only; never committed or logged.

## 10. Deployment

`docker compose up` starts the full stack: Postgres (pgvector), mcp-server, backend, frontend, and Ollama. Ingest runs idempotently at backend startup. The backend reads provider keys and the default model from environment variables.

## 11. Known limitations

Unresolved design decisions are listed in OPEN_QUESTIONS.md; intentional limitations are documented there and in the README.
