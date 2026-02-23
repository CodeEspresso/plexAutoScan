#!/bin/bash
# 部署脚本 - 同步代码到NAS
# 使用方法: ./deploy.sh [配置文件路径]

set -e

# 默认配置文件路径
CONFIG_FILE="${1:-.deploy.conf}"

# 默认SSH端口
NAS_SSH_PORT="${NAS_SSH_PORT:-22}"

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
NAS_SSH_PORT=22
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

echo -e "${GREEN}=== PlexAutoScan 代码同步脚本 ===${NC}"
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
echo -e "${GREEN}同步代码到NAS...${NC}"

# 构建rsync命令
RSYNC_CMD="rsync -avz --progress \
    --exclude 'config.env.local' \
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
    --exclude 'deploy.sh' \
    --exclude 'test_files/' \
    --exclude 'local_backup/' \
    --exclude 'tests/' \
    --exclude '.trae/' \
    --exclude '*.md'"

# 如果使用SSH密钥
if [ -n "$SSH_KEY_PATH" ]; then
    RSYNC_CMD="$RSYNC_CMD -e 'ssh -i $SSH_KEY_PATH -p $NAS_SSH_PORT'"
else
    RSYNC_CMD="$RSYNC_CMD -e 'ssh -p $NAS_SSH_PORT'"
fi

RSYNC_CMD="$RSYNC_CMD ${LOCAL_PATH}/ ${NAS_USER}@${NAS_HOST}:${NAS_PATH}/"

# 执行rsync
eval $RSYNC_CMD

echo ""
echo -e "${GREEN}=== 同步完成 ===${NC}"
echo ""
echo "请在NAS上手动执行以下命令重启Docker："
echo ""
echo "  ssh -p $NAS_SSH_PORT $NAS_USER@$NAS_HOST"
echo "  cd $NAS_PATH"
echo "  sudo docker compose down"
echo "  sudo docker compose build --no-cache"
echo "  sudo docker compose up -d"
