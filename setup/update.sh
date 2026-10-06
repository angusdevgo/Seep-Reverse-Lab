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
AGENT_DIR="$HOME/.pi/agent"
VERSION_FILE="$ROOT/VERSION"
CHANGELOG_FILE="$ROOT/CHANGELOG.md"
MCP_JSON="$AGENT_DIR/mcp.json"

GREEN="\033[1;32m"; RED="\033[1;31m"; YELLOW="\033[1;33m"
CYAN="\033[1;36m"; WHITE="\033[1;37m"; GRAY="\033[0;37m"; RESET="\033[0m"

DRY_RUN=0; NO_PULL=0; SKIP_VERIFY=0; STASHED=0
WARNINGS=()

for arg in "$@"; do
    case "$arg" in
        --dry-run)     DRY_RUN=1 ;;
        --no-pull)     NO_PULL=1 ;;
        --skip-verify) SKIP_VERIFY=1 ;;
        -h|--help)
            echo "用法: $0 [--dry-run] [--no-pull] [--skip-verify]"
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
IS_GIT=0; [ -d "$ROOT/.git" ] && IS_GIT=1

echo -e "  当前版本    : v$OLD_VERSION"
echo -e "  Git 仓库    : $([ "$IS_GIT" = 1 ] && echo '是（支持 git pull）' || echo '否（压缩包部署）')"
echo -e "  运行模式    : $([ "$DRY_RUN" = 1 ] && echo 'DRY RUN（不修改任何文件）' || echo '正常更新')"

BEFORE_KEYS="$(mcp_keys)"
info "更新前 mcp.json 中的 MCP 服务: $(if [ -n "$BEFORE_KEYS" ]; then echo "$BEFORE_KEYS" | tr '\n' ' '; else echo '（无）'; fi)"
info "受保护的用户自有数据: models.json, auth.json, lab-mode.flag"

if [ "$DRY_RUN" = 1 ]; then
    echo -e "\n  ${YELLOW}[DRY RUN] 将要执行的步骤：${RESET}"
    echo -e "    1. $([ "$NO_PULL" = 1 ] && echo '跳过 git pull（--no-pull）' || echo '自动探测代理并 git pull 拉取最新代码')"
    echo -e "    2. 打印 CHANGELOG 版本变更说明"
    echo -e "    3. 调用 setup/install.sh 做幂等增量同步（自动备份 + 保护自定义 MCP）"
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
    warn "当前目录不是 Git 仓库，无法自动拉取。请手动下载最新压缩包覆盖后重跑本脚本。"
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

if bash "$SCRIPT_DIR/install.sh"; then
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

cat <<EOF

  更新内容:
    · 9 大逆向 Skill 已同步到最新
    · 提示词 (SYSTEM.md / AGENTS.md) 与安全扩展已同步
    · mcp.json 已增量合并（自定义 MCP 完整保留）
    · 内置工具箱与知识库已校验

  下一步:
    1) 完全关闭并重新打开 Agent 会话（Pi / Claude Code / DSH / OpenCode）
       —— 这一步是必须的，新 Skill 与扩展需要重新加载
    2) 在对话框中发送:  lab：
       即可继续开工

  如需回滚:
    · 配置备份位于: $AGENT_DIR/backup-<时间戳>/
    · 代码回滚:     git -C "$ROOT" log --oneline -10  然后 git reset --hard <commit>

EOF

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
