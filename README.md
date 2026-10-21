# LessonLoop

An AI lesson writer that generates, reviews, and revises a beginner lesson before deciding whether to approve it. Built for the **GenAI Engineer — Content Systems** assessment, with **Introduction to RAG** as the submission topic.

**Stack:** Python 3.12+, uv, Gemini (`google-genai`), LangGraph, Pydantic, SQLite, Streamlit. No LangChain agent abstraction or vector database is necessary for this bounded workflow. The reference notes are the generator's grounding material; this project teaches RAG rather than claiming to implement a production RAG search service.

## Start here

```bash
uv sync --locked
cp .env.example .env
# Privately fill GEMINI_API_KEY and GEMINI_MODEL in .env
uv run streamlit run app.py
```

Open http://localhost:8501. Use a Gemini model ID available to your account that supports structured JSON output. Both UI and CLI read `.env`; shell variables take precedence. No key is printed or placed in graph state. The app binds to localhost and has no business authentication: keep it local.

## What it does

1. Load the learner brief, reviewed source notes, rubric, and active tested prompt guidance.
2. Generate a structured lesson.
3. Evaluate all nine hard pass/fail checkpoints with evidence, reasons, and corrections.
4. Approve only if every required checkpoint passes. On a content failure, feed the old lesson and failed checks back to the writer.
5. Stop after **one draft plus at most two revisions**. Unresolved failures become `needs_human_review`; provider or malformed-output failures become `error`.
6. Save automatic runs, attempts, lessons, evaluations, model name, source snapshot, prompt version, and feedback to SQLite.
7. Find repeated failures across distinct runs and propose stronger instructions. Test old/new instructions against the unchanged rubric before adopting improvements for future runs.

Python owns routing, attempt limits, output validation, and approval. The model does not decide whether it can skip a check or keep retrying.

## Test it in the UI

- Keep **Automatically evaluate and revise** enabled, then click **Generate lesson**.
- Inspect the final status, **Quality checkpoints**, and **Attempt history & rejection log**.
- Download the lesson, report, and complete run log.
- To demonstrate a rejection: expand **Test a deliberate error**, insert it, then click **Run revisions on this draft**. The submitted draft counts as attempt one.
- Open **Memory & improvements** to restore earlier runs, add checkpoint-specific feedback, inspect proposals, and test a proposal.
- Turn off automatic mode to generate and evaluate manually. Manual single drafts are session-only; automatic runs, including seeded repair runs, are persisted.

### Model usage and limits

A full run uses at most **6 model requests** (3 writer + 3 reviewer). A seeded repair run uses at most 5. A prompt experiment uses **8 requests** (old and new writer/reviewer pairs on 2 scenarios). These may consume paid quota. Each request has a 60-second HTTP timeout and 65-second outer bound; transport retries are disabled. Testing a proposal is explicit so generation does not unexpectedly start eight additional requests. The system makes the adoption decision automatically.

## CLI

Inspection and ordinary tests do not call Gemini:

```bash
uv run python -m lessonloop --show brief
uv run python -m lessonloop --show prompt
uv run python -m lessonloop --show history
uv run python -m lessonloop --show memory
uv run pytest
# Optional complete no-cost demonstration (synthetic, not live quality evidence)
uv run python scripts/offline_demo.py --output outputs/offline-demo.json
```

Model operations require explicit `--live`:

```bash
# Complete workflow and export run.json; lesson.md is written only on approval
uv run python -m lessonloop --live --output outputs/my-run

# Evaluate and repair an existing Lesson JSON, counted as attempt one
uv run python -m lessonloop --live --seed my-lesson.json --output outputs/repair

# Compare a proposed prompt with its parent and adopt only if better
uv run python -m lessonloop --live --test-prompt prompt-<id>
```

`--seed` accepts the eight-field Lesson object, not a complete run/report envelope. `main.py` is a convenience entry point for the same CLI. A failed export removes a previous generated `lesson.md` in the chosen output directory to avoid presenting stale approval.

## Persistent memory and self-evolution

Default database: `data/lessonloop.sqlite3` (gitignored). Override the path with the **environment variable** `LESSONLOOP_DB`. SQLite uses short transactions, foreign keys, and a busy timeout. Reopen the app and select a saved run to prove memory survives a restart.

A checkpoint must fail in **two distinct normal runs** before a candidate is proposed. Three retries in one run do not count as three examples. Seeded/demo runs are excluded. Human feedback contributes the checkpoint ID to this analysis; free-text feedback is saved for review, not inserted as model instructions. Duplicate reports for one run/checkpoint count once. Old-rubric model failures are excluded from current-rubric analysis.

Proposals come from a small reviewed catalog of checkpoint-specific teaching strategies, combined with the active guidance. This is a bounded, explainable form of prompt evolution; it does not retrain model weights or invent arbitrary instructions from untrusted text. The rubric remains fixed during comparisons.

The gate compares parent and candidate on the same two fictional RAG scenarios (college handbook and library opening hours). It requires:

- Fewer failures on the targeted checkpoint.
- Fewer total checkpoint failures.
- No baseline-pass → candidate-fail regression on any checkpoint in either scenario.

Experiments save both lesson versions, all evaluations, model/rubric/benchmark versions, metrics, and the candidate's failure-evidence run IDs. Only accepted improvements become active for future automatic runs. No improvement, an experiment error, or a stale parent leaves the active prompt unchanged. Concurrent promotion uses an atomic parent check. A crash during an experiment can leave it labelled `testing`; inspect its saved state rather than claiming it was adopted.

## Verification

```bash
uv sync --locked
uv run pytest
uv run --with pyrefly pyrefly check
```

Ordinary tests use fake model responses, isolated temporary SQLite files, and no paid model calls. They cover malformed/missing/duplicate checks, strict booleans, bounded retries, failure/error paths, changed-section logs, UI interactions, persistence after reopening, repeated-failure counting, prompt promotion, rejected experiments, and use of accepted memory in future runs. The live evidence in `submission/` is separate from CI.

## Project map

| File | Responsibility |
|---|---|
| `app.py` | Local UI, run history, evaluation display, feedback and experiments |
| `src/lessonloop/generation.py` | Learner brief, reviewed references, rubric conditions, writer contract |
| `src/lessonloop/evaluation.py` | Reviewer prompt, strict checklist validation, Python approval |
| `src/lessonloop/workflow.py` | LangGraph nodes, deterministic routing, attempt cap, rejection/change log |
| `src/lessonloop/memory.py` | SQLite persistence and atomic prompt promotion |
| `src/lessonloop/evolution.py` | Failure-based proposals, fixed benchmark, no-regression gate |
| `src/lessonloop/service.py` | Compose persistent memory with the workflow |
| `src/lessonloop/gemini.py` | Bounded provider calls and safe errors |
| `src/lessonloop/settings.py` | Shared .env/settings reads without environment mutation |
| `src/lessonloop/exporting.py` | Approved-lesson submission exports |
| `tests/` | No-cost automated checks |
| `docs/` | Architecture, rubric rationale, assessment checklist, Loom guide |
| `submission/` | Real generated lesson and live run evidence |

## Honest limits

This release intentionally supports the assessment's RAG topic with reviewed reference notes. Other topics require their own brief, references, and content checkpoints. It does not browse automatically, train model weights, or prove actual learner understanding.

The writer and reviewer may use the same model under separate prompts; correlated errors and inconsistent judgments remain possible. A narrow Python guard catches the specific false-guarantee demo claim, but is not a general fact checker. A two-scenario improvement gate provides observed evidence, not statistical proof of general improvement. Prompt adoption never guarantees all later lessons pass; every lesson still gets full evaluation. No multi-user authentication, hosted deployment, distributed workers, or production observability is claimed.

See [live and automated verification](docs/verification.md), [architecture and trade-offs](docs/architecture.md), [assessment checklist](docs/assessment-checklist.md), and [video walkthrough guide](docs/loom-guide.md).

## Visual walkthrough in the UI

The Create lesson view shows the five workflow stages, real progress events during generation, the final decision, and check/attempt counts. **Load recorded repair demo** replays the captured real rejection/repair evidence without Gemini calls or training the persistent memory. It is clearly labelled as recorded. Compare revisions side by side, inspect exact text differences, and filter checkpoints to failed or passed items. The memory tab shows recent saved-run counts, failure patterns, proposal states, and old/new benchmark failure counts. Layout cards wrap at narrow screen widths; native widgets retain keyboard interaction. No browser surface was available for visual screenshot verification in this session; interactions are covered by Streamlit AppTest.
