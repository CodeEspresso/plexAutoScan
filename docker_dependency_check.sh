#!/bin/bash

# docker_dependency_check.sh - Docker环境依赖验证脚本

# 打印脚本信息
echo "[DOCKER_DEPENDENCY_CHECK] 启动Docker环境依赖验证脚本"
echo "[DOCKER_DEPENDENCY_CHECK] 当前时间: $(date)"

# 创建一个简单的Python测试脚本，验证依赖导入
echo "[DOCKER_DEPENDENCY_CHECK] 创建临时依赖验证脚本"
cat > /tmp/dependency_test.py << 'EOF'
import sys

# 检查Python版本
print(f"Python版本: {sys.version}")

# 尝试导入关键依赖
print("\n=== 导入关键依赖 ===")
dependencies = [
    ('requests', 'import requests'),
    ('psutil', 'import psutil'),
    ('pysmb', 'from smb.SMBConnection import SMBConnection'),
    ('yaml', 'import yaml')
]

all_success = True

for name, import_cmd in dependencies:
    try:
        exec(import_cmd)
        print(f"✓ 成功导入 {name}")
    except ImportError as e:
        print(f"✗ 无法导入 {name}: {e}")
        all_success = False

print("\n=== 额外的路径检查 ===")
import os
from pathlib import Path

# 检查关键路径是否存在
test_paths = [
    '/vol02/CloudDrive/WebDAV',
    '/data/cache',
    '/data/snapshots'
]

for path in test_paths:
    if os.path.exists(path):
        print(f"✓ 路径存在: {path}")
        if os.path.isdir(path):
            print(f"   └─ 目录内容 ({len(os.listdir(path))} 个项目)")
    else:
        print(f"✗ 路径不存在: {path}")

# 检查环境变量
print("\n=== 检查关键环境变量 ===")
env_vars = [
    'TZ',
    'DOCKER_ENV',
    'DEBUG',
    'LOCAL_PATH_PREFIX',
    'PROD_TARGET_PATH_PREFIX'
]

for var in env_vars:
    value = os.environ.get(var)
    if value is not None:
        print(f"✓ {var} = {value}")
    else:
        print(f"✗ {var} 未设置")

# 检查项目是否能正确导入自己的模块
print("\n=== 检查项目模块导入 ===")
try:
    sys.path.append('/data')
    from src.config import Config
    print("✓ 成功导入 src.config.Config")
    # 尝试实例化配置（如果可以）
    try:
        config = Config()
        print("   └─ 成功实例化Config对象")
    except Exception as e:
        print(f"   └─ 实例化Config失败: {e}")
except Exception as e:
    print(f"✗ 导入src.config失败: {e}")

# 返回状态码
sys.exit(0 if all_success else 1)
EOF

# 执行依赖验证脚本
echo "[DOCKER_DEPENDENCY_CHECK] 执行依赖验证脚本"
/venv/bin/python /tmp/dependency_test.py
DEPENDENCY_TEST_EXIT_CODE=$?

# 打印结果摘要
echo "\n[DOCKER_DEPENDENCY_CHECK] 依赖验证完成"
if [ $DEPENDENCY_TEST_EXIT_CODE -eq 0 ];
    then
        echo "[DOCKER_DEPENDENCY_CHECK] ✅ 所有关键依赖导入成功"
    else
        echo "[DOCKER_DEPENDENCY_CHECK] ❌ 部分依赖导入失败"
fi

echo "[DOCKER_DEPENDENCY_CHECK] Docker环境依赖验证脚本结束"
exit $DEPENDENCY_TEST_EXIT_CODE