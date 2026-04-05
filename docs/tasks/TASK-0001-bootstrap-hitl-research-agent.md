# Title

Bootstrap the minimal Human-in-the-Loop research-agent loop.

# Background

This repository now has a minimal collaboration skeleton for Human, Codex, Gemini, Copilot, TASKs, ADRs, and PR-based review.

The next step is to validate that the skeleton is usable in practice for a small research or development change. The immediate goal is not full automation. The goal is to prove that a task document can drive one real implementation cycle with explicit planning, bounded code changes, review feedback, validation notes, and a final human merge decision.

Input to this workflow is a research question or a development task. Examples include a small SQL analysis improvement, a reproducibility fix, a documentation correction, or a scoped validation improvement.

# Goal

Establish the smallest runnable Human-in-the-Loop workflow for this repository so that one task can move through planning, implementation, review, and human decision-making with an auditable trail.

Expected outputs by role:

- Planner output: task breakdown, constraints, assumptions, files likely affected, and validation plan.
- Builder output: the smallest code or documentation change required to satisfy the task.
- Reviewer output: diff-based review comments that also check required context such as interfaces, configuration, and tests.
- Human output: explicit accept/reject decision and whether the pull request should be merged.

# Non-goals

- Do not pursue full automation.
- Do not introduce complex multi-agent orchestration.
- Do not connect sensitive private data pipelines.
- Do not redesign the repository architecture beyond what is required to prove the loop works.
- Do not add broad refactors unrelated to the first end-to-end exercise.

# Constraints

- Keep the first loop small enough to complete and review quickly.
- Prefer documentation and minimal code changes over larger feature work.
- Use the existing repository structure and collaboration skeleton.
- Preserve human approval as the final merge gate.
- Do not require unverified secrets or production credentials to prove the loop.

# Assumptions

- The repository will use TASK documents and PRs as the main audit trail.
- Codex is the default builder for the first implementation pass.
- Gemini is used primarily for architecture and diff-based review feedback.
- Copilot is optional local assistance, not a source of record.
- AI review may depend on GitHub-side app installation or repository settings that still need human confirmation.

# Human Approvals Needed

- Confirmation of the real repository commands for install, run, lint, test, and typecheck.
- Confirmation that the required GitHub review integrations are installed and enabled.
- Final decision on whether the resulting pull request is acceptable and ready to merge.

# Proposed Approach

1. Start from this task document as the shared specification.
2. Ask a planner to produce a concrete plan with constraints, assumptions, and validation steps.
3. Ask Codex to implement one minimal, reviewable change tied to this task.
4. Run the available local validation steps and record what was checked and what could not be checked.
5. Open a pull request using the repository template and link this task.
6. Trigger AI review on the pull request.
7. Ask Gemini to review the diff with attention to correctness, security, reproducibility, and maintainability.
8. Have a human review the PR summary, risks, and validation notes, then decide whether to merge.

# Files Likely Affected

- `docs/tasks/TASK-0001-bootstrap-hitl-research-agent.md`
- `AGENTS.md`
- `.github/pull_request_template.md`
- `SETUP_GUIDE.md`
- one small implementation file if a code-path validation change is chosen

# Validation Plan

- Confirm that this task document is specific enough to drive one real change.
- Confirm that the chosen implementation stays minimal and scoped to the task.
- Record the commands run and the observed outcome.
- Confirm that a PR can be opened with linked task, validation notes, and risk summary.
- Confirm that AI review is requested or triggered in the PR flow.
- Confirm that a human can make the final merge decision without missing context.

# Risks

- The repository may still lack verified lint or typecheck commands.
- AI review integration may not be fully enabled at the repository level.
- The first task may drift into process design instead of proving a concrete change.
- Review comments may be low-signal if the change is too small or lacks context.
- The workflow may appear complete on paper while still missing one manual step in practice.

# Definition Of Done

- One real task document drives one actual code or documentation change.
- The change is implemented through the documented planner-to-builder workflow.
- AI review is triggered or explicitly requested on the pull request.
- Validation steps and risks are recorded in the pull request or task-linked artifacts.
- A human makes the final accept/reject and merge decision.

# Acceptance Criteria

1. A task document can drive one actual code change in this repository.
2. AI review can be triggered from the resulting pull request.
3. Validation steps and risks are recorded in a reviewable artifact.
4. A human remains the final authority for acceptance and merge.
