# Artefact Music Emporium - Case Study

Customer-service agent prototype for the fictional "Empório da Música
Instrumentos Musicais Ltda." — a musical instrument store.

## Documentation

- [Requirements](./docs/REQUIREMENTS.md) - functional and non-functional requirements.
- [Architecture](./docs/ARCHITECTURE.md) — central architecture reference
  (design, decisions, trade-offs).
- [Open Questions](./docs/OPEN_QUESTIONS.md) — unresolved design decisions.

## Overview

> Under construction. See the architecture and open-questions documents linked
> above for the current state of the design.

## Assumptions

- Customer identity: The admin selector can choose one of the customers profiles to use on a testing session. This enables for testing how personal customer data is not shared between sessions of different customers, since tools are integrated exclusively using the customer id of the session. A production deployment would require authentication and authorization instead of this trusted admin simulation.
- WhatsApp Numbers: The policy manual lists two different numbers. The number in the company contact block, `(67) 3341-4444`, is treated as the operational company contact. The number in the customer-service section, `(67) 3321-4500`, is treated as the customer-service WhatsApp contact.

- CSV Inconsistencies: CSVs content are preserved without correction, even if the source may contain product name/description or specification conflicts and order totals that differ from the sum of order items. These issues are noted but considered out-of-scope for this project, and the agent must not silently invent a reconciliation.


## Decision rationale

- ReAct instead of intent branches: A fixed policy-versus-database router cannot reliably answer mixed questions. The agent therefore decides whether to answer, retrieve policy, call one tool, or call several tools. An iteration limit protects latency and cost without removing the multi-tool behavior required by `NFR9`.
- Server-bound customer context: Removing customer IDs from tool schemas is stronger than relying on prompts or guardrails. The backend resolves the customer once and the tools use only that trusted context. The local admin selector is for testing by assuming customer identities.
- Policy preprocessing: Policies PDF is preprocessed to separate information useful for the RAG from behavior-oriented policies like tone instructions for customer service. Persona, tone, scope, lookup rules, escalation behavior, and other service directives are integrated into the versioned system prompt instead of being retrieved on the RAG. Factual policies such as hours, payments, returns, delivery, promotions, guarantees, and privacy remain retrieval targets. This makes behavioral rules consistent while keeping factual answers grounded in the source.
- Customer tools: Customer-scoped tools use the session-bound customer internally. `get_customer()` has no parameters, and `get_customer_last_orders(n)` is capped at 10 orders. The agent cannot request another customer's record or provide an order ID to bypass the customer boundary.
- Model providers: The project is hybrid. Ollama is the default, while third-party providers are supported through LiteLLM. This is acceptable for the study case, but a production system would need provider privacy, PII, retention, consent, and contractual controls.

## Future
- Caching and semantic caching
- Chat compression
  - The complete raw transcript is always persisted, any future compressed context is temporary and is never persisted.
- Response validation
- Retrieval reranking
