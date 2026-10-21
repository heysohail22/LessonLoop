"""Reproducible synthetic workflow/memory demo. NO Gemini calls or quality claims."""
import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from lessonloop.evolution import propose_improvements, test_improvement
from lessonloop.generation import Lesson
from lessonloop.memory import Memory
from lessonloop.service import run_and_remember


class FixtureWriter:
    async def complete(self, *, system: str, user: str) -> str:
        revision = 'previous_lesson' in json.loads(user)
        learned = 'Audit every technical word' in system
        marker = 'improved fixture' if revision or learned else 'baseline fixture'
        return Lesson(**{name: marker for name in Lesson.model_fields}).model_dump_json()


class FixtureReviewer:
    async def complete(self, *, system: str, user: str) -> str:
        improved = json.loads(user)['lesson']['what_it_is'] == 'improved fixture'
        return json.dumps({'checks': [{'id': f'C{i}', 'passed': improved or i != 5, 'evidence': 'Synthetic fixture marker, not real lesson evidence.', 'reason': 'Synthetic pass' if improved or i != 5 else 'Synthetic unexplained-term failure', 'required_change': 'None needed' if improved or i != 5 else 'Explain the term'} for i in range(1, 10)]})


async def demo(path: Path) -> dict:
    memory = Memory(path)
    writer, reviewer = FixtureWriter(), FixtureReviewer()
    runs = []
    for _ in range(2):
        run_id, result = await run_and_remember(memory, writer, reviewer, 'synthetic-fixture')
        runs.append({'run_id': run_id, **result.model_dump(mode='json')})
    candidate = propose_improvements(memory)[0]
    experiment = await test_improvement(memory, candidate, writer, reviewer, 'synthetic-fixture')
    # Reopen the database, proving the accepted version is persistent.
    memory = Memory(path)
    run_id, future = await run_and_remember(memory, writer, reviewer, 'synthetic-fixture')
    assert experiment['adopted'] and len(future.attempts) == 1
    return {'kind': 'synthetic-test-only', 'notice': 'Deterministic fake models. This proves control flow and persistence, NOT real model quality improvement. It uses a temporary database, not your live memory.', 'training_runs': runs, 'experiment': experiment, 'future_run': {'run_id': run_id, **future.model_dump(mode='json')}, 'active_prompt': memory.active_prompt()['id']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    args = parser.parse_args()
    with TemporaryDirectory(prefix='lessonloop-demo-') as temp:
        report = asyncio.run(demo(Path(temp)/'demo.sqlite3'))
    text = json.dumps(report, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    print(text)


if __name__ == '__main__': main()
