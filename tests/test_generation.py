import asyncio
import json

import pytest
from pydantic import ValidationError

from lessonloop.generation import Lesson, generate_draft, rag_brief


class FakeModel:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response


def test_generation_supplies_brief_and_never_approves_draft():
    payload = {field: "Test fixture only; not an approved lesson." for field in Lesson.model_fields}
    model = FakeModel(json.dumps(payload))
    draft = asyncio.run(generate_draft(model, rag_brief()))
    assert draft.status == "unreviewed"
    assert draft.generation_inputs is not None
    assert draft.generation_inputs.system == model.calls[0][0]
    assert draft.generation_inputs.user == model.calls[0][1]
    sent = json.loads(model.calls[0][1])
    assert len(sent["brief"]["checkpoints"]) == 9
    assert set(sent["brief"]["references"]) == {"R1", "R2", "R3"}
    assert "limited English" in sent["brief"]["learner"]


@pytest.mark.parametrize("response", ["not json", "{}", '{"title": "Only a title"}'])
def test_invalid_model_output_is_rejected(response):
    with pytest.raises(ValidationError):
        asyncio.run(generate_draft(FakeModel(response), rag_brief()))
