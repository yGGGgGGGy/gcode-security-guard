#!/usr/bin/env bash
# install.sh — Gcode Security Guard 麒麟OS 一键部署脚本
# 用法: sudo bash deploy/install.sh [--skip-model] [--skip-selinux]
set -euo pipefail

# ─── 配置 ─────────────────────────────────────────────────────
GCODE_USER="gcode"
GCODE_GROUP="gcode"
INSTALL_DIR="/opt/gcode"
CONFIG_DIR="/etc/gcode"
LOG_DIR="/var/log/gcode"
DATA_DIR="/var/lib/gcode"
RUN_DIR="/run/gcode"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/yGGGgGGGy/gcode-security-guard.git"
BRANCH="main"

SKIP_MODEL=false
SKIP_SELINUX=false

for arg in "$@"; do
    case "$arg" in
        --skip-model)  SKIP_MODEL=true ;;
        --skip-selinux) SKIP_SELINUX=true ;;
        --help|-h)
            echo "用法: sudo bash deploy/install.sh [--skip-model] [--skip-selinux]"
            echo "  --skip-model    跳过下载 Qwen2.5-0.5B 模型"
            echo "  --skip-selinux  跳过 SELinux 策略配置"
            exit 0
            ;;
    esac
done

# ─── 前置检查 ──────────────────────────────────────────────────
info()  { echo -e "\033[1;32m[Gcode]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[警告]\033[0m $*"; }
error() { echo -e "\033[1;31m[错误]\033[0m $*"; exit 1; }

[[ $EUID -eq 0 ]] || error "请使用 root 运行: sudo bash $0"
command -v python3 >/dev/null || error "未找到 python3，请先安装 Python 3.11+"
command -v systemctl >/dev/null || error "未找到 systemctl，此脚本仅支持 systemd 系统"

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)
[[ "$PYTHON_MAJOR" -ge 3 && "$PYTHON_MINOR" -ge 11 ]] || error "需要 Python 3.11+，当前: $PYTHON_VER"

info "Python $PYTHON_VER — 满足要求"

# ─── 系统依赖 ──────────────────────────────────────────────────
info "安装系统依赖..."
if command -v dnf >/dev/null; then
    dnf install -y python3-pip python3-venv git psutil audit 2>/dev/null || true
elif command -v yum >/dev/null; then
    yum install -y python3-pip python3-venv git psutil audit 2>/dev/null || true
elif command -v apt-get >/dev/null; then
    apt-get update && apt-get install -y python3-pip python3-venv git python3-psutil auditd 2>/dev/null || true
else
    warn "未知包管理器，请手动安装: python3-pip python3-venv git"
fi

# ─── 创建用户和目录 ────────────────────────────────────────────
if ! id "$GCODE_USER" &>/dev/null; then
    info "创建用户 $GCODE_USER..."
    useradd --system --shell /sbin/nologin --home-dir "$INSTALL_DIR" "$GCODE_USER"
fi

info "创建目录结构..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" "$DATA_DIR" "$RUN_DIR"
chown "$GCODE_USER:$GCODE_GROUP" "$LOG_DIR" "$DATA_DIR" "$RUN_DIR"
chmod 750 "$LOG_DIR" "$DATA_DIR"
chmod 770 "$RUN_DIR"

# ─── 克隆/更新代码 ─────────────────────────────────────────────
if [[ -d "$INSTALL_DIR/gcode-security-guard/.git" ]]; then
    info "更新已有代码..."
    cd "$INSTALL_DIR/gcode-security-guard"
    git fetch origin "$BRANCH" && git checkout "$BRANCH" && git pull
else
    info "克隆代码到 $INSTALL_DIR/gcode-security-guard..."
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR/gcode-security-guard"
fi

chown -R "$GCODE_USER:$GCODE_GROUP" "$INSTALL_DIR/gcode-security-guard"

# ─── Python 虚拟环境 ──────────────────────────────────────────
info "创建 Python 虚拟环境..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel

info "安装项目依赖..."
"$VENV_DIR/bin/pip" install -e "$INSTALL_DIR/gcode-security-guard"

# ─── 配置文件 ──────────────────────────────────────────────────
if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
    info "生成默认配置..."
    cp "$INSTALL_DIR/gcode-security-guard/config.yaml" "$CONFIG_DIR/config.yaml"
else
    info "配置文件已存在，跳过"
fi

# ─── Qwen 模型预下载（可选）────────────────────────────────────
if [[ "$SKIP_MODEL" == false ]]; then
    info "预下载 Qwen2.5-0.5B 模型（可能需要几分钟）..."
    "$VENV_DIR/bin/python3" -c "
from transformers import pipeline
pipeline('zero-shot-classification', model='Qwen/Qwen2.5-0.5B', device=-1)
print('模型下载完成')
" || warn "模型下载失败，首次启动时会自动下载"
else
    info "跳过模型预下载"
fi

# ─── systemd 服务 ──────────────────────────────────────────────
info "安装 systemd 服务..."
cp "$INSTALL_DIR/gcode-security-guard/deploy/gcode-security-guard.service" /etc/systemd/system/
cp "$INSTALL_DIR/gcode-security-guard/deploy/gcode-mcp-server.service" /etc/systemd/system/
systemctl daemon-reload

# ─── SELinux ───────────────────────────────────────────────────
if [[ "$SKIP_SELINUX" == false ]]; then
    if command -v getenforce &>/dev/null && [[ "$(getenforce)" != "Disabled" ]]; then
        info "配置 SELinux 策略..."
        SELINUX_DIR=$(mktemp -d)
        cp "$INSTALL_DIR/gcode-security-guard/deploy/gcode-selinux.te" "$SELINUX_DIR/"
        cd "$SELINUX_DIR"
        checkmodule -M -m -o gcode-selinux.mod gcode-selinux.te 2>/dev/null && \
        semodule_package -o gcode-selinux.pp -m gcode-selinux.mod && \
        semodule -i gcode-selinux.pp && \
        info "SELinux 策略已安装" || \
        warn "SELinux 策略安装失败，请手动处理（参考 deploy/gcode-selinux.te）"
        rm -rf "$SELINUX_DIR"

        # 设置 socket 目录的 SELinux 上下文
        semanage fcontext -a -t tmpfs_t "$RUN_DIR(/.*)?" 2>/dev/null || true
        restorecon -Rv "$RUN_DIR" 2>/dev/null || true
    else
        info "SELinux 未启用，跳过"
    fi
else
    info "跳过 SELinux 配置"
fi

# ─── auditd 集成 ───────────────────────────────────────────────
if command -v auditctl &>/dev/null; then
    info "配置 auditd 规则..."
    cat > /etc/audit/rules.d/gcode.rules <<'AUDIT'
# Gcode 操作审计
-w /opt/gcode/ -p wa -k gcode-config
-w /etc/gcode/ -p wa -k gcode-config
-w /run/gcode/ -p wa -k gcode-socket
AUDIT
    augenrules --load 2>/dev/null || warn "auditd 规则加载失败，请手动执行: augenrules --load"
fi

# ─── 启用服务 ──────────────────────────────────────────────────
info "启用并启动服务..."
systemctl enable --now gcode-mcp-server.service
systemctl enable --now gcode-security-guard.service

# ─── 验证 ─────────────────────────────────────────────────────
sleep 2
GUARD_STATUS=$(systemctl is-active gcode-security-guard.service 2>/dev/null || true)
MCP_STATUS=$(systemctl is-active gcode-mcp-server.service 2>/dev/null || true)

echo ""
echo "══════════════════════════════════════════════════"
echo "  Gcode Security Guard 部署完成"
echo "══════════════════════════════════════════════════"
echo ""
echo "  安全层 (gcode-security-guard): $GUARD_STATUS"
echo "  执行层 (gcode-mcp-server):     $MCP_STATUS"
echo ""
echo "  Socket:  $RUN_DIR/gcode.sock"
echo "  配置:    $CONFIG_DIR/config.yaml"
echo "  日志:    $LOG_DIR/"
echo ""
echo "  查看日志:  journalctl -u gcode-security-guard -f"
echo "  查看状态:  systemctl status gcode-security-guard gcode-mcp-server"
echo ""
echo "  测试连接:  echo '{\"query\":\"查看磁盘使用\"}' | socat - UNIX-CONNECT:$RUN_DIR/gcode.sock"
echo ""
