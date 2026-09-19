from pathlib import Path
import numpy as np
from face_watch.review_runner import run_review


class FakeAnalyzer:
    def _read_image(self, path):
        return np.ones((16,16,3), dtype=np.uint8)

    def _detect_faces(self, image):
        if image.shape[0] == 16:
            return [np.array([0,0,10,10])]
        return [np.array([1,1,12,12]), np.array([30,1,12,12])]

    def _feature(self, image, face):
        return np.array([1.,0.], dtype=np.float32)


def test_two_simultaneous_faces_never_merge_and_evidence_is_written(tmp_path, monkeypatch):
    class Capture:
        index=0
        def isOpened(self): return True
        def get(self, key):
            import cv2
            return 1 if key == cv2.CAP_PROP_FPS else 3
        def read(self):
            self.index+=1
            return (True,np.zeros((64,64,3),dtype=np.uint8)) if self.index<=3 else (False,None)
        def release(self): pass
    monkeypatch.setattr('face_watch.review_runner.cv2.VideoCapture', lambda _:Capture())
    reference=tmp_path/'ref.bin'
    reference.write_bytes(b'test reference')
    result=run_review(FakeAnalyzer(),tmp_path/'video', [{'id':'p','name':'test','paths':[reference]}],tmp_path/'out',lambda _:None)
    assert len(result['events'])==2
    assert all(e['support_frames']==3 for e in result['events'])
    assert all(e['review_status']=='pending' for e in result['events'])
    assert result['metrics']['raw_hits']==6
    assert result['metrics']['coverage_complete'] is True
    assert len(list((tmp_path/'out').glob('*.jpg')))==2
