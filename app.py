"""Local LessonLoop workbench. Start with uv run streamlit run app.py."""
import asyncio
import os
from pathlib import Path

import streamlit as st
from dotenv import dotenv_values
from pydantic import ValidationError

from lessonloop.generation import Draft, generate_draft, rag_brief
from lessonloop.gemini import GeminiModel, GenerationError

ROOT = Path(__file__).resolve().parent


def settings() -> tuple[str, str]:
    local = dotenv_values(ROOT / '.env')
    return (
        os.environ.get('GEMINI_API_KEY') or local.get('GEMINI_API_KEY') or '',
        os.environ.get('GEMINI_MODEL') or local.get('GEMINI_MODEL') or '',
    )


async def create_draft(key: str, model_name: str) -> Draft:
    model = GeminiModel(api_key=key, model=model_name)
    try:
        return await generate_draft(model, rag_brief())
    finally:
        await model.close()


def markdown(draft: Draft) -> str:
    lesson = draft.lesson
    sections = [('What is RAG?', lesson.what_it_is), ('Why it matters', lesson.why_it_matters),
                ('How it works', lesson.how_it_works), ('Worked example', lesson.worked_example),
                ('Limitations', lesson.limitations), ('Try it yourself', lesson.exercise),
                ('Answer explained', lesson.answer_explanation)]
    return f'# {lesson.title}\n\nStatus: Unreviewed draft\n\n' + '\n\n'.join(f'## {name}\n\n{text}' for name, text in sections)


def main() -> None:
    st.set_page_config(page_title='LessonLoop · Lesson studio', page_icon='📖', layout='wide')
    st.caption('LESSONLOOP / LESSON STUDIO')
    st.title('A clearer first lesson.')
    st.write('Generate an introduction to RAG for a learner starting from zero.')
    st.info('Generation is ready. Evaluation, revisions, and learning across runs are coming next. Every draft is unreviewed.')
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
    lesson_tab, brief_tab, checks_tab = st.tabs(['Create lesson', 'Teaching brief', 'Quality checkpoints'])
    with lesson_tab:
        with st.form('generate'):
            st.selectbox('Topic', [brief.topic], help='This first version supports RAG. More topics need their own reference packs.')
            model_name = st.text_input('Gemini model', value=configured_model, placeholder='Enter a model ID available to your account')
            st.caption('Generate makes one live Gemini request and may use paid quota.')
            submitted = st.form_submit_button('Generate lesson', type='primary', disabled=not bool(key))
        if submitted:
            if not model_name.strip():
                st.error('Enter a Gemini model ID, or set GEMINI_MODEL in .env.')
            else:
                with st.status('Generating your lesson…', expanded=True) as status:
                    st.write('Preparing learner brief and reference notes.')
                    try:
                        draft = asyncio.run(create_draft(key, model_name.strip()))
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
            st.warning('Unreviewed draft — no quality checks have run.')
            st.caption(f"Generated with {st.session_state.get('draft_model', 'Gemini')}. Saved in this browser session only; on a failed retry, the previous draft remains below.")
            st.markdown(markdown(draft))
            st.download_button('Download lesson (.md)', markdown(draft), 'rag-lesson-draft.md', 'text/markdown')
            with st.expander('Structured output'):
                st.json(draft.model_dump())
                st.download_button('Download JSON', draft.model_dump_json(indent=2), 'rag-lesson-draft.json', 'application/json')
        else:
            st.subheader('Your lesson will appear here')
            st.write('You will get an explanation, a worked example, limitations, and a practice question.')
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
        st.caption('These are planned pass/fail requirements. They have not been automatically evaluated.')
        for check in brief.checkpoints:
            with st.container(border=True):
                st.write(f'**{check.id} · Not evaluated**')
                st.write(check.condition)


if __name__ == '__main__':
    main()
