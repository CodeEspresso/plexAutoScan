#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import time
import logging
from .smb_api import SMBManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class SMBAPITester:
    def __init__(self):
        self.smb_manager = SMBManager()
        self.success_count = 0
        self.fail_count = 0
    
    def print_separator(self):
        print("=" * 60)
    
    def test_path_exists(self, path):
        """测试路径是否存在"""
        self.print_separator()
        logger.info(f"测试路径存在性: {path}")
        try:
            result = self.smb_manager.path_exists(path)
            if result:
                logger.info(f"成功: 路径 '{path}' 存在")
                self.success_count += 1
            else:
                logger.warning(f"警告: 路径 '{path}' 不存在")
        except Exception as e:
            logger.error(f"失败: 检查路径 '{path}' 时出错: {str(e)}")
            self.fail_count += 1
    
    def test_get_file_info(self, path):
        """测试获取文件信息"""
        self.print_separator()
        logger.info(f"测试获取文件信息: {path}")
        try:
            info = self.smb_manager.get_file_info(path)
            if info:
                logger.info(f"成功: 获取到文件信息: {info}")
                self.success_count += 1
            else:
                logger.warning(f"警告: 无法获取文件信息: {path}")
        except Exception as e:
            logger.error(f"失败: 获取文件信息时出错: {str(e)}")
            self.fail_count += 1
    
    def test_list_files(self, path):
        """测试列出文件"""
        self.print_separator()
        logger.info(f"测试列出目录文件: {path}")
        try:
            files = self.smb_manager.list_files(path)
            if files:
                logger.info(f"成功: 找到 {len(files)} 个文件和目录")
                logger.info(f"前5个项目: {files[:5]}")
                self.success_count += 1
            else:
                logger.warning(f"警告: 目录为空或无法访问: {path}")
        except Exception as e:
            logger.error(f"失败: 列出文件时出错: {str(e)}")
            self.fail_count += 1
    
    def test_keep_connection_alive(self, path, duration=10):
        """测试保持连接活跃"""
        self.print_separator()
        logger.info(f"测试保持SMB连接活跃: {path} (持续 {duration} 秒)")
        try:
            thread = self.smb_manager.keep_connection_alive(path, interval=2)
            logger.info("连接保持线程已启动")
            
            # 等待一段时间以测试连接保持
            for i in range(duration):
                time.sleep(1)
                if i % 3 == 0:
                    logger.info(f"连接保持中... {i+1}/{duration} 秒")
            
            # 不需要显式停止线程，因为它是守护线程
            logger.info("连接保持测试完成")
            self.success_count += 1
        except Exception as e:
            logger.error(f"失败: 保持连接活跃时出错: {str(e)}")
            self.fail_count += 1
    
    def run_all_tests(self, test_path):
        """运行所有测试"""
        logger.info("开始SMB API集成测试")
        
        # 测试路径存在性
        self.test_path_exists(test_path)
        
        # 测试获取文件信息
        if os.path.isfile(test_path):
            self.test_get_file_info(test_path)
        
        # 测试列出文件（如果是目录）
        if os.path.isdir(test_path):
            self.test_list_files(test_path)
            
            # 找一个文件进行信息测试
            try:
                test_file = None
                for root, dirs, files in os.walk(test_path):
                    if files:
                        test_file = os.path.join(root, files[0])
                        break
                if test_file:
                    self.test_get_file_info(test_file)
            except Exception as e:
                logger.error(f"无法找到测试文件: {str(e)}")
        
        # 测试保持连接活跃
        self.test_keep_connection_alive(test_path)
        
        # 输出测试结果摘要
        self.print_separator()
        logger.info("SMB API集成测试完成")
        logger.info(f"成功: {self.success_count} 项")
        logger.info(f"失败: {self.fail_count} 项")
        
        if self.fail_count == 0:
            logger.info("测试结果: 通过")
        else:
            logger.warning("测试结果: 部分失败，请检查错误信息")

if __name__ == "__main__":
    # 检查参数
    if len(sys.argv) < 2:
        logger.error("用法: python test_smb_api.py <测试路径>")
        logger.error("例如: python test_smb_api.py /path/to/smb/directory")
        sys.exit(1)
    
    test_path = sys.argv[1]
    
    # 检查测试路径是否有效
    if not os.path.exists(test_path):
        logger.error(f"错误: 测试路径 '{test_path}' 不存在")
        sys.exit(1)
    
    # 创建测试器并运行测试
    tester = SMBAPITester()
    tester.run_all_tests(test_path)
    
    # 根据测试结果设置退出码
    sys.exit(0 if tester.fail_count == 0 else 1)