#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
if [ "${FACE_WATCH_CHECK_ONLY:-0}" = 1 ]; then
    echo "profile=showcase port=${FACE_WATCH_PORT:-8770} bundle=$PROJECT_DIR/showcase_bundle state=$PROJECT_DIR/data/showcase/state.json"
    exit 0
fi
supported_python() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; }
if [ -n "${FACE_WATCH_PYTHON:-}" ]; then
    RUNTIME_PYTHON=$FACE_WATCH_PYTHON
elif [ -x .venv/bin/python ] && supported_python .venv/bin/python; then
    RUNTIME_PYTHON="$PROJECT_DIR/.venv/bin/python"
elif [ -x "$HOME/miniconda3/envs/transcrafteval/bin/python" ] && supported_python "$HOME/miniconda3/envs/transcrafteval/bin/python"; then
    RUNTIME_PYTHON="$HOME/miniconda3/envs/transcrafteval/bin/python"
elif [ -x .showcase-venv/bin/python ] && supported_python .showcase-venv/bin/python; then
    RUNTIME_PYTHON="$PROJECT_DIR/.showcase-venv/bin/python"
else
    python3 -c 'import sys; assert sys.version_info >= (3,12), "需要 Python 3.12 或更新版本"'
    python3 -m venv .showcase-venv
    RUNTIME_PYTHON="$PROJECT_DIR/.showcase-venv/bin/python"
fi
supported_python "$RUNTIME_PYTHON" || { echo '启动需要 Python 3.12 或更新版本' >&2; exit 1; }
export PYTHONPATH="$PROJECT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
if ! "$RUNTIME_PYTHON" -c 'import fastapi, uvicorn, cv2, numpy, imageio_ffmpeg, multipart, httpx' 2>/dev/null; then
    "$RUNTIME_PYTHON" -m pip install -e .
fi
sh scripts/download_models.sh
export FACE_WATCH_PROFILE=showcase
exec "$RUNTIME_PYTHON" scripts/launch_showcase.py
