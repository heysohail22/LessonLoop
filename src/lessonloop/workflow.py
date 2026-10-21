"""Bounded generate/evaluate/revise workflow, with an auditable attempt log."""
from typing import Callable, Literal

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError, model_validator

from lessonloop.evaluation import Evaluation, RUBRIC_VERSION, evaluate_lesson
from lessonloop.generation import Lesson, LessonBrief, TextModel, GenerationInputs, build_generation_inputs
from lessonloop.gemini import GenerationError

MAX_ATTEMPTS = 3


class Attempt(BaseModel):
    number: int = Field(ge=1, le=MAX_ATTEMPTS)
    lesson: Lesson | None = None
    evaluation: Evaluation | None = None
    changed_sections: list[str] = Field(default_factory=list)
    error: str | None = None
    generation_inputs: GenerationInputs | None = None
    provided_draft: bool = False


class WorkflowResult(BaseModel):
    status: Literal['approved', 'needs_human_review', 'error']
    rubric_version: str = RUBRIC_VERSION
    attempts: list[Attempt] = Field(min_length=1, max_length=MAX_ATTEMPTS)

    @model_validator(mode='after')
    def validate_approval(self) -> 'WorkflowResult':
        latest = self.attempts[-1]
        if self.status == 'approved' and (latest.error or not latest.lesson or not latest.evaluation or not latest.evaluation.approved):
            raise ValueError('Approval requires a complete passing final attempt without an error.')
        return self

    @property
    def final_lesson(self) -> Lesson | None:
        return self.attempts[-1].lesson if self.attempts else None


class WorkflowState(BaseModel):
    brief: LessonBrief
    attempts: list[Attempt] = Field(default_factory=list)
    seed: Lesson | None = None
    result: WorkflowResult | None = None


def route_after_generation(state: WorkflowState) -> Literal['evaluate', 'finish']:
    return 'finish' if state.attempts[-1].error else 'evaluate'


def route_after_evaluation(state: WorkflowState) -> Literal['generate', 'finish']:
    latest = state.attempts[-1]
    if latest.error or latest.evaluation is None or latest.evaluation.approved or len(state.attempts) >= MAX_ATTEMPTS:
        return 'finish'
    return 'generate'


def safe_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return 'The model returned malformed or incomplete structured output. This run stopped without approval.'
    if isinstance(error, GenerationError):
        return str(error)
    return 'A workflow step failed unexpectedly. This run stopped without approval.'


def build_workflow(writer: TextModel, reviewer: TextModel, on_progress: Callable[[str], None] | None = None, *, guidance: str = ""):
    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    async def generate(state: WorkflowState) -> dict:
        history = state.attempts
        number = len(history) + 1
        progress(f'Attempt {number}/{MAX_ATTEMPTS}: ' + ('revising lesson' if history else 'preparing first draft'))
        attempt = Attempt(number=number)
        try:
            if not history and state.seed is not None:
                # The submitted draft counts as the first attempt, not an extra retry.
                attempt.lesson = state.seed
                attempt.provided_draft = True
            else:
                previous = history[-1] if history else None
                if previous and (previous.lesson is None or previous.evaluation is None):
                    raise ValueError('Cannot revise without a valid evaluated lesson')
                inputs = build_generation_inputs(
                    state.brief,
                    previous_lesson=previous.lesson if previous else None,
                    failures=[c.model_dump() for c in previous.evaluation.checks if not c.passed] if previous and previous.evaluation else None,
                    guidance=guidance,
                )
                attempt.generation_inputs = inputs
                attempt.lesson = Lesson.model_validate_json(await writer.complete(system=inputs.system, user=inputs.user))
            if history and history[-1].lesson and attempt.lesson:
                before = history[-1].lesson.model_dump()
                attempt.changed_sections = [name for name, value in attempt.lesson.model_dump().items() if before[name] != value]
        except Exception as error:
            attempt.error = safe_error(error)
        return {'attempts': [*history, attempt]}

    async def evaluate(state: WorkflowState) -> dict:
        history = state.attempts
        latest = history[-1].model_copy(deep=True)
        progress(f'Attempt {latest.number}/{MAX_ATTEMPTS}: evaluating all nine checkpoints')
        try:
            if latest.lesson is None:
                raise ValueError('Missing lesson')
            latest.evaluation = await evaluate_lesson(reviewer, latest.lesson, state.brief)
        except Exception as error:
            latest.error = safe_error(error)
        return {'attempts': [*history[:-1], latest]}

    async def finish(state: WorkflowState) -> dict:
        latest = state.attempts[-1]
        status: Literal['approved', 'needs_human_review', 'error'] = 'needs_human_review'
        if latest.error or latest.evaluation is None:
            status = 'error'
        elif latest.evaluation.approved:
            status = 'approved'
        progress({'approved': 'All checkpoints passed.', 'needs_human_review': 'Retry limit reached. Needs human review.', 'error': 'Run stopped with an error; no approval.'}[status])
        return {'result': WorkflowResult(status=status, attempts=state.attempts)}

    graph = StateGraph(WorkflowState)
    graph.add_node('generate', generate)
    graph.add_node('evaluate', evaluate)
    graph.add_node('finish', finish)
    graph.add_edge(START, 'generate')
    graph.add_conditional_edges('generate', route_after_generation, {'evaluate': 'evaluate', 'finish': 'finish'})
    graph.add_conditional_edges('evaluate', route_after_evaluation, {'generate': 'generate', 'finish': 'finish'})
    graph.add_edge('finish', END)
    return graph.compile()


async def run_workflow(writer: TextModel, reviewer: TextModel, brief: LessonBrief, *, seed: Lesson | None = None, on_progress: Callable[[str], None] | None = None, guidance: str = "") -> WorkflowResult:
    graph = build_workflow(writer, reviewer, on_progress, guidance=guidance)
    state = await graph.ainvoke({'brief': brief, 'attempts': [], 'seed': seed}, config={'recursion_limit': 12})
    return WorkflowResult.model_validate(state['result'])
