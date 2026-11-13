#!/usr/bin/env bash
# ============================================================================
#  Seep 逆向工程工作台 —— 一键卸载 (Linux / macOS)
# ============================================================================
#  设计原则：只移除工作台自己装的东西，绝不碰你的数据。
#
#  卸载范围（逐项可关）：
#    · ~/.pi/agent/skills/<工作台技能>      —— 仅工作台自带的 9 大技能
#    · ~/.pi/agent/AGENTS.md / SYSTEM.md    —— 工作台写入的提示词
#    · ~/.pi/agent/extensions/*.ts          —— 工作台扩展
#    · ~/.pi/agent/mcp.json 中的 seep / js-reverse / playwright 条目
#    · ~/.pi/agent/settings.json 中工作台加入的 packages
#    · ~/.pi/agent/lab-mode.flag            —— 实验环境标志
#
#  严格保护（永不删除）：
#    · models.json / auth.json / sessions/ / logs/
#    · 你自己添加的 Skill、MCP 条目、settings.json 字段
#    · 你自己的 backup-* 备份目录（除非显式 --purge）
#
#  用法：
#    ./setup/uninstall.sh --dry-run
#    ./setup/uninstall.sh
#    ./setup/uninstall.sh --yes --keep-skills
#    ./setup/uninstall.sh --restore "$HOME/.pi/agent/backup-uninstall-20261011-120000"
# ============================================================================
set -uo pipefail

DRY_RUN=0; ASSUME_YES=0
KEEP_SKILLS=0; KEEP_PROMPTS=0; KEEP_MCP=0; KEEP_PACKAGES=0; KEEP_LAB_FLAG=0
PURGE=0; RESTORE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run|-n)     DRY_RUN=1 ;;
        --yes|-y)         ASSUME_YES=1 ;;
        --keep-skills)    KEEP_SKILLS=1 ;;
        --keep-prompts)   KEEP_PROMPTS=1 ;;
        --keep-mcp)       KEEP_MCP=1 ;;
        --keep-packages)  KEEP_PACKAGES=1 ;;
        --keep-lab-flag)  KEEP_LAB_FLAG=1 ;;
        --purge)          PURGE=1 ;;
        --restore)        shift; RESTORE="${1:-}" ;;
        -h|--help)
            sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "未知参数: $1（用 --help 查看用法）" >&2; exit 2 ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_DIR="$HOME/.pi/agent"
SKILLS_DIR="$AGENT_DIR/skills"
EXT_DIR="$AGENT_DIR/extensions"
MCP_JSON="$AGENT_DIR/mcp.json"
SET_JSON="$AGENT_DIR/settings.json"
LAB_FLAG="$AGENT_DIR/lab-mode.flag"

if [ -t 1 ]; then
    RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'
    CYAN=$'\033[1;36m'; GRAY=$'\033[0;37m'; MAGENTA=$'\033[1;35m'; RESET=$'\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; GRAY=''; MAGENTA=''; RESET=''
fi

step()  { echo -e "\n${CYAN}>>> $*${RESET}"; }
ok()    { echo -e "    ${GREEN}[OK]${RESET} $*"; }
warn()  { echo -e "    ${YELLOW}[!!]${RESET} $*"; }
info()  { echo -e "    ${GRAY}[..]${RESET} $*"; }
fail()  { echo -e "    ${RED}[FAIL]${RESET} $*"; }

REMOVED=0; FAILED=0

# ---------------------------------------------------------------------------
# 工作台自有资产清单（与 install.sh / install-pi.ps1 严格对齐）
# ---------------------------------------------------------------------------
workbench_skill_names() {
    local src="$ROOT/Tool/skill" d sub
    [ -d "$src" ] || return 0
    {
        for d in "$src"/*/; do
            [ -d "$d" ] || continue
            local name; name="$(basename "$d")"
            if [ "$name" = "safe-skills" ]; then
                for sub in "$d"*/; do [ -d "$sub" ] && basename "$sub"; done
            elif [ "$name" != "update" ]; then
                echo "$name"
            fi
        done
    } | awk '!seen[$0]++'
}

WORKBENCH_PACKAGES=(
    "npm:pi-open-tui" "npm:pi-web-access" "npm:@juicesharp/rpiv-todo"
    "npm:@narumitw/pi-btw" "npm:@narumitw/pi-plan-mode" "npm:@narumitw/pi-usage"
    "npm:pi-mcp-extension" "npm:@smoose/pi-themes" "npm:pi-tool-display"
    "npm:@juicesharp/rpiv-ask-user-question" "npm:pi-playwright" "npm:pi-goal-x"
)

# 用 Python 做 JSON 读写（零新依赖，仅标准库）
# 注意：Windows 下 Python 默认把 \n 转成 \r\n，会让读出的键名带尾随 \r，
# 因此所有 helper 都强制以 LF 输出，并在 bash 侧再防御性剥离一次。
json_keys() {  # json_keys <file> <top-level-key>
    python - "$1" "$2" <<'PY' 2>/dev/null
import json, sys, io, os
try:
    sys.stdout.reconfigure(newline='\n')
except Exception:
    pass
p, k = sys.argv[1], sys.argv[2]
if not os.path.exists(p): sys.exit(0)
try:
    d = json.loads(io.open(p, encoding='utf-8-sig').read())
except Exception:
    sys.exit(0)
v = d.get(k)
if isinstance(v, dict):
    for name in v: sys.stdout.write(str(name) + '\n')
elif isinstance(v, list):
    for item in v: sys.stdout.write(str(item) + '\n')
PY
}

# 判定 MCP 条目是否归工作台所有（看 args 是否指向工作台组件）
mcp_entry_is_ours() {  # mcp_entry_is_ours <name>
    local name="${1%$'\r'}" args
    args="$(python - "$MCP_JSON" "$name" <<'PY' 2>/dev/null
import json, sys, io, os
try:
    sys.stdout.reconfigure(newline='\n')
except Exception:
    pass
p, name = sys.argv[1], sys.argv[2]
if not os.path.exists(p): sys.exit(0)
try:
    d = json.loads(io.open(p, encoding='utf-8-sig').read())
    e = d.get('mcpServers', {}).get(name, {})
    sys.stdout.write(' '.join(str(a) for a in e.get('args', [])))
except Exception:
    pass
PY
)"
    args="${args%$'\r'}"
    case "$name" in
        seep)       [[ "$args" == *seep_mcp_server.py* ]] ;;
        js-reverse) [[ "$args" == *js-reverse-mcp* ]] ;;
        playwright) [[ "$args" == *@playwright/mcp* ]] ;;
        *)          return 1 ;;
    esac
}

# ===========================================================================
# 模式 A：从备份恢复
# ===========================================================================
if [ -n "$RESTORE" ]; then
    echo -e "\n${MAGENTA}╔══════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${MAGENTA}║   Seep Lab —— 从备份恢复                                   ║${RESET}"
    echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════╝${RESET}"

    if [ ! -d "$RESTORE" ]; then fail "备份目录不存在: $RESTORE"; exit 1; fi

    step "1/2  扫描备份内容"
    info "备份目录: $RESTORE"
    COUNT=$(find "$RESTORE" -type f 2>/dev/null | wc -l | tr -d ' ')
    info "文件数: $COUNT"

    step "2/2  恢复"
    if [ "$DRY_RUN" = "1" ]; then
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            info "将恢复: ${f#$RESTORE/}"
        done < <(find "$RESTORE" -type f 2>/dev/null)
        warn '--dry-run 模式，未做任何修改'
        exit 0
    fi
    RESTORED=0
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        rel="${f#$RESTORE/}"
        dst="$AGENT_DIR/$rel"
        mkdir -p "$(dirname "$dst")"
        if cp "$f" "$dst" 2>/dev/null; then RESTORED=$((RESTORED+1)); fi
    done < <(find "$RESTORE" -type f 2>/dev/null)
    ok "已恢复 $RESTORED 个文件"
    info "请完全重启 Agent 会话后生效"
    exit 0
fi

# ===========================================================================
# 模式 B：卸载
# ===========================================================================
echo -e "\n${MAGENTA}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${MAGENTA}║   Seep 逆向工程工作台 —— 一键卸载                             ║${RESET}"
echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════╝${RESET}"
[ "$DRY_RUN" = "1" ] && warn 'DRY-RUN 模式：只预览，不做任何修改'

# ---------------------------------------------------------------- 1. 盘点
step '1/5  盘点将要移除的内容'

SKILL_NAMES=$(workbench_skill_names)
SKILL_HITS=()
if [ "$KEEP_SKILLS" = "0" ]; then
    while IFS= read -r n; do
        [ -z "$n" ] && continue
        [ -d "$SKILLS_DIR/$n" ] && SKILL_HITS+=("$n")
    done <<< "$SKILL_NAMES"
fi

PROMPT_HITS=()
if [ "$KEEP_PROMPTS" = "0" ]; then
    for f in AGENTS.md SYSTEM.md; do
        [ -f "$AGENT_DIR/$f" ] && PROMPT_HITS+=("$f")
    done
    if [ -d "$EXT_DIR" ]; then
        for f in "$EXT_DIR"/*.ts; do
            [ -f "$f" ] && PROMPT_HITS+=("extensions/$(basename "$f")")
        done
    fi
fi

MCP_HITS=()
if [ "$KEEP_MCP" = "0" ] && [ -f "$MCP_JSON" ]; then
    while IFS= read -r k; do
        k="${k%$'\r'}"
        [ -z "$k" ] && continue
        mcp_entry_is_ours "$k" && MCP_HITS+=("$k")
    done < <(json_keys "$MCP_JSON" mcpServers)
fi

PKG_HITS=()
if [ "$KEEP_PACKAGES" = "0" ] && [ -f "$SET_JSON" ]; then
    while IFS= read -r pkg; do
        pkg="${pkg%$'\r'}"
        [ -z "$pkg" ] && continue
        for wp in "${WORKBENCH_PACKAGES[@]}"; do
            [ "$pkg" = "$wp" ] && PKG_HITS+=("$pkg") && break
        done
    done < <(json_keys "$SET_JSON" packages)
fi

FLAG_HITS=()
if [ "$KEEP_LAB_FLAG" = "0" ] && [ -f "$LAB_FLAG" ]; then FLAG_HITS+=("lab-mode.flag"); fi

report_plan() {  # report_plan <label> <count> <joined>
    local label="$1" n="$2" joined="$3"
    if [ "$n" -eq 0 ]; then info "$label : （无）"; else ok "$label : $n 项 -> $joined"; fi
}
report_plan '技能 (skills)'        "${#SKILL_HITS[@]}"  "$(IFS=', '; echo "${SKILL_HITS[*]:-}")"
report_plan '提示词与扩展'          "${#PROMPT_HITS[@]}" "$(IFS=', '; echo "${PROMPT_HITS[*]:-}")"
report_plan 'MCP 条目'             "${#MCP_HITS[@]}"    "$(IFS=', '; echo "${MCP_HITS[*]:-}")"
report_plan 'settings packages'    "${#PKG_HITS[@]}"    "$(IFS=', '; echo "${PKG_HITS[*]:-}")"
report_plan '实验环境标志'          "${#FLAG_HITS[@]}"   "$(IFS=', '; echo "${FLAG_HITS[*]:-}")"

# ---------------------------------------------------------------- 2. 保护声明
step '2/5  用户自有数据保护声明'
for f in models.json auth.json sessions logs; do
    [ -e "$AGENT_DIR/$f" ] && ok "保留: $f"
done
USER_MCP=()
while IFS= read -r k; do
    k="${k%$'\r'}"
    [ -z "$k" ] && continue
    mcp_entry_is_ours "$k" || USER_MCP+=("$k")
done < <(json_keys "$MCP_JSON" mcpServers)
[ "${#USER_MCP[@]}" -gt 0 ] && ok "保留你自己的 MCP 条目: $(IFS=', '; echo "${USER_MCP[*]}")"
USER_SKILLS=()
if [ -d "$SKILLS_DIR" ]; then
    for d in "$SKILLS_DIR"/*/; do
        [ -d "$d" ] || continue
        n="$(basename "$d")"
        echo "$SKILL_NAMES" | grep -qx "$n" || USER_SKILLS+=("$n")
    done
fi
[ "${#USER_SKILLS[@]}" -gt 0 ] && ok "保留你自己安装的技能: $(IFS=', '; echo "${USER_SKILLS[*]}")"

TOTAL=$(( ${#SKILL_HITS[@]} + ${#PROMPT_HITS[@]} + ${#MCP_HITS[@]} + ${#PKG_HITS[@]} + ${#FLAG_HITS[@]} ))
if [ "$TOTAL" -eq 0 ]; then
    echo -e "\n${GREEN}[√] 没有发现需要移除的工作台内容，系统已是干净状态。${RESET}"
    exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
    echo -e "\n${YELLOW}[DRY-RUN] 以上 $TOTAL 项将被移除，未做任何修改。${RESET}"
    info '去掉 --dry-run 参数即可真正执行'
    exit 0
fi

# ---------------------------------------------------------------- 3. 确认
if [ "$ASSUME_YES" = "0" ]; then
    echo -e "\n${YELLOW}即将移除以上 $TOTAL 项。你的数据（模型凭据 / 自定义配置）不会被触碰。${RESET}"
    read -r -p '确认卸载？输入 yes 继续: ' ans
    case "$ans" in yes|y|Y|YES) ;; *) info '已取消'; exit 0 ;; esac
fi

# ---------------------------------------------------------------- 4. 执行
step '3/5  备份受影响文件'
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$AGENT_DIR/backup-uninstall-$STAMP"
mkdir -p "$BACKUP_ROOT"
info "备份目录: $BACKUP_ROOT"

backup_item() {  # backup_item <src> <rel-label>
    [ -e "$1" ] || return 0
    mkdir -p "$BACKUP_ROOT/$(dirname "$2")"
    cp -r "$1" "$BACKUP_ROOT/$2" 2>/dev/null && info "已备份: $2" || warn "备份失败: $2"
}
for n in "${SKILL_HITS[@]:-}";  do [ -n "$n" ] && backup_item "$SKILLS_DIR/$n" "skills/$n"; done
for f in "${PROMPT_HITS[@]:-}"; do [ -n "$f" ] && backup_item "$AGENT_DIR/$f" "$f"; done
if [ "${#MCP_HITS[@]}" -gt 0 ] || [ "${#PKG_HITS[@]}" -gt 0 ]; then
    backup_item "$MCP_JSON" 'mcp.json'
    backup_item "$SET_JSON" 'settings.json'
fi
[ "${#FLAG_HITS[@]}" -gt 0 ] && backup_item "$LAB_FLAG" 'lab-mode.flag'

step '4/5  执行移除'
for n in "${SKILL_HITS[@]:-}"; do
    [ -z "$n" ] && continue
    if rm -rf "$SKILLS_DIR/$n" 2>/dev/null; then ok "已移除技能: $n"; REMOVED=$((REMOVED+1))
    else fail "移除技能失败: $n"; FAILED=$((FAILED+1)); fi
done
for f in "${PROMPT_HITS[@]:-}"; do
    [ -z "$f" ] && continue
    if rm -f "$AGENT_DIR/$f" 2>/dev/null; then ok "已移除: $f"; REMOVED=$((REMOVED+1))
    else fail "移除失败: $f"; FAILED=$((FAILED+1)); fi
done

# MCP：外科手术式移除，保留用户其他条目
if [ "${#MCP_HITS[@]}" -gt 0 ]; then
    MCP_LIST="$(IFS=','; echo "${MCP_HITS[*]}")"
    if python - "$MCP_JSON" "$MCP_LIST" <<'PY'
import json, sys, io, os
p, names = sys.argv[1], [n for n in sys.argv[2].split(',') if n]
try:
    d = json.loads(io.open(p, encoding='utf-8-sig').read())
    servers = d.get('mcpServers', {})
    for n in names: servers.pop(n, None)
    d['mcpServers'] = servers
    io.open(p, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, indent=2, ensure_ascii=False) + '\n')
    print('kept=%d' % len(servers))
except Exception as e:
    print('error: %s' % e); sys.exit(1)
PY
    then ok "已移除 MCP 条目: $MCP_LIST"; REMOVED=$((REMOVED+${#MCP_HITS[@]}))
    else fail 'mcp.json 清理失败'; FAILED=$((FAILED+1)); fi
fi

# settings.json：只移除工作台加入的 packages
if [ "${#PKG_HITS[@]}" -gt 0 ]; then
    PKG_LIST="$(IFS=','; echo "${PKG_HITS[*]}")"
    if python - "$SET_JSON" "$PKG_LIST" <<'PY'
import json, sys, io
p, names = sys.argv[1], set(n for n in sys.argv[2].split(',') if n)
try:
    d = json.loads(io.open(p, encoding='utf-8-sig').read())
    d['packages'] = [x for x in d.get('packages', []) if x not in names]
    io.open(p, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, indent=2, ensure_ascii=False) + '\n')
    print('kept=%d' % len(d['packages']))
except Exception as e:
    print('error: %s' % e); sys.exit(1)
PY
    then ok "已从 settings.json 移除 ${#PKG_HITS[@]} 个 packages"; REMOVED=$((REMOVED+${#PKG_HITS[@]}))
    else fail 'settings.json 清理失败'; FAILED=$((FAILED+1)); fi
fi

if [ "${#FLAG_HITS[@]}" -gt 0 ]; then
    if rm -f "$LAB_FLAG" 2>/dev/null; then ok '已移除 lab-mode.flag（实验环境已退出）'; REMOVED=$((REMOVED+1))
    else fail '移除 lab-mode.flag 失败'; FAILED=$((FAILED+1)); fi
fi

# DSH：插件包 + 我们写的那条配置 + 状态文件（1.14.0 起的主路线）
DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
if [ -d "$DSH_HOME_DIR" ]; then
    DSH_PROFILE_PKG="$DSH_HOME_DIR/profiles/web/package.json"
    DSH_PATCH="$DSH_HOME_DIR/profiles/web/cordis.patch.yml"

    if [ -f "$DSH_PROFILE_PKG" ] && grep -q 'seep-lab' "$DSH_PROFILE_PKG"; then
        if command -v dsh >/dev/null 2>&1; then
            if dsh plugin --profile web remove seep-lab >/dev/null 2>&1; then
                ok '已从 DSH 卸下插件包 seep-lab'; REMOVED=$((REMOVED+1))
            else
                warn '插件包卸载返回非 0，可能已不存在；配置条目仍会被清理'
            fi
        else
            warn 'PATH 里没有 dsh，只能清理配置条目'
        fi
    fi

    # 我们写进 profile 的那条配置（只在能唯一定位时删）
    if [ -f "$DSH_PATCH" ] && grep -q '^- id:[[:space:]]*seep-workbench-boot[[:space:]]*$' "$DSH_PATCH"; then
        if cp "$DSH_PATCH" "$DSH_PATCH.bak" 2>/dev/null; then
            awk '
                /^- id:[[:space:]]*seep-workbench-boot[[:space:]]*$/ { skip=1; next }
                skip && /^- [^[:space:]]/ { skip=0 }
                !skip { print }
            ' "$DSH_PATCH.bak" > "$DSH_PATCH.tmp" && mv "$DSH_PATCH.tmp" "$DSH_PATCH"                 && { ok '已移除 DSH profile 里的 seep-workbench-boot 配置（备份 .bak）'; REMOVED=$((REMOVED+1)); }
        else
            warn 'DSH 配置清理失败（备份不成功，未改动原文件）'
        fi
    fi

    DSH_STATUS="$DSH_HOME_DIR/seep-workbench.status.json"
    if [ -f "$DSH_STATUS" ]; then
        rm -f "$DSH_STATUS" 2>/dev/null && { ok '已移除 DSH 插件状态文件'; REMOVED=$((REMOVED+1)); }
    fi
fi

# ---------------------------------------------------------------- 5. 深度清理
if [ "$PURGE" = "1" ]; then
    step '5/5  深度清理 (--purge)'
    PURGED=0
    while IFS= read -r b; do
        [ -z "$b" ] && continue
        [ "$b" = "$BACKUP_ROOT" ] && continue
        rm -rf "$b" 2>/dev/null && PURGED=$((PURGED+1)) || warn "无法删除: $(basename "$b")"
    done < <(find "$AGENT_DIR" -maxdepth 1 -type d -name 'backup-*' 2>/dev/null)
    for g in setup/cordis.generated.yml Tool/scripts/compliance-relay/relay-config.json; do
        if [ -f "$ROOT/$g" ]; then
            rm -f "$ROOT/$g" 2>/dev/null && { ok "已删除生成配置: $g"; PURGED=$((PURGED+1)); }
        fi
    done
    ok "深度清理完成，共 $PURGED 项（本次卸载备份已保留）"
else
    step '5/5  深度清理'
    info '未启用 --purge，历史备份与生成配置均已保留'
fi

# ---------------------------------------------------------------- 报告
echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}║   ✅ 卸载完成                                                 ║${RESET}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${RESET}"
ok "已移除: $REMOVED 项"
[ "$FAILED" -gt 0 ] && fail "失败: $FAILED 项（多为文件被占用，关闭 Agent 后重试）"
info "卸载备份: $BACKUP_ROOT"
info "如需恢复: ./setup/uninstall.sh --restore \"$BACKUP_ROOT\""
echo
info '工作台本体目录未删除。若确认不再需要，可手动删除整个工作台文件夹。'
info '请完全重启 Agent 会话，使卸载生效。'
exit 0
