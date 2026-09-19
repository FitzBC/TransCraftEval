"""Read-only fixture, separate mutable state; portable asset paths."""
import json
import hashlib
from pathlib import Path


def load_bundle(bundle: Path):
    bundle = bundle.resolve()
    def asset(relative):
        path = (bundle/relative).resolve()
        if not path.is_relative_to(bundle) or not path.is_file():
            raise ValueError(f'默认素材缺失或路径无效：{relative}')
        return str(path)
    seed = json.loads((bundle/'seed.json').read_text())
    catalog = json.loads((bundle/'catalog.json').read_text())
    for task in seed['review_tasks']:
        task['asset_path'] = asset(task['asset_path'])
    for item in seed['library_items']:
        for material in item.get('materials', []):
            asset(material['local_uri'].removeprefix('/bundled/'))
    for media in catalog:
        media['path'] = asset(media['path'])
        media['size_bytes'] = Path(media['path']).stat().st_size
        with Path(media['path']).open('rb') as stream:
            media['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        task = next((t for t in seed['review_tasks'] if t['task_id']==media.get('task_id')), None)
        if task and task.get('result', {}).get('events'):
            media['poster'] = task['result']['events'][0]['evidence_image']
    return seed, catalog
