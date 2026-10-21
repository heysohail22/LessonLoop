"""CLI: inspect locally; all model work requires explicit --live."""
import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError
from lessonloop.evaluation import Evaluation
from lessonloop.evolution import test_improvement
from lessonloop.exporting import export_run
from lessonloop.gemini import GeminiModel, GenerationError
from lessonloop.generation import Lesson, build_messages, rag_brief
from lessonloop.memory import Memory
from lessonloop.service import run_and_remember
from lessonloop.settings import settings, database_path


async def live(args) -> dict:
    key, model_name = settings()
    if not key or not model_name: raise ValueError('Set GEMINI_API_KEY and GEMINI_MODEL in .env or the environment.')
    memory = Memory(database_path())
    writer = GeminiModel(api_key=key, model=model_name)
    reviewer = GeminiModel(api_key=key, model=model_name, response_type=Evaluation)
    try:
        if args.test_prompt:
            return await test_improvement(memory, args.test_prompt, writer, reviewer, model_name)
        seed = Lesson.model_validate_json(Path(args.seed).read_text()) if args.seed else None
        run_id, result = await run_and_remember(memory, writer, reviewer, model_name, seed=seed)
        if args.output: export_run(result, Path(args.output))
        return {'run_id': run_id, **result.model_dump(mode='json')}
    finally:
        await writer.close()
        await reviewer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='LessonLoop: bounded lesson generation and tested prompt evolution.')
    parser.add_argument('--show', choices=['brief', 'prompt', 'history', 'memory'], default='brief')
    parser.add_argument('--live', action='store_true', help='Enable paid Gemini requests: up to 6 for a run or 8 for one prompt experiment.')
    parser.add_argument('--seed', help='Lesson JSON used as the initial draft (counts as attempt one).')
    parser.add_argument('--test-prompt', help='Test one proposed prompt version against its parent (requires --live).')
    parser.add_argument('--output', help='Export run.json and, only on approval, lesson.md to this directory.')
    args = parser.parse_args()
    if (args.seed or args.test_prompt or args.output) and not args.live:
        parser.error('--seed, --test-prompt and --output require explicit --live')
    if args.test_prompt and (args.seed or args.output):
        parser.error('--test-prompt cannot be combined with --seed or --output')
    if args.live:
        try:
            payload = asyncio.run(live(args))
            print(json.dumps(payload, indent=2))
            if payload.get('status') in ('needs_human_review', 'error'):
                parser.exit(2 if payload['status'] == 'needs_human_review' else 1)
        except (ValueError, GenerationError):
            parser.exit(1, 'The request could not complete. Check local settings, proposal status, input JSON, and model availability. No lesson was approved.\n')
        return
    if args.show in ('history', 'memory'):
        memory = Memory(database_path())
        print(json.dumps(memory.runs() if args.show == 'history' else {'active': memory.active_prompt(), 'versions': memory.prompts(), 'failures': memory.repeated_failures()}, indent=2))
    elif args.show == 'brief':
        print(rag_brief().model_dump_json(indent=2))
    else:
        system, user = build_messages(rag_brief())
        print(json.dumps({'system': system, 'user': json.loads(user)}, indent=2))


if __name__ == '__main__': main()
