"""Application orchestration: use learned prompts and persist every complete run."""
from collections.abc import Callable
from lessonloop.evolution import propose_improvements
from lessonloop.generation import Lesson, TextModel, rag_brief
from lessonloop.memory import Memory
from lessonloop.workflow import WorkflowResult, run_workflow


async def run_and_remember(memory: Memory, writer: TextModel, reviewer: TextModel, model_name: str, *, seed: Lesson | None = None, on_progress: Callable[[str], None] | None = None) -> tuple[str, WorkflowResult]:
    active = memory.active_prompt()
    brief = rag_brief()
    run_id = memory.start_run(model_name, brief.model_dump(), active['id'], kind='demo' if seed else 'normal')
    try:
        result = await run_workflow(writer, reviewer, brief, seed=seed, on_progress=on_progress, guidance=active['instruction'])
        memory.finish_run(run_id, result)
        propose_improvements(memory)
        return run_id, result
    except BaseException:
        memory.fail_run(run_id)
        raise
