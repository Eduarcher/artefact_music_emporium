# Open Questions

Running log of design decisions that are still open, under research, or deferred. Each entry records the question, current state, and what is blocking a decision.

---

## 1. Default generation model

- **Question:** Which local (Ollama) model should ship as the default so the agent works well out of the box, without API keys, in Portuguese?
- **State:** Open — under research.
- **Current position:** Use the locally installed Gemma model for development, but we want a more evidence-based recommendation.
- **Criteria:** PT-BR quality, latency on typical hardware, Ollama availability, memory footprint.
- **Impact:** Non-blocking — the model is swappable at runtime via the Chainlit settings panel and LiteLLM. Only the *default* value depends on this.

## 2. Prompt-injection defense depth

- **Question:** How deep should injection defense go, given the grader may try to break or inject into the agent?
- **State:** Open — needs confirmation.
- **Options:**
  1. Lightweight: hardened system prompt + strict read-only tool allowlist + a dedicated injection-check node in the graph.
  2. Deeper: a dedicated injection-detection model/classifier (more robust, more time).
- **Impact:** Affects the input guardrail node design and time budget.

## 3. Embedding model selection

- **Question:** Which embedding model for the RAG pipeline (local default)?
- **State:** Open.
- **Criteria:** Portuguese embedding quality, dimension/performance, Ollama availability.
- **Impact:** Affects chunk retrieval quality and vector column dimensions.

## 4. Chat history persistence & compression details

- **Question:** Exact schema and strategy for persisting sessions/messages in Postgres, and the compression trigger (token budget, summarization approach).
- **State:** Agreed at a high level (persist in DB; trim/summarize over budget); implementation details TBD during build.
- **Impact:** Desirable requirement; non-blocking for core functionality.

## 5. Answer cache semantics

- **Question:** Whether to implement a *semantic* answer cache (embed query, match similar past answers) or rely only on memoized tool-result caching.
- **State:** Optional/stretch.
- **Impact:** Cost-efficiency and latency; not required for correctness.