# Architecture

## 1. Document Scope
This document describes the system design of the Artefact Music Emporium customer-service agent: how its components are organized, how they interact, and why each technology was chosen. The requirements that motivate these decisions live in [REQUIREMENTS.md](./REQUIREMENTS.md) and are referenced here by identifier.

Each major decision records the problem, the chosen approach, and the trade-off. This makes deliberate case-study assumptions distinguishable from production requirements.

## 2. System overview

The system is a set of five containerized services behind `docker compose`:

- **Frontend:** Chainlit renders the chat and administrative settings. It forwards messages to the backend and renders status and response events. The local admin view selects the simulated customer and model for a new conversation.
- **Backend:** FastAPI owns the agent runtime, LangGraph workflow, prompt resolution, RAG retrieval, session context, and the API exposed to the frontend.
- **MCP server:** The only operational-data access path available to the agent. It exposes read-only, typed tools and queries Postgres.
- **Postgres:** The single datastore for operational tables, policy embeddings, sessions, and the complete raw chat transcript.
- **Ollama:** The local model and embedding runtime, required for both generation and embeddings. LiteLLM can route generation to one of the explicitly configured alternative providers for the study case.

## 3. Identity, sessions, and privacy boundary

### 3.1 Local customer selection for testing

The prototype does not implement customer login. The admin page contains a selectbox backed by a hardcoded list of fixture customers in the frontend; there is no customer-listing endpoint. Selecting a customer starts a new conversation session.

The backend validates the selected customer ID once and stores a binding between a newly generated opaque `session_id` and that customer. Every subsequent chat request carries only the `session_id`; it does not carry a customer ID selected by the model or repeated by the frontend.

This is a deliberate study-case compromise: it allows safe, repeatable testing with any fixture customer without building authentication. It is not an authentication mechanism. A production system would replace the selector with authenticated identity resolution, authorization, retention controls, and audit logging.

Changing the selected customer creates a new session. An existing session is never reassigned to another customer. This prevents accidental cross-session mixing inside the prototype, while the documented admin-only assumption keeps the interface appropriate for local testing.

### 3.2 Out-of-band customer context

The resolved customer context is attached by the backend to the request-scoped tool context. It is not part of the model-facing tool schema.

The MCP server is reachable only by the backend over the internal service network. The backend must pass the context through an internal authenticated or signed transport mechanism. The MCP server must reject calls that lack valid backend context rather than accepting a customer ID from an arbitrary caller.

The design deliberately prevents the model from selecting another customer through tool arguments. Read-only access alone is insufficient for privacy; the important boundary is that customer identity is resolved outside the model and outside customer-scoped tool parameters.

## 4. Technology decisions

### 4.1 Orchestration: LangGraph

LangGraph models the agent as a state machine and provides the control loop needed for repeated tool use. The graph is a ReAct-style loop: the model can answer directly or request one or more tools, receive their results, and decide whether another tool call is necessary.

LangGraph was selected instead of hand-rolling the loop because it provides typed state, conditional routing, tool integration, and a natural place to enforce execution limits. The trade-off is an additional framework dependency for a small prototype. The multi-step requirement in `NFR9` justifies it because a fixed intent branch would prevent combined product, customer, and policy answers.

### 4.2 Model access: LiteLLM

LiteLLM is the gateway for the configured model providers. It makes the generation model replaceable without changing the agent workflow. The default is a local Ollama model to keep the normal path inexpensive and usable without API keys; Ollama remains required for embeddings. The admin model setting exposes only an application allowlist, never arbitrary provider or model strings.

The trade-off is accepting a relatively large abstraction layer. It is justified here because model comparison is part of the study and the same application can be evaluated with local and optional hosted providers. This is not a production data-governance decision; real deployments would need provider privacy, PII, retention, consent, and contract analysis.

### 4.3 API Backend: FastAPI

FastAPI provides the asynchronous HTTP API and Server-Sent Events used by the frontend. The backend resolves the session, loads the transcript, runs the graph, persists the turn, and emits status and response events.

The async design addresses `NFR2`, but blocking model, embedding, PDF, or database operations must still be isolated from the event loop during implementation. The architecture does not claim that an async framework alone guarantees unlimited concurrency.

### 4.4 Frontend: Chainlit

Chainlit provides the reference chat UI, streaming display, and administrative settings. The customer selector is explicitly an admin/testing affordance, not a login flow. The model selector is also administrative and must be restricted to configured models.

During a multi-step turn, the backend emits user-facing status events. The UI can show messages such as:

- `thinking`: "Pensando..."
- `consulting_data`: "Consultando os dados do atendimento..."
- `consulting_policies`: "Consultando as politicas da loja..."
- `preparing_response`: "Preparando a resposta..."
- `validating_response`: "Conferindo a resposta..."

These statuses improve transparency without exposing hidden chain-of-thought or raw internal tool arguments.

### 4.5 Data storage: Postgres, pgvector, and SQLAlchemy

Postgres is the single datastore. Relational tables hold the operational data, pgvector stores policy embeddings, and session tables store the complete raw transcript. SQLAlchemy with `asyncpg` provides the database layer.

Using one datastore avoids the operational cost of a separate vector database and keeps the Docker deployment small. The trade-off is that vector search and transactional application data share one service, which is appropriate for the dataset size and prototype scope.

### 4.6 Tool access: MCP

MCP separates the agent from structured-data access and provides typed, discoverable tools. The MCP server is intentionally read-only and exposes only approved queries. The backend loads the tools through the MCP adapter and binds them to the LangGraph agent.

MCP adds a service and a network hop compared with backend-local repository functions. It is retained because tool boundaries and schemas are central to the security design, especially the requirement that customer identity never be model-selectable.

## 5. Agent workflow

### 5.1 State

The graph state contains the current user message, `session_id`, request-scoped customer context reference, available evidence, tool results, response status, and final response. Customer identity itself is resolved by the backend and is not exposed as a model argument.

The complete transcript is loaded from the session store. If compression is later enabled, a temporary model-context representation may be derived, but the original transcript remains authoritative and unchanged.

System and task prompts are stored as versioned files under `prompts/`, and the active prompt version id is recorded with the session so a transcript can be traced to the prompt that produced it.

### 5.2 ReAct loop

The core graph is:

```text
START
  -> prepare request context
  -> agent decides: answer or call tool(s)
  -> execute selected tools
  -> return tool results to agent
  -> agent decides again or produces final answer
  -> persist complete turn
  -> stream final response
```

The agent can call structured tools and policy retrieval in the same turn, in any useful order. It can call multiple tools, perform multiple policy searches, or call no tool when the existing prompt and conversation context are sufficient.

There is no exclusive policy-versus-database intent branch. Removing that branch avoids a central failure mode where a mixed question is forced into only one retrieval path. A configurable maximum number of graph iterations and tool calls is still required to prevent loops, runaway latency, and uncontrolled model cost. The limit is an execution safeguard, not a restriction on the normal multi-tool behavior required by `NFR9`.

### 5.3 Workflow events

Status events are emitted as the graph progresses. Tool names are mapped to friendly UI states: structured operational tools produce `consulting_data`, while the policy retriever produces `consulting_policies`. The final response is emitted only after the graph finishes.

Response validation is an optional extension. If enabled, the UI may show `validating_response`; if validation fails, the response is hidden and replaced with a specific safe-failure message.

## 6. Tools

### 6.1 Customer-scoped tools

Customer tools have no identity parameters:

- `get_customer()` returns the current session customer's permitted profile fields.
- `get_customer_last_orders(n: int)` returns the current customer's most recent orders, ordered by date, with `n` capped at 10.

The agent cannot request another customer's record, pass a customer ID, pass an order ID, or query arbitrary customer rows. If a user names an order, the agent retrieves the current customer's recent orders and identifies the matching record from those results. The server enforces the customer binding independently of prompts and guardrails.

The exact profile fields returned by `get_customer()` should follow least privilege. The model should receive only useful fields instead of the complete customer table row.

### 6.2 Public operational tools

Public catalog and promotion tools may accept product or catalog parameters because those parameters do not identify another customer.

All tools use typed schemas, parameterized queries, read-only database credentials, and bounded result sizes. The model never receives raw tables or arbitrary SQL access.

### 6.3 Policy retrieval tool

The RAG retriever is exposed to the agent as a information and knowledge search capability. It returns section-aware chunks with source metadata.

## 7. Policy retrieval

The complete policy manual is treated uniformly as a RAG source. Behavioral, tone, operational, and customer-facing sections are not given special preprocessing treatment. This avoids a manual classification process that would become impractical as the number of source documents grows.

The trade-off is that behavioral sections may occasionally be retrieved when they are not useful to the answer. The system accepts this possibility and controls it through retrieval quality rather than document-specific rules. The system prompt still defines general agent instructions, but policy behavior is not manually copied from each source document into the prompt.

Preprocessing may annotate or lightly rewrite derived policy text, such as clarifying which WhatsApp number has which role. Such changes are allowed only in derived materialized data, never in `data/raw`. Each transformation must record its source document version, changed interpretation, and reason in project documentation.

### 7.1 Section-aware chunking

All policy content is chunked along numbered sections and subsections rather than arbitrary fixed windows. Each chunk stores the section number, title, source version, and text.

### 7.2 Embedding and retrieval

Chunks are embedded with one selected model and stored in pgvector using cosine similarity. The selected embedding model is BGE-M3 (1024 dimensions), chosen for being free, lightweight for this scope, and strong in Portuguese. Embeddings are produced by the local Ollama runtime, keeping the fixed 1024-dimension schema stable. The embedding model must be selected before database initialization because its dimension is part of the vector schema. The model is used consistently for indexing and querying.

The retriever returns relevant sections and metadata only when they pass a configured relevance threshold. A score filter, implemented as a minimum similarity score or equivalent maximum cosine-distance threshold, prevents weak matches from being inserted into the model context. The agent may perform more than one search when a question covers multiple policies. A future reranking step may improve ordering and precision after initial retrieval, but is not required for the core implementation.

## 8. Data layer and source-data assumptions

Operational data is materialized from the raw CSV files into relational tables: `categories`, `products`, `customers`, `orders`, `order_items`, and `promotions`. Ingestion is idempotent and never changes the raw files.

The source data may contain inconsistencies that are outside the case study's control. Examples include product names that disagree with descriptions or specifications, and order totals that do not equal the sum of order items. These records are preserved and documented rather than silently corrected. If an answer depends on an unresolved contradiction, the agent should avoid inventing a reconciliation and should communicate the limitation.

The order record remains the source for its stored order status and total; order-item records remain the source for item composition. This avoids silently replacing a provided value with a calculated value.

## 9. Persistence and optional extensions

### 9.1 Complete transcript

The full session transcript is persisted as-is. It is the authoritative conversation history and satisfies the stronger interpretation of `FR5`. Persistence is not replaced by summarization.

### 9.2 Compression extension

Compression is deferred until the core prototype works. If implemented, older turns may be summarized temporarily when constructing model context, while recent messages remain unchanged. The summary is not persisted; the full raw transcript remains available for every request.

### 9.3 Caching extension

Caching is also deferred. A future implementation may cache public product or promotion lookups with explicit freshness rules. Customer profiles, orders, tracking information, and other personal data must not enter a shared cache. Semantic answer caching is not part of the core correctness path.

### 9.4 Response validation extension

Response validation is welcome but not required for the first core implementation. If added, it must fail closed from the user's perspective: an invalid response is hidden and replaced with a specific message rather than streamed to completion first.

## 10. Security and safety

- Customer identity is resolved by the backend session binding, never by model arguments.
- Customer-scoped tools have no customer or order ID parameters.
- MCP is internal-only and requires valid backend context.
- Operational tools are read-only, parameterized, and bounded.
- The system prompt defines scope, tone, grounding, and escalation behavior.
- Model and provider selection uses an allowlist.
- Secrets are injected through environment variables and are never committed or logged.
- Prompt-injection defense depth remains an open question; tool isolation does not depend on trusting the model.

## 11. Deployment

`docker compose` starts Postgres, the MCP server, backend, frontend, and Ollama. Database readiness, schema creation, and ingestion must be coordinated before serving requests. The ingestion operation is idempotent and should be implemented as an explicit initialization step or readiness-controlled startup task rather than relying on an uncoordinated race between services.

Python dependencies should be declared in `pyproject.toml` and managed with `uv`.

The backend reads the configured model allowlist and provider settings from environment variables. The local default path should work without hosted-provider credentials. Ollama is a required service for both generation and embeddings, so `docker compose` must wait for it to be ready and for the required models to be available.

A `pytest` suite covers CSV ingestion idempotency, customer-scoped tool isolation (no cross-customer leakage), and policy retrieval. Tests run against the containerized stack.

## 12. Open limitations

- The admin customer selector simulates trusted local testing and is not authentication.
- The raw source data may contain contradictions that are not corrected.
- Complaint registration and human handoff are not yet represented by a tool or external queue; the decision is tracked in [OPEN_QUESTIONS.md](./OPEN_QUESTIONS.md).
- Compression, caching, response validation, and reranking are deferred extensions.
- The exact default generation and embedding models remain configurable decisions until selected and benchmarked.
