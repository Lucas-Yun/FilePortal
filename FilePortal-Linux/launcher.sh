#!/usr/bin/env bash
# FilePortal Linux 启动器：双击运行 / 终端执行 ./launcher.sh
# 依赖：python3（3.10+）。第一次运行会把 app/config.ini 里的 Windows 路径
# 改成当前用户的「文档」目录，并在 ~/FilePortalCloud 建立云盘根目录。
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3（例如 sudo apt install python3）。"
  exit 1
fi

exec "$PYTHON" "$DIR/app/linux_launcher.py" "$@"
