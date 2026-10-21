"""Local LessonLoop workbench. Start with uv run streamlit run app.py."""
import asyncio
import json

import streamlit as st
from pydantic import ValidationError

from lessonloop.generation import Draft, Lesson, generate_draft, rag_brief
from lessonloop.gemini import GeminiModel, GenerationError
from lessonloop.evaluation import CheckResult, Evaluation, evaluate_lesson, fingerprint, RUBRIC_VERSION

from lessonloop.workflow import WorkflowResult
from lessonloop.memory import Memory
from lessonloop.settings import settings, database_path
from lessonloop.service import run_and_remember
from lessonloop.evolution import propose_improvements, test_improvement





async def create_draft(key: str, model_name: str) -> Draft:
    model = GeminiModel(api_key=key, model=model_name)
    try:
        return await generate_draft(model, rag_brief())
    finally:
        await model.close()


async def review_draft(key: str, model_name: str, draft: Draft) -> Evaluation:
    model = GeminiModel(api_key=key, model=model_name, response_type=Evaluation)
    try:
        return await evaluate_lesson(model, draft.lesson, rag_brief())
    finally:
        await model.close()


async def run_full_workflow(key: str, model_name: str, *, seed: Lesson | None = None, on_progress=None) -> tuple[str, WorkflowResult]:
    writer = GeminiModel(api_key=key, model=model_name)
    reviewer = GeminiModel(api_key=key, model=model_name, response_type=Evaluation)
    try:
        run_id, result = await run_and_remember(Memory(database_path()), writer, reviewer, model_name, seed=seed, on_progress=on_progress)
        return run_id, result
    finally:
        await writer.close()
        await reviewer.close()


def execute_workflow(key: str, model_name: str, seed: Lesson | None = None) -> None:
    # Clear prior outcomes before starting so a failed new run cannot show old approval.
    for name in ('workflow', 'draft', 'evaluation', 'evaluation_hash', 'run_id'):
        st.session_state.pop(name, None)
    with st.status('Running lesson workflow…', expanded=True) as progress:
        try:
            run_id, result = asyncio.run(run_full_workflow(key, model_name, seed=seed, on_progress=st.write))
            st.session_state['run_id'] = run_id
            st.session_state['workflow'] = result.model_dump()
            st.session_state['draft_model'] = model_name
            latest = result.attempts[-1]
            if latest.lesson:
                st.session_state['draft'] = Draft(lesson=latest.lesson).model_dump()
                if latest.evaluation:
                    st.session_state['evaluation'] = latest.evaluation.model_dump()
                    st.session_state['evaluation_hash'] = fingerprint(latest.lesson)
            progress.update(label={'approved':'Lesson approved', 'needs_human_review':'Needs human review — retry limit reached', 'error':'Workflow stopped with an error'}[result.status], state='complete' if result.status == 'approved' else 'error', expanded=result.status != 'approved')
        except Exception:
            progress.update(label='Workflow could not finish', state='error')
            st.error('The workflow stopped unexpectedly. No lesson was approved. Try starting a new run.')


def render_attempts() -> None:
    if 'workflow' not in st.session_state:
        return
    import json
    result = WorkflowResult.model_validate(st.session_state['workflow'])
    st.subheader('Attempt history & rejection log')
    if result.status == 'needs_human_review':
        st.warning('Needs human review. Three attempts were evaluated; the last lesson still has failed checkpoints.')
    elif result.status == 'error':
        st.error('This run stopped with an error. No lesson was approved.')
    for attempt in result.attempts:
        label = 'Error' if attempt.error else ('Passed' if attempt.evaluation and attempt.evaluation.approved else 'Rejected')
        with st.expander(f'Attempt {attempt.number} · {label}', expanded=bool(attempt.error)):
            if attempt.number > 1:
                st.write('**Sections changed from previous attempt:**', ', '.join(attempt.changed_sections) or 'No sections changed.')
                st.caption('Changes are detected by comparing section text; a change alone does not prove a fix.')
            if attempt.error:
                st.error(attempt.error)
            if attempt.evaluation:
                for check in attempt.evaluation.checks:
                    if not check.passed:
                        st.write(f'**{check.id} failed:** {check.reason}')
                        st.write('**Evidence:**', check.evidence)
                        st.write('**Requested correction:**', check.required_change)
                st.json(attempt.evaluation.model_dump())
            if attempt.lesson:
                st.markdown(markdown(Draft(lesson=attempt.lesson), label))
    st.download_button('Download workflow & rejection log', json.dumps(result.model_dump(mode='json'), indent=2), 'lessonloop-run.json', 'application/json')


async def experiment(key: str, model_name: str, prompt_id: str) -> dict:
    writer = GeminiModel(api_key=key, model=model_name)
    reviewer = GeminiModel(api_key=key, model=model_name, response_type=Evaluation)
    try:
        return await test_improvement(Memory(database_path()), prompt_id, writer, reviewer, model_name, on_progress=st.write)
    finally:
        await writer.close()
        await reviewer.close()


def render_memory(key: str, model_name: str) -> None:
    memory = Memory(database_path())
    active = memory.active_prompt()
    st.subheader('Memory across runs')
    st.caption('SQLite keeps automatic runs, feedback, and prompt versions after restart. This is a local single-user workbench.')
    st.write('**Active prompt:**', active['id'])
    st.write(active['instruction'] or 'Original teaching instructions; no learned additions yet.')
    runs = memory.runs()
    if runs:
        run_id = st.selectbox('Saved run', [run['id'] for run in runs], key='saved_run', format_func=lambda value: next(f"{r['created_at'][:19]} · {r['status']} · {r['kind']} · {r['id'][:8]}" for r in runs if r['id'] == value))
        saved = memory.run(run_id)
        st.write('**Prompt used:**', saved['prompt_version'])
        if saved['result']:
            st.download_button('Download saved run', saved['result'], f'{run_id}.json', 'application/json')
            if st.button('Open saved run', key='restore_run'):
                result = WorkflowResult.model_validate_json(saved['result'])
                st.session_state['workflow'] = result.model_dump()
                st.session_state['run_id'] = run_id
                st.session_state['draft_model'] = saved['model']
                for name in ('draft', 'evaluation', 'evaluation_hash'):
                    st.session_state.pop(name, None)
                latest = result.attempts[-1]
                if latest.lesson:
                    st.session_state['draft'] = Draft(lesson=latest.lesson).model_dump()
                    if latest.evaluation:
                        st.session_state['evaluation'] = latest.evaluation.model_dump()
                        st.session_state['evaluation_hash'] = fingerprint(latest.lesson)
                st.rerun()
        else:
            st.warning('This run did not save a completed result. It may have been interrupted; start a new run.')
        with st.form('feedback'):
            checkpoint = st.selectbox('Checkpoint needing improvement', [f'C{i}' for i in range(1, 10)], key='feedback_checkpoint')
            comment = st.text_area('Your feedback', key='feedback_text', max_chars=1000, help='Describe the teaching issue. Do not include credentials or personal data.')
            if st.form_submit_button('Save feedback'):
                if comment.strip():
                    memory.add_feedback(run_id, checkpoint, comment)
                    propose_improvements(memory)
                    st.success('Feedback saved. It contributes to repeated-failure analysis; the original evaluation stays unchanged.')
                else:
                    st.error('Enter feedback before saving.')
    else:
        st.info('Run the automatic workflow to build persistent history.')
    st.subheader('Learn from repeated failures')
    st.caption('Two distinct normal runs must fail the same check before a proposal is created. Demo runs do not train memory. The rubric never changes to make passing easier.')
    failures = memory.repeated_failures()
    if failures:
        st.json({checkpoint: len(ids) for checkpoint, ids in failures.items()})
    if st.button('Find improvement proposals'):
        propose_improvements(memory)
    for prompt in memory.prompts():
        if prompt['id'] == 'base-v1':
            continue
        with st.expander(f"{prompt['id']} · {prompt['status']} · {prompt['checkpoint']}"):
            st.write(prompt['instruction'])
            st.write('**Failure evidence (run IDs):**', json.loads(prompt['evidence']))
            if prompt['experiment']:
                st.json(json.loads(prompt['experiment']))
            if prompt['status'] in ('proposed', 'error') and prompt['parent_id'] == active['id']:
                st.caption('Tests old and proposed prompts on two fixed scenarios: eight paid requests maximum. Adoption requires fewer target and total failures with no observed checkpoint regressions.')
                if st.button('Test and adopt if better', key='test_' + prompt['id'], disabled=not bool(key and model_name)):
                    with st.status('Comparing prompt versions…'):
                        try:
                            report = asyncio.run(experiment(key, model_name, prompt['id']))
                            if report['adopted']:
                                st.success('Improvement adopted. Future automatic runs will use it.')
                            else:
                                st.info('No proven improvement. The existing prompt remains active.')
                            st.json(report)
                        except Exception:
                            st.error('The experiment could not finish. The active prompt was not changed; you can retry the proposal.')


def current_review(draft: Draft) -> Evaluation | None:
    if st.session_state.get('evaluation_hash') != fingerprint(draft.lesson):
        return None
    value = st.session_state.get('evaluation')
    return Evaluation.model_validate(value) if value else None


def markdown(draft: Draft, status: str = "Unreviewed draft") -> str:
    lesson = draft.lesson
    sections = [('What is RAG?', lesson.what_it_is), ('Why it matters', lesson.why_it_matters),
                ('How it works', lesson.how_it_works), ('Worked example', lesson.worked_example),
                ('Limitations', lesson.limitations), ('Try it yourself', lesson.exercise),
                ('Answer explained', lesson.answer_explanation)]
    return f'# {lesson.title}\n\nStatus: {status}\n\n' + '\n\n'.join(f'## {name}\n\n{text}' for name, text in sections)


def main() -> None:
    st.set_page_config(page_title='LessonLoop · Lesson studio', page_icon='📖', layout='wide')
    st.caption('LESSONLOOP / LESSON STUDIO')
    st.title('A clearer first lesson.')
    st.write('Generate an introduction to RAG for a learner starting from zero.')
    st.info('Generate, evaluate, and revise automatically. A lesson gets at most three attempts. Runs are saved locally; tested prompt improvements carry into future runs.')
    key, configured_model = settings()
    brief = rag_brief()
    with st.sidebar:
        st.subheader('Your workspace')
        st.caption('Local development · Gemini')
        if key:
            st.success('API key configured')
        else:
            st.warning('Add GEMINI_API_KEY to your local .env file.')
        st.write('**Audience**')
        st.write(brief.learner)
        st.caption('The API key stays on the server and is never displayed here.')
    lesson_tab, brief_tab, checks_tab, memory_tab = st.tabs(['Create lesson', 'Teaching brief', 'Quality checkpoints', 'Memory & improvements'])
    with lesson_tab:
        automatic = st.checkbox('Automatically evaluate and revise', value=True, key='automatic_mode', help='Up to 3 attempts and 6 Gemini requests. Turn off to inspect a single draft manually.')
        with st.form('generate'):
            st.selectbox('Topic', [brief.topic], help='This first version supports RAG. More topics need their own reference packs.')
            model_name = st.text_input('Gemini model', value=configured_model, placeholder='Enter a model ID available to your account')
            st.caption('Automatic mode uses up to six live Gemini requests and may use paid quota.')
            submitted = st.form_submit_button('Generate lesson', type='primary', disabled=not bool(key))
        if submitted:
            if not model_name.strip():
                st.error('Enter a Gemini model ID, or set GEMINI_MODEL in .env.')
            else:
                if automatic:
                    execute_workflow(key, model_name.strip())
                else:
                    with st.status('Generating your lesson…', expanded=True) as status:
                        st.write('Preparing learner brief and reference notes.')
                        try:
                            draft = asyncio.run(create_draft(key, model_name.strip()))
                            st.session_state.pop('workflow', None)
                            st.session_state.pop('run_id', None)
                            st.session_state.pop('evaluation', None)
                            st.session_state.pop('evaluation_hash', None)
                            st.session_state['draft'] = draft.model_dump()
                            st.session_state['draft_model'] = model_name.strip()
                            status.update(label='Draft generated · not evaluated', state='complete', expanded=False)
                        except ValidationError:
                            status.update(label='Generation failed', state='error')
                            st.error('The response did not contain all required lesson sections. Try again.')
                        except GenerationError as error:
                            status.update(label='Generation failed', state='error')
                            st.error(str(error))
                        except Exception:
                            status.update(label='Generation failed', state='error')
                            st.error('Could not generate a lesson. Check your model ID, API key, quota, and connection. No draft was approved.')
        if 'draft' in st.session_state:
            draft = Draft.model_validate(st.session_state['draft'])
            st.divider()
            if st.button('Run revisions on this draft', key='revise_workflow', disabled=not bool(key)):
                if model_name.strip():
                    execute_workflow(key, model_name.strip(), seed=draft.lesson)
                    st.rerun()
                else:
                    st.error('Enter a Gemini model ID before starting revisions.')
            if st.button('Evaluate lesson', type='primary', disabled=not bool(key), key='evaluate'):
                st.session_state.pop('workflow', None)
                st.session_state.pop('run_id', None)
                st.session_state.pop('evaluation', None)
                st.session_state.pop('evaluation_hash', None)
                if not model_name.strip():
                    st.error('Enter a Gemini model ID before evaluating.')
                else:
                    with st.spinner('Checking accuracy, language, examples, and teaching flow…'):
                        try:
                            review = asyncio.run(review_draft(key, model_name.strip(), draft))
                            st.session_state['evaluation'] = review.model_dump()
                            st.session_state['evaluation_hash'] = fingerprint(draft.lesson)
                        except ValidationError:
                            st.error('The evaluator returned an incomplete or invalid checklist. The lesson remains unreviewed. Try evaluation again.')
                        except GenerationError as error:
                            st.error(str(error))
                        except Exception:
                            st.error('Evaluation could not finish. No lesson was approved. Try again.')
            st.caption('Evaluate makes a separate live Gemini request and may use paid quota.')
            with st.expander('Test a deliberate error'):
                st.write('Replace the limitations section with “RAG always gives correct answers.” Then click Run revisions on this draft to demonstrate rejection and repair, or Evaluate lesson for one review. This changes your current draft and clears its prior evaluation.')
                if st.button('Insert deliberate error', key='inject_error'):
                    draft = draft.model_copy(update={'lesson': draft.lesson.model_copy(update={'limitations': 'RAG always gives correct answers.'})})
                    st.session_state['draft'] = draft.model_dump()
                    st.session_state.pop('workflow', None)
                    st.session_state.pop('run_id', None)
                    st.session_state.pop('evaluation', None)
                    st.session_state.pop('evaluation_hash', None)
            review = current_review(draft)
            review_status = 'Unreviewed draft'
            if review is None:
                st.warning('Unreviewed draft — no valid quality evaluation is attached.')
            elif review.approved:
                review_status = 'Approved by rubric'
                st.success('Approved by rubric — all 9 checkpoints passed.')
            else:
                review_status = 'Rejected — needs revision'
                st.error(f'Rejected — {sum(not c.passed for c in review.checks)} checkpoint(s) failed. See Quality checkpoints for feedback.')
            st.caption(f"Generated with {st.session_state.get('draft_model', 'Gemini')}. Automatic runs are saved to local SQLite. Manual drafts stay in this browser session until downloaded.")
            st.markdown(markdown(draft, review_status))
            st.download_button('Download lesson (.md)', markdown(draft, review_status), 'rag-lesson-draft.md', 'text/markdown')
            with st.expander('Structured output'):
                st.json(draft.model_dump())
                st.caption('The original draft remains unreviewed; evaluation and approval are tracked in the separate report.')
                st.download_button('Download JSON', draft.model_dump_json(indent=2), 'rag-lesson-draft.json', 'application/json')
        else:
            st.subheader('Your lesson will appear here')
            st.write('You will get an explanation, a worked example, limitations, and a practice question.')
        render_attempts()
    with brief_tab:
        st.subheader('What this lesson should teach')
        for goal in brief.goals:
            st.write(f'• {goal}')
        st.subheader('Reference notes')
        st.caption('Curated summaries supplied to the generator. Sources are not fetched during generation.')
        for reference_id, note in brief.references.items():
            st.write(f'**{reference_id}** — {note}')
    with checks_tab:
        st.subheader('The quality bar')
        review = current_review(Draft.model_validate(st.session_state['draft'])) if 'draft' in st.session_state else None
        st.caption('Every checkpoint must pass. Invalid or missing evaluation results never approve a lesson. Model judgments can still be wrong.')
        by_id: dict[str, CheckResult] = {check.id: check for check in review.checks} if review else {}
        for check in brief.checkpoints:
            result = by_id.get(check.id)
            label = ('PASS' if result.passed else 'FAIL') if result else 'Not evaluated'
            with st.container(border=True):
                st.write(f'**{check.id} · {label}**')
                st.write(check.condition)
                if result:
                    st.write('**Evidence:**', result.evidence)
                    st.write('**Reason:**', result.reason)
                    if not result.passed:
                        st.write('**Required change:**', result.required_change)
        if review:
            report = {'rubric_version': RUBRIC_VERSION, 'lesson_sha256': st.session_state['evaluation_hash'], 'approved': review.approved, **review.model_dump()}
            import json
            st.download_button('Download evaluation report', json.dumps(report, indent=2), 'evaluation.json', 'application/json')

    with memory_tab:
        render_memory(key, model_name.strip())



if __name__ == '__main__':
    main()
