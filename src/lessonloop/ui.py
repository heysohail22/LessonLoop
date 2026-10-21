"""Presentation helpers: explain actual workflow state without inventing progress."""
from difflib import unified_diff

import streamlit as st

from lessonloop.evaluation import Evaluation
from lessonloop.workflow import WorkflowResult

CHECK_NAMES = {
    'C1': 'Defines RAG', 'C2': 'Explains why it matters', 'C3': 'Teaches the process',
    'C4': 'Works through an example', 'C5': 'Explains technical words',
    'C6': 'States the limitations', 'C7': 'Supports factual claims',
    'C8': 'Checks understanding', 'C9': 'Uses a clear teaching flow',
}
SECTION_NAMES = {
    'title': 'Title', 'what_it_is': 'What is RAG?', 'why_it_matters': 'Why it matters',
    'how_it_works': 'How it works', 'worked_example': 'Worked example',
    'limitations': 'Limitations', 'exercise': 'Practice question',
    'answer_explanation': 'Answer explained',
}

STYLE = '''
<style>
:root { --ll-gold: #F6C453; --ll-muted: #A7B0BC; }
.block-container { max-width: 1360px; padding-top: 2.1rem; padding-bottom: 3rem; }
[data-testid="stAppViewContainer"] { background: radial-gradient(ellipse at 85% 0%, #292519 0, #14171c 42%); }
h1 { letter-spacing: -.045em; line-height: 1.12 !important; }
h2,h3 { letter-spacing: -.025em; }
.ll-kicker { color: #F6C453; font-size: .74rem; font-weight: 700; letter-spacing: .17em; margin: 0 0 .8rem; }
.ll-intro { color: #A7B0BC; max-width: 690px; font-size: 1.05rem; line-height: 1.7; margin-bottom: 1.6rem; }
.ll-flow { display: grid; grid-template-columns: repeat(5,minmax(0,1fr)); gap: .65rem; margin: .8rem 0 1.4rem; }
.ll-step { border: 1px solid #343a43; border-radius: 12px; padding: 1rem; background: #1b2027; min-height: 128px; }
.ll-step.done { border-color: #45644e; background: #1d2a23; }
.ll-step.active { border-color: #F6C453; background: #302b1e; }
.ll-step.problem { border-color: #b7776c; background: #302222; }
.ll-step .ll-num { color: #A7B0BC; font-size: .72rem; letter-spacing: .08em; }
.ll-step h4 { margin: .25rem 0 .4rem; font-size: .98rem; color: #F2F0E9; }
.ll-step p { color: #BDC3CD; font-size: .8rem; line-height: 1.5; margin: 0; }
.ll-guide { border-left: 3px solid #F6C453; padding: .2rem 0 .2rem 1rem; margin: .6rem 0 1.2rem; color: #c9cdd3; }
[data-testid="stMetricValue"] { font-size: 1.65rem; }
[data-baseweb="tab-list"] { gap: 1rem; }
@media(max-width: 760px) {
  .block-container { padding-top: 1rem; }
  .ll-flow { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .ll-step:last-child { grid-column: 1 / -1; min-height: auto; }
  .ll-step { min-height: 116px; padding: .8rem; }
  [data-baseweb="tab-list"] { gap: .4rem; }
}
</style>
'''


def pipeline_html(*, stage: str = 'ready', attempt: int = 0) -> str:
    """Stages are selected from actual workflow events or persisted outcomes."""
    stages = [
        ('plan', '01 / PLAN', 'Know the learner', 'Topic, simple-language goals, and trusted notes.'),
        ('write', '02 / WRITE', 'Create a lesson', 'Explain the idea with a familiar example.'),
        ('check', '03 / CHECK', 'Review all 9 rules', 'Each rule must pass. No partial credit.'),
        ('revise', '04 / REVISE', 'Fix the failures', 'Use the feedback. At most two revisions.'),
        ('decide', '05 / DECIDE', 'Approve or stop', 'Ship only if all rules pass; otherwise flag review.'),
    ]
    done = {'ready': {'plan'}, 'write': {'plan'}, 'check': {'plan','write'},
            'revise': {'plan','write','check'}, 'draft_ready': {'plan','write'}, 'rejected': {'plan','write','check'}, 'approved': {'plan','write','check','decide'},
            'needs_human_review': {'plan','write','check'}, 'error': {'plan'}}.get(stage, set())
    cards = []
    for key, number, title, description in stages:
        state = 'done' if key in done else ''
        label = 'Complete' if state else 'Waiting'
        if key == stage:
            state, label = 'active', 'In progress'
        if key == 'check' and stage == 'draft_ready':
            label = 'Ready for review'
        if key == 'revise' and stage == 'rejected':
            label = 'Revision needed'
        if key == 'revise' and stage == 'approved':
            state, label = ('done', 'Used') if attempt > 1 else ('', 'Not needed')
        if key == 'decide' and stage in ('needs_human_review','error'):
            state, label = 'problem', 'Needs review' if stage == 'needs_human_review' else 'Stopped'
        if stage == 'ready' and key == 'plan': label = 'Ready'
        if key == 'revise' and stage == 'needs_human_review': state, label = 'problem','Limit reached'
        cards.append(f'<div class="ll-step {state}" role="listitem"><span class="ll-num">{number} · {label}</span><h4>{title}</h4><p>{description}</p></div>')
    return '<div class="ll-flow" role="list" aria-label="Lesson workflow">' + ''.join(cards) + '</div>'


def pipeline(*, stage: str = 'ready', attempt: int = 0) -> None:
    st.markdown(pipeline_html(stage=stage, attempt=attempt), unsafe_allow_html=True)


def outcome_summary(result: WorkflowResult | None, review: Evaluation | None = None) -> None:
    columns = st.columns(3)
    attempts = len(result.attempts) if result else 0
    if result:
        review = result.attempts[-1].evaluation
    passed = sum(check.passed for check in review.checks) if review else None
    columns[0].metric('Checks passed', f'{passed} / 9' if passed is not None else 'Not checked')
    columns[1].metric('Attempts used', f'{attempts} / 3' if attempts else 'Not started')
    status = 'Waiting for a lesson'
    if result:
        status = {'approved':'Approved', 'needs_human_review':'Human review', 'error':'Stopped'}[result.status]
    elif review:
        status = 'Approved' if review.approved else 'Needs revision'
    columns[2].metric('Decision', status)


def compare_attempts(result: WorkflowResult) -> None:
    if len(result.attempts) < 2:
        st.caption('A revision comparison appears when the workflow creates a second attempt.')
        return
    st.markdown('#### What changed on retry?')
    selection = st.selectbox('Compare revision', [a.number for a in result.attempts[1:]], format_func=lambda number: f'Attempt {number-1} → Attempt {number}', key='compare_revision')
    before = result.attempts[selection-2]
    after = result.attempts[selection-1]
    if not before.lesson or not after.lesson:
        st.info('A complete pair of lessons is unavailable because a model step failed.')
        return
    if not after.changed_sections:
        st.warning('The writer returned the same section text. This is not evidence of a successful fix.')
        return
    section = st.selectbox('Changed section', after.changed_sections, format_func=lambda value: SECTION_NAMES.get(value, value), key=f'compare_section_{selection}')
    left, right = st.columns(2)
    with left:
        st.caption(f'BEFORE · ATTEMPT {before.number}')
        with st.container(border=True):
            st.write(getattr(before.lesson, section))
    with right:
        st.caption(f'AFTER · ATTEMPT {after.number}')
        with st.container(border=True):
            st.write(getattr(after.lesson, section))
    if before.evaluation:
        failed = [c for c in before.evaluation.checks if not c.passed]
        st.caption('Feedback sent to the writer: ' + '; '.join(f'{c.id}: {c.required_change}' for c in failed))
    with st.expander('See exact text differences'):
        diff = '\n'.join(unified_diff(getattr(before.lesson, section).splitlines(), getattr(after.lesson, section).splitlines(), fromfile='Before', tofile='After', lineterm=''))
        st.code(diff, language='diff')
    st.caption('Changed text is evidence of a revision. The next full evaluation decides whether it fixes the problem.')
