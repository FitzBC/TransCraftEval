#!/bin/sh
set -eu

usage() {
  echo "Usage: $0 VIDEO_PATH REFERENCE_IMAGE [PERSON_NAME] [PORT]" >&2
  exit 2
}

[ "$#" -ge 2 ] || usage

video_path=$1
reference_path=$2
person_name=${3:-目标人物}
port=${4:-8765}
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

[ -f "$video_path" ] || { echo "Video not found: $video_path" >&2; exit 1; }
[ -f "$reference_path" ] || { echo "Reference image not found: $reference_path" >&2; exit 1; }

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
