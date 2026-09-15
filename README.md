# 视频人脸检索原型（Face Watch）

一个本地离线的开放集人脸检索原型：给定一段视频和一张关键人物照片，逐帧检测人脸，以轨迹时间间隔聚合匹配结果，并输出“自动确认 / 建议复核”两级线索与证据帧。

它是工程原型，不应用于执法、处分或其他高风险自动决策。

## 快速启动

```bash
git clone <repository-url>
cd TransCraftEval
./scripts/run_prototype.sh
```

零参数启动会直接使用仓库内置的 `examples/sample.mp4`、`examples/reference.jpeg` 和人物标签“目标人物（老许）”。脚本会创建 Python 虚拟环境、安装依赖、下载并校验模型，然后启动服务。打开 <http://127.0.0.1:8765>，点击“开始全视频检索”。需要 Python 3.12+、`curl` 和网络连接（首次下载模型时）。

也可以覆盖任意默认值：

```bash
./scripts/run_prototype.sh '/path/to/video.mp4' '/path/to/reference.jpg' '人物名称' 8765
```

如果希望分步启动：

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
./scripts/download_models.sh
FACE_WATCH_VIDEO='/path/to/video.mp4' \
FACE_WATCH_REFERENCE='/path/to/reference.jpg' \
FACE_WATCH_PERSON='人物名称' \
.venv/bin/face-watch --host 127.0.0.1 --port 8765
```

## 实现组成

- `FastAPI`：任务创建、异步进度和结果 API
- OpenCV Zoo `YuNet`：人脸检测和五点定位
- OpenCV Zoo `SFace`：对齐后的人脸特征
- 精确余弦相似度：单个关键人物无需近似向量索引
- 双阈值：高分、多帧证据自动确认；低分线索进入人工复核
- 本地静态 Web UI：无需 Node.js 或云端服务

模型文件由 `scripts/download_models.sh` 下载并校验 SHA-256，不提交到仓库。证据输出位于 `artifacts/`。

仓库中的电影片段和人物照片仅作为原型技术测试样例；用于其他环境或对外分发前，请确认拥有相应使用权限。

## 验证

```bash
.venv/bin/pytest -q
TEST_REFERENCE_IMAGE='/path/to/reference.png' \
  .venv/bin/pytest -q tests/test_real_analyzer_integration.py
```

## 已知边界

- 当前任务状态保存在进程内；重启后不保留，适合单机演示。
- 当前按时间间隔聚合候选帧，尚未接入正式的人脸 tracker 和镜头切分。
- 单张现代正脸照片与 1982 年影片存在显著年龄域差异；低质量、侧脸和背脸线索必须人工复核。
- 相似度不是概率，当前阈值只对这段样片做过初始检查；更换人物、视频来源或模型后必须重新标定。
- 人脸照片和 embedding 属敏感生物识别数据；实际部署前需完成授权、保留期、删除、审计和当地法规评估。
