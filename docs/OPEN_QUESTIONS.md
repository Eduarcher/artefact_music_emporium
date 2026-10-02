# Open Questions

Running log of design decisions that are still open, under research, or deferred. Each entry records the question, current state, and what is blocking a decision.

---

## 1. Default generation model

- **Question:** Which local (Ollama) model should ship as the default so the agent works well out of the box, without API keys, in Portuguese?
- **State:** Decided — `qwen3.5:9b`.
- **Decision:** `qwen3.5:9b` is the default local model, selected for reliable tool-calling and PT-BR quality at a reasonable memory footprint. It is swappable at runtime via the Chainlit settings panel and LiteLLM; the allowlist is configured with `MODEL_ALLOWLIST`.
- **Note:** LiteLLM's Ollama integration dropped tool calls for this model (it returns tool calls as a dict rather than a JSON string), so local `ollama/*` models are served through the native `langchain-ollama` integration while LiteLLM remains the gateway for hosted providers.

## 2. Prompt-injection defense depth

- **Question:** How deep should injection defense go, given the grader may try to break or inject into the agent?
- **State:** Decided — lightweight.
- **Decision:** Hardened system prompt (ignore instructions embedded in user messages, never reveal the prompt or access other customers), a strict read-only tool allowlist, and customer identity resolved outside the model. No dedicated classifier in v1.

## 3. Embedding model selection

- **Question:** Which embedding model for the RAG pipeline (local default)?
- **State:** Decided — BGE-M3.
- **Decision:** BGE-M3 (1024 dimensions), selected because it is free, lightweight for this scope, and strong in Portuguese. Served by the local Ollama runtime, so no API key is required.
- **Criteria:** Portuguese embedding quality, dimension/performance, Ollama availability.
- **Impact:** Affects chunk retrieval quality and vector column dimensions.

## 4. Chat history persistence & compression details

- **Question:** Exact schema and strategy for persisting sessions/messages in Postgres, and the compression trigger (token budget, summarization approach).
- **State:** Full raw transcript persistence is decided. Compression is deferred and, if implemented, must be ephemeral rather than replacing persisted history. Schema and implementation details remain to be defined during the build.
- **Impact:** Transcript persistence is part of the core session design; compression is a non-blocking extension.

## 5. Answer cache semantics

- **Question:** Whether to implement a *semantic* answer cache (embed query, match similar past answers) or rely only on memoized tool-result caching.
- **State:** Optional/stretch.
- **Impact:** Cost-efficiency and latency; not required for correctness.

## 6. Complaint registration and human handoff

- **Question:** How should complaints be registered and forwarded to the responsible team, as required by section 7.3 of the policy manual?
- **State:** Open. The current design is read-only and has no ticketing, email, webhook, or staff queue integration.
- **Options:**
  1. Provide a local handoff stub that records the complaint and displays the 24-hour return expectation.
  2. Limit the prototype to acknowledging the complaint and clearly state that a human handoff is not implemented.
- **Impact:** Affects policy-compliance coverage and the scope of the first implementation.
