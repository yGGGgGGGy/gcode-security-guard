# Gcode 麒麟OS 部署指南

## 文件清单

```
deploy/
├── install.sh                    # 一键安装脚本
├── gcode-security-guard.service  # 安全层 systemd 单元
├── gcode-mcp-server.service      # 执行层 systemd 单元
├── gcode-selinux.te              # SELinux 策略模块
├── .env.example                  # 环境变量模板
└── README.md                     # 本文档
```

## 快速部署

```bash
# 完整安装（含模型下载 + SELinux 配置）
sudo bash deploy/install.sh

# 跳过模型预下载（首次启动时自动下载）
sudo bash deploy/install.sh --skip-model

# 跳过 SELinux（SELinux 已禁用的环境）
sudo bash deploy/install.sh --skip-selinux
```

## 手动部署

### 1. 系统要求

- 麒麟OS V10 或 CentOS 7+ / Fedora 38+
- Python 3.11+
- systemd
- 2GB+ RAM（模型推理需要）

### 2. 安装依赖

```bash
# 麒麟OS / CentOS
sudo dnf install -y python3-pip python3-venv git socat audit

# 或 Ubuntu
sudo apt-get install -y python3-pip python3-venv git socat auditd
```

### 3. 创建用户

```bash
sudo useradd --system --shell /sbin/nologin --home-dir /opt/gcode gcode
```

### 4. 部署代码

```bash
sudo git clone https://github.com/yGGGgGGGy/gcode-security-guard.git /opt/gcode
cd /opt/gcode
sudo python3 -m venv venv
sudo ./venv/bin/pip install -e .
```

### 5. 配置

```bash
# 环境变量
sudo cp deploy/.env.example /opt/gcode/.env
sudo vi /opt/gcode/.env

# 配置文件
sudo mkdir -p /etc/gcode
sudo cp config.yaml /etc/gcode/config.yaml
sudo vi /etc/gcode/config.yaml
```

### 6. 目录权限

```bash
sudo mkdir -p /var/log/gcode /var/lib/gcode /run/gcode /opt/gcode/models
sudo chown gcode:gcode /var/log/gcode /var/lib/gcode /run/gcode /opt/gcode/models
sudo chmod 750 /var/log/gcode /var/lib/gcode
sudo chmod 770 /run/gcode
```

### 7. 安装 systemd 服务

```bash
sudo cp deploy/gcode-security-guard.service /etc/systemd/system/
sudo cp deploy/gcode-mcp-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gcode-mcp-server gcode-security-guard
```

### 8. SELinux 配置

```bash
# 检查 SELinux 状态
getenforce

# 如果是 Enforcing，编译安装策略模块
cd /tmp
cp /opt/gcode/deploy/gcode-selinux.te .
checkmodule -M -m -o gcode-selinux.mod gcode-selinux.te
semodule_package -o gcode-selinux.pp -m gcode-selinux.mod
sudo semodule -i gcode-selinux.pp

# 设置 socket 目录上下文
sudo semanage fcontext -a -t tmpfs_t "/run/gcode(/.*)?"
sudo restorecon -Rv /run/gcode

# 如果 semanage 不可用，临时方案：
sudo chcon -t tmpfs_t /run/gcode
```

## 验证部署

```bash
# 检查服务状态
systemctl status gcode-security-guard gcode-mcp-server

# 查看日志
journalctl -u gcode-security-guard -f
journalctl -u gcode-mcp-server -f

# 测试 socket 连接
echo '{"query":"查看磁盘使用"}' | socat - UNIX-CONNECT:/run/gcode/gcode.sock

# 测试 MCP Server（stdio 模式）
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | /opt/gcode/venv/bin/python -m gcode.mcp.server
```

## 常见问题

### SELinux 阻止 socket 创建

```
avc: denied { create } for pid=xxx comm="python" name="gcode.sock"
```

解决：安装 SELinux 策略模块（见上方步骤 8），或临时设置宽容模式：
```bash
sudo setenforce 0   # 临时，重启后恢复
```

### 模型下载失败

国内网络可能无法直接访问 HuggingFace。解决方案：
```bash
# 使用镜像
export HF_ENDPOINT=https://hf-mirror.com
sudo -E /opt/gcode/venv/bin/python -c "from transformers import pipeline; pipeline('zero-shot-classification', model='Qwen/Qwen2.5-0.5B')"

# 或手动下载后放到模型目录
export HF_HOME=/opt/gcode/models
```

### 权限不足（执行层无法重启服务）

`gcode-mcp-server.service` 需要 `CAP_SYS_ADMIN` 权限来执行 `systemctl restart`。如果使用 Podman/Docker 部署，需要 `--cap-add SYS_ADMIN`。

### Socket 文件残留

服务异常退出可能留下 socket 文件，导致重启失败：
```bash
sudo rm -f /run/gcode/gcode.sock /run/gcode/gcode-dp1.sock
sudo systemctl restart gcode-mcp-server gcode-security-guard
```

## 架构说明

```
                     ┌─ gcode-security-guard.service
用户请求 → Unix Socket ─┤   (意图过滤 + 审计)
                     └─ gcode-mcp-server.service
                         (MCP Tool 执行)
```

两个服务通过 `/run/gcode/` 下的 Unix Socket 通信。
安全层依赖执行层（`Requires=` + `After=`），启动顺序自动保证。
