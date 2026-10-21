from pathlib import Path
import importlib.util

from streamlit.testing.v1 import AppTest

from lessonloop.generation import Draft, Lesson

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_missing_key_disables_live_generation(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    # Prevent local developer credentials from affecting the test.
    monkeypatch.setattr('dotenv.dotenv_values', lambda *a, **kw: {})
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.button[0].disabled
    assert len(app.tabs) == 3
    assert any('Not evaluated' in item.value for item in app.markdown)


def test_generate_renders_unreviewed_lesson_without_network(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'fake-model')
    calls = []

    async def fake_complete(self, *, system, user):
        calls.append(user)
        return Lesson(**{name: 'Example lesson content' for name in Lesson.model_fields}).model_dump_json()

    async def fake_close(self):
        pass

    monkeypatch.setattr('lessonloop.gemini.GeminiModel.complete', fake_complete)
    monkeypatch.setattr('lessonloop.gemini.GeminiModel.close', fake_close)
    app = AppTest.from_file(str(APP)).run()
    app.button[0].click().run()
    assert not app.exception
    assert len(calls) == 1
    assert app.session_state['draft']['status'] == 'unreviewed'
    assert any('Example lesson content' in item.value for item in app.markdown)
    app.run()
    assert len(calls) == 1  # Rerenders must not trigger another paid request.


def test_generation_error_is_sanitized(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'fake-model')

    async def broken(self, *, system, user):
        raise RuntimeError('secret-provider-detail')

    async def fake_close(self):
        pass

    monkeypatch.setattr('lessonloop.gemini.GeminiModel.complete', broken)
    monkeypatch.setattr('lessonloop.gemini.GeminiModel.close', fake_close)
    app = AppTest.from_file(str(APP)).run()
    app.button[0].click().run()
    assert not app.exception
    assert 'Could not generate' in app.error[0].value
    assert 'secret-provider-detail' not in app.error[0].value


def test_evaluation_and_changed_lesson_clear_approval(monkeypatch):
    from lessonloop.evaluation import Evaluation
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'fake-model')
    calls = []

    async def fake_complete(self, *, system, user):
        calls.append(self.response_type)
        if self.response_type is Evaluation:
            return Evaluation(checks=[{'id': f'C{i}', 'passed': True, 'evidence': 'Example excerpt', 'reason': 'Met', 'required_change': 'None needed'} for i in range(1, 10)]).model_dump_json()
        return Lesson(**{name: 'Example lesson content' for name in Lesson.model_fields}).model_dump_json()

    async def fake_close(self):
        pass

    monkeypatch.setattr('lessonloop.gemini.GeminiModel.complete', fake_complete)
    monkeypatch.setattr('lessonloop.gemini.GeminiModel.close', fake_close)
    app = AppTest.from_file(str(APP)).run()
    app.button[0].click().run()
    app.button(key='evaluate').click().run()
    assert not app.exception
    assert any('Approved by rubric' in x.value for x in app.success)
    assert len(calls) == 2
    app.run()
    assert len(calls) == 2
    app.button(key='inject_error').click().run()
    assert 'evaluation' not in app.session_state
    app.button(key='evaluate').click().run()
    assert not app.exception
    assert any('Rejected' in x.value for x in app.error)
    assert any('C6 · FAIL' in x.value for x in app.markdown)
