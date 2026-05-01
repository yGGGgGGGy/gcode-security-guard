#!/bin/bash
# Gcode 一键部署脚本 (麒麟OS)
# bash deploy/setup.sh

set -euo pipefail

GCODE_HOME="${GCODE_HOME:-/opt/gcode}"
VENV_DIR="$GCODE_HOME/venv"
GCODE_USER="${GCODE_USER:-gcode}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Gcode 部署 ==="
echo "项目目录: $PROJECT_ROOT"
echo "安装目录: $GCODE_HOME"

# 1. 创建系统用户
if ! id "$GCODE_USER" &>/dev/null; then
    sudo useradd -r -s /sbin/nologin -d "$GCODE_HOME" -m "$GCODE_USER"
    echo "[+] 用户 $GCODE_USER 已创建"
else
    echo "[=] 用户 $GCODE_USER 已存在"
fi

# 2. 创建目录
sudo mkdir -p /opt/gcode /run/gcode /data/gcode
sudo chown -R "$GCODE_USER:$GCODE_USER" /opt/gcode /run/gcode /data/gcode
echo "[+] 目录已创建"

# 3. 复制项目文件
sudo rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.egg-info' \
    "$PROJECT_ROOT/" "$GCODE_HOME/"
sudo chown -R "$GCODE_USER:$GCODE_USER" "$GCODE_HOME"
echo "[+] 项目文件已同步到 $GCODE_HOME"

# 4. 安装虚拟环境 + 依赖
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -e "$GCODE_HOME/"
echo "[+] 依赖安装完成"

# 5. 配置环境变量
if [ ! -f "$GCODE_HOME/.env" ]; then
    cp "$GCODE_HOME/config/.env.template" "$GCODE_HOME/.env"
    echo "[+] 配置文件已生成: $GCODE_HOME/.env"
    echo "    请按需修改后启动服务"
else
    echo "[=] 配置文件已存在，跳过"
fi

# 6. 安装 systemd 服务
sudo cp "$GCODE_HOME/deploy/gcode-mcp-server.service" /etc/systemd/system/
sudo cp "$GCODE_HOME/deploy/gcode-security-guard.service" /etc/systemd/system/
sudo systemctl daemon-reload
echo "[+] systemd 服务已安装"

# 7. SELinux (麒麟OS)
if command -v semanage &>/dev/null; then
    sudo semanage fcontext -a -t svirt_socket_t "/run/gcode(/.*)?" 2>/dev/null || true
    sudo restorecon -Rv /run/gcode
    echo "[+] SELinux 上下文已设置"
fi

echo ""
echo "=== 部署完成 ==="
echo ""
echo "启动服务:"
echo "  sudo systemctl enable --now gcode-mcp-server gcode-security-guard"
echo ""
echo "查看状态:"
echo "  sudo systemctl status gcode-mcp-server gcode-security-guard"
echo ""
echo "测试:"
echo "  echo '{\"query\":\"查看内存\",\"user_id\":\"admin\",\"session_id\":\"test-001\"}' | nc -U /run/gcode/gcode.sock"
