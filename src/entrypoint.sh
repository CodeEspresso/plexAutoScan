#!/bin/bash

# entrypoint.sh - Docker容器入口点脚本

# 设置中文支持和时区
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8
# 确保Python环境使用正确的时区
export TZ=Asia/Shanghai
# 设置Python的时区环境变量
export PYTHON_TZ=Asia/Shanghai

# 打印环境信息
if [ "$DEBUG" = "1" ]; then
    echo "[DEBUG] 环境变量信息："
    env | sort
    echo "[DEBUG] 当前目录内容："
    ls -la
fi

# 检查配置文件
if [ -f /data/config.env ]; then
    echo "[INFO] 检测到配置文件 /data/config.env，加载环境变量..."
    # 定义简单的info函数用于配置文件中的输出
    info() {
        echo "[INFO] $@"
    }
    # 使用source命令加载配置文件（因为它包含bash脚本语法）
    source /data/config.env || echo "[WARN] 配置文件加载可能存在问题，但继续执行..."
else
    echo "[WARN] 未找到配置文件 /data/config.env，使用默认环境变量..."
fi

# 确保日志目录存在 - 针对飞牛OS优化路径处理
mkdir -p /data/logs
chmod 777 /data/logs

# 检查并确保快照目录存在
if [ -n "$SNAPSHOT_DIR" ]; then
    echo "[INFO] 确保快照目录 $SNAPSHOT_DIR 存在..."
    mkdir -p "$SNAPSHOT_DIR"
    chmod 777 "$SNAPSHOT_DIR"
else
    echo "[INFO] 使用默认快照目录 /data/snapshots..."
    mkdir -p /data/snapshots
    chmod 777 /data/snapshots
    export SNAPSHOT_DIR=/data/snapshots
fi

# 检查并确保输出目录存在
mkdir -p /data/output
chmod 777 /data/output

# 飞牛OS特定：确保挂载点目录存在并可访问
if [ -d /vol02/CloudDrive/WebDAV ]; then
    echo "[INFO] 验证挂载点 /vol02/CloudDrive/WebDAV 可访问"
    ls -la /vol02/CloudDrive/WebDAV > /dev/null 2>&1 && echo "[INFO] 挂载点访问成功" || echo "[WARN] 挂载点访问可能存在权限问题"
else
    echo "[WARN] 挂载点 /vol02/CloudDrive/WebDAV 不存在，将在运行时尝试访问"
fi

# 显示Python和依赖版本信息
echo "[INFO] Python版本：$(/venv/bin/python --version)"
echo "[INFO] pip版本：$(/venv/bin/pip --version)"

# 详细的虚拟环境诊断信息
echo "[INFO] === 虚拟环境诊断信息 ==="
echo "[INFO] 虚拟环境路径：$VIRTUAL_ENV"
echo "[INFO] PATH环境变量：$PATH"
echo "[INFO] Python解释器完整路径：$(which /venv/bin/python)"
echo "[INFO] sys.prefix：$(/venv/bin/python -c "import sys; print(sys.prefix)")"
echo "[INFO] sys.base_prefix：$(/venv/bin/python -c "import sys; print(sys.base_prefix)")"
echo "[INFO] 是否在虚拟环境中：$([[ $(/venv/bin/python -c "import sys; print(sys.prefix != sys.base_prefix)") == "True" ]] && echo "是" || echo "否")"
echo "[INFO] === 已安装的关键依赖 ==="
/venv/bin/pip show pysmb pyyaml requests psutil tqdm || echo "[INFO] 无法获取依赖信息"

# 如果有特定的启动命令参数，则执行，否则启动主程序
if [ $# -gt 0 ]; then
    echo "[INFO] 执行自定义命令：$@"
    exec "$@"
else
    # 默认启动主程序 - 确保使用虚拟环境中的Python解释器
    echo "[INFO] 启动PlexAutoScan主程序..."
    if [ "$DEBUG" = "1" ]; then
        exec /venv/bin/python -m src.main --debug
    else
        exec /venv/bin/python -m src.main
    fi
fi