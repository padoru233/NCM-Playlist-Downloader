#!/usr/bin/env bash

# -------------------------------------------------------------
# 您正在阅读此脚本的源代码。
# 若要运行 Downloader，请右键此脚本选择“作为程序运行”
# 或使用终端执行此脚本
# sh ./run.sh
# -------------------------------------------------------------


set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

trap 'echo "发生错误，脚本终止" >&2; exit 1' ERR

printf "\033]0;网易云音乐下载器\007" || true

if [ ! -t 0 ] && [ -z "${CI:-}" ]; then
    if [[ "${PREFIX:-}" == *com.termux* ]]; then
        : # termux: ok
    elif [[ "$OSTYPE" == darwin* ]] && command -v osascript >/dev/null 2>&1; then
        osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$PROJECT_DIR' && bash './run.sh'"
end tell
EOF
        exit 0
    else
        if command -v x-terminal-emulator >/dev/null 2>&1; then
            exec x-terminal-emulator -e "$0" "$@"
        elif command -v gnome-terminal >/dev/null 2>&1; then
            exec gnome-terminal -- "$0" "$@"
        elif command -v konsole >/dev/null 2>&1; then
            exec konsole -e "$0" "$@"
        elif command -v xfce4-terminal >/dev/null 2>&1; then
            exec xfce4-terminal -e "$0" "$@"
        elif command -v xterm >/dev/null 2>&1; then
            exec xterm -e "$0" "$@"
        else
            echo "找不到终端模拟器，请在终端中运行此脚本" >&2
            exit 1
        fi
    fi
fi
        VENV_CREATED=false

        try_install_python() {
            echo "尝试自动安装 Python（若可行）..."
            # Termux
            if [[ "${PREFIX:-}" == *com.termux* ]] && command -v pkg >/dev/null 2>&1; then
                pkg install -y python || true
                return
            fi

            # macOS with brew
            if [[ "$OSTYPE" == darwin* ]] && command -v brew >/dev/null 2>&1; then
                brew install python || true
                return
            fi

            # Linux - try common package managers with sudo if available
            SUDO=""
            if command -v sudo >/dev/null 2>&1; then
                SUDO="sudo"
            fi
            if command -v apt >/dev/null 2>&1 || command -v apt-get >/dev/null 2>&1; then
                ${SUDO} apt-get update || true
                ${SUDO} apt-get install -y python3 python3-venv python3-pip || true
                return
            fi
            if command -v dnf >/dev/null 2>&1; then
                ${SUDO} dnf install -y python3 python3-venv python3-pip || true
                return
            fi
            if command -v pacman >/dev/null 2>&1; then
                ${SUDO} pacman -Syu --noconfirm python python-virtualenv || true
                return
            fi
            if command -v zypper >/dev/null 2>&1; then
                ${SUDO} zypper install -y python3 python3-venv python3-pip || true
                return
            fi
            if command -v apk >/dev/null 2>&1; then
                ${SUDO} apk add --no-cache python3 py3-virtualenv python3-dev || true
                return
            fi
            echo "未检测到可用的包管理器或权限不足，无法自动安装 Python。请参考 README 手动安装。" >&2
        }

# 选择 Python 解释器（优先 python3）
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "未找到 Python，请先安装 Python 3。" >&2
    if [[ "$OSTYPE" == darwin* ]]; then
    # 再次检测
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            PYTHON="$cmd"
            break
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo "仍未找到 Python，请手动安装 Python 3（示例：apt-get install python3 python3-venv 或 brew install python）。" >&2
        exit 1
    fi
        echo "macOS 可使用: brew install python" >&2
    fi
    if [[ "${PREFIX:-}" == *com.termux* ]]; then
        echo "Termux 可使用: pkg install python" >&2
    fi
    exit 1
fi

"$PYTHON" - <<'PY' || true
import sys
v = sys.version_info
if v < (3,7):
        print(f"警告：检测到 Python 版本 {v.major}.{v.minor}.{v.micro}，建议使用 3.7+。", flush=True)
PY

VENV_DIR="$PROJECT_DIR/venv"
DEPS_INSTALLED=true
VENV_CREATED=true
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境..."
    if ! "$PYTHON" -m venv "$VENV_DIR" 2>/dev/null; then
        echo "venv 模块不可用，尝试 ensurepip 修复..." >&2
        "$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
        "$PYTHON" -m venv "$VENV_DIR"
    fi
    DEPS_INSTALLED=false
fi

# 激活虚拟环境
on_error() {
  echo "脚本发生错误，进行清理..." >&2
  # 如果 venv 存在则删除（按要求）
  if [ -d "$VENV_DIR" ]; then
    echo "删除虚拟环境 $VENV_DIR ..."
    rm -rf "$VENV_DIR" || true
  fi
  cleanup
  exit 1
}

# 在 ERR 时删除 venv（用户要求）
trap on_error ERR
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# 退出时确保退出 venv（不因错误而中断）
cleanup() {
    deactivate 2>/dev/null || true
}
trap cleanup EXIT

# 检查 pip 是否可用
if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
    echo "pip 未安装，将进行安装..."
    DEPS_INSTALLED=false
    "$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
fi

# 首次或修复后安装依赖（使用清华源，与 run.bat 一致）
if [ "$DEPS_INSTALLED" = false ]; then
    echo "安装依赖，这可能需要一段时间..."
    "$PYTHON" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple/
    if [ -f requirements.txt ]; then
        "$PYTHON" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
    fi

# 成功执行后，保持 venv（不删除）并正常退出
else
    echo "依赖检查完成..."
fi

# 清屏后运行主脚本
clear || true
"$PYTHON" script.py

