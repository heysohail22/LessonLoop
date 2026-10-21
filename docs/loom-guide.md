# Loom walkthrough — about 18 minutes

Record this yourself with your face visible. Do not show `.env`, API keys, account settings, or raw logs that might contain credentials. Keep the UI, source files, and tests ready before recording. Use real live requests or clearly identify prerecorded evidence; do not present fake-model tests as a live-model run.

## 0:00–1:30 — Explain the learner and problem

“This learner has finished Class 12, has limited English, and is new to AI. LessonLoop writes a RAG lesson and checks whether it meets a fixed quality bar. It revises failures instead of shipping the first fluent answer.”

Open Generation inputs and show the actual system prompt, user message, schema, and learned guidance. Distinguish a next-run preview from a captured attempt. Explain why the audience changes vocabulary, examples, and sequence.

## 1:30–5:00 — Run the complete workflow

Open http://localhost:8501, keep automatic mode on, and Generate. Explain the model call budget while it runs. Show whether the output passes, revises, reaches human review, or hits an error. Do not hide a real failure; explain the safe stopping behavior.

Show the lesson, final status, all checkpoints, attempt history, and downloadable JSON. Explain that all required checks must pass and Python owns the approval decision.

## 5:00–8:00 — Deliberately introduce an error

Insert “RAG always gives correct answers.” Run revisions on this draft. Show the failed evidence, requested changes, revised limitations, and reevaluation. Explain that the injected draft counts as attempt one and the system allows two revisions maximum. Disclose the narrow Python guarantee safeguard; the general semantic review is still performed by Gemini.

If the live provider is unavailable, show the saved real deliberate-error run in `submission/` and explain when it was captured. Keep a backup of that evidence before recording.

## 8:00–11:00 — Explain the architecture

Open `workflow.py`: generate, evaluate, finish, and pure conditional routes. Show the cap and the revision prompt receiving source notes, original goals, old lesson, and failed checks. Open `evaluation.py`: exactly nine strict booleans and Python `all(...)` approval. Explain why schema validation and factual quality are different.

Show that “sections changed” is detected from actual text, not a self-reported model claim.

## 11:00–14:30 — Memory and self-evolution

Open Memory & improvements. Restore a saved run after restarting or reopening the app. Show prompt version, feedback, distinct-run failure counts, and any proposal. Explain why three retries in one run count as one failure example and why deliberate demos do not train memory.

If a real proposal exists, show its provenance, then run the paired test (eight requests maximum), or inspect a recorded real experiment. Show both lesson versions, evaluator results, metrics, and accepted/rejected status. If rejected, say so; do not claim improvement. Explain the no-regression gate and how an accepted instruction is loaded into later runs.

If there is not enough genuine failure evidence, explain the threshold honestly and run `uv run python scripts/offline_demo.py` or show the deterministic automated test proving proposal/adoption logic with fake model responses. Clearly label the test as a test, not a real measured quality improvement.

## 14:30–16:30 — Tests and trade-offs

Run `uv run pytest`. Show tests for the retry limit, invalid evaluations, memory after restart, and promotion gates. Explain the separate live verification. Mention correlated writer/reviewer errors, short source notes, two benchmark scenarios, and the intentionally local single-user scope.

## 16:30–18:00 — Submission walkthrough

Show the README setup, final lesson Markdown, real run/rejection log, verification notes, and repository structure. Explain that this implementation focuses on Introduction to RAG; supporting another topic requires a reviewed brief, sources, and topic-specific content checks.

Before submitting, upload the lesson to a Google Doc or Notion page under your own account, verify reviewer access, copy the actual GitHub repo URL and Loom URL, and complete the supplied form yourself.
