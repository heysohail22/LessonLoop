# LessonLoop

A beginner lesson generator with a planned evaluate/revise loop. This is an independent uv project.

## Current milestone

The RAG learner brief, nine rubric conditions, source-linked reference notes, structured lesson contract, provider-independent async generation function, and Gemini adapter are implemented. By default the CLI displays inputs. Only `--live` calls Gemini. Evaluation, LangGraph orchestration, retries, persistent memory, and prompt improvement are future milestones. Schema validity is not a quality pass.

## Setup (uv only)

```bash
cd /home/sohail/Desktop/lesson_loop
uv sync
uv run python -m lessonloop --show brief
uv run python -m lessonloop --show prompt
uv run pytest
```

The inspection commands and tests make no network/model calls and require no API key. Keep future credentials in environment variables; never commit them.

## Generate a draft with Gemini

Set `GEMINI_API_KEY` privately in your shell and `GEMINI_MODEL` to an available model supporting structured output. `.env.example` documents these variables; files are not loaded automatically. Then run:

```bash
uv run python -m lessonloop --live
```

This explicitly makes a model call and may incur API charges. The adapter uses the official `google-genai` SDK, a 60-second HTTP timeout, a 65-second outer bound, and no automatic retries. Output is JSON with status `unreviewed`. No live call is part of ordinary tests. See [Gemini structured output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).

`src/lessonloop/generation.py` contains the teaching rules and `generate_draft(model, brief)`. A provider adapter must implement asynchronous `complete(system=..., user=...)`, enforce a request timeout, and return JSON text. Pydantic rejects incomplete or malformed lessons. All generated lessons remain `unreviewed` until a separate evaluator is implemented.

Reference notes are curated summaries, not automatically fetched source documents. Their coverage is intentionally limited to introductory RAG. Other topics need their own reviewed brief and references. Rubric C7 will check support against these notes, not prove universal factual accuracy.

## Local testing UI

```bash
uv sync
uv run streamlit run app.py
```

Open http://localhost:8501. The UI reads GEMINI_API_KEY and GEMINI_MODEL from the project .env file, with shell variables taking precedence. It does not print credentials or modify the environment. The CLI continues to require shell variables. A model ID can also be entered in the UI. Clicking Generate makes one live request; tab changes and downloads do not generate again. This version supports RAG only. Lessons are unreviewed, remain in browser-session memory only, and can be downloaded as Markdown or JSON. Checkpoints are displayed as not evaluated. No evaluator, retry loop, or persistent learning is implemented yet. Bind to localhost for local testing.

UI tests use Streamlit AppTest and fake model responses; they never call Gemini.

## Editor import errors

Open this project folder as the workspace. Use Python: Select Interpreter and select `.venv/bin/python` if an interpreter was already selected. The workspace defaults and Pyright configuration point to the uv environment and src directory. Reload the editor window after switching. Run `uv sync` first if the environment is absent.
