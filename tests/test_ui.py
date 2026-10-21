from pathlib import Path
import importlib.util

from streamlit.testing.v1 import AppTest

from lessonloop.generation import Draft, Lesson

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_missing_key_disables_live_generation(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    # Prevent local developer credentials from affecting the test.
    monkeypatch.setattr('lessonloop.settings.dotenv_values', lambda *a, **kw: {})
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.button[0].disabled
    assert len(app.tabs) == 4
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
    app.checkbox[0].uncheck().run()
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
    app.checkbox[0].uncheck().run()
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
    app.checkbox[0].uncheck().run()
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


def test_automatic_workflow_revises_and_shows_log(monkeypatch):
    import json
    from lessonloop.evaluation import Evaluation
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'fake-model')
    reviews = []
    writer_inputs = []

    async def fake_complete(self, *, system, user):
        if self.response_type is Evaluation:
            reviews.append(user)
            passing = len(reviews) > 1
            return json.dumps({'checks': [{'id': f'C{i}', 'passed': passing or i != 5, 'evidence': 'Example', 'reason': 'Met' if passing else 'Define jargon', 'required_change': 'Explain the term'} for i in range(1, 10)]})
        writer_inputs.append(json.loads(user))
        content = 'First draft' if len(writer_inputs) == 1 else 'Revised draft'
        return Lesson(**{name: content for name in Lesson.model_fields}).model_dump_json()

    async def fake_close(self):
        pass

    monkeypatch.setattr('lessonloop.gemini.GeminiModel.complete', fake_complete)
    monkeypatch.setattr('lessonloop.gemini.GeminiModel.close', fake_close)
    app = AppTest.from_file(str(APP)).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['workflow']['status'] == 'approved'
    assert len(app.session_state['workflow']['attempts']) == 2
    assert writer_inputs[1]['failures'][0]['id'] == 'C5'
    assert any('Attempt 1' in e.label for e in app.expander)
    assert any('Attempt 2' in e.label for e in app.expander)
    app.run()
    assert len(reviews) == 2


def test_saved_run_restores_in_new_ui_session_and_feedback_persists(monkeypatch):
    from lessonloop.memory import Memory
    from lessonloop.settings import database_path
    from lessonloop.workflow import WorkflowResult, Attempt
    from lessonloop.evaluation import Evaluation
    review = Evaluation(checks=[{'id':f'C{i}', 'passed':True, 'evidence':'Excerpt', 'reason':'Met', 'required_change':'None needed'} for i in range(1,10)])
    memory=Memory(database_path())
    from lessonloop.generation import rag_brief
    run_id=memory.start_run('test-model',rag_brief().model_dump(),'base-v1')
    result=WorkflowResult(status='approved', attempts=[Attempt(number=1,lesson=Lesson(**{field:'Saved lesson' for field in Lesson.model_fields}),evaluation=review)])
    memory.finish_run(run_id,result)
    app=AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert 'draft' not in app.session_state
    app.button(key='restore_run').click().run()
    assert not app.exception
    assert app.session_state['draft']['lesson']['title']=='Saved lesson'
    app.selectbox(key='feedback_checkpoint').select('C5')
    app.text_area(key='feedback_text').input('Explain the terms more clearly.')
    app.button(key='FormSubmitter:feedback-Save feedback').click().run()
    assert not app.exception
    assert Memory(database_path()).repeated_failures()['C5']==[run_id]
