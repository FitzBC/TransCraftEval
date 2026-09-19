import cv2
import numpy as np
from fastapi.testclient import TestClient
from face_watch.api import create_app
from face_watch.reference_quality import assess_reference


def test_background_texture_does_not_hide_blurred_face():
    image=np.random.default_rng(3).integers(0,256,(240,240,3),dtype=np.uint8)
    image[40:180,40:180]=120
    result=assess_reference(image,[np.array([40,40,140,140])])
    assert any('模糊' in r for r in result['issues'])


def test_multiple_small_and_side_faces():
    image=np.random.default_rng(4).integers(0,256,(240,240,3),dtype=np.uint8)
    assert assess_reference(image,[])['issues']
    assert assess_reference(image,[np.zeros(4),np.zeros(4)])['issues']
    assert any('太小' in r for r in assess_reference(image,[np.array([30,30,40,40])])['issues'])
    face=np.array([20,20,180,180,70,80,140,80,175,120,70,155,135,155])
    assert any('偏侧' in r for r in assess_reference(image,[face])['issues'])


def test_disabled_reference_persists_and_blocks_empty_gallery(tmp_path):
    c=TestClient(create_app(state_file=tmp_path/'state.json'))
    person='person.zhao_benshan'
    material=c.get('/api/library-items/'+person+'/materials').json()[0]
    url='/api/library-items/'+person+'/materials/'+material['material_id']
    assert c.patch(url,json={'status':'disabled','quality_note':'画面模糊'}).status_code==200
    video=tmp_path/'sample.mp4';video.touch()
    assert c.post('/api/review-tasks',json={'name':'test','asset_path':str(video),'object_ids':[person]}).status_code==422
    restarted=TestClient(create_app(state_file=tmp_path/'state.json'))
    assert restarted.get('/api/library-items/'+person+'/materials').json()[0]['status']=='disabled'
    assert restarted.patch(url,json={'status':'pending_validation','quality_note':'人工复查后恢复待验证'}).status_code==200
