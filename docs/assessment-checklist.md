# Assessment submission checklist

| Requirement | Implementation / evidence |
|---|---|
| Beginner audience | `generation.py` learner profile and goals; final lesson in `submission/approved/lesson.md` |
| What, why, how | Structured Lesson fields and C1-C3 |
| Hard pass/fail rubric | C1-C9 and strict Evaluation schema |
| Generate → evaluate → revise | LangGraph in `workflow.py` |
| Max 1-2 retries | Three total attempts, deterministic routing |
| Passing lesson or safe stop | `approved`, `needs_human_review`, `error` |
| Rejection log and changes | Full attempts, failed evidence/corrections, actual changed sections |
| Memory across runs | SQLite runs, feedback, source/prompt versions, experiment history |
| Self-evolving | Repeated failures → reviewed proposal → paired test → conditional adoption |
| Evaluator catches deliberate error | UI injection and real saved demo evidence when available |
| Planning and design decisions | `docs/architecture.md` and README |
| Setup and no-cost tests | `uv sync --locked`, `uv run pytest`; CI workflow |

## You still need to submit these external links

- Your GitHub repository URL. Code remains local because you requested no publishing. Review `git diff` and staged changes before committing/pushing; do not include `.env` or local SQLite files.
- A Google Docs or Notion link containing the final lesson. The connected Google accounts were not yours, so no document was created there. Copy `submission/approved/lesson.md` into a document in your own account, preserve headings, and verify reviewer access. A local Markdown file is a preparation artifact, not a replacement for the assessment's document-link requirement.
- Your face-visible Loom recording, 15–20 minutes. Use `docs/loom-guide.md` as the speaking outline. This recording must be made by you.

Use the current submission form supplied by the assessor. Verify its destination yourself before entering personal information. No form submission has been made automatically.
