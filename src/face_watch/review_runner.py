"""Local multi-person candidate scan. No automatic identity confirmation."""
from pathlib import Path
from uuid import uuid4
import hashlib
import time
import shutil

import cv2
import numpy as np

from .multi_reference import ReferenceEmbedding, PersonGallery, PersonPolicy, score_person


def run_review(analyzer, video, people, output, progress, interval=1.0):
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    policy = PersonPolicy(.35, .5, .03)
    galleries, snapshot = [], []
    for person in people:
        refs, hashes, accepted_paths, rejected_references = [], [], [], []
        for path in person['paths']:
            image = analyzer._read_image(path)
            faces = analyzer._detect_faces(image)
            if len(faces) != 1:
                if person.get('skip_invalid_references'):
                    rejected_references.append({'filename':path.name,'reason':'参考图须包含一张可检测人脸','detected_faces':len(faces)})
                    continue
                raise ValueError(f"{person['name']}参考图须包含一张可检测人脸：{path.name}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            refs.append(ReferenceEmbedding(analyzer._feature(image, faces[0]), cluster_id=digest))
            hashes.append(digest)
            accepted_paths.append(path)
        if not refs:
            raise ValueError(f"{person['name']}没有通过质检的参考图，不能跳过该人物")
        galleries.append(PersonGallery(person['id'], tuple(refs)))
        materials=[]
        for path, digest in zip(accepted_paths, hashes):
            filename=f'reference-{digest}{path.suffix}'
            shutil.copy2(path,output/filename)
            materials.append({'kind':'reference_image','local_uri':f'/artifacts/{output.name}/{filename}'})
        snapshot.append({'person_id': person['id'], 'name': person['name'], 'reference_count': len(refs), 'reference_hashes': hashes, 'materials':materials, 'rejected_references':rejected_references})
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError('无法打开本地媒资')
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps <= 0:
        capture.release()
        raise ValueError('无法读取有效帧率')
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    events, active = [], []
    index = sampled = face_count = hits = 0
    next_time = 0.0
    names = {p['id']: p['name'] for p in people}
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = index / fps
            index += 1
            if timestamp < next_time:
                continue
            next_time += interval
            sampled += 1
            active = [t for t in active if timestamp - t['last'] <= interval * 1.5]
            used = set()
            for face in analyzer._detect_faces(frame):
                face_count += 1
                feature = analyzer._feature(frame, face)
                scores = sorted((score_person(feature, g, policy) for g in galleries), key=lambda s: s.recall_score, reverse=True)
                best = scores[0]
                if best.recall_score < policy.candidate_threshold:
                    continue
                hits += 1
                margin = best.recall_score - scores[1].recall_score if len(scores) > 1 else None
                ambiguous = margin is not None and margin < .03
                match = None
                # Spatial AND appearance continuity; never merge simultaneous faces.
                for track in active:
                    if track['event']['event_id'] in used or track['event']['person_id'] != best.person_id:
                        continue
                    a, b = face[:4], track['box']
                    left, top = max(a[0], b[0]), max(a[1], b[1])
                    right, bottom = min(a[0]+a[2], b[0]+b[2]), min(a[1]+a[3], b[1]+b[3])
                    intersection = max(0, right-left)*max(0, bottom-top)
                    union = a[2]*a[3]+b[2]*b[3]-intersection
                    if union > 0 and intersection/union > .15 and feature @ track['feature'] > .5:
                        match = track
                        break
                if match is None:
                    event = {'event_id': uuid4().hex, 'person_id': best.person_id, 'person_name': names[best.person_id], 'start_seconds': round(timestamp, 3), 'end_seconds': round(timestamp, 3), 'support_frames': 0, 'best_score': -1, 'review_status': 'pending', 'note': '', 'history': [], 'ambiguous': False}
                    match = {'event': event}
                    active.append(match)
                    events.append(event)
                event = match['event']
                used.add(event['event_id'])
                event['end_seconds'] = round(timestamp, 3)
                event['support_frames'] += 1
                event['ambiguous'] |= ambiguous
                if best.recall_score > event['best_score']:
                    event.update(best_score=round(best.recall_score, 5), evidence_seconds=round(timestamp, 3), margin=None if margin is None else round(margin, 5), topk_score=round(best.topk_mean_score, 5))
                    preview = frame.copy()
                    x, y, w, h = map(int, face[:4])
                    cv2.rectangle(preview, (x,y), (x+w,y+h), (52,211,153), 3)
                    ok, encoded = cv2.imencode('.jpg', preview)
                    if not ok:
                        raise ValueError('证据图编码失败')
                    encoded.tofile(output / f"{event['event_id']}.jpg")
                    event['evidence_image'] = f"/artifacts/{output.name}/{event['event_id']}.jpg"
                match.update(last=timestamp, box=face[:4].copy(), feature=feature)
            progress({'progress': min(.99, index/total) if total > 0 else 0, 'sampled_frames': sampled, 'detected_faces': face_count, 'candidate_count': len(events), 'scanned_seconds': round(timestamp, 1)})
    finally:
        capture.release()
    if index == 0:
        raise ValueError('未能解码任何帧')
    complete = total > 0 and index >= total - max(2, int(fps))
    return {'events': events, 'metrics': {'sampled_frames': sampled, 'detected_faces': face_count, 'raw_hits': hits, 'decoded_frames': index, 'expected_frames': total, 'duration_seconds': round(index/fps, 2), 'sample_seconds': interval, 'coverage_complete': complete, 'elapsed_seconds': round(time.monotonic()-started, 2)}, 'reference_snapshot': snapshot, 'method': 'YuNet + SFace / 多图候选召回 / 空间与外观短时关联', 'validation_note': '候选尚未经独立标注；无法据此计算召回率。' if complete else '解码长度未通过完整性检查，结果仅覆盖已读取区间。'}
