#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用于验证Docker容器内Python依赖是否正确安装的脚本"""
import sys

def verify_basic_dependencies():
    """验证基本依赖库"""
    try:
        import requests
        import psutil
        import yaml
        print('✓ 基本模块导入成功')
        return True
    except ImportError as e:
        print(f'✗ 基本模块导入失败: {e}')
        return False

def verify_smb_dependency():
    """验证pysmb依赖库（非强制）"""
    try:
        import smb
        from smb.SMBConnection import SMBConnection
        print('✓ pysmb模块导入成功')
        return True
    except ImportError as e:
        print(f'! 警告: pysmb导入失败: {e}')
        print('继续构建过程...')
        return False

def main():
    """主函数"""
    print("验证Python依赖库导入情况：")
    basic_success = verify_basic_dependencies()
    
    print("\n尝试导入pysmb模块（非强制验证步骤）")
    smb_success = verify_smb_dependency()
    
    # 基本依赖必须成功，pysmb可选
    if not basic_success:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()