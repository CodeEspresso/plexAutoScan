#!/bin/bash

# debug_docker_env.sh - Docker环境诊断脚本

# 打印脚本信息
echo "[DEBUG] Docker环境诊断脚本启动"
echo "[DEBUG] 当前时间: $(date)"
echo "[DEBUG] 脚本路径: $(realpath $0)"

echo "[DEBUG] === 系统基本信息 ==="
echo "[DEBUG] 主机名: $(hostname)"
echo "[DEBUG] 当前用户: $(whoami)"
echo "[DEBUG] 工作目录: $(pwd)"

echo "[DEBUG] === 文件系统信息 ==="
echo "[DEBUG] /vol02/CloudDrive/WebDAV 目录内容:"
ls -la /vol02/CloudDrive/WebDAV | head -10 || echo "[DEBUG] 无法列出目录内容"

echo "[DEBUG] === 磁盘挂载信息 ==="
df -h | grep -E '/vol02|Filesystem'

echo "[DEBUG] === 关键环境变量 ==="
env | grep -E 'PATH_PREFIX|BACKUP|DOCKER|DEBUG|MOUNT|EXCLUDE'

echo "[DEBUG] === Python环境信息 ==="
/venv/bin/python --version 2>&1
/venv/bin/pip --version 2>&1

# 检查关键依赖
echo "[DEBUG] === 关键依赖检查 ==="
for dep in pysmb pyyaml requests psutil;
do
    if /venv/bin/pip show $dep > /dev/null 2>&1;
    then
        echo "[DEBUG] ✓ $dep 已安装"
    else
        echo "[DEBUG] ✗ $dep 未安装"
    fi
done

echo "[DEBUG] === 配置文件检查 ==="
if [ -f /data/config.env ];
    then
        echo "[DEBUG] ✓ 找到配置文件: /data/config.env"
        echo "[DEBUG] 配置文件中的关键路径:" 
        grep -E 'BASE_PATH|MOUNT_PATHS|EXCLUDE_PATHS' /data/config.env 2>/dev/null || echo "[DEBUG] 未找到相关配置项"
    else
        echo "[DEBUG] ✗ 未找到配置文件: /data/config.env"
fi

# 执行Docker环境依赖验证脚本
echo "[DEBUG] === 执行Docker环境依赖验证脚本 ==="
if [ -f /docker_dependency_check.sh ];
    then
        echo "[DEBUG] ✓ 找到依赖验证脚本: /docker_dependency_check.sh"
        # 直接使用bash执行，因为脚本可能挂载为只读
        /bin/bash /docker_dependency_check.sh
        DEPENDENCY_CHECK_RESULT=$?
        if [ $DEPENDENCY_CHECK_RESULT -eq 0 ];
            then
                echo "[DEBUG] ✅ 依赖验证成功"
            else
                echo "[DEBUG] ❌ 依赖验证失败 (退出码: $DEPENDENCY_CHECK_RESULT)"
        fi
    else
        echo "[DEBUG] ✗ 未找到依赖验证脚本: /docker_dependency_check.sh"
fi

echo "[DEBUG] Docker环境诊断脚本完成"