#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试Plex API的scan_library方法是否正常工作
"""

import os
import sys
import logging
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入必要的模块
from src.utils.config import Config
from src.utils.logger import setup_logger
from src.plex.api import PlexAPI

# 设置日志
s_logger = setup_logger(
    name='test_plex_scan',
    level=logging.DEBUG,
    log_file='test_plex_scan.log'
)
logger = logging.getLogger('test_plex_scan')


def test_plex_scan():
    """测试Plex API的scan_library方法"""
    logger.info("=== 开始测试Plex API扫描功能 ===")
    logger.info(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 加载配置
        config_path = '/data/config.env' if os.path.exists('/data/config.env') else 'config.env'
        logger.info(f"使用配置文件: {config_path}")
        config = Config(config_path)
        
        # 打印配置信息（隐藏敏感信息）
        logger.info(f"PLEX_URL: {config.get('PLEX_URL', '')}")
        plex_token = config.get('PLEX_TOKEN', '')
        masked_token = f"{plex_token[:3]}...{plex_token[-3:]}" if plex_token else ''
        logger.info(f"PLEX_TOKEN: {masked_token}")
        
        # 临时修改缓存目录为可写的临时目录
        import tempfile
        temp_cache_dir = tempfile.mkdtemp(prefix='plex_cache_')
        logger.info(f"使用临时缓存目录: {temp_cache_dir}")
        # 直接修改配置的内部字典（因为Config类没有set方法）
        config._config['CACHE_DIR'] = temp_cache_dir
        
        # 初始化Plex API
        logger.info("初始化Plex API客户端...")
        plex_api = PlexAPI(config)
        logger.info("Plex API客户端初始化成功")
        
        # 使用硬编码的媒体库ID和扫描路径（非交互式运行）
        library_id = '1'  # 假设媒体库ID为1，根据实际情况调整
        test_path = '/vol02/CloudDrive/WebDAV/电影/动画电影'  # 使用日志中看到的扫描路径
        
        logger.info(f"开始扫描媒体库 {library_id} 路径: {test_path}")
        start_time = datetime.now()
        
        result = plex_api.scan_library(library_id, test_path)
        
        elapsed_time = datetime.now() - start_time
        logger.info(f"扫描请求完成，结果: {result}，耗时: {elapsed_time.total_seconds():.2f}秒")
        
        if result:
            logger.info("✅ Plex扫描请求发送成功")
            print("✅ Plex扫描请求发送成功")
        else:
            logger.error("❌ Plex扫描请求发送失败")
            print("❌ Plex扫描请求发送失败")
            
    except Exception as e:
        logger.error(f"测试过程中发生异常: {str(e)}")
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("=== 测试完成 ===")


if __name__ == "__main__":
    test_plex_scan()