import asyncio
import json

from lessonloop.generation import Lesson, rag_brief
from lessonloop.workflow import run_workflow


def lesson(text='Original content'):
    return Lesson(**{field: text for field in Lesson.model_fields})


def evaluation(passed):
    return json.dumps({'checks': [{'id': f'C{i}', 'passed': passed or i != 5, 'evidence': 'Example', 'reason': 'Met' if passed or i != 5 else 'Term unexplained', 'required_change': 'None needed' if passed or i != 5 else 'Explain the term'} for i in range(1, 10)]})


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def complete(self, *, system, user):
        self.calls.append(json.loads(user))
        value = next(self.responses)
        if isinstance(value, Exception): raise value
        return value


def test_pass_first_attempt_stops():
    writer=FakeModel([lesson().model_dump_json()]); reviewer=FakeModel([evaluation(True)])
    result=asyncio.run(run_workflow(writer,reviewer,rag_brief()))
    assert result.status == 'approved'
    assert len(result.attempts) == len(writer.calls) == len(reviewer.calls) == 1


def test_revision_receives_failure_and_records_actual_changes():
    original=lesson(); revised=original.model_copy(update={'how_it_works':'Now defines the term'})
    writer=FakeModel([original.model_dump_json(),revised.model_dump_json()]); reviewer=FakeModel([evaluation(False),evaluation(True)])
    result=asyncio.run(run_workflow(writer,reviewer,rag_brief()))
    assert result.status == 'approved'
    assert len(result.attempts) == 2
    assert writer.calls[1]['previous_lesson'] == original.model_dump()
    assert [c['id'] for c in writer.calls[1]['failures']] == ['C5']
    assert writer.calls[1]['original_brief']['references']
    assert result.attempts[1].changed_sections == ['how_it_works']
    assert result.attempts[0].evaluation.checks[4].passed is False


def test_three_failures_stop_without_fourth_attempt():
    writer=FakeModel([lesson().model_dump_json()]*3); reviewer=FakeModel([evaluation(False)]*3)
    result=asyncio.run(run_workflow(writer,reviewer,rag_brief()))
    assert result.status == 'needs_human_review'
    assert len(result.attempts) == len(writer.calls) == len(reviewer.calls) == 3
    assert result.attempts[-1].changed_sections == []


def test_invalid_evaluator_stops_without_approval():
    result=asyncio.run(run_workflow(FakeModel([lesson().model_dump_json()]),FakeModel(['{}']),rag_brief()))
    assert result.status == 'error'
    assert len(result.attempts) == 1
    assert result.attempts[0].error


def test_failed_revision_keeps_rejection_log_and_hides_exception():
    result=asyncio.run(run_workflow(FakeModel([lesson().model_dump_json(),RuntimeError('SECRET')]),FakeModel([evaluation(False)]),rag_brief()))
    assert result.status == 'error'
    assert result.attempts[0].evaluation is not None
    assert 'SECRET' not in result.model_dump_json()
    assert result.final_lesson is None


def test_existing_draft_counts_as_attempt_one():
    writer=FakeModel([lesson('Revised').model_dump_json()]); reviewer=FakeModel([evaluation(False),evaluation(True)])
    result=asyncio.run(run_workflow(writer,reviewer,rag_brief(),seed=lesson()))
    assert len(result.attempts) == 2
    assert len(writer.calls) == 1
    assert result.status == 'approved'
