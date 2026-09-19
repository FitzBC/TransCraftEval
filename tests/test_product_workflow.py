import json
from threading import Lock

import pytest
from fastapi.testclient import TestClient

from face_watch.api import create_app


def test_saved_library_is_authoritative(tmp_path):
    state=tmp_path/'state.json'
    c=TestClient(create_app(state_file=state))
    item=c.get('/api/library-items').json()[2]
    item.update(definition='人工维护内容',status='disabled')
    assert c.put('/api/library-items/'+item['item_id'],json=item).status_code==200
    before=c.get('/api/library-items').json()
    restarted=TestClient(create_app(state_file=state))
    assert restarted.get('/api/library-items').json()==before


def test_corrupt_state_is_not_overwritten(tmp_path):
    state=tmp_path/'state.json'
    state.write_text('invalid')
    with pytest.raises(RuntimeError):
        create_app(state_file=state)
    assert state.read_text()=='invalid'


def test_production_gate_and_capability_contract(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    c=TestClient(create_app())
    request={'name':'核查','asset_path':str(video),'object_ids':['person.zhao_benshan'],'purpose':'production'}
    assert c.post('/api/review-tasks',json=request).status_code==422
    item=c.get('/api/library-items').json()[0]
    item['status']='active'
    assert c.put('/api/library-items/'+item['item_id'],json=item).status_code==200
    assert c.post('/api/review-tasks',json=request).status_code==201
    assert c.post('/api/review-tasks',json={**request,'capabilities':['face','ocr']}).status_code==422
    assert c.post('/api/review-tasks',json={**request,'object_ids':['text.seed_terms']}).status_code==422
    other=tmp_path/'ordinary.txt'
    other.touch()
    assert c.post('/api/review-tasks',json={**request,'asset_path':str(other)}).status_code==422


def test_scope_edit_and_state_guard(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    c=TestClient(create_app())
    request={'name':'验证','asset_path':str(video),'object_ids':['person.zhao_benshan']}
    task=c.post('/api/review-tasks',json=request).json()
    url='/api/review-tasks/'+task['task_id']
    assert c.put(url+'/scope',json={**request,'name':'修改后'}).json()['name']=='修改后'
    assert c.patch(url,json={'status':'needs_review'}).status_code==409
    assert c.put(url+'/scope',json={**request,'purpose':'production'}).status_code==422


def test_retry_preserves_previous_result(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    state=tmp_path/'state.json'
    c=TestClient(create_app(state_file=state))
    task=c.post('/api/review-tasks',json={'name':'旧任务','asset_path':str(video),'object_ids':['person.zhao_benshan']}).json()
    saved=json.loads(state.read_text())
    saved['review_tasks'][0].update(status='needs_review',result={'events':[],'metrics':{'coverage_complete':False}})
    state.write_text(json.dumps(saved))
    c=TestClient(create_app(state_file=state))
    url='/api/review-tasks/'+task['task_id']
    assert c.post(url+'/complete').status_code==409
    new=c.post(url+'/retry')
    assert new.status_code==201
    assert new.json()['previous_task_id']==task['task_id']
    assert new.json()['status']=='ready'
    assert 'result' not in new.json()
    assert c.get(url).json()['result']['metrics']['coverage_complete'] is False


def test_execution_rechecks_production_gate(tmp_path):
    video=tmp_path/'local.mp4'
    video.touch()
    class Stub:
        _analysis_lock=Lock()
    c=TestClient(create_app(analyzer=Stub(),artifact_dir=tmp_path/'artifacts'))
    item=c.get('/api/library-items').json()[0]
    item['status']='active'
    c.put('/api/library-items/'+item['item_id'],json=item)
    task=c.post('/api/review-tasks',json={'name':'生产','asset_path':str(video),'object_ids':[item['item_id']],'purpose':'production'}).json()
    item['status']='disabled'
    c.put('/api/library-items/'+item['item_id'],json=item)
    assert c.post('/api/review-tasks/'+task['task_id']+'/run').status_code==422
