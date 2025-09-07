#!/bin/bash

# main.sh - PlexAutoScan定期扫描任务入口脚本

# 设置中文支持
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8

# 打印脚本信息
echo "[INFO] 启动PlexAutoScan定期扫描任务入口脚本"
echo "[INFO] 当前时间: $(date)"
echo "[INFO] 脚本路径: $(realpath $0)"

# 验证Python环境
echo "[INFO] 检查Python环境..."
if command -v python &> /dev/null; then
    echo "[INFO] Python版本: $(python --version)"
else
    echo "[ERROR] 未找到Python解释器，尝试使用python3..."
    if command -v python3 &> /dev/null; then
        echo "[INFO] Python3版本: $(python3 --version)"
        alias python=python3
    else
        echo "[ERROR] 未找到Python解释器，请检查环境配置!"
        exit 1
    fi
fi

# 验证项目结构
echo "[INFO] 检查项目结构..."
if [ -f /data/src/main.py ]; then
    echo "[INFO] 找到主程序文件: /data/src/main.py"
else
    echo "[ERROR] 未找到主程序文件: /data/src/main.py" >&2
    exit 1
fi

# 执行主程序
echo "[INFO] 开始执行PlexAutoScan主程序..."
if [ "$DEBUG" = "1" ]; then
    echo "[DEBUG] 以调试模式启动主程序"
    exec python -m src.main --debug
else
    exec python -m src.main
fi