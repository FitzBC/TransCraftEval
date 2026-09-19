"""Run an explicit all-media/person batch through the application's real API.

Resume with the same output directory to reuse task IDs, never rerun reviewed tasks.
Ground-truth windows are selected independently of detections; humans must label them.
"""
import argparse
import json
import random
import time
from pathlib import Path

import cv2
import httpx


def save(path, data):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--retry-failed',action='store_true')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    manifest_path=args.output/'manifest.json'
    with httpx.Client(base_url='http://127.0.0.1:8766',trust_env=False,timeout=30) as client:
        if manifest_path.exists():
            manifest=json.loads(manifest_path.read_text())
        else:
            media=client.get('/api/local-media').raise_for_status().json()
            people=[p for p in client.get('/api/library-items').raise_for_status().json() if p['category']=='person' and p['status']!='disabled' and any(m['kind']=='reference_image' for m in p['materials'])]
            manifest={'batch':'全媒资交叉验证','people':[{'id':p['item_id'],'name':p['name']} for p in people],'tasks':[]}
            # Register every task before starting expensive analysis.
            for asset in media:
                response=client.post('/api/review-tasks',json={'name':'全库交叉验证 · '+Path(asset['name']).stem,'asset_path':asset['path'],'object_ids':[p['item_id'] for p in people],'purpose':'validation','capabilities':['face']})
                response.raise_for_status()
                task=response.json()
                manifest['tasks'].append({'task_id':task['task_id'],'asset_path':asset['path'],'name':task['name']})
                save(manifest_path,manifest)
                print('CREATED',task['task_id'],task['name'],flush=True)

        if not (args.output/'blind_windows.json').exists():
            windows=[]
            rng=random.Random(20260919)
            for task in manifest['tasks']:
                capture=cv2.VideoCapture(task['asset_path'])
                fps=capture.get(cv2.CAP_PROP_FPS)
                count=capture.get(cv2.CAP_PROP_FRAME_COUNT)
                capture.release()
                duration=count/fps if fps>0 else 0
                if duration<=0:
                    windows.append({'task_id':task['task_id'],'error':'无法读取时长，需人工划定验证区间'})
                    continue
                n=20 if duration>600 else 1
                for i in range(n):
                    width=duration/n
                    length=30 if n>1 else duration
                    start=i*width+rng.uniform(0,max(0,width-length))
                    windows.append({'window_id':f"{task['task_id']}-{i+1}",'task_id':task['task_id'],'asset_path':task['asset_path'],'start_seconds':round(start,2),'end_seconds':round(min(duration,start+length),2),'reviewed':False,'appearances':[]})
            save(args.output/'blind_windows.json',{'seed':20260919,'instruction':'先隐藏检测结果，由人工逐段标注所有目标人物的可辨识出镜区间；appearances填写person_id,start_seconds,end_seconds。完整核查窗口后再设reviewed=true。未标注不等于无人出现。此分层抽样只能估计样本召回，不代表整片真实召回。','people':manifest['people'],'windows':windows})

        for entry in manifest['tasks']:
            task_id=entry['task_id']
            if args.retry_failed:
                task=client.get('/api/review-tasks/'+task_id).raise_for_status().json()
                if task['status']=='failed':
                    response=client.post('/api/review-tasks/'+task_id+'/run')
                    response.raise_for_status()
            last_status=None
            while True:
                try:
                    task=client.get('/api/review-tasks/'+task_id).raise_for_status().json()
                    status=task['status']
                    if status!=last_status:
                        print('STATUS',entry['name'],status,task.get('error',''),flush=True)
                        last_status=status
                    if status in ('needs_review','completed','failed'):
                        save(args.output/(task_id+'.json'),task)
                        break
                    if status=='ready':
                        response=client.post('/api/review-tasks/'+task_id+'/run')
                        if response.status_code not in (202,409):
                            print('BLOCKED',entry['name'],response.status_code,response.text,flush=True)
                            save(args.output/(task_id+'-error.json'),{'status_code':response.status_code,'detail':response.text})
                            break
                    time.sleep(5)
                except httpx.HTTPError as exc:
                    print('NETWORK RETRY',type(exc).__name__,flush=True)
                    time.sleep(10)
        summaries=[]
        for entry in manifest['tasks']:
            task=client.get('/api/review-tasks/'+entry['task_id']).raise_for_status().json()
            result=task.get('result') or {}
            events=result.get('events',[])
            confirmed=sum(e.get('review_status')=='confirmed' for e in events)
            rejected=sum(e.get('review_status')=='rejected' for e in events)
            summaries.append({'task_id':task['task_id'],'name':task['name'],'status':task['status'],'candidates':len(events),'confirmed':confirmed,'rejected':rejected,'reviewed_candidate_precision':confirmed/(confirmed+rejected) if confirmed+rejected else None,'recall':None,'metrics':result.get('metrics',{}),'note':'准确率/召回率待独立人工标注；已复核部分精确率存在选择偏差，不能代替全体候选精确率。'})
        save(args.output/'summary.json',summaries)
        print('BATCH FINISHED; human ground truth still required',flush=True)


if __name__=='__main__':
    main()
