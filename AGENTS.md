# Purpose

This repository uses a minimal Human-in-the-Loop collaboration model.

Agents must read the task context before changing code, prefer the smallest viable change, and leave a clear audit trail for humans to review and merge.

# Roles

- Human: final decision maker, reviewer of sensitive changes, and only merge authority.
- Codex: primary implementer for scoped code and doc changes.
- Gemini: primary automated pull request reviewer focused on architecture, design, and high-value risks.
- Copilot: local autocomplete and lightweight coding assistance.
- GitHub Issues, TASKs, ADRs, and PRs: shared planning and review surface.
- GitHub private repository: source of truth, audit history, and collaboration record.

# Working Rules

- Read `docs/tasks/*.md` and related ADRs before making changes.
- If task docs do not exist, state that clearly in your output before proceeding.
- List assumptions in your output when requirements are incomplete or ambiguous.
- Make the minimum necessary change to satisfy the task.
- Do not refactor unrelated code as a side effect.
- Follow the existing project structure and style unless the task says otherwise.
- Add or update tests when practical; if no tests are added, explain why.
- Avoid adding dependencies unless they are necessary for the task.
- Keep PR descriptions explicit about scope and tradeoffs.
- PR descriptions must include: what changed, risks, validation, and unresolved questions.

# Definition Of Done

- The task scope is implemented with minimal necessary changes.
- Related docs are updated when behavior, workflow, or design intent changed.
- Tests were added or updated, or the reason for not doing so is documented.
- Validation steps are recorded and reproducible.
- The final output includes a change summary, risks, and verification steps.

# Review Checklist

- Was the related task document read first?
- Were relevant ADRs checked?
- Is the change scoped tightly to the request?
- Does the change preserve correctness and avoid unrelated refactors?
- Are security and sensitive data handling still acceptable?
- Are risks and rollback considerations stated?
- Are validation steps concrete and reproducible?
- Were tests added or was the lack of tests justified?

# Project Commands

- Install: `pip install sqlglot networkx pydantic openai`
- Run: `python main_pipeline.py`
- Lint: `Not yet defined in repo`
- Test: `python main_pipeline.py`
- Typecheck: `Not yet defined in repo`
