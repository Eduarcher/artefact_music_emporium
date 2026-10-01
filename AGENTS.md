# Artefact Music Emporium - Case Study

## Context

### Case Scenario
"Empório da Música Instrumentos Musicais Ltda." is a fictional musical instrument store located in Campo Grande, MS. Currently, customer service is handled entirely by the staff, who are overwhelmed with recurring inquiries: business hours, order status, product pricing and availability, etc.

### Goals
- *Main Goal*: Prototype a customer service agent that will assist the team with inquiries.
- Document clearly and concisely on the README.md

---

## Requirements
### Functional Requirements
- Receive client messages.
- Process messages using available context, data, defined policies and rules
- Return a response to the client.
- Agent should be able to connect to the database to recover specific information when needed
- Agent should have the full session chat history.

### Non-Functional Requirements
- Agent persona should be aligned with the identity and tone of the Music Emporium store.
- Asynchronous operation. 
  - Support for multiple clients without data leakage, system degradation or security issues
- Scope-bound conversation. Gracefully handle out-of-scope questions and requests.
- Agent should be cost-efficient.
- Agent should avoid unnecessary calls to the database and use cache if possible.
- Agent should be respectful, policy-compliant and safe.

### Desirable (Optional/Extension)
- Chat history persistence on database
- Chat session compression for long-running conversation

---

## Project Structure
### Data
#### Raw Data
- Raw data is available at `data/raw`.
- Data on this directory should not be transformed in any way.
- Every transformation or materialization should be created on a different directory.
- Not every table should necessarily be used.

Data Content:
- `data/raw/*csv`: Table of operational data, like products, orders, clients, categories and promotions.
- `data/raw/políticas_da_loja.pdf`: Internal politics and proceedings for customer service.

> NOTE: Understanding of the raw data is part of the project. There's no additional documentation of the data.

### Tech Stack
- Python
  - The main language of the project.
- Docker
  - The whole project should be easily runnable and testable on any machine

#### Open Questions
- Agent(s) Framework(s)
- Agentic workflow and architecture
- Model(s) Provider(s)
- UI framework
- Database AND/OR Vectorial Database
- Data Processing
- On-Premises, Cloud or Hybrid?
- Prompting (Versioning, prompt techniques to use...)

### Committing Rules
- Every commit must update the project to a valid state. In other words, no commit can break or disable the project, even if temporarily
- Every commit must be concise, minimal and relate to a single change. Example: "Refactor directory structure", "Update Dependencies", "Add custom integration feature". 
- Every commit should be described on a single paragraph and have a meaningful name that summarizes it.

---

## Documentation Structure
### Core Documentation (`README.md`)
- `README.md` is the main documentation file. Any other documentation should be inserted in a `docs` directory and linked in the `README.md`
- Should contain all instructions for running the project from scratch with minimal knowledge
- Main technical decisions should be clearly explained. This part is dependent on my decisions on the brainstorm and architectural phases, I will write it personally.
- Known limitations of the project.
- AI-Assisted coding detailed personal workflow. I will write this part personally.

### Use Case Examples Documentations
- `examples` directory should contain between 3 to 5 example conversations (`markdown` or image)
- At least one of the examples should be non-trivial and apply policy rules (See `data/raw/políticas_da_loja.pdf`)

### Questions Documentations
If any ambiguous question arise and I decide on a reasonable interpretation, we should document it along with the assumption.