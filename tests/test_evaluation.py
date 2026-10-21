import asyncio
import json

import pytest
from pydantic import ValidationError

from lessonloop.evaluation import Evaluation, evaluate_lesson
from lessonloop.generation import Lesson, rag_brief


def results():
    return {'checks': [{'id': f'C{i}', 'passed': True, 'evidence': 'Example excerpt', 'reason': 'Requirement met', 'required_change': 'None needed'} for i in range(1, 10)]}


class FakeModel:
    def __init__(self, response):
        self.response = response
        self.messages = None

    async def complete(self, *, system, user):
        self.messages = json.loads(user)
        return json.dumps(self.response)


def lesson():
    return Lesson(**{name: 'Example lesson content.' for name in Lesson.model_fields})


def test_all_checks_must_pass():
    data = results()
    assert Evaluation.model_validate(data).approved
    data['checks'][4]['passed'] = False
    assert not Evaluation.model_validate(data).approved


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'unknown', 'string_boolean', 'empty_feedback', 'approval_override'])
def test_invalid_evaluations_fail_closed(mutation):
    data = results()
    if mutation == 'missing': data['checks'].pop()
    if mutation == 'duplicate': data['checks'][-1]['id'] = 'C1'
    if mutation == 'unknown': data['checks'][-1]['id'] = 'C10'
    if mutation == 'string_boolean': data['checks'][0]['passed'] = 'true'
    if mutation == 'empty_feedback': data['checks'][0]['reason'] = ' '
    if mutation == 'approval_override': data['approved'] = True
    with pytest.raises(ValidationError): Evaluation.model_validate(data)


def test_evaluator_gets_sources_rubric_and_lesson():
    model = FakeModel(results())
    result = asyncio.run(evaluate_lesson(model, lesson(), rag_brief()))
    assert result.approved
    assert len(model.messages['brief']['references']) == 3
    assert len(model.messages['brief']['checkpoints']) == 9
    assert model.messages['lesson'] == lesson().model_dump()


def test_deliberate_guarantee_is_rejected_even_if_model_misses_it():
    bad = lesson().model_copy(update={'limitations': 'RAG always gives correct answers.'})
    result = asyncio.run(evaluate_lesson(FakeModel(results()), bad, rag_brief()))
    assert not result.approved
    assert {c.id for c in result.checks if not c.passed} == {'C6', 'C7'}


def test_explaining_a_false_claim_is_not_automatically_rejected():
    good = lesson().model_copy(update={'limitations': 'It is incorrect to say RAG always gives correct answers.'})
    assert asyncio.run(evaluate_lesson(FakeModel(results()), good, rag_brief())).approved
