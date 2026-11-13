#!/usr/bin/env bash
# ==============================================================================
# Seep Lab — 外部能力包安装器（Linux / macOS）
# ==============================================================================
# 为什么需要它
#   工作台 seep MCP 有 38 个工具，其中一部分真正的算力来自外部程序。
#   这些不在 git 仓库里，也不该塞进去（体积大、平台相关、版本要和设备对齐）。
#   以前的 Unix 部署链路完全没碰这一层，结果是：工具在 tools/list 里看得见，
#   一调用就返回「未部署」。
#
# 组件
#   web       ffmpeg + ffprobe。HLS 取证核心。走包管理器安装。
#   android   frida / frida-tools / objection / frida-dexdump / APKiD。独立 venv。
#   scanners  nuclei / ffuf。可选。
#   aotopsy   仅 Windows（aotopsy.exe 是 Windows PE 单文件），Unix 显式跳过。
#
# 纪律
#   · 默认只装 web + android（Unix 上真正零成本的只有这两项里的检测）
#   · 任何组件失败只警告，绝不中断部署
#   · 需要下载的组件必须显式点名
#
# 用法
#   ./setup/install-capabilities.sh                       # 默认 web + android
#   ./setup/install-capabilities.sh --only all
#   ./setup/install-capabilities.sh --only scanners
#   ./setup/install-capabilities.sh --check-only          # 只报表
#   ./setup/install-capabilities.sh --root ~/.seep        # 统一改工具箱根
#   ./setup/install-capabilities.sh --strict              # 有缺失则非零退出
# ==============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN="\033[1;32m"; RED="\033[1;31m"; YELLOW="\033[1;33m"
CYAN="\033[1;36m"; WHITE="\033[1;37m"; GRAY="\033[0;37m"; RESET="\033[0m"

ONLY_RAW="auto"
CHECK_ONLY=0
STRICT=0
SKIP_PATH=0
TOOLBOX_ROOT=""

while [ $# -gt 0 ]; do
    case "$1" in
        --only)            ONLY_RAW="${2:-auto}"; shift 2 ;;
        --only=*)          ONLY_RAW="${1#*=}"; shift ;;
        --check-only)      CHECK_ONLY=1; shift ;;
        --strict)          STRICT=1; shift ;;
        --skip-path)       SKIP_PATH=1; shift ;;
        --root)            TOOLBOX_ROOT="${2:-}"; shift 2 ;;
        --root=*)          TOOLBOX_ROOT="${1#*=}"; shift ;;
        -h|--help)         sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数: $1" >&2; exit 2 ;;
    esac
done

step() { echo -e "\n${CYAN}[$1]${RESET}"; }
ok()   { echo -e "  ${GREEN}[OK]${RESET}   $1"; }
warn() { echo -e "  ${YELLOW}[!!]${RESET}   $1"; }
info() { echo -e "  ${GRAY}[..]${RESET}   $1"; }

# ---------------------------------------------------------------- 根目录
ANDROID_ROOT="${SEEP_ANDROID_TOOLBOX:-$HOME/.seep/android}"
WEB_ROOT="${SEEP_WEB_TOOLBOX:-$HOME/.seep/web}"
if [ -n "$TOOLBOX_ROOT" ]; then
    ANDROID_ROOT="$TOOLBOX_ROOT/android"
    WEB_ROOT="$TOOLBOX_ROOT/web"
fi
export SEEP_ANDROID_TOOLBOX="$ANDROID_ROOT"
export SEEP_WEB_TOOLBOX="$WEB_ROOT"

# ---------------------------------------------------------------- 参数归一
REQUESTED=()
IFS=', ' read -r -a _tokens <<< "$ONLY_RAW"
for t in "${_tokens[@]}"; do
    case "$t" in
        auto)     REQUESTED+=("web" "android") ;;
        all)      REQUESTED+=("web" "android" "scanners" "aotopsy") ;;
        none)     ;;
        web|android|scanners|aotopsy) REQUESTED+=("$t") ;;
        "")       ;;
        *)        warn "未知组件 '$t'，已忽略（可选：web / android / scanners / aotopsy / all / none）" ;;
    esac
done

# ---------------------------------------------------------------- 能力探测
have() { command -v "$1" >/dev/null 2>&1; }

resolve_web() {
    local n="$1"
    if [ -x "$WEB_ROOT/bin/$n" ]; then echo "$WEB_ROOT/bin/$n"; return; fi
    if have "$n"; then command -v "$n"; return; fi
    echo ""
}

resolve_android() {
    local n="$1"
    for c in "$ANDROID_ROOT/bin/$n" "$ANDROID_ROOT/frida-env/bin/$n" \
             "$ANDROID_ROOT/platform-tools/$n"; do
        if [ -x "$c" ]; then echo "$c"; return; fi
    done
    if have "$n"; then command -v "$n"; return; fi
    echo ""
}

board() {
    step "能力看板"
    echo -e "  ${WHITE}-- Web --${RESET}"
    for n in ffmpeg ffprobe; do
        p="$(resolve_web "$n")"
        if [ -n "$p" ]; then ok "$(printf '%-10s %s' "$n" "$p")"
        else warn "$(printf '%-10s MISSING' "$n")"; fi
    done
    echo -e "  ${WHITE}-- Android --${RESET}"
    for n in frida objection apkid adb; do
        p="$(resolve_android "$n")"
        if [ -n "$p" ]; then ok "$(printf '%-10s %s' "$n" "$p")"
        else warn "$(printf '%-10s MISSING' "$n")"; fi
    done
    echo -e "  ${WHITE}-- Scanners --${RESET}"
    for n in nuclei ffuf; do
        p="$(resolve_web "$n")"
        if [ -n "$p" ]; then ok "$(printf '%-10s %s' "$n" "$p")"
        else warn "$(printf '%-10s MISSING' "$n")"; fi
    done
    echo -e "  ${WHITE}-- Flutter AOT --${RESET}"
    warn "$(printf '%-10s %s' aotopsy "Windows-only（aotopsy.exe 为 Windows PE）")"
}

echo -e "${CYAN}================================================================================${RESET}"
echo -e "${CYAN}          Seep 外部能力包（Linux / macOS）${RESET}"
echo -e "${CYAN}================================================================================${RESET}"
info "仓库根目录 : $ROOT"
info "Android 根 : $ANDROID_ROOT"
info "Web 根     : $WEB_ROOT"
info "本次目标   : $([ "$CHECK_ONLY" = 1 ] && echo '（仅报表，不动磁盘）' || echo "${REQUESTED[*]:-（无）}")"

if [ "$CHECK_ONLY" = 1 ]; then
    board
    exit 0
fi

FAILED=()

# ---------------------------------------------------------------- 包管理器
PM=""
if have brew; then PM="brew"
elif have apt-get; then PM="apt"
elif have dnf; then PM="dnf"
elif have pacman; then PM="pacman"
fi

pkg_install() {
    case "$PM" in
        brew)    brew install "$@" ;;
        apt)     sudo apt-get update -qq && sudo apt-get install -y "$@" ;;
        dnf)     sudo dnf install -y "$@" ;;
        pacman)  sudo pacman -S --noconfirm "$@" ;;
        *)       return 1 ;;
    esac
}

# ---------------------------------------------------------------- web
do_web() {
    step "web — ffmpeg / ffprobe（HLS 取证核心）"
    mkdir -p "$WEB_ROOT/bin"
    local missing=()
    for n in ffmpeg ffprobe; do
        [ -n "$(resolve_web "$n")" ] || missing+=("$n")
    done
    if [ ${#missing[@]} -eq 0 ]; then
        ok "ffmpeg / ffprobe 已就绪，跳过"
        return 0
    fi
    info "缺: ${missing[*]}"
    if [ -n "$PM" ]; then
        info "尝试通过 $PM 安装 ffmpeg ..."
        if pkg_install ffmpeg >/dev/null 2>&1; then
            ok "已通过 $PM 安装 ffmpeg"
            return 0
        fi
        warn "$PM 安装失败"
    else
        warn "未检测到 brew / apt-get / dnf / pacman"
    fi
    warn "ffmpeg 未安装。请手动安装后重跑："
    echo "        macOS : brew install ffmpeg"
    echo "        Debian: sudo apt-get install -y ffmpeg"
    echo "        Fedora: sudo dnf install -y ffmpeg"
    echo "        Arch  : sudo pacman -S ffmpeg"
    echo "        或把 ffmpeg/ffprobe 放到: $WEB_ROOT/bin/"
    FAILED+=("web")
    return 1
}

# ---------------------------------------------------------------- android
do_android() {
    step "android — frida / objection / frida-dexdump / APKiD"
    mkdir -p "$ANDROID_ROOT/bin"

    # 解析可用解释器（Git Bash 上可能只有 py 启动器）
    local pyc=""
    if [ -n "${SEEP_PYTHON:-}" ] && [ -x "${SEEP_PYTHON}" ]; then
        pyc="$SEEP_PYTHON"
    elif have python3; then
        pyc="$(command -v python3)"
    elif have python; then
        pyc="$(command -v python)"
    elif have py; then
        pyc="py -3"
    fi
    if [ -z "$pyc" ]; then
        warn "未找到可用的 Python，无法创建 venv"
        FAILED+=("android")
        return 1
    fi

    local venv="$ANDROID_ROOT/frida-env"
    if [ ! -x "$venv/bin/python" ]; then
        info "创建 venv: $venv"
        if ! $pyc -m venv "$venv" >/dev/null 2>&1; then
            warn "创建 venv 失败（可能需要 python3-venv 包）"
            FAILED+=("android")
            return 1
        fi
    else
        info "venv 已存在，复用: $venv"
    fi

    info "pip 安装 frida / frida-tools / objection / frida-dexdump / apkid ..."
    if "$venv/bin/python" -m pip install --upgrade --quiet \
            frida frida-tools objection frida-dexdump apkid >/dev/null 2>&1; then
        ok "pip 安装完成"
    else
        warn "pip 安装失败（网络或编译依赖问题）"
        FAILED+=("android")
        return 1
    fi

    # 生成 PATH shim（只建软链接，不写用户的 shell rc）
    for n in frida frida-ps frida-trace objection frida-dexdump apkid; do
        if [ -x "$venv/bin/$n" ]; then
            ln -sf "$venv/bin/$n" "$ANDROID_ROOT/bin/$n"
        fi
    done
    ok "shim 已生成: $ANDROID_ROOT/bin/"

    if [ "$SKIP_PATH" = 0 ]; then
        info "如未在 PATH 中，可自行加入 shell 配置："
        echo "        export PATH=\"$ANDROID_ROOT/bin:\$PATH\""
    fi
    return 0
}

# ---------------------------------------------------------------- scanners
do_scanners() {
    step "scanners — nuclei / ffuf（可选）"
    mkdir -p "$WEB_ROOT/bin"
    local need=() n
    for n in nuclei ffuf; do
        [ -n "$(resolve_web "$n")" ] || need+=("$n")
    done
    if [ ${#need[@]} -eq 0 ]; then
        ok "nuclei / ffuf 已就绪，跳过"
        return 0
    fi
    info "缺: ${need[*]}"
    if [ "$PM" = "brew" ]; then
        for n in "${need[@]}"; do
            if pkg_install "$n" >/dev/null 2>&1; then ok "$n 已安装"; else warn "$n 安装失败"; FAILED+=("$n"); fi
        done
        return 0
    fi
    warn "未检测到 Homebrew，自动下载需按架构选包，本脚本不代劳。请手动安装："
    echo "        nuclei : https://github.com/projectdiscovery/nuclei/releases"
    echo "        ffuf   : https://github.com/ffuf/ffuf/releases"
    echo "        解压后放到: $WEB_ROOT/bin/"
    FAILED+=("scanners")
    return 1
}

# ---------------------------------------------------------------- aotopsy
do_aotopsy() {
    step "aotopsy — Flutter / Dart AOT 分析"
    warn "Unix 跳过：aotopsy.exe 是 Windows PE 单文件，无法在 Linux/macOS 运行"
    info "Unix 上的 Flutter 分析路线：用 apktool 解包后直接读 libapp.so 的 Dart 符号，"
    info "或用 seep_aotopsy 的诊断输出定位 libapp.so 再交给 radare2 / IDA"
    return 0
}

# ---------------------------------------------------------------- 主流程
if [ ${#REQUESTED[@]} -gt 0 ]; then
    # 去重
    UNIQ=()
    for c in "${REQUESTED[@]}"; do
        skip=0
        for u in "${UNIQ[@]:-}"; do [ "$u" = "$c" ] && skip=1 && break; done
        [ "$skip" = 0 ] && UNIQ+=("$c")
    done
    for c in "${UNIQ[@]}"; do
        case "$c" in
            web)      do_web || true ;;
            android)  do_android || true ;;
            scanners) do_scanners || true ;;
            aotopsy)  do_aotopsy || true ;;
        esac
    done
fi

board

step "结论"
MISSING=0
for n in ffmpeg ffprobe; do [ -z "$(resolve_web "$n")" ] && MISSING=$((MISSING+1)); done
for n in frida objection apkid; do [ -z "$(resolve_android "$n")" ] && MISSING=$((MISSING+1)); done

if [ "$MISSING" -eq 0 ]; then
    ok "核心外部能力已就绪"
else
    warn "仍有 $MISSING 项缺失（不影响 MCP 服务启动，相关工具会返回修复指引）"
    info "重跑：./setup/install-capabilities.sh --only all"
    info "或查看：./setup/install-capabilities.sh --check-only"
fi

if [ "$STRICT" = 1 ] && [ "$MISSING" -gt 0 ]; then
    exit 1
fi
exit 0
