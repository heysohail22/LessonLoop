"""Submission exports use only an approved final attempt."""
from pathlib import Path
from lessonloop.workflow import WorkflowResult
from lessonloop.generation import rag_brief

SECTIONS = [('what_it_is', 'What is RAG?'), ('why_it_matters', 'Why it matters'), ('how_it_works', 'How it works'), ('worked_example', 'A worked example'), ('limitations', 'What can go wrong?'), ('exercise', 'Try it yourself'), ('answer_explanation', 'Answer explained')]


def lesson_markdown(result: WorkflowResult) -> str:
    if result.status != 'approved' or not result.final_lesson:
        raise ValueError('Only an approved final lesson can be exported as the submission lesson.')
    lesson = result.final_lesson
    return '# ' + lesson.title + '\n\n' + '\n\n'.join('## ' + title + '\n\n' + getattr(lesson, field) for field, title in SECTIONS) + '\n\n## Reference notes\n\n' + '\n\n'.join(f'**{key}:** {note}' for key, note in rag_brief().references.items()) + '\n'


def export_run(result: WorkflowResult, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'run.json').write_text(result.model_dump_json(indent=2))
    if result.status == 'approved':
        (directory / 'lesson.md').write_text(lesson_markdown(result))
    elif (directory / 'lesson.md').exists():
        (directory / 'lesson.md').unlink()
