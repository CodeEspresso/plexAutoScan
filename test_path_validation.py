#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试路径验证逻辑的脚本
"""

import os
import sys
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_path_validation')

# 正确添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入需要的模块 - 修复导入路径和日志格式化语法
try:
    from src.utils.config import Config
    from src.utils.path_utils import verify_path
    from src.utils.snapshot import SnapshotManager
    logger.info("成功导入所有必要模块")
except ImportError as e:
    logger.error(f"导入模块失败: {str(e)}")
    logger.info(f"当前Python路径: {sys.path}")
    logger.info(f"当前工作目录: {os.getcwd()}")
    raise

def test_path_validation():
    """测试路径验证逻辑"""
    # 加载配置
    config = Config('/data/config.env')
    
    # 即使配置文件中TEST_ENV=1，我们也强制使用生产环境验证模式
    is_test_env = False  # 强制设置为生产环境
    logger.info(f"强制设置为生产环境模式: is_test_env={is_test_env}")
    
    # 测试有效的生产环境路径
    valid_prod_path = '/vol02/CloudDrive/WebDAV'
    verified_path, is_valid = verify_path(valid_prod_path, is_test_env)
    logger.info(f"验证有效生产路径 {valid_prod_path}: 结果={is_valid}, 验证后路径={verified_path}")
    
    # 测试无效的测试环境路径
    invalid_test_path = '/Volumes/PSSD/项目/plexAutoScan/test_files/电影'
    verified_path, is_valid = verify_path(invalid_test_path, is_test_env)
    logger.info(f"验证无效测试路径 {invalid_test_path}: 结果={is_valid}, 验证后路径={verified_path}")
    
    # 测试SnapshotManager
    snapshot_manager = SnapshotManager(config)
    logger.info("测试SnapshotManager.generate_snapshot方法...")
    
    # 尝试使用有效路径生成快照
    if is_valid:
        snapshot_path, snapshot_content, is_success = snapshot_manager.generate_snapshot(
            valid_prod_path, 
            test_env=is_test_env
        )
        logger.info(f"生成有效路径快照结果: {is_success}")
        if is_success:
            logger.info(f"快照文件路径: {snapshot_path}")
            logger.info(f"快照文件数量: {len(snapshot_content.get('files', []))}")
    
    # 尝试使用无效路径生成快照
    snapshot_path, snapshot_content, is_success = snapshot_manager.generate_snapshot(
        invalid_test_path, 
        test_env=is_test_env
    )
    logger.info(f"生成无效路径快照结果: {is_success}")
    
    logger.info("路径验证测试完成")


if __name__ == '__main__':
    test_path_validation()