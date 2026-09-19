#!/bin/sh
cd "$(dirname "$0")" || exit 1
./scripts/start_showcase.sh
START_RESULT=$?
if [ "$START_RESULT" -ne 0 ]; then
    printf '\n启动失败，请查看上方提示。按回车关闭。'
    read -r START_REPLY
fi
exit "$START_RESULT"
