"""Local LessonLoop workbench. Start with uv run streamlit run app.py."""
import asyncio
import json
from pathlib import Path
import re

import streamlit as st
from pydantic import ValidationError

from lessonloop.generation import Draft, Lesson, GenerationInputs, build_generation_inputs, generate_draft, rag_brief
from lessonloop.gemini import GeminiModel, GenerationError
from lessonloop.evaluation import CheckResult, Evaluation, evaluate_lesson, fingerprint, RUBRIC_VERSION

from lessonloop.workflow import WorkflowResult
from lessonloop.memory import Memory
from lessonloop.settings import settings, database_path
from lessonloop.service import run_and_remember
from lessonloop.evolution import propose_improvements, test_improvement
from lessonloop.ui import STYLE, CHECK_NAMES, SECTION_NAMES, pipeline_html, outcome_summary, compare_attempts





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


def execute_workflow(key: str, model_name: str, seed: Lesson | None = None, pipeline_slot=None) -> None:
    # Clear prior outcomes before starting so a failed new run cannot show old approval.
    for name in ('workflow', 'draft', 'evaluation', 'evaluation_hash', 'run_id', 'recorded_preview'):
        st.session_state.pop(name, None)
    st.session_state['run_events'] = []
    st.session_state['active_attempt'] = 0
    def show_progress(message: str) -> None:
        st.session_state['run_events'].append(message)
        if pipeline_slot is not None:
            match = re.search(r'Attempt (\d+)', message)
            if match:
                st.session_state['active_attempt'] = int(match.group(1))
            number = st.session_state['active_attempt']
            stage = 'check' if 'evaluating' in message else ('revise' if 'revising' in message else 'write')
            if message.startswith('All checkpoints passed'):
                stage = 'approved'
            elif message.startswith('Retry limit reached'):
                stage = 'needs_human_review'
            elif message.startswith('Run stopped'):
                stage = 'error'
            pipeline_slot.markdown(pipeline_html(stage=stage, attempt=number), unsafe_allow_html=True)
        st.write(message)

    with st.status('Running lesson workflow…', expanded=True) as progress:
        try:
            run_id, result = asyncio.run(run_full_workflow(key, model_name, seed=seed, on_progress=show_progress))
            st.session_state['run_id'] = run_id
            st.session_state['workflow'] = result.model_dump()
            st.session_state['draft_model'] = model_name
            latest = result.attempts[-1]
            if latest.lesson:
                st.session_state['draft'] = Draft(lesson=latest.lesson).model_dump()
                if latest.evaluation:
                    st.session_state['evaluation'] = latest.evaluation.model_dump()
                    st.session_state['evaluation_hash'] = fingerprint(latest.lesson)
            if pipeline_slot is not None:
                pipeline_slot.markdown(pipeline_html(stage=result.status, attempt=len(result.attempts)), unsafe_allow_html=True)
            progress.update(label={'approved':'Lesson approved', 'needs_human_review':'Needs human review — retry limit reached', 'error':'Workflow stopped with an error'}[result.status], state='complete' if result.status == 'approved' else 'error', expanded=result.status != 'approved')
        except Exception:
            progress.update(label='Workflow could not finish', state='error')
            st.error('The workflow stopped unexpectedly. No lesson was approved. Try starting a new run.')


def load_recorded_demo() -> None:
    """Load real captured evidence; no model call or memory training."""
    folder = Path(__file__).resolve().parent / 'submission' / 'error-demo'
    try:
        result = WorkflowResult.model_validate_json((folder / 'run.json').read_text())
        provenance = json.loads((folder / 'provenance.json').read_text())
    except (OSError, ValueError):
        st.error('The recorded demo is unavailable. Generate a lesson to explore a new run.')
        return
    for name in ('draft', 'evaluation', 'evaluation_hash', 'run_id'):
        st.session_state.pop(name, None)
    st.session_state['workflow'] = result.model_dump()
    st.session_state['recorded_preview'] = True
    st.session_state['draft_model'] = provenance['model']
    latest = result.attempts[-1]
    if latest.lesson:
        st.session_state['draft'] = Draft(lesson=latest.lesson).model_dump()
        if latest.evaluation:
            st.session_state['evaluation'] = latest.evaluation.model_dump()
            st.session_state['evaluation_hash'] = fingerprint(latest.lesson)


def render_attempts() -> None:
    if 'workflow' not in st.session_state:
        return
    result = WorkflowResult.model_validate(st.session_state['workflow'])
    st.divider()
    st.subheader('Follow the decisions')
    st.caption('Read the journey from first draft to final decision. Each revision is checked against the full rubric again.')
    if result.status == 'needs_human_review':
        st.warning('Needs human review. Three attempts were evaluated; the last lesson still has failed checkpoints.')
    elif result.status == 'error':
        st.error('This run stopped with an error. No lesson was approved.')
    rows = []
    for attempt in result.attempts:
        label = 'Error' if attempt.error else ('Passed' if attempt.evaluation and attempt.evaluation.approved else 'Rejected')
        rows.append({'Attempt': attempt.number, 'Decision':label,
                     'Failed checks': ', '.join(c.id for c in attempt.evaluation.checks if not c.passed) if attempt.evaluation else 'Not evaluated',
                     'Changed sections': ', '.join(SECTION_NAMES.get(section,section) for section in attempt.changed_sections) or ('First draft' if attempt.number==1 else 'No changes')})
    st.dataframe(rows, hide_index=True, width='stretch')
    compare_attempts(result)
    st.markdown('#### Full attempt history & rejection log')
    for attempt in result.attempts:
        label = 'Error' if attempt.error else ('Passed' if attempt.evaluation and attempt.evaluation.approved else 'Rejected')
        with st.expander(f'Attempt {attempt.number} · {label}', expanded=bool(attempt.error)):
            if attempt.error:
                st.error(attempt.error)
            if attempt.evaluation:
                failed = [check for check in attempt.evaluation.checks if not check.passed]
                if not failed:
                    st.success('All nine requirements passed in this attempt.')
                for check in failed:
                    st.markdown(f'**{check.id} · {CHECK_NAMES[check.id]} — failed**')
                    st.write('**What the reviewer found:**', check.evidence)
                    st.write('**Why it failed:**', check.reason)
                    st.write('**Instruction for the next draft:**', check.required_change)
                st.caption('Complete structured review')
                st.json(attempt.evaluation.model_dump(), expanded=False)
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
    st.subheader('What the system remembers')
    st.caption('SQLite keeps automatic runs, feedback, and prompt versions after restart. This is a local single-user workbench.')
    versions = memory.prompts()
    stats = st.columns(3)
    stats[0].metric('Recent saved runs', len(memory.runs()))
    stats[1].metric('Improvement proposals', sum(p['id'] != 'base-v1' for p in versions))
    stats[2].metric('Accepted improvements', sum(p['status'] == 'accepted' and p['id'] != 'base-v1' for p in versions))
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
                st.session_state.pop('recorded_preview', None)
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
    st.divider()
    st.subheader('How failures become better instructions')
    st.markdown('**Notice a pattern → propose guidance → compare prompts → adopt only if better**')
    st.caption('Two distinct normal runs must fail the same check before a proposal is created. Demo runs do not train memory. The rubric never changes to make passing easier.')
    failures = memory.repeated_failures()
    if failures:
        st.dataframe([{'Checkpoint': checkpoint, 'Teaching rule': CHECK_NAMES[checkpoint], 'Distinct failing runs':len(ids), 'Evidence threshold': 'Ready for proposal' if len(ids)>=2 else 'Needs one more run'} for checkpoint,ids in sorted(failures.items())], hide_index=True, width='stretch')
    else:
        st.info('No repeated normal-run failures yet. The original prompt stays active until there is evidence to test a change.')
    if st.button('Find improvement proposals'):
        propose_improvements(memory)
    for prompt in memory.prompts():
        if prompt['id'] == 'base-v1':
            continue
        with st.expander(f"{prompt['id']} · {prompt['status']} · {prompt['checkpoint']}"):
            st.write(prompt['instruction'])
            st.write('**Failure evidence (run IDs):**', json.loads(prompt['evidence']))
            if prompt['experiment']:
                report = json.loads(prompt['experiment'])
                if 'baseline_failures' in report:
                    left, right = st.columns(2)
                    left.metric('Old prompt · failed checks', report['baseline_failures'])
                    right.metric('Proposed prompt · failed checks', report['candidate_failures'])
                    st.write('**Adoption decision:**', prompt['status'])
                    st.caption('Target failures and total failures must decrease, with no observed checkpoint regressions.')
                st.json(report, expanded=False)
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


def render_generation_inputs() -> None:
    st.subheader('What do we send to Gemini?')
    st.write('Inspect the instructions and information used to produce a lesson. New runs capture these messages before each writer call, including revisions.')
    st.code('System instructions + user message + output schema → Gemini → lesson JSON', language=None)
    memory = Memory(database_path())
    active = memory.active_prompt()
    choices = ['Next automatic run · preview', 'Next manual draft · preview']
    requests: dict[str, GenerationInputs | None] = {}
    seeds: dict[str, Lesson] = {}
    if 'workflow' in st.session_state:
        result = WorkflowResult.model_validate(st.session_state['workflow'])
        for attempt in result.attempts:
            label = f'Attempt {attempt.number} · ' + ('provided draft' if attempt.provided_draft else ('captured request' if attempt.generation_inputs else 'older run — inputs unavailable'))
            choices.append(label)
            requests[label] = attempt.generation_inputs
            if attempt.provided_draft and attempt.lesson:
                seeds[label] = attempt.lesson
    elif 'draft' in st.session_state:
        draft = Draft.model_validate(st.session_state['draft'])
        label = 'Current manual draft · captured request' if draft.generation_inputs else 'Current draft · inputs unavailable'
        choices.append(label)
        requests[label] = draft.generation_inputs
    default = len(choices)-1 if len(choices)>2 else (0 if st.session_state.get('automatic_mode', True) else 1)
    selected = st.selectbox('Inspect generation request', choices, index=default, key='generation_request')
    if selected == choices[0]:
        inputs = build_generation_inputs(rag_brief(), guidance=active['instruction'])
        st.info('Preview for the next automatic run. This is not evidence of a past request. A prompt improvement adopted later may change future requests.')
        st.caption('Active memory prompt version: ' + active['id'])
    elif selected == choices[1]:
        inputs = build_generation_inputs(rag_brief())
        st.info('Preview for manual generation. Manual drafts use the base writer instructions; automatic runs also load accepted guidance from memory.')
    elif selected in seeds:
        st.info('This attempt used a supplied draft. No writer request was made for it; the draft was sent directly to evaluation. Select the next attempt to inspect revision inputs.')
        st.json(seeds[selected].model_dump(), expanded=False)
        return
    else:
        inputs = requests[selected]
        if inputs is None:
            st.warning('This older result did not capture its original generation messages. They cannot be shown as exact past inputs. Select a preview, or start a new run to capture the real request.')
            return
        st.success('Captured writer input for this attempt. The same snapshot is included in its run/draft JSON download.')
    st.markdown('### 1. System prompt — how to write')
    st.caption('Passed to Gemini as system_instruction. It controls language, terminology, grounding, and output format.')
    st.code(inputs.system, language=None, wrap_lines=True)
    st.markdown('### 2. User message — what to teach')
    st.caption('Passed to Gemini as contents. It contains the topic, learner, learning goals, reference notes, and C1–C9. Revision requests also include the previous lesson and failed-check feedback.')
    st.json(json.loads(inputs.user), expanded=2)
    st.markdown('### 3. Required response structure')
    st.caption('Passed through response_json_schema with application/json. These fields define the lesson format; having them does not prove teaching quality.')
    st.json(inputs.response_schema, expanded=False)
    st.markdown('### 4. Accepted guidance from memory')
    if inputs.learned_guidance:
        st.code(inputs.learned_guidance, language=None, wrap_lines=True)
    else:
        st.write('No additional learned guidance is included in this request.')
    st.caption('Any learned guidance is already included in the system prompt shown above. No credentials or hidden model reasoning are displayed.')
    st.download_button('Download generation inputs', inputs.model_dump_json(indent=2), 'generation-inputs.json', 'application/json')


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
    st.markdown(STYLE, unsafe_allow_html=True)
    st.markdown('<div class="ll-kicker">LESSONLOOP / THE LESSON WORKBENCH</div>', unsafe_allow_html=True)
    st.title('From first draft to ready to teach.')
    st.markdown('<div class="ll-intro">Watch a beginner lesson get written, checked, and improved. Every decision has evidence. Every run has a stopping rule.</div>', unsafe_allow_html=True)
    workflow_panel = st.empty()
    key, configured_model = settings()
    brief = rag_brief()
    with st.sidebar:
        st.subheader('Your workspace')
        st.caption('LOCAL WORKSPACE · GEMINI')
        st.write('**Your workflow**')
        st.write('1. Generate a lesson\n2. Inspect the decision\n3. Compare revisions\n4. Explore saved memory')
        if key:
            st.success('API key configured')
        else:
            st.warning('Add GEMINI_API_KEY to your local .env file.')
        st.write('**Audience**')
        st.write(brief.learner)
        st.caption('The API key stays on the server and is never displayed here.')
    lesson_tab, inputs_tab, checks_tab, memory_tab = st.tabs(['Create lesson', 'Generation inputs', 'Quality checkpoints', 'Memory & improvements'])
    with lesson_tab:
        with st.container(border=True):
            introduction, demo = st.columns([3, 1])
            introduction.markdown('**See a real repair before making a live request.**')
            introduction.caption('The saved demo shows a rejected claim, the feedback, and the corrected lesson. No API calls.')
            if demo.button('Load recorded repair demo', key='load_demo', width='stretch'):
                load_recorded_demo()
        st.markdown('### Create a lesson')
        automatic = st.checkbox('Automatically evaluate and revise', value=True, key='automatic_mode', help='Up to 3 attempts and 6 Gemini requests. Turn off to inspect a single draft manually.')
        with st.form('generate'):
            st.selectbox('Topic', [brief.topic], help='This first version supports RAG. More topics need their own reference packs.')
            model_name = st.text_input('Gemini model', value=configured_model, placeholder='Enter a model ID available to your account')
            st.caption('Automatic mode uses up to six live Gemini requests and may use paid quota.')
            submitted = st.form_submit_button('Generate lesson', key='generate_submit', type='primary', disabled=not bool(key))
        if submitted:
            if not model_name.strip():
                st.error('Enter a Gemini model ID, or set GEMINI_MODEL in .env.')
            else:
                if automatic:
                    execute_workflow(key, model_name.strip(), pipeline_slot=workflow_panel)
                else:
                    with st.status('Generating your lesson…', expanded=True) as status:
                        st.write('Preparing learner brief and reference notes.')
                        try:
                            draft = asyncio.run(create_draft(key, model_name.strip()))
                            st.session_state.pop('recorded_preview', None)
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
            if st.session_state.get('recorded_preview'):
                st.info('Recorded live demonstration · you are exploring saved evidence, not a new model call. Changing this draft clears its saved approval.')
            st.markdown('### Your lesson and its decision')
            if st.button('Run revisions on this draft', key='revise_workflow', disabled=not bool(key)):
                if model_name.strip():
                    execute_workflow(key, model_name.strip(), seed=draft.lesson, pipeline_slot=workflow_panel)
                    st.rerun()
                else:
                    st.error('Enter a Gemini model ID before starting revisions.')
            if st.button('Evaluate lesson', type='primary', disabled=not bool(key), key='evaluate'):
                st.session_state.pop('recorded_preview', None)
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
                    st.session_state.pop('recorded_preview', None)
                    st.session_state.pop('workflow', None)
                    st.session_state.pop('run_id', None)
                    st.session_state.pop('evaluation', None)
                    st.session_state.pop('evaluation_hash', None)
            review = current_review(draft)
            report = WorkflowResult.model_validate(st.session_state['workflow']) if 'workflow' in st.session_state else None
            outcome_summary(report, review)
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
            st.markdown('### Your lesson starts here')
            st.write('Load the recorded demo to explore the system, or generate a new RAG lesson. The final lesson, reviewer evidence, and revision history will appear here.')
        render_attempts()
        final = WorkflowResult.model_validate(st.session_state['workflow']) if 'workflow' in st.session_state else None
        stage, count = ('ready', 0)
        if final:
            stage, count = final.status, len(final.attempts)
        elif 'draft' in st.session_state:
            last_review = current_review(Draft.model_validate(st.session_state['draft']))
            stage = ('approved' if last_review.approved else 'rejected') if last_review else 'draft_ready'
        workflow_panel.markdown(pipeline_html(stage=stage, attempt=count), unsafe_allow_html=True)
    with inputs_tab:
        render_generation_inputs()
    with checks_tab:
        st.subheader('Why did this lesson pass or fail?')
        st.write('Each checkpoint is a separate requirement. All nine must pass; there is no average score.')
        review = current_review(Draft.model_validate(st.session_state['draft'])) if 'draft' in st.session_state else None
        st.caption('Every checkpoint must pass. Invalid or missing evaluation results never approve a lesson. Model judgments can still be wrong.')
        by_id: dict[str, CheckResult] = {check.id: check for check in review.checks} if review else {}
        view = st.radio('Show checkpoints', ['All', 'Failed', 'Passed'], horizontal=True, key='checkpoint_filter')
        visible = 0
        for check in brief.checkpoints:
            result = by_id.get(check.id)
            if view == 'Failed' and (not result or result.passed):
                continue
            if view == 'Passed' and (not result or not result.passed):
                continue
            visible += 1
            label = ('PASS' if result.passed else 'FAIL') if result else 'Not evaluated'
            with st.container(border=True):
                st.write(f'**{check.id} · {label}** — {CHECK_NAMES[check.id]}')
                st.write(check.condition)
                if result:
                    st.write('**Evidence:**', result.evidence)
                    st.write('**Reason:**', result.reason)
                    if not result.passed:
                        st.write('**Required change:**', result.required_change)
        if not visible:
            st.info('No checkpoints match this filter. Unevaluated requirements are shown under All.')
        if review:
            report = {'rubric_version': RUBRIC_VERSION, 'lesson_sha256': st.session_state['evaluation_hash'], 'approved': review.approved, **review.model_dump()}
            import json
            st.download_button('Download evaluation report', json.dumps(report, indent=2), 'evaluation.json', 'application/json')

    with memory_tab:
        render_memory(key, model_name.strip())



if __name__ == '__main__':
    main()
