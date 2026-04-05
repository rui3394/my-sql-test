# ADR Number

ADR-0001

# Title

Use GitHub + TASK + ADR + PR as the collaboration substrate for a Human-in-the-Loop research agent.

# Status

Accepted

# Context

This repository is used for research-oriented engineering work where planning quality, implementation traceability, review quality, and human oversight all matter.

The project needs a collaboration model that is practical for day-to-day coding, easy to audit, and lightweight enough to use on small tasks. It also needs clear role boundaries across Human, Codex, Gemini, and Copilot.

The key design concern is to separate durable facts from transient reasoning. Source code, task records, architectural decisions, pull requests, and review comments should remain inspectable and attributable over time. At the same time, not every intermediate model thought or local autocomplete suggestion should become a system-of-record artifact.

# Decision

This repository uses GitHub Issues, TASK documents, ADRs, and pull requests as the primary collaboration substrate.

Operational rules:

- The repository is the fact layer, not a shared thought layer.
- TASK documents define scoped work and expected validation.
- ADRs record durable architectural and governance decisions.
- Pull requests are the main collaboration and review interface.
- Codex is the primary implementation agent for scoped changes.
- Gemini is used primarily for review, architecture critique, and risk-focused feedback.
- Copilot is limited to local completion and lightweight assistance.
- A Human remains the final authority for acceptance and merge.

# Alternatives Considered

- Chat-only collaboration without durable TASKs or ADRs
  - Rejected because decisions, assumptions, and validation become hard to audit and easy to lose.

- Fully automated multi-agent orchestration as the default workflow
  - Rejected because it increases operational complexity before the repository has validated a minimal working loop.

- Treating model outputs or planner notes as authoritative system-of-record artifacts
  - Rejected because model reasoning is not equivalent to verified repository state.

- Using Copilot or another local assistant as the primary implementation and review system
  - Rejected because local assistance is useful for speed, but weak as an auditable coordination surface.

# Consequences

- GitHub becomes the durable collaboration substrate for facts, decisions, diffs, and review history.
- The repository records what changed, why it changed, how it was reviewed, and what was validated.
- Pull requests become the default place where implementation, review, risks, and merge readiness are evaluated together.
- Codex is optimized for focused implementation work and therefore serves as the main writer for scoped repository changes.
- Gemini is positioned as a reviewer and architecture critic so that it can focus on correctness, risk, maintainability, and decision quality rather than competing for authorship.
- Copilot remains useful for local completion and iteration speed, but it is not relied on as the source of truth or primary reviewer.
- Human reviewers retain the final decision because repository changes may involve judgment about correctness, scope, security, scientific validity, and organizational risk that should not be delegated fully to automation.
- The workflow stays lightweight and maintainable, but some manual coordination remains necessary.

# Follow-up Actions

- Use TASK documents for new scoped work.
- Use PR templates consistently so validation and risk notes are not omitted.
- Add future ADRs when model roles, review policy, data governance, or tool boundaries change.
- Verify GitHub-side review integrations and branch protection settings with a human maintainer.
