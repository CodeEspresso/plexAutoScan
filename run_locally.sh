#!/bin/bash
# 在本地环境中运行plex-auto-scan，无需Docker

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# 打印欢迎信息
printf "${BLUE}===== Plex Auto Scan 本地运行脚本 =====${NC}\n\n"

# 检查Python是否安装
if ! command -v python3 &> /dev/null
then
    printf "${RED}错误: 未找到Python 3。请先安装Python 3.9或更高版本。${NC}\n"
    exit 1
fi

# 检查Python版本
PYTHON_VERSION="$(python3 --version 2>&1 | cut -d ' ' -f 2)"
PYTHON_MAJOR="$(echo $PYTHON_VERSION | cut -d '.' -f 1)"
PYTHON_MINOR="$(echo $PYTHON_VERSION | cut -d '.' -f 2)"

if [ $PYTHON_MAJOR -lt 3 ] || [ $PYTHON_MINOR -lt 9 ]
then
    printf "${YELLOW}警告: 检测到Python版本 $PYTHON_VERSION。建议使用Python 3.9或更高版本。${NC}\n"
fi

printf "${GREEN}✓ Python已安装: $PYTHON_VERSION${NC}\n"

# 创建本地虚拟环境
VENV_DIR="local_venv"
if [ ! -d "$VENV_DIR" ]
then
    printf "${BLUE}\n创建Python虚拟环境...${NC}\n"
    python3 -m venv "$VENV_DIR"
    printf "${GREEN}✓ 虚拟环境创建成功${NC}\n"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 更新pip和安装依赖
printf "${BLUE}\n更新pip并安装依赖...${NC}\n"
pip install --upgrade pip setuptools wheel
pip install -r src/requirements.txt

# 检查核心依赖是否安装成功
printf "${BLUE}\n验证依赖安装...${NC}\n"

# 检查requests和psutil
try_import() {
    python -c "import $1"
    return $?
}

if try_import "requests, psutil"
then
    printf "${GREEN}✓ requests和psutil模块导入成功${NC}\n"
else
    printf "${RED}✗ requests或psutil模块导入失败${NC}\n"
    DEPENDENCY_ERROR=1
fi

# 检查pysmb
if try_import "smb; from smb.SMBConnection import SMBConnection"
then
    printf "${GREEN}✓ smb模块和SMBConnection导入成功${NC}\n"
else
    printf "${RED}✗ pysmb模块导入失败${NC}\n"
    SMB_ERROR=1
fi

# 检查pyyaml
if try_import "yaml"
then
    printf "${GREEN}✓ pyyaml模块导入成功${NC}\n"
else
    printf "${RED}✗ pyyaml模块导入失败${NC}\n"
    YAML_ERROR=1
fi

# 如果有依赖错误，提供安装帮助
if [ -n "$DEPENDENCY_ERROR" ] || [ -n "$SMB_ERROR" ] || [ -n "$YAML_ERROR" ]
then
    printf "${RED}\n依赖安装失败。尝试使用以下命令单独安装有问题的包:${NC}\n"
    if [ -n "$DEPENDENCY_ERROR" ]
    then
        echo "pip install requests psutil"
    fi
    if [ -n "$SMB_ERROR" ]
    then
        echo "pip install pysmb==1.2.9.1"
        echo "# 或尝试其他版本"
        echo "pip install pysmb"
    fi
    if [ -n "$YAML_ERROR" ]
    then
        echo "pip install pyyaml"
    fi
    printf "${RED}\n解决依赖问题后，请重新运行此脚本。${NC}\n"
    deactivate
    exit 1
fi

# 创建必要的目录
printf "${BLUE}\n创建必要的目录...${NC}\n"
mkdir -p data/snapshots logs
chmod -R 755 data logs

# 设置环境变量
printf "${BLUE}\n设置环境变量...${NC}\n"
export DOCKER_ENV=0
# 设置其他必要的环境变量
export SMB_USER=""  # 请根据实际情况设置
export SMB_PASSWORD=""  # 请根据实际情况设置
export SMB_DOMAIN=""

# 提供运行命令
printf "${GREEN}\n===== 准备就绪！=====${NC}\n"
printf "${BLUE}\n要运行应用程序，请执行以下命令:${NC}\n"
printf "${YELLOW}cd src && python main.py${NC}\n\n"

# 保持虚拟环境激活状态
printf "${BLUE}虚拟环境已激活。按Ctrl+C退出...${NC}\n"
# 防止脚本退出，保持虚拟环境激活状态
sleep infinity