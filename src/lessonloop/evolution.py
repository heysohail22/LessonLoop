"""Conservative prompt evolution: repeated failures → proposal → paired test → adoption."""
from collections.abc import Callable

from lessonloop.evaluation import Evaluation, evaluate_lesson, RUBRIC_VERSION
from lessonloop.generation import Lesson, LessonBrief, TextModel, build_messages, rag_brief
from lessonloop.memory import Memory

RULES = {
    'C1': 'Explicitly expand Retrieval-Augmented Generation and explain retrieval and generation as two linked actions.',
    'C2': 'Explain the missing-information problem before introducing the solution, using a familiar student situation.',
    'C3': 'Separate document preparation from question-time retrieval and answer writing; explain each in plain English.',
    'C4': 'Use one fictional example with a question, a quoted source passage, and an answer supported only by that passage.',
    'C5': 'Audit every technical word before finishing. Explain each essential term in simple English at first use; remove unnecessary jargon.',
    'C6': 'State both limitations explicitly: retrieval can miss useful passages, and the model can still write an incorrect answer. Never promise correctness.',
    'C7': 'Audit each core factual claim against the supplied reference notes. Remove unsupported claims and place reference IDs next to supported explanations.',
    'C8': 'Add a practice question testing a stated learning goal, followed by a correct answer with a simple explanation.',
    'C9': 'Read each sentence as a learner with no AI knowledge. Replace difficult English, introduce concepts in order, and keep paragraphs short.',
}
BENCHMARK_VERSION = 'rag-bench-v1'
SCENARIOS = ('Use a fictional college handbook example.', 'Use a fictional library opening-hours example.')


class InstructedModel:
    def __init__(self, model: TextModel, instruction: str):
        self.model, self.instruction = model, instruction

    async def complete(self, *, system: str, user: str) -> str:
        if self.instruction:
            system += '\nAdditional tested teaching guidance:\n' + self.instruction
        return await self.model.complete(system=system, user=user)


def propose_improvements(memory: Memory) -> list[str]:
    active = memory.active_prompt()
    candidates = []
    for checkpoint, run_ids in sorted(memory.repeated_failures().items()):
        rule = RULES.get(checkpoint)
        if len(run_ids) >= 2 and rule and rule not in active['instruction']:
            instruction = '\n'.join(filter(None, (active['instruction'], rule)))
            candidates.append(memory.propose(checkpoint, instruction, run_ids, active['id']))
    return candidates


def decision(pairs: list[dict], target: str) -> tuple[bool, dict]:
    if len(pairs) != len(SCENARIOS): raise ValueError('Incomplete benchmark')
    before_total = after_total = before_target = after_target = 0
    regressions = []
    for pair in pairs:
        before = Evaluation.model_validate(pair['baseline'])
        after = Evaluation.model_validate(pair['candidate'])
        baseline: dict[str, bool] = {c.id: c.passed for c in before.checks}
        candidate: dict[str, bool] = {c.id: c.passed for c in after.checks}
        before_total += sum(not v for v in baseline.values())
        after_total += sum(not v for v in candidate.values())
        before_target += int(not baseline[target])
        after_target += int(not candidate[target])
        regressions.extend(f"{pair['scenario']}: {key}" for key in baseline if baseline[key] and not candidate[key])
    accepted = after_target < before_target and after_total < before_total and not regressions
    return accepted, {'baseline_failures': before_total, 'candidate_failures': after_total, 'baseline_target_failures': before_target, 'candidate_target_failures': after_target, 'regressions': regressions}


async def test_improvement(memory: Memory, prompt_id: str, writer: TextModel, reviewer: TextModel, model_name: str, on_progress: Callable[[str], None] | None = None) -> dict:
    candidate = memory.prompt(prompt_id)
    baseline = memory.prompt(candidate['parent_id'])
    if memory.active_prompt()['id'] != baseline['id']: raise ValueError('Candidate is stale; propose against the current active prompt.')
    if not memory.claim_experiment(prompt_id): raise ValueError('This proposal has already been tested or is being tested.')
    pairs = []
    try:
        for number, scenario in enumerate(SCENARIOS, 1):
            pair: dict = {'scenario': scenario}
            for arm, instruction in (('baseline', baseline['instruction']), ('candidate', candidate['instruction'])):
                if on_progress: on_progress(f'Benchmark {number}/{len(SCENARIOS)}: {arm}')
                brief: LessonBrief = rag_brief().model_copy(deep=True)
                brief.goals.append(scenario)
                system, user = build_messages(brief)
                lesson = Lesson.model_validate_json(await InstructedModel(writer, instruction).complete(system=system, user=user))
                evaluation = await evaluate_lesson(reviewer, lesson, brief)
                pair[arm] = evaluation.model_dump()
                pair[arm + '_lesson'] = lesson.model_dump()
            pairs.append(pair)
        accepted, metrics = decision(pairs, candidate['checkpoint'])
        report = {'benchmark_version': BENCHMARK_VERSION, 'rubric_version': RUBRIC_VERSION, 'model': model_name, 'target': candidate['checkpoint'], 'pairs': pairs, **metrics}
        report['adopted'] = memory.complete_experiment(prompt_id, report, accepted)
        return report
    except Exception:
        memory.experiment_error(prompt_id, {'error': 'Experiment did not complete; no prompt was adopted.', 'pairs_completed': pairs, 'benchmark_version': BENCHMARK_VERSION, 'rubric_version': RUBRIC_VERSION, 'model': model_name})
        raise
