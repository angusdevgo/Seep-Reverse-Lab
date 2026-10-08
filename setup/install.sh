#!/usr/bin/env bash
# ==============================================================================
# Seep Reverse Lab — 跨平台 (Linux/macOS) 一键自动化安装部署脚本
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOL_DIR="$ROOT/Tool"
SAFE_DIR="$TOOL_DIR/mcp/Tool/safe"
AGENT_DIR="$HOME/.pi/agent"

echo "================================================================================"
echo "          Seep Reverse Lab — Linux/macOS 部署管线 (Installer)"
echo "================================================================================"
echo "  工作台物理根目录: $ROOT"
echo "  Agent 目标根目录: $AGENT_DIR"

# 1. 基础环境探测
echo -e "\n[1/5] 🔍 检查基础运行环境..."
if ! command -v python3 &>/dev/null; then
    echo "❌ 错误: 未检测到 python3，请先安装 Python 3.11+。"
    exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  [√] Python 解释器: python3 (v$PY_VER)"

# 2. 离线依赖解压
echo -e "\n[2/5] 📦 解压内置离线依赖..."
for mod in "js-reverse-mcp" "playwright-mcp"; do
    TARGET_DIR="$SAFE_DIR/$mod/node_modules"
    ZIP_FILE="$SAFE_DIR/$mod/node_modules.zip"
    if [ ! -d "$TARGET_DIR" ] && [ -f "$ZIP_FILE" ]; then
        echo "  正在解压: $ZIP_FILE -> $TARGET_DIR"
        unzip -q "$ZIP_FILE" -d "$SAFE_DIR/$mod/"
        echo "  [√] $mod 依赖解压就绪"
    else
        echo "  [√] $mod 依赖目录已存在"
    fi
done

# 3. 赋予工具执行权限 + Radare2 运行时引擎探测
echo -e "\n[3/5] 🔧 配置文件执行权限 / Radare2 引擎..."
if [ -d "$SAFE_DIR/radare2/bin" ]; then
    chmod +x "$SAFE_DIR/radare2/bin/"* 2>/dev/null || true
fi
if [ -f "$SAFE_DIR/jadx/bin/jadx" ]; then
    chmod +x "$SAFE_DIR/jadx/bin/jadx" 2>/dev/null || true
fi

# 内置 radare2/bin 为 Windows 二进制 (*.exe/*.dll)，在 Linux/macOS 无法执行。
# seep MCP 的 _resolve_binary() 在非 Windows 下优先走系统 PATH，故此处确保系统已装 radare2。
if command -v radare2 &>/dev/null; then
    echo "  [√] Radare2 引擎: $(radare2 -v 2>/dev/null | head -1)"
elif [ "$(uname -s)" = "Darwin" ]; then
    if command -v brew &>/dev/null; then
        echo "  [i] 未检测到系统 radare2，正在通过 Homebrew 安装..."
        brew install radare2 && echo "  [√] Radare2 安装完成: $(radare2 -v 2>/dev/null | head -1)" \
            || echo "  ⚠️ brew install radare2 失败，请手动执行: brew install radare2"
    else
        echo "  ⚠️ 未检测到 radare2 与 Homebrew。请先安装 Homebrew，再执行: brew install radare2"
    fi
else
    echo "  ⚠️ 未检测到系统 radare2。请用包管理器安装 (如 apt install radare2 / 参见 https://rada.re)。"
fi
echo "  [√] 二进制可执行权限设置完成"

# 4. 安装 Python mcp 协议库
echo -e "\n[4/5] 🐍 安装 Python 协议支持..."
python3 -m pip install "mcp>=1.20,<1.29" --quiet || {
    echo "⚠️ 自动安装失败，建议手动执行: python3 -m pip install 'mcp>=1.20,<1.29'"
}
echo "  [√] Python MCP 协议支持就绪"

# 5. Pi Agent 配置同步
echo -e "\n[5/5] 🧠 部署 Pi Agent 技能与提示词..."
mkdir -p "$AGENT_DIR/skills" "$AGENT_DIR/extensions"

# 复制 Skills
if [ -d "$TOOL_DIR/skill" ]; then
    for s in "$TOOL_DIR/skill/"*; do
        if [ -d "$s" ]; then
            sname=$(basename "$s")
            if [ "$sname" = "safe-skills" ]; then
                for sub in "$s/"*; do
                    [ -d "$sub" ] && cp -r "$sub" "$AGENT_DIR/skills/"
                done
            elif [ "$sname" != "update" ]; then
                cp -r "$s" "$AGENT_DIR/skills/"
            fi
        fi
    done
    echo "  [√] 技能包同步完成"
fi

# 复制提示词与扩展
[ -f "$TOOL_DIR/prompts/SYSTEM.md" ] && cp "$TOOL_DIR/prompts/SYSTEM.md" "$AGENT_DIR/"
[ -f "$TOOL_DIR/prompts/AGENTS.md" ] && cp "$TOOL_DIR/prompts/AGENTS.md" "$AGENT_DIR/"
if [ -d "$TOOL_DIR/prompts/extensions" ]; then
    cp "$TOOL_DIR/prompts/extensions/"*.ts "$AGENT_DIR/extensions/" 2>/dev/null || true
    echo "  [√] 提示词与安全拦截扩展同步完成"
fi

# 生成 mcp.json
TEMPLATE="$TOOL_DIR/mcp/mcp.json.template"
if [ -f "$TEMPLATE" ]; then
    sed "s|<SEEP_ROOT>|$ROOT|g" "$TEMPLATE" > "$AGENT_DIR/mcp.json"
    echo "  [√] 已生成 ~/.pi/agent/mcp.json (已绑定物理绝对路径)"
fi

echo "================================================================================"
echo "  🎉 恭喜！Seep Reverse Lab 在当前系统部署完毕！"
echo "  下一步提示:"
echo "  1. 退出并重新打开终端启动 Agent (Pi / Claude Code / DSH)"
echo "  2. 在对话框中发送: lab： 即可开启测试！"
echo "================================================================================"
