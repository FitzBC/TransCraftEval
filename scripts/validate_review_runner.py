"""Determinism and sampling-density experiment; does not assign identity labels."""
import json
from pathlib import Path
from face_watch.opencv_analyzer import OpenCvAnalyzer, AnalyzerConfig
from face_watch.review_runner import run_review

ROOT = Path(__file__).resolve().parents[1]
out = ROOT/'output/review_runner_validation'
out.mkdir(parents=True, exist_ok=True)
refs = ROOT/'frontend_dist/assets/references/historical-validation'
people = [
    {'id':'person.zhu_shimao','name':'朱时茂','paths':[ROOT/'examples/reference.jpeg']},
    {'id':'person.zhao_yue','name':'赵越','paths':[refs/'zhao-yue.jpg',refs/'zhao-yue-2.jpg']},
    {'id':'person.tao_jin','name':'陶金','paths':[refs/'tao-jin.jpg',refs/'tao-jin-film-still.jpg']},
]
analyzer = OpenCvAnalyzer(AnalyzerConfig(detector_model=ROOT/'models/face_detection_yunet_2023mar.onnx',recognizer_model=ROOT/'models/face_recognition_sface_2021dec.onnx',output_dir=out,detection_score_threshold=.65))
results = []
for name, interval in [('one_second_a',1.0),('one_second_b',1.0),('half_second',.5)]:
    result = run_review(analyzer, ROOT/'examples/sample.mp4', people, out/name, lambda _:None, interval)
    result['signature'] = [(e['person_id'],e['start_seconds'],e['end_seconds'],e['best_score'],e['support_frames']) for e in result['events']]
    results.append(result)
    print(name, result['metrics'], 'events',len(result['events']),flush=True)
assert results[0]['signature']==results[1]['signature'], 'Repeated scan differs'
report = {'repeat_identical':True,'runs':results,'limitation':'Unlabelled candidate experiment; precision and recall unavailable.'}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('Repeat stability PASS; report:',out/'report.json')
