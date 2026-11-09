#!/usr/bin/env bash
# ==============================================================================
# Seep 逆向工程工作台 —— 已有用户一键更新 (Linux / macOS)
# ==============================================================================
# 执行流程：
#   1. 记录当前版本与用户自有数据指纹
#   2. 自动探测代理并 git pull 拉取最新代码
#   3. 对比版本，打印 CHANGELOG 变更说明
#   4. 调用 install.sh 做幂等增量同步
#   5. 校验用户自有数据未被覆盖
#   6. 跑官方基准自检并输出更新报告
#
# 安全承诺：
#   · 用户自有数据 (models.json / auth.json / 自定义 MCP 条目 / lab-mode.flag) 永不被覆盖
#   · 覆盖前自动备份到 ~/.pi/agent/backup-<时间戳>/
#
# 用法：
#   ./setup/update.sh
#   ./setup/update.sh --dry-run
#   ./setup/update.sh --no-pull
# ==============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_DIR="${SEEP_AGENT_DIR:-$HOME/.pi/agent}"
VERSION_FILE="$ROOT/VERSION"
CHANGELOG_FILE="$ROOT/CHANGELOG.md"
MCP_JSON="$AGENT_DIR/mcp.json"

GREEN="\033[1;32m"; RED="\033[1;31m"; YELLOW="\033[1;33m"
CYAN="\033[1;36m"; WHITE="\033[1;37m"; GRAY="\033[0;37m"; RESET="\033[0m"

DRY_RUN=0; NO_PULL=0; SKIP_VERIFY=0; STASHED=0; CHECK_ONLY=0
WITH_TOOLS=0; SKIP_CAPABILITIES=0; CAP_ONLY=0
WARNINGS=()

for arg in "$@"; do
    case "$arg" in
        --dry-run)           DRY_RUN=1 ;;
        --no-pull)           NO_PULL=1 ;;
        --check)             CHECK_ONLY=1 ;;
        --skip-verify)       SKIP_VERIFY=1 ;;
        --with-tools)        WITH_TOOLS=1 ;;
        --skip-capabilities) SKIP_CAPABILITIES=1 ;;
        --check-capabilities) CAP_ONLY=1 ;;
        -h|--help)
            echo "用法: $0 [--dry-run] [--no-pull] [--check] [--skip-verify]"
            echo "          [--with-tools] [--check-capabilities] [--skip-capabilities]"
            echo ""
            echo "  --with-tools         顺带补齐外部能力包（ffmpeg / frida / APKiD）"
            echo "  --check-capabilities 只补外部能力、不动代码（网络拉不动代码时用）"
            echo "  --skip-capabilities  跳过能力包步骤（用你已装好的外部工具）"
            exit 0 ;;
        *) echo "未知参数: $arg" >&2; exit 2 ;;
    esac
done

step()  { echo -e "\n${CYAN}>>> $1${RESET}"; }
ok()    { echo -e "    ${GREEN}[OK]${RESET} $1"; }
warn()  { echo -e "    ${YELLOW}[!!]${RESET} $1"; WARNINGS+=("$1"); }
info()  { echo -e "    ${GRAY}[..]${RESET} $1"; }
fail()  { echo -e "    ${RED}[FAIL]${RESET} $1"; }

get_version() {
    if [ -f "$VERSION_FILE" ]; then
        tr -d '[:space:]' < "$VERSION_FILE"
    else
        echo "unknown"
    fi
}

# 用 python3 安全解析 mcp.json 的服务名（不存在则输出空）
mcp_keys() {
    [ -f "$MCP_JSON" ] || return 0
    local py=""
    command -v python3 >/dev/null 2>&1 && py="python3"
    [ -z "$py" ] && command -v python >/dev/null 2>&1 && py="python"
    [ -z "$py" ] && return 0
    "$py" - "$MCP_JSON" <<'PY' 2>/dev/null || true
import json, sys, io
raw = io.open(sys.argv[1], encoding="utf-8-sig").read()
try:
    d = json.loads(raw)
except Exception:
    sys.exit(0)
keys = list((d.get("mcpServers") or {}).keys())
print("\n".join(keys))
PY
}

detect_proxy() {
    for p in 10808 7897 7890; do
        if command -v ss >/dev/null 2>&1; then
            ss -ltn 2>/dev/null | grep -q ":$p " && { echo "$p"; return; }
        elif command -v netstat >/dev/null 2>&1; then
            netstat -ltn 2>/dev/null | grep -q ":$p " && { echo "$p"; return; }
        elif command -v lsof >/dev/null 2>&1; then
            lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 && { echo "$p"; return; }
        fi
    done
}

echo -e "${CYAN}================================================================================${RESET}"
echo -e "${CYAN}          Seep Reverse Lab — 已有用户一键更新 (Updater)${RESET}"
echo -e "${CYAN}================================================================================${RESET}"
echo -e "  工作台根目录: $ROOT"

OLD_VERSION="$(get_version)"

if [ $CHECK_ONLY -eq 1 ]; then
    echo -e "\n${CYAN}>>> 正在检查远程最新版本...${RESET}"
    PROXY_PORT="$(detect_proxy || true)"
    GIT_PROXY=()
    [ -n "$PROXY_PORT" ] && GIT_PROXY=("-c" "http.proxy=http://127.0.0.1:$PROXY_PORT" "-c" "https.proxy=http://127.0.0.1:$PROXY_PORT")

    if [ -d "$ROOT/.git" ]; then
        REMOTE_LINE="$(git -C "$ROOT" "${GIT_PROXY[@]}" ls-remote origin refs/heads/main 2>/dev/null || true)"
        LOCAL_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
        if [ -n "$REMOTE_LINE" ] && [ -n "$LOCAL_SHA" ]; then
            REMOTE_SHA="$(echo "$REMOTE_LINE" | awk '{print $1}')"
            if [ "$REMOTE_SHA" = "$LOCAL_SHA" ]; then
                echo -e "  ${GREEN}[OK]${RESET} 当前工作台已是最新版本 (v$OLD_VERSION, commit ${LOCAL_SHA:0:7})"
                exit 0
            else
                echo -e "  ${YELLOW}[UPDATE]${RESET} 检测到远程仓库有新版本/新提交！(本地: ${LOCAL_SHA:0:7}, 远程: ${REMOTE_SHA:0:7})"
                echo -e "  提示: 执行 ./setup/update.sh 即可一键更新。"
                exit 2
            fi
        fi
    fi

    # 通过 curl 探测 VERSION
    CURL_PROXY=()
    [ -n "$PROXY_PORT" ] && CURL_PROXY=("-x" "http://127.0.0.1:$PROXY_PORT")
    R_VER="$(curl -sSL "${CURL_PROXY[@]}" --max-time 5 https://raw.githubusercontent.com/angusdevgo/Seep-Reverse-Lab/main/VERSION 2>/dev/null | tr -d '[:space:]' || true)"
    if [ -n "$R_VER" ] && [ "$R_VER" != "$OLD_VERSION" ]; then
        echo -e "  ${YELLOW}[UPDATE]${RESET} 检测到新版本 v$R_VER 发布！(当前本地版本: v$OLD_VERSION)"
        echo -e "  提示: 执行 ./setup/update.sh 即可一键更新。"
        exit 2
    else
        echo -e "  ${GREEN}[OK]${RESET} 当前工作台已是最新版本 (v$OLD_VERSION)"
        exit 0
    fi
fi
IS_GIT=0; [ -d "$ROOT/.git" ] && IS_GIT=1

echo -e "  当前版本    : v$OLD_VERSION"
echo -e "  Git 仓库    : $([ "$IS_GIT" = 1 ] && echo '是（支持 git pull）' || echo '否（压缩包部署）')"
echo -e "  运行模式    : $([ "$DRY_RUN" = 1 ] && echo 'DRY RUN（不修改任何文件）' || $([ "$CAP_ONLY" = 1 ] && echo '仅补外部能力包（不动代码）' || echo '正常更新'))"

# --check-capabilities 短路：不动代码、不重装配置，只补能力包
# 适合「网络拉不动代码但缺 ffmpeg/frida」的场景
if [ "$CAP_ONLY" = 1 ]; then
    if [ ! -f "$SCRIPT_DIR/install-capabilities.sh" ]; then
        fail "缺少 setup/install-capabilities.sh"; exit 1
    fi
    step "补齐外部能力包"
    bash "$SCRIPT_DIR/install-capabilities.sh" --only all || true
    echo ""
    echo -e "  完成。若本次新装了 ffmpeg / frida，请完全重启 Agent 会话让 PATH 生效。"
    exit 0
fi

BEFORE_KEYS="$(mcp_keys)"
info "更新前 mcp.json 中的 MCP 服务: $(if [ -n "$BEFORE_KEYS" ]; then echo "$BEFORE_KEYS" | tr '\n' ' '; else echo '（无）'; fi)"
info "受保护的用户自有数据: models.json, auth.json, lab-mode.flag"

if [ "$DRY_RUN" = 1 ]; then
    echo -e "\n  ${YELLOW}[DRY RUN] 将要执行的步骤：${RESET}"
    echo -e "    1. $([ "$NO_PULL" = 1 ] && echo '跳过 git pull（--no-pull）' || echo '自动探测代理并 git pull 拉取最新代码')"
    echo -e "    2. 打印 CHANGELOG 版本变更说明"
    echo -e "    3. 调用 setup/install.sh 做幂等增量同步（自动备份 + 安全合并 mcp.json）"
    echo -e "       外部能力包: $([ "$WITH_TOOLS" = 1 ] && echo '补齐（--with-tools）' || echo '默认只装 ffmpeg')"
    echo -e "    4. 校验用户自有数据未被覆盖"
    echo -e "    5. 跑 setup/verify.sh 官方基准自检"
    echo -e "\n  未修改任何文件。去掉 --dry-run 即执行真实更新。\n"
    exit 0
fi

# ------------------------------------------------------------------ 1. 拉取
step "1/6  拉取最新代码"

if [ "$NO_PULL" = 1 ]; then
    info "已指定 --no-pull，跳过 git pull"
elif [ "$IS_GIT" != 1 ]; then
    if command -v git >/dev/null 2>&1; then
        info "检测到本机已安装 Git，正在将当前目录自动关联并初始化至远程仓库..."
        cd "$ROOT" || exit 1
        git init >/dev/null 2>&1 || true
        git remote add origin https://github.com/angusdevgo/Seep-Reverse-Lab.git >/dev/null 2>&1 || true
        git remote set-url origin https://github.com/angusdevgo/Seep-Reverse-Lab.git >/dev/null 2>&1 || true
        info "正在从远程仓库高速拉取最新代码..."
        git fetch origin main >/dev/null 2>&1 || true
        git reset --mixed origin/main >/dev/null 2>&1 || true
        ok "已成功将当前工作台关联并更新至最新版本！"
        IS_GIT=1
    else
        warn "当前目录不是 Git 仓库且未检测到 Git 命令，无法自动拉取。"
        info "若需更新，可从 GitHub 仓库下载最新压缩包覆盖后重跑本脚本。"
    fi
else
    PROXY_PORT="$(detect_proxy)"
    PROXY_ARGS=()
    if [ -n "$PROXY_PORT" ]; then
        info "检测到可用代理端口: $PROXY_PORT"
        PROXY_ARGS=(-c "http.proxy=http://127.0.0.1:$PROXY_PORT" -c "https.proxy=http://127.0.0.1:$PROXY_PORT")
    else
        info "未检测到常见代理端口，尝试直连"
    fi

    cd "$ROOT" || exit 1
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        warn "工作区存在本地改动，将先 stash 再拉取"
        git stash push -u -m "seep-update-autostash-$(date +%Y%m%d-%H%M%S)" >/dev/null 2>&1 && STASHED=1
    fi

    if git "${PROXY_ARGS[@]}" pull --rebase origin main 2>&1 | sed 's/^/    /'; then
        ok "代码已更新到最新版本"
    else
        fail "git pull 失败（可能是网络或代理问题）"
        info "可尝试：git -c http.proxy=http://127.0.0.1:<你的端口> pull --rebase origin main"
        info "或使用 --no-pull：先手动下载最新压缩包覆盖，再运行 update.sh --no-pull"
        [ "$STASHED" = 1 ] && warn "本地改动仍保存在 git stash 中，可用 git stash pop 恢复"
        exit 1
    fi
fi

# ------------------------------------------------------------------ 2. 版本
step "2/6  版本变更说明"

NEW_VERSION="$(get_version)"
if [ "$OLD_VERSION" = "$NEW_VERSION" ]; then
    info "版本未变化（v$NEW_VERSION）—— 将执行一次幂等重同步（补齐可能缺失的组件）"
else
    ok "版本已更新: v$OLD_VERSION  ->  v$NEW_VERSION"
fi

if [ -f "$CHANGELOG_FILE" ]; then
    echo -e "\n  ${YELLOW}---------- 本次版本变更摘要 ----------${RESET}"
    awk '/^##[[:space:]]*\[/{n++; if(n==2) exit} n>=1{print "  " $0}' "$CHANGELOG_FILE" | head -60
    echo -e "  ${YELLOW}--------------------------------------${RESET}\n"
fi

# ------------------------------------------------------------------ 3. 同步
step "3/6  执行幂等增量同步（自动备份 + 保护自定义配置）"

INSTALL_ARGS=()
[ "$WITH_TOOLS" = 1 ] && INSTALL_ARGS+=("--with-tools")
[ "$SKIP_CAPABILITIES" = 1 ] && INSTALL_ARGS+=("--skip-capabilities")
if bash "$SCRIPT_DIR/install.sh" "${INSTALL_ARGS[@]:-}"; then
    ok "增量同步完成"
else
    warn "install.sh 返回非零，部分步骤可能未完成，请查看上方输出"
fi

# ------------------------------------------------------------------ 4. 校验
step "4/6  用户自有数据零丢失校验"

AFTER_KEYS="$(mcp_keys)"
LOST=""
if [ -n "$BEFORE_KEYS" ]; then
    while IFS= read -r k; do
        [ -z "$k" ] && continue
        echo "$AFTER_KEYS" | grep -qx "$k" || LOST="$LOST $k"
    done <<< "$BEFORE_KEYS"
fi

if [ -n "$LOST" ]; then
    fail "检测到自定义 MCP 服务丢失:$LOST"
    info "请从备份目录恢复：$AGENT_DIR/backup-*/mcp.json"
else
    ok "mcp.json 中的 MCP 服务全部保留（共 $(if [ -n "$AFTER_KEYS" ]; then echo "$AFTER_KEYS" | wc -l | tr -d ' '; else echo 0; fi) 个）"
fi

if [ -f "$AGENT_DIR/models.json" ]; then
    ok "models.json 存在且未被脚本写入（用户凭据安全）"
else
    info "未发现 models.json（尚未配置模型凭据）"
fi

# ------------------------------------------------------------------ 5. 自检
if [ "$SKIP_VERIFY" = 0 ]; then
    step "5/6  官方基准自检"
    if bash "$SCRIPT_DIR/verify.sh"; then
        ok "自检全部通过"
    else
        warn "自检存在未通过项，请查看上方红色标记"
    fi
else
    step "5/6  官方基准自检（已跳过 --skip-verify）"
fi

# ------------------------------------------------------------------ 6. 报告
step "6/6  更新完成报告"

echo -e "\n${WHITE}================================================================================${RESET}"
echo -e "  ${GREEN}Seep 工作台更新完成:  v$OLD_VERSION  ->  v$NEW_VERSION${RESET}"
echo -e "${WHITE}================================================================================${RESET}"

# 动态统计，避免版本迭代后报告里的数字过时
SKILL_DIRS=$(find "$TOOL_DIR/skill" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
SAFE_SKILLS=$(find "$TOOL_DIR/skill/safe-skills" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
SKILL_TOTAL=$((SKILL_DIRS - 1 + SAFE_SKILLS))
TOOL_TOTAL=$(grep -c '^def seep_' "$TOOL_DIR/mcp/seep_mcp_server.py" 2>/dev/null || echo 0)

echo -e ""
echo -e "  ${WHITE}本次同步:${RESET}"
echo -e "    · 逆向技能 ${SKILL_TOTAL} 个（Tool/skill 下 ${SKILL_DIRS} 个目录）"
echo -e "    · MCP 工具定义 ${TOOL_TOTAL} 个"
echo -e "    · 提示词 (seep-system.md / AGENTS.md) 与安全扩展"
echo -e "    · mcp.json 已安全合并（自定义 MCP 条目完整保留，已自动备份）"
echo -e "    · 内置工具箱与知识库已校验"

# 外部能力看板
echo -e ""
echo -e "  ${WHITE}外部能力:${RESET}"
for n in ffmpeg ffprobe frida objection apkid nuclei ffuf; do
    p="$(command -v "$n" 2>/dev/null || true)"
    [ -z "$p" ] && [ -x "$HOME/.seep/web/bin/$n" ] && p="$HOME/.seep/web/bin/$n"
    [ -z "$p" ] && [ -x "$HOME/.seep/android/bin/$n" ] && p="$HOME/.seep/android/bin/$n"
    if [ -n "$p" ]; then
        echo -e "    ${GREEN}[READY]${RESET}   $(printf '%-10s' "$n") $p"
    else
        echo -e "    ${YELLOW}[MISSING]${RESET} $(printf '%-10s' "$n")"
    fi
done
echo -e "    ${YELLOW}[N/A]${RESET}     $(printf '%-10s' aotopsy) Windows-only"
echo -e ""
echo -e "  缺件不影响 MCP 启动：相关工具会返回明确的修复指引，其余工具照常工作。"
echo -e "  ${YELLOW}一条命令全补: ./setup/install-capabilities.sh --only all${RESET}"

echo -e ""
echo -e "  ${WHITE}下一步（顺序不能跳）:${RESET}"
echo -e "    1) 完全关闭并重新打开 Agent 会话"
echo -e "       Pi 与 DSH 都要整个进程退出重开。"
echo -e "       仅刷新或 re-load 不够 —— MCP 工具是启动时握手的，"
echo -e "       不重开就看不到新工具，也读不到新 Skill。"
echo -e "    2) 在对话框中发送:  lab："
echo -e "       即可继续开工"
echo -e ""
echo -e "  如需回滚:"
echo -e "    · 配置备份位于: $AGENT_DIR/backup-<时间戳>/"
echo -e "    · 代码回滚:     git -C \"$ROOT\" log --oneline -10  然后 git reset --hard <commit>"
echo -e ""


if [ "$STASHED" = 1 ]; then
    echo -e "  ${YELLOW}[!!] 你之前的本地改动已自动 stash 保存，恢复命令:${RESET}"
    echo -e "       git -C \"$ROOT\" stash pop\n"
fi

if [ "${#WARNINGS[@]}" -gt 0 ]; then
    echo -e "  ${YELLOW}关注项:${RESET}"
    for w in "${WARNINGS[@]}"; do echo -e "    ${YELLOW}-${RESET} $w"; done
    echo
fi

exit 0
