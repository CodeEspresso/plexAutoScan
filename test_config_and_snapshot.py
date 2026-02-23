#!/usr/bin/env python3
"""
测试配置文件读取和快照生成功能
"""
import sys
import os
import logging

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.config import Config
from src.utils.snapshot import SnapshotManager
from src.utils.logger import setup_logger

# 设置日志
setup_logger(name='test', level='INFO')
logger = logging.getLogger('test')


def test_config_reading():
    """测试配置文件读取功能"""
    logger.info("=== 开始测试配置文件读取 ===")
    
    # 初始化配置
    config = Config('/Volumes/PSSD/项目/plexAutoScan/config.env')
    
    # 测试基本配置项
    test_env = config.get_bool('TEST_ENV')
    logger.info(f"TEST_ENV: {test_env}")
    
    # 测试挂载路径
    mount_paths = config.get_mount_paths()
    logger.info(f"找到{len(mount_paths)}个挂载路径")
    for path in mount_paths:
        logger.info(f"  - {path}")
    
    # 检查Docker环境设置
    is_docker = config.get_bool('DOCKER_ENV')
    logger.info(f"DOCKER_ENV: {is_docker}")
    
    return mount_paths


def test_snapshot_generation(mount_paths):
    """测试快照生成功能"""
    logger.info("=== 开始测试快照生成 ===")
    
    if not mount_paths:
        logger.error("没有找到挂载路径，无法测试快照生成")
        return False
    
    # 初始化配置和快照管理器
    config = Config('/Volumes/PSSD/项目/plexAutoScan/config.env')
    snapshot_manager = SnapshotManager(config)
    
    # 选择第一个目录进行测试
    test_directory = mount_paths[0]
    logger.info(f"测试目录: {test_directory}")
    
    # 检查目录是否存在
    if not os.path.exists(test_directory):
        logger.warning(f"测试目录不存在: {test_directory}")
        # 选择一个存在的测试目录
        test_directory = '/Volumes/PSSD/项目/plexAutoScan'
        logger.info(f"使用备用测试目录: {test_directory}")
    
    # 生成快照
    try:
        snapshot_path, snapshot_content, success, added_files = snapshot_manager.generate_snapshot(test_directory)
        if success:
            logger.info(f"快照生成成功: {snapshot_path}")
            logger.info(f"新增文件数量: {len(added_files)}")
            return True
        else:
            logger.error("快照生成失败")
            return False
    except Exception as e:
        logger.error(f"快照生成时发生错误: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return False


def main():
    """主测试函数"""
    logger.info("=== 开始综合测试 ===")
    
    # 测试配置文件读取
    mount_paths = test_config_reading()
    
    # 测试快照生成
    snapshot_success = test_snapshot_generation(mount_paths)
    
    # 输出测试结果
    if mount_paths and snapshot_success:
        logger.info("=== 测试通过！所有功能正常工作 ===")
        return 0
    else:
        logger.error("=== 测试失败！某些功能不正常 ===")
        return 1


if __name__ == '__main__':
    sys.exit(main())