#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
model_dir="$project_dir/models"
mkdir -p "$model_dir"

download_and_verify() {
  url=$1
  output=$2
  expected_sha=$3

  if [ -f "$output" ]; then
    existing_sha=$(shasum -a 256 "$output" | awk '{print $1}')
    if [ "$existing_sha" = "$expected_sha" ]; then
      echo "Using verified model: $output"
      return
    fi
  fi

  curl -fL --retry 3 --output "$output.part" "$url"
  actual_sha=$(shasum -a 256 "$output.part" | awk '{print $1}')
  if [ "$actual_sha" != "$expected_sha" ]; then
    rm -f "$output.part"
    echo "Checksum mismatch for $output" >&2
    exit 1
  fi
  mv "$output.part" "$output"
}

download_and_verify \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  "$model_dir/face_detection_yunet_2023mar.onnx" \
  "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

download_and_verify \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" \
  "$model_dir/face_recognition_sface_2021dec.onnx" \
  "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"

echo "Models downloaded and verified in $model_dir"
