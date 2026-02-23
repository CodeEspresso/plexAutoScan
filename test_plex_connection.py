#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Plex API连接和媒体库匹配功能
"""

import os
import sys
import logging

# 导入必要的模块
# 删除: 添加到Python路径的代码，这会干扰正常的包导入
# 改为: 使用相对导入方式
from src.utils.config import Config
from src.plex.api import PlexAPI
from src.plex.library import PlexLibraryManager
from src.main import PlexAutoScan

# 设置控制台输出
print("=== 测试Plex连接和媒体库匹配功能 ===")
print(f"当前工作目录: {os.getcwd()}")

# 直接使用print函数进行调试，避免日志配置问题


def test_plex_connection():
    """测试Plex API连接和媒体库获取"""
    print("=== 开始测试Plex API连接 ===")
    
    try:
        # 初始化配置
        config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.env')
        print(f"配置文件路径: {config_file}")
        print(f"配置文件是否存在: {os.path.exists(config_file)}")
        config = Config(config_file)
        print(f"使用配置文件: {config_file}")
        print(f"Plex URL: {config.get('PLEX_URL')}")
        print(f"Plex Token: {'已设置' if config.get('PLEX_TOKEN') else '未设置'}")
        print(f"MOUNT_PATHS: {config.get('MOUNT_PATHS')}")
        
        # 初始化Plex API
        try:
            plex_api = PlexAPI(config)
            print("Plex API初始化成功")
        except Exception as e:
            print(f"Plex API初始化失败: {str(e)}")
            return False
        
        # 测试获取媒体库
        print("尝试获取媒体库列表...")
        libraries = plex_api.get_plex_media_libraries()
        
        if not libraries:
            print("未获取到任何媒体库")
            # 尝试直接调用API查看原始响应
            print("尝试直接调用API查看原始响应...")
            raw_response = plex_api._make_request('/library/sections')
            print(f"原始API响应: {raw_response}")
            return False
        
        print(f"成功获取到{len(libraries)}个媒体库")
        for lib in libraries:
            print(f"媒体库: {lib['name']} (ID: {lib['id']}, 类型: {lib['type']}, 路径: {lib.get('path', '未设置')})")
        
        # 测试媒体库管理器
        library_manager = PlexLibraryManager(config)
        print(f"媒体库管理器已加载{len(library_manager.libraries)}个媒体库")
        
        # 测试路径匹配
        test_paths = config.get('MOUNT_PATHS', [])
        if isinstance(test_paths, str):
            test_paths = test_paths.split()
        
        if test_paths:
            print(f"测试路径匹配，共{len(test_paths)}个路径")
            for path in test_paths[:3]:  # 只测试前3个路径以节省时间
                print(f"测试路径: {path}")
                # 打印路径规范化信息
                normalized_path = path.replace('\\', '/')
                print(f"  规范化路径: {normalized_path}")
                
                matched_library = library_manager.find_deepest_matching_library(path)
                if matched_library:
                    print(f"  匹配成功: {matched_library['name']} (ID: {matched_library['id']})")
                    print(f"  匹配分数: {matched_library.get('match_score')}")
                    print(f"  相对路径: {matched_library.get('relative_path')}")
                else:
                    print(f"  未找到匹配的媒体库")
        
        # 添加更具体的测试用例 - 针对特定的动画电影目录
        print(f"\n=== 特定目录匹配测试 ===")
        
        # 测试具体的动画电影目录
        specific_test_paths = [
            '/vol02/CloudDrive/WebDAV/电影/动画电影/国产动画',
            '/vol02/CloudDrive/WebDAV/电影/动画电影/日韩动画',
            '/vol02/CloudDrive/WebDAV/电影/动画电影/欧美动画'
        ]
        
        for test_path in specific_test_paths:
            print(f"\n测试特定路径: {test_path}")
            normalized_path = test_path.replace('\\', '/')
            print(f"  规范化路径: {normalized_path}")
            
            matched_library = library_manager.find_deepest_matching_library(test_path)
            if matched_library:
                print(f"  匹配成功: {matched_library['name']} (ID: {matched_library['id']})")
                print(f"  匹配分数: {matched_library.get('match_score')}")
                print(f"  相对路径: {matched_library.get('relative_path')}")
                if 'match_type' in matched_library:
                    print(f"  匹配类型: {matched_library.get('match_type', 'path_based')}")
            else:
                print(f"  未找到匹配的媒体库")
        
        print("=== Plex API连接测试完成 ===")
        return True
    
    except Exception as e:
        print(f"测试过程中发生错误: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

def test_import_order():
    """检查Python模块导入顺序"""
    print("=== 检查导入顺序 ===")
    
    # 打印当前已导入的模块
    print(f"已导入的src相关模块: {[m for m in sys.modules if m.startswith('src.')]}")
    
    # 尝试重新导入main模块
    try:
        if 'src.main' in sys.modules:
            print("src.main模块已经在sys.modules中")
            del sys.modules['src.main']
            print("已删除src.main模块，准备重新导入")
        
        from src.main import PlexAutoScan
        print("src.main模块重新导入成功")
        return True
    except Exception as e:
        print(f"重新导入src.main模块失败: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False


if __name__ == '__main__':
    print("启动Plex连接测试脚本")
    
    # 测试Plex连接
    plex_result = test_plex_connection()
    
    # 测试导入顺序
    import_result = test_import_order()
    
    print(f"测试结果: Plex连接={'成功' if plex_result else '失败'}, 导入顺序={'正常' if import_result else '异常'}")