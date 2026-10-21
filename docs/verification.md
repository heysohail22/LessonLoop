# Verification record — 21 October 2026

## Automated checks

- `uv sync --locked`: dependency resolution succeeded from the project lockfile.
- `uv run pytest`: **43 passed**. All ordinary tests use fake models and isolated temporary SQLite memory.
- `uv run --with pyrefly pyrefly check --min-severity=warn`: **0 diagnostics**.
- `git diff --check` and `git diff --cached --check`: passed.
- `.env` and `data/lessonloop.sqlite3` are ignored by Git. A source/artifact scan found no Google API key pattern or private-key block. No GitHub push, external document write, or form submission was performed.

## Live Gemini evidence

### Final lesson

- Model: `gemini-3.5-flash-lite` (the locally configured model).
- Run ID: `423cbc21-75f9-43cb-a840-431941889b16`.
- Rubric: `rag-v2`.
- Result: **approved on attempt 1**; all nine checkpoints passed.
- Files: `submission/approved/lesson.md`, `run.json`, and `provenance.json`.
- The lesson was exported from the saved approved result. Reference notes were appended for traceability; it was not hand-edited to manufacture a passing evaluation.

### Deliberate-error repair

- Starting draft: real approved lesson with its limitations section replaced by “RAG always gives correct answers.”
- Result: **attempt 1 rejected under C6; attempt 2 approved**.
- Actual changed section on retry: **limitations**.
- Files: `submission/deliberate-error-input.json`, `submission/error-demo/run.json`, and `submission/error-demo/provenance.json`.
- The log is real model output, not a fixture. A subsequent local regression fix tightened the Python safeguard so an exercise's “True or False” text cannot excuse a guarantee in another section. The original live evidence is preserved as captured, rather than rewritten to match later code.

## Memory and evolution evidence

- Saved live runs remain readable after reopening SQLite.
- UI tests restore a run in a new session and save feedback durably.
- Automated tests prove distinct-run thresholds, proposal deduplication, benchmark improvement/no-regression gates, adoption persistence, stale-parent rejection, failed-experiment behavior, and future use of accepted guidance.
- `uv run python scripts/offline_demo.py` successfully runs the complete memory/evolution path in a temporary database with deterministic fake models.
- `submission/synthetic-evolution-demo.json` is explicitly labelled **synthetic-test-only**. Its candidate improves the artificial fixture and the next fixture run passes on attempt one. It is control-flow evidence, **not evidence of improved real-model teaching quality**.
- No prompt was promoted in the real local memory during this verification. Real live runs had not yet accumulated the required repeated failures. Future genuine failure/feedback data can produce proposals and explicit paired experiments.

## UI and remaining human steps

- Streamlit restarted successfully at http://localhost:8501; health endpoint returned `ok`.
- Streamlit AppTest verified generation, evaluation, revision history, error handling, saved-run restoration, feedback, and protection against rerender-triggered paid calls. A separate visual desktop/mobile browser inspection was not performed.
- Record the face-visible Loom yourself using `docs/loom-guide.md`.
- Publish your reviewed local code to your repository when ready; it was kept local at your request.
- Upload the final Markdown lesson to Google Docs or Notion under your own account to obtain the required document link. The connected Google accounts were not yours and were not used.

## Visual walkthrough UI upgrade

The upgraded UI adds a five-stage progress display, a How it works explorer, recorded live-demo replay, decision metrics, side-by-side revision comparison and exact text differences, checkpoint filters, and clearer memory/benchmark summaries. The suite now has **45 passing tests**, including no-model-call replay and unchanged persistent history during playback. Type checking reports zero diagnostics. No connected browser surface was available for screenshot inspection; this verification uses Streamlit AppTest and local server health. No paid calls were made for the UI upgrade.
