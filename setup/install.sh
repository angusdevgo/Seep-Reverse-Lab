#!/usr/bin/env bash
# ==============================================================================
# Seep Reverse Lab — Linux / macOS 一键部署（Installer）
# ==============================================================================
# 与 setup/install.ps1 行为对齐的 7 步流程：
#   1. 环境探测（python3 / node / radare2）
#   2. 解压离线依赖 + 赋执行权限
#   3. 安装 Python mcp 协议库（PEP 668 兜底）
#   4. 备份 + 安全增量合并 ~/.pi/agent/mcp.json（不再整体覆盖）
#   5. 同步技能（先删后拷）/ 提示词 / 扩展
#   6. 生成 .mcp.json / opencode.jsonc / cordis.generated.yml
#   7. 可选：补齐外部能力包
#
# 关键修正（相对旧版）
#   · 旧版 `sed template > mcp.json` 会**整体覆盖**，用户自加 MCP 与 playwright
#     token 直接丢失，且没有备份。现在改走 setup/mcp-merge.py：备份 + 只 upsert
#     工作台托管的条目。
#   · 技能同步改为「先删后拷」，避免上游删掉的文件在本地残留。
#   · 补上 PEP 668 兜底，uv 托管的解释器不再必然失败。
#
# 用法：
#   ./setup/install.sh
#   ./setup/install.sh --with-tools          # 顺带补齐外部能力包
#   ./setup/install.sh --skip-python --skip-pi
#   ./setup/install.sh --non-interactive
# ==============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOL_DIR="$ROOT/Tool"
SAFE_DIR="$TOOL_DIR/mcp/Tool/safe"
# 允许用 SEEP_AGENT_DIR 覆盖（沙盒测试 / 自定义 agent 根目录）
AGENT_DIR="${SEEP_AGENT_DIR:-$HOME/.pi/agent}"

GREEN="\033[1;32m"; RED="\033[1;31m"; YELLOW="\033[1;33m"
CYAN="\033[1;36m"; WHITE="\033[1;37m"; GRAY="\033[0;37m"; RESET="\033[0m"

SKIP_PYTHON=0; SKIP_PI=0; SKIP_CAPABILITIES=0; WITH_TOOLS=0; NON_INTERACTIVE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --skip-python)       SKIP_PYTHON=1; shift ;;
        --skip-pi)           SKIP_PI=1; shift ;;
        --skip-capabilities) SKIP_CAPABILITIES=1; shift ;;
        --with-tools)        WITH_TOOLS=1; shift ;;
        --non-interactive)   NON_INTERACTIVE=1; shift ;;
        -h|--help)           sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数: $1" >&2; exit 2 ;;
    esac
done

step() { echo -e "\n${CYAN}>>> $1${RESET}"; }
ok()   { echo -e "    ${GREEN}[OK]${RESET} $1"; }
warn() { echo -e "    ${YELLOW}[!!]${RESET} $1"; }
info() { echo -e "    ${GRAY}[..]${RESET} $1"; }
err()  { echo -e "    ${RED}[FAIL]${RESET} $1"; }

FAILED=()

echo -e "${CYAN}================================================================================${RESET}"
echo -e "${CYAN}          Seep Reverse Lab — Linux/macOS 部署管线 (Installer)${RESET}"
echo -e "${CYAN}================================================================================${RESET}"
echo -e "  工作台物理根目录: $ROOT"
echo -e "  Agent 目标根目录: $AGENT_DIR"

# ---------------------------------------------------------------- 1. 环境
step "1/7  检查基础运行环境"

# PEP 668：uv 托管的解释器与多数发行版自带 Python 都带 externally-managed 标记，
# 裸 pip install 会直接以 externally-managed-environment 退出，导致 mcp 装不上。
export PIP_BREAK_SYSTEM_PACKAGES=1

# 解析成**绝对解释器路径**：mcp.json 里要写死这个路径，所以不能只留 "python3"
# 这种靠 PATH 解析的名字。Windows 上的 Git Bash 只有 `py` 启动器、没有 python3，
# 因此补一条 `py -3` 兜底。
PY_BIN=""
if [ -n "${SEEP_PYTHON:-}" ] && [ -x "${SEEP_PYTHON}" ]; then
    PY_BIN="$SEEP_PYTHON"
fi
for cand in python3 python; do
    [ -n "$PY_BIN" ] && break
    if command -v "$cand" >/dev/null 2>&1; then
        real="$("$cand" -c "import sys; print(sys.executable)" 2>/dev/null || true)"
        if [ -n "$real" ] && [ -x "$real" ]; then PY_BIN="$real"; fi
    fi
done
# 工作台自带的 venv（与 install-pi.ps1 的 Resolve-SeepPython 对齐）
for v in "$AGENT_DIR/seep-venv/bin/python" "$AGENT_DIR/seep-venv/Scripts/python.exe"; do
    [ -n "$PY_BIN" ] && break
    [ -x "$v" ] && PY_BIN="$v"
done
if [ -z "$PY_BIN" ] && command -v py >/dev/null 2>&1; then
    real="$(py -3 -c "import sys; print(sys.executable)" 2>/dev/null || true)"
    if [ -n "$real" ] && [ -x "$real" ]; then PY_BIN="$real"; fi
fi

if [ -z "$PY_BIN" ]; then
    err "未检测到可执行的 Python 3.11+，请先安装（或用 SEEP_PYTHON 指定）"
    exit 1
fi
ok "Python: $("$PY_BIN" --version 2>&1) ($PY_BIN)"

if command -v node >/dev/null 2>&1; then
    ok "Node.js: $(node --version 2>/dev/null)"
else
    warn "未找到 Node.js（可选，用于 JS 逆向与 Playwright 自动化）"
fi

if [ -d "$TOOL_DIR/mcp" ] && [ -d "$TOOL_DIR/skill" ]; then
    ok "内置离线逆向工具箱完整"
else
    err "Tool/ 目录不完整，请在仓库根目录运行本脚本"
    exit 1
fi

# ---------------------------------------------------------------- 2. 解压
step "2/7  解压内置离线依赖 + 赋执行权限"
for mod in js-reverse-mcp playwright-mcp; do
    target="$SAFE_DIR/$mod/node_modules"
    zipf="$SAFE_DIR/$mod/node_modules.zip"
    if [ ! -d "$target" ] && [ -f "$zipf" ]; then
        info "解压 $mod ..."
        if unzip -q "$zipf" -d "$SAFE_DIR/$mod/" 2>/dev/null; then
            ok "$mod 依赖解压就绪"
        else
            warn "$mod 解压失败（缺 unzip 或压缩包损坏）"
        fi
    else
        ok "$mod 依赖目录已存在"
    fi
done

[ -d "$SAFE_DIR/radare2/bin" ] && chmod +x "$SAFE_DIR/radare2/bin/"* 2>/dev/null || true
[ -f "$SAFE_DIR/jadx/bin/jadx" ] && chmod +x "$SAFE_DIR/jadx/bin/jadx" 2>/dev/null || true
info "radare2 内置二进制为 Windows 版；Unix 下 seep MCP 会优先走系统 PATH"

# ---------------------------------------------------------------- 3. Python 依赖
if [ "$SKIP_PYTHON" = 0 ]; then
    step "3/7  安装 Python mcp 协议库"
    if "$PY_BIN" -m pip install "mcp>=1.20,<1.29" --quiet 2>/dev/null; then
        ok "mcp 协议支持就绪"
    else
        warn "mcp 安装失败，可手动执行：$PY_BIN -m pip install 'mcp>=1.20,<1.29'"
        FAILED+=("python-deps")
    fi
else
    step "3/7  安装 Python mcp 协议库（已跳过 --skip-python）"
fi

# ---------------------------------------------------------------- 4. mcp.json 安全合并
step "4/7  备份并安全合并 ~/.pi/agent/mcp.json"
if [ "$SKIP_PI" = 0 ]; then
    merge_py="$SCRIPT_DIR/mcp-merge.py"
    if [ -f "$merge_py" ]; then
        MERGE_JSON="$("$PY_BIN" "$merge_py" --root "$ROOT" --python "$PY_BIN"             --target "$AGENT_DIR/mcp.json" --json 2>&1)"
        MERGE_RC=$?
        if [ "$MERGE_RC" -eq 0 ]; then
            ok "mcp.json 已安全合并（自定义 MCP 条目完整保留）"
            echo "$MERGE_JSON" | sed 's/^/        /'
            PRESERVED_LIST="$MERGE_JSON"
        else
            warn "mcp.json 合并失败："
            echo "$MERGE_JSON" | sed 's/^/        /'
            FAILED+=("mcp-merge")
        fi
    else
        warn "缺少 setup/mcp-merge.py，无法安全合并；跳过（未覆盖你现有的 mcp.json）"
        FAILED+=("mcp-merge-missing")
    fi
else
    info "已跳过 --skip-pi"
fi

# ---------------------------------------------------------------- 5. 技能与提示词
if [ "$SKIP_PI" = 0 ]; then
    step "5/7  同步技能 / 提示词 / 扩展"
    mkdir -p "$AGENT_DIR/skills" "$AGENT_DIR/extensions"

    for s in "$TOOL_DIR/skill/"*; do
        [ -d "$s" ] || continue
        sname="$(basename "$s")"
        [ "$sname" = "update" ] && continue
        if [ "$sname" = "safe-skills" ]; then
            for sub in "$s/"*; do
                [ -d "$sub" ] || continue
                dst="$AGENT_DIR/skills/$(basename "$sub")"
                rm -rf "$dst"            # 先删后拷：上游删除的文件不会残留
                cp -r "$sub" "$dst" && ok "skill: $(basename "$sub")"
            done
        else
            dst="$AGENT_DIR/skills/$sname"
            rm -rf "$dst"
            cp -r "$s" "$dst" && ok "skill: $sname"
        fi
    done

    if [ -f "$TOOL_DIR/prompts/SYSTEM.md" ]; then
        cp "$TOOL_DIR/prompts/SYSTEM.md" "$AGENT_DIR/seep-system.md"
        rm -f "$AGENT_DIR/SYSTEM.md" 2>/dev/null || true
        ok "prompt: seep-system.md（会话按需加载）"
    fi
    if [ -f "$TOOL_DIR/prompts/AGENTS.md" ]; then
        cp "$TOOL_DIR/prompts/AGENTS.md" "$AGENT_DIR/AGENTS.md"
        ok "prompt: AGENTS.md"
    fi
    if [ -d "$TOOL_DIR/prompts/extensions" ]; then
        for f in "$TOOL_DIR/prompts/extensions/"*.ts; do
            [ -f "$f" ] || continue
            cp "$f" "$AGENT_DIR/extensions/" && ok "extension: $(basename "$f")"
        done
    fi
else
    step "5/7  同步技能 / 提示词 / 扩展（已跳过 --skip-pi）"
fi

# ---------------------------------------------------------------- 6. 生成多 Agent 配置
step "6/7  生成多 Agent 配置文件（.mcp.json / opencode.jsonc / cordis.generated.yml）"
gen_py="$SCRIPT_DIR/generate-configs.py"
if [ -f "$gen_py" ]; then
    if "$PY_BIN" "$gen_py" >/dev/null 2>&1; then
        ok "三份配置已生成"
    else
        warn "生成失败，手动执行：$PY_BIN setup/generate-configs.py"
        FAILED+=("generate-configs")
    fi
else
    warn "缺少 setup/generate-configs.py，跳过"
fi

# ---------------------------------------------------------------- 7. 能力包
if [ "$SKIP_CAPABILITIES" = 0 ]; then
    step "7/7  外部能力包"
    cap_sh="$SCRIPT_DIR/install-capabilities.sh"
    if [ -f "$cap_sh" ]; then
        # 默认只装零成本件；要下载/装包的必须显式 --with-tools
        if [ "$WITH_TOOLS" = 1 ]; then
            bash "$cap_sh" --only all 2>&1 | sed 's/^/    /'
        else
            bash "$cap_sh" --only web 2>&1 | sed 's/^/    /'
            info "其余组件（frida / APKiD / nuclei / ffuf）按需补全："
            info "    ./setup/install-capabilities.sh --only all"
        fi
    else
        warn "缺少 setup/install-capabilities.sh，跳过"
    fi
else
    step "7/7  外部能力包（已跳过 --skip-capabilities）"
fi

# ---------------------------------------------------------------- 汇总
echo -e "\n${CYAN}================================================================================${RESET}"
if [ ${#FAILED[@]} -eq 0 ]; then
    echo -e "  ${GREEN}🎉 Seep Reverse Lab 在当前系统部署完毕！${RESET}"
else
    echo -e "  ${YELLOW}⚠️  部署完成，但以下步骤未完全成功：${FAILED[*]}${RESET}"
    echo -e "     工作台核心功能不受影响，按上方提示补齐即可。"
fi
echo -e "${CYAN}================================================================================${RESET}"
echo    "  下一步提示:"
echo    "  1. 完全退出并重新打开 Agent（Pi / Claude Code / DSH / OpenCode）"
echo    "     —— MCP 工具在会话启动时握手，不重开看不到新工具"
echo    "  2. 在对话框中发送: lab： 即可开启测试"
echo -e "${CYAN}================================================================================${RESET}"

[ ${#FAILED[@]} -eq 0 ] && exit 0 || exit 0
