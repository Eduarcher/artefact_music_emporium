# Requirements

## Functional Requirements
- FR1: Receive client messages.
- FR2: Process messages using available context, data, defined policies and rules.
- FR3: Return a response to the client.
- FR4: Connect to the database to recover specific information when needed.
- FR5: Have the full session chat history.

## Non-Functional Requirements
- NFR1: Persona aligned with the identity and tone of the Music Emporium store.
- NFR2: Asynchronous operation for supporting multiple clients.
- NFR3: Support for multiple clients without data leakage, system degradation or security issues.
- NFR4: Scope-bound conversation. Gracefully handle out-of-scope questions and requests.
- NFR5: Cost-efficient.
- NFR6: Avoid unnecessary calls to the database and use cache if possible.
- NFR7: Respectful, policy-compliant and safe.
- NFR8: Accurate and grounded, must never hallucinate. Information used should be limited to the provided context and prompt.

## Desirable (Optional/Extension)
- DR1: Chat history persistence on database.
- DR2: Chat session compression for long-running conversation.
