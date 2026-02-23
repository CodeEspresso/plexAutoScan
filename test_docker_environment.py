#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本 - 验证Docker环境中的依赖和设置
"""

import os
import sys
import socket
import time
from datetime import datetime

# 设置socket超时时间
socket.setdefaulttimeout(30)

# 测试结果记录
results = {
    "success": True,
    "messages": []
}

# 打印测试开始信息
def log(message, is_error=False):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    level = "[ERROR]" if is_error else "[INFO]"
    print(f"{timestamp} {level} {message}")
    results["messages"].append(f"{level} {message}")
    if is_error:
        results["success"] = False

def check_python_environment():
    """检查Python环境"""
    log("=== 检查Python环境 ===")
    log(f"Python版本: {sys.version}")
    log(f"Python路径: {sys.executable}")
    log(f"虚拟环境: {(os.environ.get('VIRTUAL_ENV') or '未设置')}")
    log(f"PATH环境变量: {os.environ.get('PATH', '')[:200]}...")
    
def check_dependencies():
    """检查项目依赖"""
    log("=== 检查项目依赖 ===")
    
    # 检查核心依赖
    dependencies = [
        ('requests', 'import requests'),
        ('psutil', 'import psutil'),
        ('pysmb', 'from smb.SMBConnection import SMBConnection'),
        ('yaml', 'import yaml')
    ]
    
    for name, import_cmd in dependencies:
        try:
            exec(import_cmd)
            log(f"✓ 成功导入 {name}")
        except ImportError as e:
            log(f"✗ 无法导入 {name}: {e}", is_error=True)
        except Exception as e:
            log(f"✗ 导入 {name} 时发生异常: {e}", is_error=True)

def check_file_system():
    """检查文件系统设置"""
    log("=== 检查文件系统 ===")
    
    # 检查关键路径
    paths_to_check = [
        '/vol02/CloudDrive/WebDAV',
        '/data/cache',
        '/data/snapshots',
        '/data/config.env',
        '/debug_docker_env.sh',
        '/docker_dependency_check.sh'
    ]
    
    for path in paths_to_check:
        if os.path.exists(path):
            file_type = "文件" if os.path.isfile(path) else "目录"
            log(f"✓ 路径存在 ({file_type}): {path}")
            if os.path.isdir(path):
                try:
                    content_count = len(os.listdir(path))
                    log(f"   └─ 包含 {content_count} 个项目")
                except Exception as e:
                    log(f"   └─ 无法列出目录内容: {e}", is_error=True)
        else:
            log(f"✗ 路径不存在: {path}", is_error=True)

def check_environment_variables():
    """检查环境变量"""
    log("=== 检查环境变量 ===")
    
    env_vars = [
        'TZ', 'DOCKER_ENV', 'DEBUG', 'LOCAL_PATH_PREFIX', 'PROD_TARGET_PATH_PREFIX',
        'SMB_USER', 'SMB_PASSWORD', 'SMB_DOMAIN', 'PLEX_URL', 'PLEX_TOKEN'
    ]
    
    for var in env_vars:
        value = os.environ.get(var)
        if value is not None:
            # 敏感信息不打印完整值
            if var in ['SMB_PASSWORD', 'PLEX_TOKEN']:
                log(f"✓ {var} = [已设置，值隐藏]")
            else:
                log(f"✓ {var} = {value}")
        else:
            log(f"✗ {var} 未设置")

def test_smb_import_only():
    """仅测试SMB导入，不尝试实际连接"""
    log("=== 测试SMB导入功能 ===")
    
    try:
        # 只尝试导入，不建立实际连接
        from smb.SMBConnection import SMBConnection
        log("✓ 成功导入 SMBConnection 类")
        # 打印一些SMB模块信息以确认它能正常工作
        log(f"✓ SMB模块导入成功，可以使用SMBConnection类")
    except ImportError as e:
        log(f"✗ 无法导入SMBConnection: {e}", is_error=True)
    except Exception as e:
        log(f"✗ SMB导入测试时发生异常: {e}", is_error=True)

def check_project_imports():
    """检查项目内部模块导入"""
    log("=== 检查项目内部模块导入 ===")
    
    try:
        # 添加项目根目录到Python路径
        project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # 尝试导入一些核心模块
        from src.utils.config import Config
        log("✓ 成功导入 src.utils.config.Config")
        
        from src.plex.api import PlexAPI
        log("✓ 成功导入 src.plex.api.PlexAPI")
        
        from src.smb_api import SMBManager
        log("✓ 成功导入 src.smb_api.SMBManager")
    except ImportError as e:
        log(f"✗ 导入项目模块失败: {e}", is_error=True)
    except Exception as e:
        log(f"✗ 项目模块导入测试时发生异常: {e}", is_error=True)

def main():
    """主函数"""
    log("开始Docker环境验证测试")
    
    check_python_environment()
    check_dependencies()
    check_file_system()
    check_environment_variables()
    test_smb_import_only()  # 只测试导入，不连接
    check_project_imports()
    
    # 打印测试结果摘要
    log("\n=== 测试结果摘要 ===")
    if results["success"]:
        log("✅ 所有测试通过！Docker环境设置正确。")
    else:
        log("❌ 测试失败！请查看上面的错误信息并修复问题。", is_error=True)
    
    log("测试完成")

if __name__ == "__main__":
    main()
    # 根据测试结果设置退出码
    sys.exit(0 if results["success"] else 1)