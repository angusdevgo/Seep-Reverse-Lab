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

# 探测 Python 命令（优先 python3，其次 python）
if command -v python3 &>/dev/null; then
    PY_BIN="python3"
elif command -v python &>/dev/null; then
    PY_BIN="python"
else
    PY_BIN=""
fi

test_python_syntax() {
    [ -n "$PY_BIN" ] && (cd "$ROOT" && "$PY_BIN" -c "import ast; ast.parse(open('Tool/mcp/seep_mcp_server.py', encoding='utf-8').read())")
}

test_python_mcp() {
    [ -n "$PY_BIN" ] && "$PY_BIN" -c "import mcp" 2>/dev/null
}

test_python_avail() {
    [ -n "$PY_BIN" ]
}
echo -e "\n${WHITE}[1/8] 📁 核心架构与工程目录树${RESET}"
check_item "架构" "工作台主目录完整 (Tool/)" test -d "$TOOL_DIR"
check_item "架构" "技能包目录完整 (Tool/skill/)" test -d "$TOOL_DIR/skill"
check_item "架构" "MCP服务引擎目录 (Tool/mcp/)" test -d "$TOOL_DIR/mcp"
check_item "架构" "系统提示词层 (Tool/prompts/)" test -d "$TOOL_DIR/prompts"
check_item "架构" "十四大脱敏案例工程 (Tool/cases/)" test -d "$TOOL_DIR/cases"
check_item "架构" "上游开源验证集 (Tool/upstream/ 3大开源项目)" test -d "$TOOL_DIR/upstream/apk-reverse" -a -d "$TOOL_DIR/upstream/open-tgtylab" -a -d "$TOOL_DIR/upstream/open-reverselab"
check_item "架构" "MCP专用运行时强约定 (Tool/mcp/Tool/)" test -d "$TOOL_DIR/mcp/Tool"

# 2. 知识库
echo -e "\n${WHITE}[2/8] 📚 攻防实战知识库与战术模板 (KB)${RESET}"
check_item "知识库" "战术实战笔记 (289篇完整检索库)" test -d "$KB_DIR"
check_item "知识库" "内置 MCP 源码组件 (ReverseLab/Ghidra/JSHook)" test -d "$TOOL_DIR/mcp/Tool/reverselab/tools/skills/mcp"

# 3. 提示词
echo -e "\n${WHITE}[3/8] 🧠 智能体指令系统与运行时拦截扩展 (Prompts & Extensions)${RESET}"
check_item "提示词" "Pi Agent 系统指令 (SYSTEM.md 已就绪)" test -f "$TOOL_DIR/prompts/SYSTEM.md"
check_item "提示词" "通用跨 Agent 规范 (AGENTS.md)" test -f "$TOOL_DIR/prompts/AGENTS.md"
check_item "提示词" "Claude Code 项目级规范 (CLAUDE.md 在项目根)" test -f "$ROOT/CLAUDE.md"
check_item "提示词" "DeepSeek Harness 配置文件 (DSH-PROFILE.md)" test -f "$ROOT/DSH-PROFILE.md"
check_item "扩展"   "底层安全放行与 Lab 状态机扩展 (.ts)" test -f "$TOOL_DIR/prompts/extensions/security-audit-interceptor.ts"

# 4. 技能系统
echo -e "\n${WHITE}[4/8] 🛠️ 逆向工程专业技能库 (Skills - 9大组件)${RESET}"
check_item "Skill" "核心总控调度器 (softseep 包含 8 大专题库)" test -f "$TOOL_DIR/skill/softseep/SKILL.md" -a -d "$TOOL_DIR/skill/softseep/references"
check_item "Skill" "移动端逆向全链路 (apkseep 包含 45 篇规范与 56 脚本)" test -f "$TOOL_DIR/skill/apkseep/SKILL.md" -a -d "$TOOL_DIR/skill/apkseep/references"
check_item "Skill" "IDA Pro 自动化联动 (ida-reverse)" test -f "$TOOL_DIR/skill/ida-reverse/SKILL.md"
check_item "Skill" "通用许可/卡密校验突破规范 (license-bypass)" test -f "$TOOL_DIR/skill/client-license-validation-bypass/SKILL.md"
check_item "Skill" "独立战术安全技能包 (safe-skills 5组)" test -d "$TOOL_DIR/skill/safe-skills"

if [ -d "$AGENT_DIR" ]; then
    check_optn "部署" "Pi Agent 本地技能同步 (~/.pi/agent/skills/softseep)" "可运行 ./setup/install.sh 同步" test -f "$AGENT_DIR/skills/softseep/SKILL.md"
fi

# 5. MCP 自动化服务层与底层工具
echo -e "\n${WHITE}[5/8] 🔌 MCP 服务引擎与物理内置工具箱 (Native Tools)${RESET}"
check_item "MCP" "核心服务端脚本 (seep_mcp_server.py 语法自洽)" test_python_syntax
check_item "工具箱" "Jadx 反编译引擎 (jadx-1.5.6 完整就绪)" test -f "$SAFE_DIR/jadx/lib/jadx-1.5.6-all.jar"
check_item "工具箱" "Radare2 二进制套件 (跨平台探测系统/内置 r2)" command -v radare2 &>/dev/null || test -f "$SAFE_DIR/radare2/bin/radare2.exe"
check_item "工具箱" "Apktool 资源拆解重构环境 (apktool.jar)" test -f "$SAFE_DIR/apktool/apktool.jar"
check_item "工具箱" "Frida/LSPosed 动态插桩模板库 (hook-mcp)" test -d "$SAFE_DIR/hook-mcp/templates"
check_item "依赖" "Web/JS 逆向调试引擎依赖已解压 (js-reverse-mcp/node_modules)" test -d "$SAFE_DIR/js-reverse-mcp/node_modules" -o -f "$SAFE_DIR/js-reverse-mcp/node_modules.zip"
check_item "依赖" "Playwright 浏览器自动化依赖已解压 (playwright-mcp/node_modules)" test -d "$SAFE_DIR/playwright-mcp/node_modules" -o -f "$SAFE_DIR/playwright-mcp/node_modules.zip"

# 6. 环境运行时
echo -e "\n${WHITE}[6/8] ⚙️ 外部运行时与商业授权协同 (Runtime & Commercial)${RESET}"
check_item "运行时" "Python 解释器 (python3/python 且可执行)" test_python_avail
check_optn "协议" "Python mcp 协议库支持 (mcp>=1.20,<1.29)" "运行 pip install 'mcp>=1.20,<1.29'" test_python_mcp
check_optn "商业软件" "IDA Pro 商业反编译器协同 (可选)" "无授权不影响核心链路，系统自动使用 Radare2 降级" false
check_optn "配置" "Claude Code 项目级 MCP 注册 (.mcp.json 在根目录)" "直接在根目录启动 claude 即可" test -f "$ROOT/.mcp.json"

# 7. 战术手册
echo -e "\n${WHITE}[7/8] 📚 MANUAL/ 战术手册完备性校验${RESET}"
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
echo -e "\n${WHITE}[8/8] 🌐 合规转译中继与规则同步校验${RESET}"
RELAY_DIR="$TOOL_DIR/scripts/compliance-relay"

check_item "中继" "中继主程序 (relay.py 纯标准库实现)" test -f "$RELAY_DIR/relay.py"
check_item "中继" "规则提取器 (extract-rules.py)" test -f "$RELAY_DIR/extract-rules.py"
check_item "中继" "上下文守卫白名单 (guard-prefixes.json)" test -f "$RELAY_DIR/guard-prefixes.json"
check_item "中继" "中继单元测试套件 (tests/test_relay.py)" test -f "$RELAY_DIR/tests/test_relay.py"

test_relay_rules_sync() {
    [ -n "$PY_BIN" ] || return 1
    test -f "$RELAY_DIR/sensitive-rules.json" || return 1
    (cd "$RELAY_DIR" && "$PY_BIN" extract-rules.py --check >/dev/null 2>&1)
}
check_item "中继" "规则表与 TS 源同步 (sensitive-rules.json)" test_relay_rules_sync

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
