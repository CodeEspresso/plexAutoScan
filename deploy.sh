#!/bin/bash
# 部署脚本 - 同步代码到NAS并重启容器
# 使用方法: ./deploy.sh [配置文件路径]

set -e

# 默认配置文件路径
CONFIG_FILE="${1:-.deploy.conf}"

# 检查配置文件是否存在
if [ ! -f "$CONFIG_FILE" ]; then
    echo "错误: 配置文件不存在: $CONFIG_FILE"
    echo ""
    echo "请创建配置文件 .deploy.conf，内容如下:"
    echo "----------------------------------------"
    cat << 'EOF'
# NAS连接配置
NAS_HOST=your-nas-host
NAS_USER=admin
NAS_PATH=/volume1/docker/plexAutoScan

# SSH密钥路径（可选，如果使用密钥认证）
# SSH_KEY_PATH=~/.ssh/id_rsa

# 是否在部署前检查Git状态（yes/no）
CHECK_GIT_STATUS=yes
EOF
    echo "----------------------------------------"
    exit 1
fi

# 读取配置文件
source "$CONFIG_FILE"

# 设置默认值
LOCAL_PATH="$(pwd)"
CHECK_GIT_STATUS="${CHECK_GIT_STATUS:-yes}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PlexAutoScan 部署脚本 ===${NC}"
echo -e "${BLUE}配置文件: $CONFIG_FILE${NC}"
echo "本地路径: $LOCAL_PATH"
echo "NAS地址: $NAS_USER@$NAS_HOST:$NAS_PATH"
echo ""

# 1. 检查本地是否有未提交的修改
if [ "$CHECK_GIT_STATUS" = "yes" ] && [ -d ".git" ]; then
    if ! git diff-index --quiet HEAD --; then
        echo -e "${YELLOW}警告: 检测到未提交的修改${NC}"
        git status --short
        read -p "是否继续部署? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# 2. 同步代码到NAS（排除配置文件和数据目录）
echo -e "${GREEN}步骤1: 同步代码到NAS...${NC}"

# 构建rsync命令
RSYNC_CMD="rsync -avz --progress \
    --exclude 'config.env' \
    --exclude 'config.env.local' \
    --exclude '*.env' \
    --exclude 'data/' \
    --exclude 'logs/' \
    --exclude 'cache/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude '.DS_Store' \
    --exclude '*.log' \
    --exclude 'tmp_venv/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude '.idea/' \
    --exclude '.vscode/' \
    --exclude '.deploy.conf' \
    --exclude 'deploy.sh'"

# 如果使用SSH密钥
if [ -n "$SSH_KEY_PATH" ]; then
    RSYNC_CMD="$RSYNC_CMD -e 'ssh -i $SSH_KEY_PATH'"
fi

RSYNC_CMD="$RSYNC_CMD ${LOCAL_PATH}/ ${NAS_USER}@${NAS_HOST}:${NAS_PATH}/"

# 执行rsync
eval $RSYNC_CMD

# 3. 在NAS上重启Docker容器
echo -e "${GREEN}步骤2: 重启Docker容器...${NC}"

SSH_CMD="ssh"
if [ -n "$SSH_KEY_PATH" ]; then
    SSH_CMD="ssh -i $SSH_KEY_PATH"
fi

$SSH_CMD "${NAS_USER}@${NAS_HOST}" "cd ${NAS_PATH} && docker compose down && docker compose up -d"

# 4. 检查容器状态
echo -e "${GREEN}步骤3: 检查容器状态...${NC}"
$SSH_CMD "${NAS_USER}@${NAS_HOST}" "docker compose ps"

echo -e "${GREEN}=== 部署完成 ===${NC}"
echo -e "查看日志: $SSH_CMD ${NAS_USER}@${NAS_HOST} 'cd ${NAS_PATH} && docker compose logs -f'"
