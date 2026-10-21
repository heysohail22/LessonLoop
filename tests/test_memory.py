import asyncio
import json
from pathlib import Path

from lessonloop.evolution import decision, propose_improvements, test_improvement as run_experiment
from lessonloop.generation import Lesson, rag_brief
from lessonloop.memory import Memory
from lessonloop.service import run_and_remember
from lessonloop.workflow import Attempt, WorkflowResult
from lessonloop.evaluation import Evaluation


def lesson(text='Sample'):
    return Lesson(**{key: text for key in Lesson.model_fields})


def evaluation(failed=()):
    return Evaluation(checks=[{'id': f'C{i}', 'passed': f'C{i}' not in failed, 'evidence': 'Sample excerpt', 'reason': 'Met' if f'C{i}' not in failed else 'Term undefined', 'required_change': 'None needed' if f'C{i}' not in failed else 'Define jargon'} for i in range(1, 10)])


def save(memory, failed=('C5',), kind='normal'):
    run_id = memory.start_run('fake-model', rag_brief().model_dump(), 'base-v1', kind=kind)
    memory.finish_run(run_id, WorkflowResult(status='needs_human_review' if failed else 'approved', attempts=[Attempt(number=1, lesson=lesson(), evaluation=evaluation(failed))]))
    return run_id


def test_runs_feedback_and_versions_survive_restart(tmp_path):
    path=tmp_path/'memory.sqlite3'; memory=Memory(path)
    first=save(memory)
    memory.add_feedback(first, 'C9', 'Too difficult')
    memory=Memory(path)
    assert memory.run(first)['status'] == 'needs_human_review'
    assert memory.repeated_failures() == {'C5':[first], 'C9':[first]}
    assert memory.active_prompt()['id'] == 'base-v1'


def test_two_distinct_normal_runs_needed_and_proposals_deduplicate(tmp_path):
    memory=Memory(tmp_path/'db')
    first=save(memory)
    assert propose_improvements(memory) == []
    save(memory,kind='demo')
    assert propose_improvements(memory) == []
    second=save(memory)
    ids=propose_improvements(memory)
    assert len(ids)==1
    assert json.loads(memory.prompt(ids[0])['evidence'])==sorted([first,second])
    assert propose_improvements(memory)==ids
    assert memory.active_prompt()['id']=='base-v1'


def test_attempt_retries_do_not_count_as_distinct_runs(tmp_path):
    memory=Memory(tmp_path/'db')
    run_id=memory.start_run('fake',rag_brief().model_dump(),'base-v1')
    memory.finish_run(run_id,WorkflowResult(status='needs_human_review', attempts=[Attempt(number=i,lesson=lesson(),evaluation=evaluation(('C5',))) for i in range(1,4)]))
    assert propose_improvements(memory)==[]


def pairs(before,after):
    return [{'scenario':str(i),'baseline':evaluation(before).model_dump(),'candidate':evaluation(after).model_dump()} for i in range(2)]


def test_adoption_gate_requires_improvement_without_regression():
    assert decision(pairs(('C5',),()),'C5')[0]
    assert not decision(pairs((),()),'C5')[0]
    assert not decision(pairs(('C5',),('C7',)),'C5')[0]
    assert not decision(pairs(('C5',),('C5',)),'C5')[0]


class Writer:
    def __init__(self): self.systems=[]
    async def complete(self, *, system,user):
        self.systems.append(system)
        return lesson('Improved' if 'Audit every technical word' in system else 'Baseline').model_dump_json()


class Reviewer:
    async def complete(self, *, system,user):
        content=json.loads(user)['lesson']['what_it_is']
        return evaluation(() if content=='Improved' else ('C5',)).model_dump_json()


def test_benchmark_promotes_and_future_runs_use_learned_instruction(tmp_path):
    memory=Memory(tmp_path/'db')
    save(memory); save(memory)
    candidate=propose_improvements(memory)[0]
    writer=Writer()
    report=asyncio.run(run_experiment(memory,candidate,writer,Reviewer(),'fake-model'))
    assert report['adopted']
    assert report['baseline_failures']==2 and report['candidate_failures']==0
    assert Memory(tmp_path/'db').active_prompt()['id']==candidate
    run_id,result=asyncio.run(run_and_remember(memory,writer,Reviewer(),'fake-model'))
    assert result.status=='approved'
    assert 'Audit every technical word' in writer.systems[-1]
    assert memory.run(run_id)['prompt_version']==candidate


def test_no_improvement_keeps_parent_active(tmp_path):
    memory=Memory(tmp_path/'db'); save(memory); save(memory)
    candidate=propose_improvements(memory)[0]
    class AlwaysPass:
        async def complete(self, **kwargs): return evaluation().model_dump_json()
    report=asyncio.run(run_experiment(memory,candidate,Writer(),AlwaysPass(),'fake-model'))
    assert not report['adopted']
    assert memory.active_prompt()['id']=='base-v1'
    assert memory.prompt(candidate)['status']=='rejected'


def test_benchmark_error_keeps_active_and_allows_retry(tmp_path):
    import pytest
    memory=Memory(tmp_path/'db'); save(memory); save(memory)
    candidate=propose_improvements(memory)[0]
    class Broken:
        async def complete(self,**kwargs): raise RuntimeError('failure')
    with pytest.raises(RuntimeError): asyncio.run(run_experiment(memory,candidate,Broken(),Reviewer(),'fake'))
    assert memory.active_prompt()['id']=='base-v1'
    assert memory.prompt(candidate)['status']=='error'


def test_export_rejects_nonapproved_result(tmp_path):
    import pytest
    from lessonloop.exporting import lesson_markdown
    result=WorkflowResult(status='needs_human_review',attempts=[Attempt(number=1,lesson=lesson(),evaluation=evaluation(('C5',)))])
    with pytest.raises(ValueError): lesson_markdown(result)


def test_unjustified_approval_is_invalid():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        WorkflowResult(status='approved',attempts=[Attempt(number=1,lesson=lesson(),evaluation=evaluation(('C5',)))])


def test_stale_experiment_cannot_replace_newer_prompt(tmp_path):
    memory=Memory(tmp_path/'db')
    save(memory);save(memory)
    a=propose_improvements(memory)[0]
    b=memory.propose('C9','Use simpler language',['fixture'],'base-v1')
    assert memory.claim_experiment(a)
    assert memory.claim_experiment(b)
    assert memory.complete_experiment(a,{'test':True},True)
    assert not memory.complete_experiment(b,{'test':True},True)
    assert memory.active_prompt()['id']==a
    assert memory.prompt(b)['status']=='stale'


def test_failed_export_removes_stale_generated_lesson(tmp_path):
    from lessonloop.exporting import export_run
    approved=WorkflowResult(status='approved',attempts=[Attempt(number=1,lesson=lesson(),evaluation=evaluation())])
    export_run(approved,tmp_path)
    assert (tmp_path/'lesson.md').exists()
    rejected=WorkflowResult(status='needs_human_review',attempts=[Attempt(number=1,lesson=lesson(),evaluation=evaluation(('C5',)))])
    export_run(rejected,tmp_path)
    assert not (tmp_path/'lesson.md').exists()
