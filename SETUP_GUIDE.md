# Purpose

This repository setup creates a minimal Human-in-the-Loop collaboration skeleton for agent-assisted engineering work.

The goal is to make planning, implementation, review, and merge decisions easier to audit across humans and coding agents.

# Who Reads What

- Human maintainers: `SETUP_GUIDE.md`, task documents, ADRs, pull requests
- Codex: `AGENTS.md`, task documents, ADRs, relevant code
- Gemini: `.gemini/styleguide.md`, `.gemini/config.yaml`, pull requests, relevant context
- Copilot: `.github/copilot-instructions.md`, `AGENTS.md`, nearby code

# Recommended Workflow

1. Create a TASK document from `docs/templates/TASK_TEMPLATE.md`.
2. Ask a planner to turn the task into a concrete implementation approach.
3. Ask Codex to implement the scoped change.
4. Run local checks and validate the result.
5. Open a pull request using the repository template.
6. Request `@codex review` or equivalent automated review support.
7. Ask Gemini to review architecture, risk, and change quality.
8. Have a human make the final merge decision.

# Human Confirmation Required

The following items must be confirmed by a human repository maintainer:

- The real install, run, lint, test, and typecheck commands
- Credentials, secrets, and sensitive data handling
- Whether the required GitHub app or review integrations are installed
- Whether branch protection rules are enabled and appropriate

# Current Repository Commands

See `AGENTS.md` for the current repository command list.
Those commands are still inferred from the current repository contents and should be verified by a human.

# First Task Suggestion

Create the smallest end-to-end HITL research-agent loop for this repository.

Suggested scope:

- add a first TASK document
- add one ADR for agent role split and review ownership
- run one small Codex change through PR review
- validate that human review remains the final merge gate
