#!/bin/sh
set -eu

usage() {
  echo "Usage: $0 [VIDEO_PATH] [REFERENCE_IMAGE] [PERSON_NAME] [PORT]" >&2
  exit 2
}

[ "$#" -le 4 ] || usage

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
video_path=${1:-$project_dir/examples/sample.mp4}
reference_path=${2:-$project_dir/examples/reference.jpeg}
person_name=${3:-目标人物（老许）}
port=${4:-${FACE_WATCH_PORT:-8765}}

[ -f "$video_path" ] || { echo "Video not found: $video_path" >&2; exit 1; }
[ -f "$reference_path" ] || { echo "Reference image not found: $reference_path" >&2; exit 1; }

echo "Video: $video_path"
echo "Reference: $reference_path"
echo "Person: $person_name"

if [ "${FACE_WATCH_CHECK_ONLY:-0}" = "1" ]; then
  exit 0
fi

cd "$project_dir"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -e .
./scripts/download_models.sh

echo "Starting Face Watch at http://127.0.0.1:$port"
FACE_WATCH_VIDEO=$video_path \
FACE_WATCH_REFERENCE=$reference_path \
FACE_WATCH_PERSON=$person_name \
exec .venv/bin/face-watch --host 127.0.0.1 --port "$port"
