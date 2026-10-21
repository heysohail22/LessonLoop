"""Shared UI/CLI settings; .env reads never mutate os.environ."""
import os
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def settings() -> tuple[str, str]:
    values = dotenv_values(ROOT / '.env')
    def value(name: str) -> str:
        return (os.environ.get(name) or values.get(name) or '').strip()
    return value('GEMINI_API_KEY'), value('GEMINI_MODEL')


def database_path() -> Path:
    return Path(os.environ.get('LESSONLOOP_DB', str(ROOT / 'data' / 'lessonloop.sqlite3'))).expanduser()
