from pathlib import Path
import json
from fastapi.testclient import TestClient
from face_watch.api import create_app


def test_review_survives_restart_and_retains_history(tmp_path):
    state = tmp_path/'state.json'
    state.write_text(json.dumps({'library_items':[], 'review_tasks':[{'task_id':'t', 'name':'test', 'asset_path':str(tmp_path/'video.mp4'), 'object_ids':[], 'status':'needs_review', 'result':{'events':[{'event_id':'e', 'review_status':'pending', 'start_seconds':0,'person_name':'test'}]}}]}))
    client = TestClient(create_app(state_file=state))
    response = client.patch('/api/review-tasks/t/events/e', json={'review_status':'rejected', 'note':'不是目标'})
    assert response.status_code == 200
    assert response.json()['status'] == 'needs_review'
    assert client.post('/api/review-tasks/t/complete').json()['status'] == 'completed'
    assert client.get('/api/review-tasks/t/report').status_code == 200
    restarted = TestClient(create_app(state_file=state))
    event = restarted.get('/api/review-tasks/t').json()['result']['events'][0]
    assert event['note'] == '不是目标'
    assert event['history'][0]['previous'] == 'pending'
    response = restarted.patch('/api/review-tasks/t/events/e', json={'review_status':'uncertain'})
    assert response.json()['status'] == 'needs_review'
    assert len(response.json()['result']['events'][0]['history']) == 2
    assert restarted.patch('/api/review-tasks/t', json={'status':'completed'}).status_code == 409


def test_restart_marks_running_task_interrupted(tmp_path):
    state = tmp_path/'state.json'
    state.write_text(json.dumps({'library_items':[], 'review_tasks':[{'task_id':'t','status':'running'}]}))
    client = TestClient(create_app(state_file=state))
    assert client.get('/api/review-tasks/t').json()['status'] == 'failed'
    assert client.get('/api/review-tasks/missing').status_code == 404
