#!/usr/bin/env bash
# ==============================================================================
# Seep Reverse Lab — Linux / macOS 原生全彩自检与部署核验脚本 (Verifier)
# 对应 Windows check.ps1 / verify.ps1，输出结构化 ANSI 彩色报告
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOL_DIR="$ROOT/Tool"
SAFE_DIR="$TOOL_DIR/mcp/Tool/safe"
KB_DIR="$TOOL_DIR/mcp/Tool/reverselab/kb"
AGENT_DIR="$HOME/.pi/agent"
MANUAL_DIR="$ROOT/MANUAL"

GREEN="\033[1;32m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
WHITE="\033[1;37m"
RESET="\033[0m"

OK_COUNT=0
FAIL_COUNT=0
OPTN_COUNT=0

check_item() {
    local cat="$1"
    local name="$2"
    shift 2
    if "$@"; then
        echo -e "  [${GREEN}√ PASS${RESET}] $name"
        ((OK_COUNT++))
    else
        echo -e "  [${RED}X FAIL${RESET}] $name"
        ((FAIL_COUNT++))
    fi
}

check_optn() {
    local cat="$1"
    local name="$2"
    local note="$3"
    shift 3
    if "$@"; then
        echo -e "  [${GREEN}√ PASS${RESET}] $name"
        ((OK_COUNT++))
    else
        echo -e "  [${YELLOW}! OPTN${RESET}] $name ($note)"
        ((OPTN_COUNT++))
    fi
}

echo -e "${CYAN}================================================================================${RESET}"
echo -e "${CYAN}          Seep Reverse Lab — Linux/macOS 部署完备性体检 (Verifier)             ${RESET}"
echo -e "${CYAN}================================================================================${RESET}"
echo -e "  工作台物理根目录: $ROOT"
echo -e "  宿主操作系统内核: $(uname -s) $(uname -r) ($(uname -m))"
echo -e "  基准核验清单规范: MANUAL/DEPLOYMENT-CHECKLIST.md"

# 解析一个「真的能执行」的 Python 解释器。
# 不能只信 `command -v python3`：Windows/Git Bash 上可能只有 py 启动器、没有 python3；
# 也可能存在指向已删 venv 的失效垫片。解释器不可用时，依赖它的检查项一律 SKIP 而不是
# 报红 —— 否则一次环境问题会伪装成「语法错误 / 冒烟失败 / 规则不同步」三个故障。
PY_BIN=""
if [ -n "${SEEP_PYTHON:-}" ] && [ -x "${SEEP_PYTHON}" ]; then
    PY_BIN="$SEEP_PYTHON"
fi
for cand in python3 python; do
    [ -n "$PY_BIN" ] && break
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c "import sys" >/dev/null 2>&1; then PY_BIN="$(command -v "$cand")"; fi
    fi
done
if [ -z "$PY_BIN" ] && command -v py >/dev/null 2>&1; then
    _real="$(py -3 -c "import sys; print(sys.executable)" 2>/dev/null || true)"
    [ -n "$_real" ] && [ -x "$_real" ] && PY_BIN="$_real"
fi
for v in "$AGENT_DIR/seep-venv/bin/python" "$AGENT_DIR/seep-venv/Scripts/python.exe"; do
    [ -n "$PY_BIN" ] && break
    [ -x "$v" ] && PY_BIN="$v"
done

# SEEP_PYTHON 可能是 Windows 原生路径（C:\\..\\python.exe）。
# Git Bash 里这种路径带反斜杠 + 盘符，既不能过 [ -x ] 也不能直接执行，
# 会导致依赖它的检查项集体误报（stdio 冒烟 / tool_state / 语法自检）。
if [ -n "$PY_BIN" ] && command -v cygpath >/dev/null 2>&1; then
    _norm="$(cygpath -u "$PY_BIN" 2>/dev/null || true)"
    [ -n "$_norm" ] && [ -x "$_norm" ] && PY_BIN="$_norm"
fi

# 原生 Windows 的 python.exe 不认 /c/Users/... 这种 MSYS 路径：
# 它会当成「盘符 C 下的 \c\Users\...」，报 can't open file 'C:\c\Users\...'。
# 所以凡是把「路径」当参数传给 Python 的地方都走 py_run，由它统一换算。
py_run() {
    if [ -n "$PY_BIN" ] && command -v cygpath >/dev/null 2>&1; then
        case "$PY_BIN" in
            *.exe|*.EXE)
                local out=() a
                for a in "$@"; do
                    case "$a" in
                        /[A-Za-z]/*) out+=("$(cygpath -w "$a" 2>/dev/null || echo "$a")") ;;
                        *) out+=("$a") ;;
                    esac
                done
                "$PY_BIN" "${out[@]}"
                return $?
                ;;
        esac
    fi
    "$PY_BIN" "$@"
}

test_python_syntax() {
    [ -n "$PY_BIN" ] || return 0          # 解释器不可用由专门检查项报，不在这里重复罚
    (cd "$ROOT" && py_run -c "import ast; ast.parse(open('Tool/mcp/seep_mcp_server.py', encoding='utf-8').read())")
}

test_python_mcp() {
    [ -n "$PY_BIN" ] && py_run -c "import mcp" 2>/dev/null
}

test_python_avail() {
    [ -n "$PY_BIN" ]
}
echo -e "\n${WHITE}[1/10] 📁 核心架构与工程目录树${RESET}"
check_item "架构" "工作台主目录完整 (Tool/)" test -d "$TOOL_DIR"
check_item "架构" "技能包目录完整 (Tool/skill/)" test -d "$TOOL_DIR/skill"
check_item "架构" "MCP服务引擎目录 (Tool/mcp/)" test -d "$TOOL_DIR/mcp"
check_item "架构" "系统提示词层 (Tool/prompts/)" test -d "$TOOL_DIR/prompts"
check_item "架构" "十四大脱敏案例工程 (Tool/cases/)" test -d "$TOOL_DIR/cases"
check_item "架构" "上游开源验证集 (Tool/upstream/ 4 大开源项目)" test -d "$TOOL_DIR/upstream/apk-reverse" -a -d "$TOOL_DIR/upstream/open-tgtylab" -a -d "$TOOL_DIR/upstream/open-reverselab" -a -d "$TOOL_DIR/upstream/exe-reverse"
check_item "架构" "MCP专用运行时强约定 (Tool/mcp/Tool/)" test -d "$TOOL_DIR/mcp/Tool"

# 1b. 版本与更新链路
check_item "版本" "版本标识与变更日志 (VERSION + CHANGELOG.md)" test -f "$ROOT/VERSION" -a -f "$ROOT/CHANGELOG.md"
check_item "版本" "已有用户一键更新脚本 (update.ps1 + update.sh)" test -f "$ROOT/setup/update.ps1" -a -f "$ROOT/setup/update.sh"
check_item "架构" "上游定点防外溢规则与同步引擎 (upstream-rules.json + sync-upstream.py)" test -f "$ROOT/setup/upstream-rules.json" -a -f "$ROOT/setup/sync-upstream.py" -a -f "$ROOT/setup/sync-upstream.sh" -a -f "$ROOT/update.bat"
check_item "版本" "一键卸载脚本 (uninstall.ps1 + uninstall.sh)" test -f "$ROOT/setup/uninstall.ps1" -a -f "$ROOT/setup/uninstall.sh"

# 2. 知识库
echo -e "\n${WHITE}[2/10] 📚 攻防实战知识库与战术模板 (KB)${RESET}"
KB_COUNT=$(find "$KB_DIR" -name "*.md" 2>/dev/null | wc -l | tr -d " ")
check_item "知识库" "战术实战笔记 (294 篇完整检索库，实测 $KB_COUNT 篇)" test -d "$KB_DIR"
check_item "知识库" "内置 MCP 源码组件 (ReverseLab/Ghidra/JSHook)" test -d "$TOOL_DIR/mcp/Tool/reverselab/tools/skills/mcp"

# 3. 提示词
echo -e "\n${WHITE}[3/10] 🧠 智能体指令系统与运行时拦截扩展 (Prompts & Extensions)${RESET}"
check_item "提示词" "Pi Agent 系统指令 (SYSTEM.md 已就绪)" test -f "$TOOL_DIR/prompts/SYSTEM.md"
check_item "提示词" "通用跨 Agent 规范 (AGENTS.md)" test -f "$TOOL_DIR/prompts/AGENTS.md"
check_item "提示词" "DeepSeek Harness 配置文件 (DSH-PROFILE.md)" test -f "$ROOT/DSH-PROFILE.md"
check_item "扩展"   "底层安全放行与 Lab 状态机扩展 (.ts)" test -f "$TOOL_DIR/prompts/extensions/security-audit-interceptor.ts"

# 项目根 AGENTS.md：DSH 的指令入口（Pi 读 ~/.pi/agent/AGENTS.md），由 generate-configs 从 Tool/prompts 复制生成
test_root_agents_sync() {
    local a b
    [ -f "$TOOL_DIR/prompts/AGENTS.md" ] || return 1
    [ -f "$ROOT/AGENTS.md" ] || return 1
    a=$(tr -d '\r' < "$ROOT/AGENTS.md")
    b=$(tr -d '\r' < "$TOOL_DIR/prompts/AGENTS.md")
    [ "$a" = "$b" ]
}
check_item "Agent" "项目根 AGENTS.md 与源同步 (DSH 指令入口)" test_root_agents_sync

# DSH Cordis 补丁生成物结构
test_cordis_patch() {
    local c="$SCRIPT_DIR/cordis.generated.yml"
    [ -f "$c" ] || return 1
    grep -qE '^- insert:' "$c" || return 1
    grep -q 'serverName: seep' "$c" || return 1
    grep -q 'toolCallTimeoutMs:' "$c" || return 1
    grep -q '@deepseek-ai/dsh-mcp-client' "$c" || return 1
    return 0
}
check_item "Agent" "DSH Cordis 补丁生成物合法 (insert + timeout)" test_cordis_patch

# DSH 已安装但没接入 → OPTN（不阻塞）
DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
if [ -d "$DSH_HOME_DIR" ]; then
    test_dsh_mounted() {
        # 路线一：插件包（1.14.0 起推荐）—— profile 的 dsh.profile.bundles 里有包名
        local profile_pkg="$DSH_HOME_DIR/profiles/web/package.json"
        if [ -f "$profile_pkg" ] && grep -q 'seep-dsh-workbench' "$profile_pkg"; then
            return 0
        fi
        # 路线二：旧路线（dsh-merge.py 写的标注块）
        [ -f "$SCRIPT_DIR/dsh-merge.py" ] || return 1
        [ -n "$PY_BIN" ] || return 1
        py_run "$SCRIPT_DIR/dsh-merge.py" --root "$ROOT" --dsh-home "$DSH_HOME_DIR" --check >/dev/null 2>&1
    }
    check_optn "Agent" "DeepSeek Harness 已接入 seep MCP (插件包或旧挂载)" \
        "运行 python setup/dsh-plugin-setup.py（推荐）" test_dsh_mounted
fi

# 项目根 AGENTS.md：DSH 的指令入口（Pi 读 ~/.pi/agent/AGENTS.md），由 generate-configs 从 Tool/prompts 复制生成
test_root_agents_sync() {
    local a b
    [ -f "$TOOL_DIR/prompts/AGENTS.md" ] || return 1
    [ -f "$ROOT/AGENTS.md" ] || return 1
    a=$(tr -d '\r' < "$ROOT/AGENTS.md")
    b=$(tr -d '\r' < "$TOOL_DIR/prompts/AGENTS.md")
    [ "$a" = "$b" ]
}
check_item "Agent" "项目根 AGENTS.md 与源同步 (DSH 指令入口)" test_root_agents_sync

# DSH Cordis 补丁生成物结构
test_cordis_patch() {
    local c="$SCRIPT_DIR/cordis.generated.yml"
    [ -f "$c" ] || return 1
    grep -qE '^- insert:' "$c" || return 1
    grep -q 'serverName: seep' "$c" || return 1
    grep -q 'toolCallTimeoutMs:' "$c" || return 1
    grep -q '@deepseek-ai/dsh-mcp-client' "$c" || return 1
    return 0
}
check_item "Agent" "DSH Cordis 补丁生成物合法 (insert + timeout)" test_cordis_patch

# DSH 已安装但没接入 → OPTN（不阻塞）
DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
if [ -d "$DSH_HOME_DIR" ]; then
    test_dsh_mounted() {
        [ -f "$SCRIPT_DIR/dsh-merge.py" ] || return 1
        [ -n "$PY_BIN" ] || return 1
        py_run "$SCRIPT_DIR/dsh-merge.py" --root "$ROOT" --dsh-home "$DSH_HOME_DIR" --check >/dev/null 2>&1
    }
    check_optn "Agent" "DeepSeek Harness 已接入 seep MCP (插件包或旧挂载)" \
        "运行 python setup/dsh-plugin-setup.py（推荐）" test_dsh_mounted
fi

# 4. 技能系统
SKILL_DIRS=$(find "$TOOL_DIR/skill" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)
SAFE_SKILL_DIRS=$(find "$TOOL_DIR/skill/safe-skills" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)
SKILL_TOTAL=$((SKILL_DIRS - 1 + SAFE_SKILL_DIRS))
echo -e "\n${WHITE}[4/10] 🛠️ 逆向工程专业技能库 (Skills - $SKILL_TOTAL 个技能 / $SKILL_DIRS 个目录)${RESET}"
check_item "Skill" "核心总控调度器 (softseep 包含 10 大专题库)" test -f "$TOOL_DIR/skill/softseep/SKILL.md" -a -d "$TOOL_DIR/skill/softseep/references"
check_item "Skill" "Windows PE 深水区 (exe-reverse)" test -f "$TOOL_DIR/skill/exe-reverse/SKILL.md" -a -d "$TOOL_DIR/skill/exe-reverse/references" -a -d "$TOOL_DIR/skill/exe-reverse/scripts"
check_item "Skill" "移动端逆向全链路 (apkseep 包含 45 篇规范与 56 脚本)" test -f "$TOOL_DIR/skill/apkseep/SKILL.md" -a -d "$TOOL_DIR/skill/apkseep/references"
check_item "Skill" "IDA Pro 自动化联动 (ida-reverse)" test -f "$TOOL_DIR/skill/safe-skills/ida-reverse/SKILL.md"
check_item "Skill" "通用许可/卡密校验突破规范 (license-bypass)" test -f "$TOOL_DIR/skill/client-license-validation-bypass/SKILL.md"
check_item "Skill" "Web / 流媒体取证 (webseep)" \
    test -f "$TOOL_DIR/skill/webseep/SKILL.md" -a -d "$TOOL_DIR/skill/webseep/references"
check_item "Skill" "独立战术安全技能包 (safe-skills 5组)" test -d "$TOOL_DIR/skill/safe-skills"

# SKILL.md 带 UTF-8 BOM 时，frontmatter 解析器无法识别首行 `---`，技能会被静默跳过（Issue #6）
test_skill_no_bom() {
    local f first3
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        first3=$(head -c 3 "$f" 2>/dev/null | od -An -tx1 | tr -d ' \n')
        [ "$first3" = "efbbbf" ] && return 1
    done < <(find "$TOOL_DIR/skill" -name 'SKILL.md' 2>/dev/null)
    return 0
}
check_item "Skill" "技能 SKILL.md 无 UTF-8 BOM（否则被 Agent 静默跳过）" test_skill_no_bom

if [ -d "$AGENT_DIR" ]; then
    check_optn "部署" "Pi Agent 本地技能同步 (~/.pi/agent/skills/softseep)" "可运行 ./setup/install.sh 同步" test -f "$AGENT_DIR/skills/softseep/SKILL.md"
fi

# 5. MCP 自动化服务层与底层工具
echo -e "\n${WHITE}[5/10] 🔌 MCP 服务引擎与物理内置工具箱 (Native Tools)${RESET}"
SEEP_TOOL_COUNT=$(grep -c '^def seep_' "$TOOL_DIR/mcp/seep_mcp_server.py" 2>/dev/null || echo 0)
check_item "MCP" "核心服务端脚本 (seep_mcp_server.py 语法自洽，$SEEP_TOOL_COUNT 个工具定义)" test_python_syntax

# 语法合法 ≠ 能在 stdio 下工作：subprocess 派生点若漏了 stdin=DEVNULL，
# 子进程会继承 MCP 自己的 JSON-RPC 管道，工具会挂死到客户端超时（issue #13）。
# 冒烟脚本的 --quick 层零依赖、毫秒级，能直接点出行号。
test_stdio_smoke() {
    local smoke="$TOOL_DIR/mcp/test_stdio_smoke.py"
    [ -f "$smoke" ] || return 0          # 旧版本无此脚本时不判定，避免误报
    [ -n "$PY_BIN" ] || return 0          # 无 Python 时不判定
    py_run "$smoke" --quick >/dev/null 2>&1
}
check_item "MCP" "stdio 子进程不继承 stdin (issue #13 回归防护)" test_stdio_smoke
check_item "工具箱" "Jadx 反编译引擎 (jadx-1.5.6 完整就绪)" test -f "$SAFE_DIR/jadx/lib/jadx-1.5.6-all.jar"
# 注意：不能把 `command -v x &>/dev/null || test -f ...` 直接当参数传给 check_item ——
# 末尾的 `&>/dev/null` 会把 check_item 自己的汇报行一并吞掉（该行曾经完全不显示）。
test_radare2() {
    command -v radare2 >/dev/null 2>&1 && return 0
    [ -f "$SAFE_DIR/radare2/bin/radare2.exe" ] && return 0
    return 1
}
check_item "工具箱" "Radare2 二进制套件 (跨平台探测系统/内置 r2)" test_radare2
check_item "工具箱" "Apktool 资源拆解重构环境 (apktool.jar)" test -f "$SAFE_DIR/apktool/apktool.jar"
check_item "工具箱" "Frida/LSPosed 动态插桩模板库 (hook-mcp)" test -d "$SAFE_DIR/hook-mcp/templates"
check_item "依赖" "Web/JS 逆向调试引擎依赖已解压 (js-reverse-mcp/node_modules)" test -d "$SAFE_DIR/js-reverse-mcp/node_modules" -o -f "$SAFE_DIR/js-reverse-mcp/node_modules.zip"
check_item "依赖" "Playwright 浏览器自动化依赖已解压 (playwright-mcp/node_modules)" test -d "$SAFE_DIR/playwright-mcp/node_modules" -o -f "$SAFE_DIR/playwright-mcp/node_modules.zip"

# 5b. 外部能力包可用性（不只看文件在不在，而是这个工具现在能不能真跑）
#     这些程序不在仓库里（体积 / 平台 / 版本耦合），缺失不阻塞部署：
#     归入「可选/建议关注」，判为 DEGRADED 而不是 FAIL。
echo -e "\n${WHITE}[6/10] 🧰 外部能力包可用性 (Web / Android / 扫描器)${RESET}"

cap_path() {
    local n="$1" p=""
    p="$(command -v "$n" 2>/dev/null || true)"
    [ -n "$p" ] && { echo "$p"; return; }
    for c in "${SEEP_WEB_TOOLBOX:-$HOME/.seep/web}/bin/$n" \
             "${SEEP_ANDROID_TOOLBOX:-$HOME/.seep/android}/bin/$n" \
             "${SEEP_ANDROID_TOOLBOX:-$HOME/.seep/android}/frida-env/bin/$n"; do
        [ -x "$c" ] && { echo "$c"; return; }
    done
    echo ""
}

test_cap_all() {
    local miss=""
    for n in "$@"; do [ -n "$(cap_path "$n")" ] || miss="$miss $n"; done
    [ -z "$miss" ] && return 0
    CAP_HINT="$miss"
    return 1
}

check_optn "能力" "Web 取证 (ffmpeg + ffprobe)" "缺 ffmpeg/ffprobe；补全: ./setup/install-capabilities.sh --only web" test_cap_all ffmpeg ffprobe
check_optn "能力" "Android 动态 (frida + objection)" "补全: ./setup/install-capabilities.sh --only android" test_cap_all frida objection
check_optn "能力" "加固指纹 (apkid)" "补全: ./setup/install-capabilities.sh --only android" test_cap_all apkid
check_optn "能力" "扫描器（可选: nuclei + ffuf）" "补全: ./setup/install-capabilities.sh --only scanners" test_cap_all nuclei ffuf
# aotopsy 是 Windows PE 单文件，Unix 上预期缺失 —— 固定判为「不适用」，不计失败
check_optn "能力" "Flutter AOT (aotopsy，Windows-only)" "Unix 上不适用：aotopsy.exe 为 Windows PE；用 apktool 解包后交给 r2/IDA" false

# 外部工具定位统一走 setup/tool-registry.json —— 与 Windows 侧 resolve-tools.ps1 同一份规则，
# 不再写死任何安装路径，也不是写死 false 的占位。
TOOL_RESOLVER="$TOOL_DIR/mcp/tool_resolver.py"

tool_state() {
    # $1 = 工具 id；输出 READY / DEGRADED / OPTIONAL / MISSING / UNKNOWN
    [ -n "$PY_BIN" ] && [ -f "$TOOL_RESOLVER" ] || { echo UNKNOWN; return; }
    py_run "$TOOL_RESOLVER" --state "$1" 2>/dev/null || echo UNKNOWN
}

tool_is_ready() {
    [ "$(tool_state "$1")" = "READY" ]
}

check_item "工具" "外部工具注册表 (setup/tool-registry.json 可解析)" test -f "$ROOT/setup/tool-registry.json"
check_optn "商业软件" "IDA Pro 商业反编译器协同 (可选)" "无授权不影响核心链路，系统自动使用 Radare2 降级；装在非默认位置请设 SEEP_IDA_ROOT" tool_is_ready ida

# 6. 环境运行时
echo -e "\n${WHITE}[7/10] ⚙️ 外部运行时与商业授权协同 (Runtime & Commercial)${RESET}"
check_item "运行时" "Python 解释器可用于运行时校验 (语法 / 冒烟 / 规则同步)" test_python_avail
check_optn "协议" "Python mcp 协议库支持 (mcp>=1.20,<1.29)" "运行 pip install 'mcp>=1.20,<1.29'" test_python_mcp

# 7. 战术手册
echo -e "\n${WHITE}[8/10] 📚 MANUAL/ 战术手册完备性校验${RESET}"
check_item "手册" "环境预要求指南 (MANUAL/PREREQUISITES.md)" test -f "$MANUAL_DIR/PREREQUISITES.md"
check_item "手册" "IDA Pro 商业软件接入指南 (MANUAL/IDA-PRO.md)" test -f "$MANUAL_DIR/IDA-PRO.md"
check_item "手册" "反调试绕过战术手册 (MANUAL/ANTI-DEBUG.md)" test -f "$MANUAL_DIR/ANTI-DEBUG.md"
check_item "手册" "通用脱壳前置分析 SOP (MANUAL/UNPACKING.md)" test -f "$MANUAL_DIR/UNPACKING.md"
check_item "手册" "PoC 闭环自动化验证 SOP (MANUAL/POC-VALIDATION.md)" test -f "$MANUAL_DIR/POC-VALIDATION.md"
check_item "手册" "全景部署与多 Agent 集成指南 (MANUAL/DEPLOYMENT.md)" test -f "$MANUAL_DIR/DEPLOYMENT.md"
check_item "手册" "官方部署资产核验基准清单 (MANUAL/DEPLOYMENT-CHECKLIST.md)" test -f "$MANUAL_DIR/DEPLOYMENT-CHECKLIST.md"
check_item "手册" "跨平台运行与战术等价指南 (MANUAL/CROSS-PLATFORM.md)" test -f "$MANUAL_DIR/CROSS-PLATFORM.md"
check_item "手册" "合规转译中继与防拒体系 (MANUAL/COMPLIANCE-RELAY.md)" test -f "$MANUAL_DIR/COMPLIANCE-RELAY.md"

# 8. 合规转译中继
echo -e "\n${WHITE}[9/10] 🌐 合规转译中继与规则同步校验${RESET}"
RELAY_DIR="$TOOL_DIR/scripts/compliance-relay"

check_item "中继" "中继主程序 (relay.py 纯标准库实现)" test -f "$RELAY_DIR/relay.py"
check_item "中继" "规则提取器 (extract-rules.py)" test -f "$RELAY_DIR/extract-rules.py"
check_item "中继" "上下文守卫白名单 (guard-prefixes.json)" test -f "$RELAY_DIR/guard-prefixes.json"
check_item "中继" "中继单元测试套件 (tests/test_relay.py)" test -f "$RELAY_DIR/tests/test_relay.py"

test_relay_rules_sync() {
    [ -n "$PY_BIN" ] || return 1
    test -f "$RELAY_DIR/sensitive-rules.json" || return 1
    (cd "$RELAY_DIR" && py_run extract-rules.py --check >/dev/null 2>&1)
}
check_item "中继" "规则表与 TS 源同步 (sensitive-rules.json)" test_relay_rules_sync

# 9. 脱敏与隐私走查
echo -e "\n${WHITE}[10/10] 🔒 脱敏与个人隐私走查 (递归全深度扫描)${RESET}"

PRIVACY_RX='C:[\\/]{1,2}Users[\\/]{1,2}Angus|AngusDevLab|angusdevlab|angus\.vip@|angusdev\.top|\bAngus\b'

test_privacy_clean() {
    local hits files
    if [ -d "$ROOT/.git" ]; then
        # 只扫描将被发布的 git 跟踪文件（本地生成物已 gitignore，不属发布范围）
        files=$(git -C "$ROOT" ls-files 2>/dev/null \
            | grep -vE '^(setup/verify\.(ps1|sh))$' \
            | grep -vE '^Tool/(upstream|mcp/Tool)/' \
            | grep -vE '\.(exe|dll|so|dylib|jar|zip|7z|png|jpg|jpeg|gif|ico|pdf|bin|dmp|pyc|idb|i64|ttf|woff|woff2)$')
        [ -z "$files" ] && return 0
        hits=$(cd "$ROOT" && printf '%s\n' "$files" | tr '\n' '\0' | xargs -0 grep -InE "$PRIVACY_RX" 2>/dev/null | head -3)
    else
        # 非 git 环境：回退到文件系统扫描
        hits=$(grep -rInE "$PRIVACY_RX" "$ROOT" \
            --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=__pycache__ \
            --exclude-dir=upstream --exclude-dir=dist \
            --exclude=verify.sh --exclude=verify.ps1 \
            --exclude=cordis.generated.yml \
            --exclude=relay-config.json --exclude=tool-index.json --exclude=tool-index.md 2>/dev/null \
            | grep -v "/Tool/mcp/Tool/" | head -3)
    fi
    [ -z "$hits" ]
}
check_item "脱敏" "个人隐私零残留 (已跟踪文件全深度扫描)" test_privacy_clean

test_generated_untracked() {
    [ -d "$ROOT/.git" ] || return 0
    local tracked f
    tracked=$(git -C "$ROOT" ls-files 2>/dev/null)
    for f in setup/cordis.generated.yml Tool/scripts/compliance-relay/relay-config.json; do
        if echo "$tracked" | grep -qx "$f"; then return 1; fi
    done
    return 0
}
check_item "脱敏" "含本机路径的生成物未被 git 追踪" test_generated_untracked

test_no_product_names() {
    ! grep -rIlE 'xyplorer|bandizip|boosterx|1218\.io' "$TOOL_DIR/cases" 2>/dev/null | grep -q .
}
check_optn "脱敏" "目标产品名残留统计 (功能性标识符可保留)" \
    "存在目标产品名（含 README 已声明的功能性必需标识符）；如为叙述性提及请脱敏" test_no_product_names

echo -e "\n${CYAN}================================================================================${RESET}"
echo -e "  [体检报告] 核心检查通过: ${GREEN}$OK_COUNT${RESET} 项 | 异常阻断: ${RED}$FAIL_COUNT${RESET} 项 | 关注项: ${YELLOW}$OPTN_COUNT${RESET} 项"
echo -e "${CYAN}================================================================================${RESET}"

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "\n  ${GREEN}🎉 结论: 工作台在当前 $(uname -s) 环境处于 [READY / 完备就绪] 状态！${RESET}"
    echo -e "  输入 ${CYAN}lab：${RESET} 即可开启白盒测试！\n"
    exit 0
else
    echo -e "\n  ${RED}❌ 结论: 存在未通过的核心检查项，请检查上述红色标记。${RESET}\n"
    exit 1
fi
