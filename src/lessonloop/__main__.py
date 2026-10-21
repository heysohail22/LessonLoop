"""Inspect the generation brief without making paid API calls."""

import argparse
import asyncio
import json

from pydantic import ValidationError

from lessonloop.generation import build_messages, generate_draft, rag_brief


async def live_draft() -> str:
    from lessonloop.gemini import GeminiModel

    model = GeminiModel.from_environment()
    try:
        draft = await generate_draft(model, rag_brief())
        return draft.model_dump_json(indent=2)
    finally:
        await model.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect LessonLoop's RAG generation inputs (no model call).")
    parser.add_argument("--show", choices=["brief", "prompt"], default="brief")
    parser.add_argument("--live", action="store_true", help="Call Gemini to generate an unreviewed draft; may incur API charges.")
    args = parser.parse_args()
    if args.live:
        try:
            print(asyncio.run(live_draft()))
        except ValidationError:
            parser.exit(1, "Gemini returned an invalid lesson structure. No draft approved.\n")
        except (ValueError, RuntimeError) as error:
            parser.exit(1, f"{error}\n")
        return
    brief = rag_brief()
    if args.show == "brief":
        print(brief.model_dump_json(indent=2))
    else:
        system, user = build_messages(brief)
        print(json.dumps({"system": system, "user": json.loads(user)}, indent=2))


if __name__ == "__main__":
    main()
