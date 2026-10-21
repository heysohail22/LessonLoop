"""Ordinary tests have isolated temporary memory and no tracing."""
import pytest


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    monkeypatch.setenv('LESSONLOOP_DB', str(tmp_path/'test-memory.sqlite3'))
    monkeypatch.setenv('LANGSMITH_TRACING', 'false')
    monkeypatch.setenv('LANGCHAIN_TRACING_V2', 'false')
