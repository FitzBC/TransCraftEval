"""Non-labeling local smoke check: bundle assets and playback endpoints."""
import json
from pathlib import Path

import httpx


def main():
    with httpx.Client(base_url='http://127.0.0.1:8770', trust_env=False, timeout=60) as client:
        assert client.get('/api/settings').raise_for_status().json()['profile']=='showcase'
        media=client.get('/api/local-media').raise_for_status().json()
        tasks=client.get('/api/review-tasks').raise_for_status().json()
        people=client.get('/api/library-items').raise_for_status().json()
        for person in people:
            for material in person['materials']:
                client.get(material['local_uri']).raise_for_status()
        checked=[]
        for asset in media:
            response=client.get(asset['url'],headers={'Range':'bytes=0-1023'})
            assert response.status_code==206
            if not asset.get('task_id'):
                checked.append({'name':asset['name'],'playback':'range ok','note':'用户导入素材，尚无默认验证任务关联'})
                continue
            task=next(t for t in tasks if t['task_id']==asset['task_id'])
            assert task['result']['metrics']['coverage_complete']
            events=task['result']['events']
            for event in events:
                assert 0 <= event['evidence_seconds'] <= asset['duration_seconds']
                client.get(event['evidence_image']).raise_for_status()
            for person in task['result']['reference_snapshot']:
                for material in person['materials']:
                    client.get(material['local_uri']).raise_for_status()
            if events:
                preview=client.post(f"/api/review-tasks/{task['task_id']}/events/{events[0]['event_id']}/preview").raise_for_status().json()
                client.get(preview['url'],headers={'Range':'bytes=0-1023'}).raise_for_status()
            checked.append({'name':asset['name'],'duration_seconds':asset['duration_seconds'],'candidates':len(events),'playback':'ok'})
        report={'media':checked,'reference_materials':sum(len(p['materials']) for p in people),'note':'仅验证工程流程；不包含人工身份标注或准确率/召回率结论。'}
        output=Path('output/showcase-check.json')
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
