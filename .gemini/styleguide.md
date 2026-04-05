# Review Priorities

Focus on high-value review findings first.

- Prioritize correctness, security, data integrity, error handling, test coverage, and maintainability.
- Comment on formatting only when it hurts readability, consistency, or reviewability.

# Review Method

- Start from the diff.
- Check the surrounding context required to validate the diff:
  - call chain
  - public interfaces
  - configuration
  - tests
- Prefer a small number of high-signal comments over many low-value style comments.

# Additional Checks For Research And Agent Systems

- Verify prompt boundaries and tool-calling boundaries are explicit and safe.
- Flag any leaked secrets, credentials, or private data immediately.
- Flag workflows that are not reproducible or depend on undocumented manual steps.
- Do not treat model output as ground truth unless it is validated by deterministic logic or explicit human review.
- Check whether auditability is preserved across prompts, tools, decisions, and artifacts.
