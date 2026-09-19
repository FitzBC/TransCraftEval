"""Import a completed offline experiment while the local server is stopped."""
import argparse
import json
from pathlib import Path
import shutil
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('experiment', type=Path)
    args = parser.parse_args()
    source = args.experiment.resolve()
    evidence = json.loads((source/'machine_evidence_manifest.json').read_text())
    observations = json.loads((source/'machine_observations.json').read_text())
    state_path = ROOT/'data/media_review_state.json'
    state = json.loads(state_path.read_text())
    people = {p['item_id']: p['name'] for p in state['library_items']}
    for media in sorted({r['media'] for r in observations}):
        import_key = f'{source.name}:{media}'
        if any(t.get('import_key') == import_key for t in state['review_tasks']):
            continue
        paths = [p for p in (ROOT/'媒资').rglob('*') if p.suffix in ('.mp4','.ts') and media in p.name]
        if len(paths) != 1:
            raise ValueError(f'Expected one local file for {media}')
        run_id = uuid4().hex
        folder = ROOT/'artifacts'/run_id
        folder.mkdir(parents=True)
        events = []
        for row in evidence:
            if row['media'] != media:
                continue
            person_id = 'person.'+row['candidate_bucket'].split('__')[-1]
            event_id = uuid4().hex
            image = (source/row['evidence_file']).resolve()
            if not image.is_relative_to(source):
                raise ValueError('Invalid evidence path')
            shutil.copy2(image, folder/f'{event_id}.jpg')
            events.append({'event_id': event_id, 'person_id': person_id, 'person_name': people.get(person_id, person_id), 'start_seconds': row['timestamp_seconds'], 'end_seconds': row['timestamp_seconds'], 'evidence_seconds': row['timestamp_seconds'], 'support_frames': 1, 'best_score': row['candidate_score'], 'review_status': 'pending', 'note': '', 'history': [], 'evidence_image': f'/artifacts/{run_id}/{event_id}.jpg'})
        events.sort(key=lambda e: (e['start_seconds'], e['person_name']))
        state['review_tasks'].insert(0, {'task_id': uuid4().hex, 'import_key': import_key, 'name': f'多人物验证 · {media}', 'asset_path': str(paths[0]), 'object_ids': sorted({e['person_id'] for e in events}), 'status': 'needs_review', 'progress': 1, 'channels': {'face':'available','ocr':'not_configured','asr':'not_configured','content':'not_configured'}, 'result': {'events': events, 'method': '历史全片30秒抽样实验', 'metrics': {'sample_seconds':30, 'detected_faces':sum(r['media']==media for r in observations), 'coverage_complete':None}, 'validation_note':'历史实验抽检集：每个人物仅保留得分最高的2张证据，包括低分和交叉片干扰。此处展示20张抽检证据，不是全部候选；没有逐帧真值，不能计算准确率或召回率。'}})
    temporary = state_path.with_suffix('.import.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    temporary.replace(state_path)
    print('Imported experiment; tasks:', len(state['review_tasks']))


if __name__ == '__main__':
    main()
