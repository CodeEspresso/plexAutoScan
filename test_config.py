#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置验证脚本
用于测试Config类的路径处理逻辑是否正确
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入Config类
from src.utils.config import Config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ConfigTest')


def test_config():
    """测试Config类的配置加载和路径处理逻辑"""
    logger.info("开始配置测试...")
    
    # 创建Config实例
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'config.env')
    config = Config(config_file, logger)
    
    # 打印环境信息
    logger.info("当前环境信息:")
    logger.info(f"  TEST_ENV (配置值): {config.get('TEST_ENV')}")
    logger.info(f"  TEST_ENV (布尔值): {config.is_test_env}")
    logger.info(f"  DOCKER_ENV (配置值): {config.get('DOCKER_ENV')}")
    logger.info(f"  DOCKER_ENV (布尔值): {config.is_docker}")
    logger.info(f"  PATH_PREFIX: {config.get('PATH_PREFIX')}")
    logger.info(f"  MOUNT_PATHS: {config.get('MOUNT_PATHS')}")
    logger.info(f"  PROD_BASE_PATH: {config.get('PROD_BASE_PATH')}")
    logger.info(f"  TEST_BASE_PATH: {config.get('TEST_BASE_PATH')}")
    
    # 获取并打印挂载路径
    logger.info("\n获取挂载路径列表...")
    mount_paths = config.get_mount_paths()
    logger.info(f"  挂载路径数量: {len(mount_paths)}")
    for i, path in enumerate(mount_paths, 1):
        logger.info(f"  {i}. {path}")
        # 检查路径是否存在
        if os.path.exists(path):
            logger.info(f"    ✓ 路径存在: {path}")
        else:
            logger.warning(f"    ✗ 路径不存在: {path}")
    
    # 验证配置
    logger.info("\n验证配置...")
    validation_result = config.validate()
    logger.info(f"  配置验证结果: {'通过' if validation_result else '失败'}")
    
    # 检查环境变量TEST_ENV是否正确设置
    logger.info("\n检查环境变量TEST_ENV...")
    env_test_env = os.environ.get('TEST_ENV', '未设置')
    logger.info(f"  环境变量TEST_ENV: {env_test_env}")
    
    logger.info("\n配置测试完成！")


if __name__ == '__main__':
    test_config()