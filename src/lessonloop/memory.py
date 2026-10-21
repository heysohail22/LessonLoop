"""Local persistent runs, feedback and versioned prompt experiments (SQLite)."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from lessonloop.workflow import WorkflowResult
from lessonloop.evaluation import RUBRIC_VERSION


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Memory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS prompts (
                id TEXT PRIMARY KEY, parent_id TEXT, checkpoint TEXT,
                instruction TEXT NOT NULL, status TEXT NOT NULL,
                evidence TEXT NOT NULL, experiment TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
                model TEXT NOT NULL, prompt_version TEXT NOT NULL,
                brief TEXT NOT NULL, result TEXT, kind TEXT NOT NULL DEFAULT 'normal'
            );
            CREATE TABLE IF NOT EXISTS feedback (
                run_id TEXT NOT NULL REFERENCES runs(id), checkpoint TEXT NOT NULL,
                comment TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(run_id, checkpoint)
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO prompts VALUES (?,NULL,NULL,?,?,?,NULL,?)', ('base-v1', '', 'accepted', '[]', now()))
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('active_prompt', 'base-v1'))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('PRAGMA busy_timeout=10000')
                yield db
        finally:
            db.close()

    def active_prompt(self) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT p.* FROM prompts p JOIN meta m ON m.value=p.id WHERE m.key='active_prompt'").fetchone()
            return dict(row)

    def prompt(self, prompt_id: str) -> dict:
        with self.connect() as db:
            row = db.execute('SELECT * FROM prompts WHERE id=?', (prompt_id,)).fetchone()
            if row is None: raise ValueError('Unknown prompt version')
            return dict(row)

    def prompts(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM prompts ORDER BY created_at DESC')]

    def start_run(self, model: str, brief: dict, prompt_version: str, *, kind: str = 'normal') -> str:
        run_id = str(uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)', (run_id, now(), 'running', model, prompt_version, json.dumps(brief), None, kind))
        return run_id

    def finish_run(self, run_id: str, result: WorkflowResult) -> None:
        with self.connect() as db:
            db.execute('UPDATE runs SET status=?,result=? WHERE id=?', (result.status, result.model_dump_json(), run_id))

    def fail_run(self, run_id: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE runs SET status='error' WHERE id=?", (run_id,))

    def runs(self, limit: int = 30) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,created_at,status,model,prompt_version,kind FROM runs ORDER BY created_at DESC LIMIT ?', (min(max(limit, 1), 200),))]

    def run(self, run_id: str) -> dict:
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if row is None: raise ValueError('Unknown run')
            return dict(row)

    def add_feedback(self, run_id: str, checkpoint: str, comment: str) -> None:
        if checkpoint not in {f'C{i}' for i in range(1, 10)}: raise ValueError('Unknown checkpoint')
        if not 1 <= len(comment.strip()) <= 1000: raise ValueError('Feedback must contain 1-1000 characters')
        with self.connect() as db:
            db.execute('INSERT INTO feedback VALUES (?,?,?,?) ON CONFLICT(run_id,checkpoint) DO UPDATE SET comment=excluded.comment,created_at=excluded.created_at', (run_id, checkpoint, comment.strip(), now()))

    def repeated_failures(self) -> dict[str, list[str]]:
        """Count distinct normal runs, not three retries as three independent failures."""
        failures: dict[str, set[str]] = {}
        with self.connect() as db:
            rows = db.execute("SELECT id,result FROM runs WHERE kind='normal' AND result IS NOT NULL").fetchall()
            for row in rows:
                result = WorkflowResult.model_validate_json(row['result'])
                if result.rubric_version != RUBRIC_VERSION:
                    continue
                for attempt in result.attempts:
                    if attempt.evaluation:
                        for check in attempt.evaluation.checks:
                            if not check.passed: failures.setdefault(check.id, set()).add(row['id'])
            for row in db.execute("SELECT f.run_id,f.checkpoint FROM feedback f JOIN runs r ON r.id=f.run_id WHERE r.kind='normal'"):
                failures.setdefault(row['checkpoint'], set()).add(row['run_id'])
        return {key: sorted(ids) for key, ids in failures.items()}

    def propose(self, checkpoint: str, instruction: str, evidence: list[str], parent_id: str) -> str:
        with self.connect() as db:
            existing = db.execute('SELECT id FROM prompts WHERE parent_id=? AND checkpoint=?', (parent_id, checkpoint)).fetchone()
            if existing: return existing['id']
            prompt_id = 'prompt-' + uuid4().hex[:12]
            db.execute('INSERT INTO prompts VALUES (?,?,?,?,?,?,NULL,?)', (prompt_id, parent_id, checkpoint, instruction, 'proposed', json.dumps(evidence), now()))
        return prompt_id

    def claim_experiment(self, prompt_id: str) -> bool:
        with self.connect() as db:
            return db.execute("UPDATE prompts SET status='testing' WHERE id=? AND status IN ('proposed','error')", (prompt_id,)).rowcount == 1

    def complete_experiment(self, prompt_id: str, report: dict, accepted: bool) -> bool:
        """Atomic compare-and-swap prevents concurrent tests overwriting newer memory."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            candidate = db.execute('SELECT * FROM prompts WHERE id=?', (prompt_id,)).fetchone()
            if candidate is None or candidate['status'] != 'testing':
                raise ValueError('Experiment was not claimed')
            active = db.execute("SELECT value FROM meta WHERE key='active_prompt'").fetchone()['value']
            promote = accepted and candidate['parent_id'] == active
            status = 'accepted' if promote else ('stale' if accepted else 'rejected')
            db.execute('UPDATE prompts SET status=?,experiment=? WHERE id=?', (status, json.dumps(report), prompt_id))
            if promote: db.execute("UPDATE meta SET value=? WHERE key='active_prompt'", (prompt_id,))
        return promote

    def experiment_error(self, prompt_id: str, report: dict | None = None) -> None:
        with self.connect() as db:
            db.execute("UPDATE prompts SET status='error',experiment=? WHERE id=?", (json.dumps(report or {"error": "Experiment did not complete; no prompt was adopted."}), prompt_id))
