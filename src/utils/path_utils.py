#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径处理工具模块
"""

import os
import sys
import re
from pathlib import Path
import logging
from src.utils.config import Config

# 获取日志记录器
logger = logging.getLogger(__name__)


class PathUtils:
    """路径处理工具类"""
    
    @staticmethod
    def normalize_path(path):
        """规范化路径格式，处理不同操作系统的路径差异
        
        Args:
            path (str): 要规范化的路径
            
        Returns:
            str: 规范化后的路径
        """
        if not path:
            return ''
        
        try:
            # 确保路径是字符串类型
            if not isinstance(path, str):
                path = str(path)
            
            # 清理可能的引号
            cleaned_path = path.strip('"').strip("'")
            
            # 规范化路径
            norm_path = os.path.normpath(cleaned_path)
            
            # 处理Windows路径
            if sys.platform == 'win32':
                # 确保路径分隔符正确
                norm_path = norm_path.replace('/', '\\')
            else:
                # 确保路径分隔符正确
                norm_path = norm_path.replace('\\', '/')
            
            # 移除尾部斜杠（除了根目录）
            if len(norm_path) > 1 and norm_path.endswith(('\\', '/')):
                norm_path = norm_path[:-1]
            
            return norm_path
        except Exception as e:
            logger.error(f"规范化路径失败 {path}: {str(e)}")
            return path
    
    @staticmethod
    def is_excluded(path, exclude_list):
        """检查路径是否在排除列表中
        
        Args:
            path (str): 要检查的路径
            exclude_list (list): 排除路径列表
            
        Returns:
            bool: 如果路径在排除列表中，返回True，否则返回False
        """
        if not path or not exclude_list:
            return False
        
        try:
            normalized_path = PathUtils.normalize_path(path)
            
            for exclude in exclude_list:
                normalized_exclude = PathUtils.normalize_path(exclude)
                
                # 检查路径是否完全匹配排除项
                if normalized_path == normalized_exclude:
                    return True
                
                # 检查路径是否是排除项的子目录
                # 确保路径分隔符一致
                if sys.platform == 'win32':
                    if normalized_path.startswith(normalized_exclude + '\\'):
                        return True
                else:
                    if normalized_path.startswith(normalized_exclude + '/'):
                        return True
            
            return False
        except Exception as e:
            logger.error(f"检查排除路径失败 {path}: {str(e)}")
            return False
    
    @staticmethod
    def verify_path(path, test_env=False):
        """验证路径是否可访问
        
        Args:
            path (str): 要验证的路径
            test_env (bool): 是否为测试环境
            
        Returns:
            tuple: (验证后的路径, 是否有效)
        """
        if not path:
            return 'ERROR:EMPTY_PATH', False
        
        # 从utils.timeout_decorator导入超时控制函数
        from .timeout_decorator import run_with_timeout
        
        # 定义核心验证逻辑函数
        def _verify_path_core():
            nonlocal path  # 声明使用外部函数的path变量
            try:
                # 处理编码问题，确保中文路径能正确处理
                if isinstance(path, bytes):
                    path = path.decode('utf-8', errors='replace')
                
                # 清理路径
                cleaned_path = path.strip('"').strip("'")
                if not cleaned_path or cleaned_path == ' ':
                    return 'ERROR:EMPTY_PATH', False
                
                # 规范化路径
                verified_path = PathUtils.normalize_path(cleaned_path)
                
                # 检查Docker环境
                is_docker = PathUtils.is_docker_environment()
                
                # 设置超时时间
                check_timeout = 30  # 默认30秒
                if is_docker:
                    check_timeout = 20  # Docker环境下20秒
                
                # 路径存在性检查（带超时）
                def _check_path_exists(check_path):
                    return os.path.exists(check_path)
                
                # Docker环境: 仍然检查路径存在性，因为挂载可能失败
                if is_docker:
                    path_exists = run_with_timeout(
                        _check_path_exists,
                        verified_path,
                        timeout_seconds=check_timeout,
                        default=False,
                        error_message=f"Docker环境下检查路径存在性超时: {verified_path}"
                    )
                    
                    if path_exists:
                        return verified_path, True
                    else:
                        # 尝试使用路径的原始形式，可能包含中文
                        logger.debug(f"Docker环境中路径验证失败，尝试使用原始路径: {cleaned_path}")
                        original_path_exists = run_with_timeout(
                            _check_path_exists,
                            cleaned_path,
                            timeout_seconds=check_timeout,
                            default=False,
                            error_message=f"Docker环境下检查原始路径存在性超时: {cleaned_path}"
                        )
                        
                        if original_path_exists:
                            return cleaned_path, True
                        else:
                            logger.warning(f"路径不存在: {verified_path}")
                            return verified_path, False
                elif not test_env:
                    # 生产环境(非Docker): 严格检查路径存在性
                    path_exists = run_with_timeout(
                        _check_path_exists,
                        verified_path,
                        timeout_seconds=check_timeout,
                        default=False,
                        error_message=f"检查路径存在性超时: {verified_path}"
                    )
                    
                    if not path_exists:
                        logger.warning(f"路径不存在: {verified_path}")
                        return verified_path, False
                    
                    # 权限检查
                    try:
                        if not os.access(verified_path, os.R_OK):
                            logger.warning(f"没有读取权限: {verified_path}")
                            return verified_path, False
                        elif os.path.isdir(verified_path) and not os.access(verified_path, os.X_OK):
                            logger.warning(f"没有执行权限: {verified_path}")
                            return verified_path, False
                    except Exception as e:
                        logger.error(f"检查路径权限时出错: {str(e)}")
                        return verified_path, False
                    
                    # 直接使用传入的test_env参数来确定路径范围验证逻辑
                    if test_env:
                        # 测试环境: 直接返回True
                        logger.debug("测试环境，跳过路径范围验证")
                        return verified_path, True
                    else:
                        # 生产环境: 严格检查路径是否在有效的生产路径列表中
                        # 获取MOUNT_PATHS配置
                        # 优先检查是否在Docker环境中，即使TEST_ENV=1
                        is_production = PathUtils.is_docker_environment() or (not test_env)
                        
                        # 从环境变量读取配置文件路径
                        config_path = os.environ.get('CONFIG_PATH', '/data/config.env')
                        # Config类会自动从多个位置加载配置文件
                        config = Config(config_path)
                        mount_paths_str = config.get('MOUNT_PATHS', '')
                        
                        # 如果在生产环境，确保使用正确的MOUNT_PATHS
                        if is_production and not mount_paths_str:
                            # 在Docker环境中，如果没有配置MOUNT_PATHS，使用默认路径
                            if PathUtils.is_docker_environment():
                                mount_paths_str = os.environ.get('PROD_BASE_PATH', '/vol02/CloudDrive/WebDAV')
                            logger.warning(f"未配置有效的生产挂载路径，使用默认值: {mount_paths_str}")
                        # 如果仍然没有有效的挂载路径，使用一个安全的默认行为
                        if not mount_paths_str:
                            logger.error("未找到有效的挂载路径配置，将严格验证路径")
                            # 返回False，因为没有有效的挂载路径来验证
                            return verified_path, False
                        
                        # 解析MOUNT_PATHS配置
                        paths = []
                        for separator in [',', ';', '\n', ' ']:
                            if separator in mount_paths_str:
                                paths = mount_paths_str.split(separator)
                                break
                        
                        # 如果没有找到分隔符，整个字符串作为一个路径
                        if not paths:
                            paths = [mount_paths_str]
                        
                        # 清理并过滤空路径
                        mount_paths = [path.strip() for path in paths if path.strip()]
                        
                        if not mount_paths:
                            logger.warning("解析后的生产挂载路径列表为空")
                            return verified_path, True
                        
                        # 检查路径是否在有效的生产挂载路径列表中
                        is_valid = False
                        for mount_path in mount_paths:
                            mount_path_normalized = PathUtils.normalize_path(mount_path)
                            if sys.platform == 'win32':
                                if verified_path.startswith(mount_path_normalized + '\\') or verified_path == mount_path_normalized:
                                    is_valid = True
                                    break
                            else:
                                if verified_path.startswith(mount_path_normalized + '/') or verified_path == mount_path_normalized:
                                    is_valid = True
                                    break
                        
                        if not is_valid:
                            logger.warning(f"路径不在有效的生产挂载路径范围内: {verified_path}")
                            return verified_path, False
                        
                        return verified_path, True
                else:
                    # 测试环境: 不严格检查路径存在性，但确保路径不为空
                    return verified_path, True
            except Exception as e:
                logger.error(f"验证路径失败 {path}: {str(e)}")
                return path, False
        
        # 直接运行核心路径验证逻辑
        result = _verify_path_core()
        
        return result
    
    @staticmethod
    def is_docker_environment():
        """检测是否在Docker环境中运行
        
        Returns:
            bool: 是否在Docker环境中
        """
        # 方法1: 检查环境变量
        if os.environ.get('DOCKER_ENV') == '1':
            return True
        # 方法2: 检查Docker特有的文件
        if os.path.exists('/.dockerenv'):
            return True
        # 方法3: 检查cgroup信息
        try:
            with open('/proc/1/cgroup', 'r') as f:
                if 'docker' in f.read():
                    return True
        except Exception:
            pass
        return False
    
    @staticmethod
    def get_file_encoding(file_path, default_encoding='utf-8'):
        """尝试检测文件编码
        
        Args:
            file_path (str): 文件路径
            default_encoding (str): 默认编码
            
        Returns:
            str: 检测到的编码或默认编码
        """
        try:
            # 简单的编码检测逻辑
            encodings = ['utf-8', 'gbk', 'latin-1']
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        # 尝试读取前几行
                        for _ in range(5):
                            f.readline()
                    return encoding
                except UnicodeDecodeError:
                    continue
        except Exception as e:
            logger.error(f"检测文件编码失败 {file_path}: {str(e)}")
        
        return default_encoding
    
    @staticmethod
    def ensure_directory(directory):
        """确保目录存在
        
        Args:
            directory (str): 目录路径
            
        Returns:
            bool: 是否成功
        """
        try:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"创建目录失败 {directory}: {str(e)}")
            return False
    
    @staticmethod
    def get_relative_path(path, base_path):
        """获取相对路径
        
        Args:
            path (str): 目标路径
            base_path (str): 基础路径
            
        Returns:
            str: 相对路径或原路径（如果无法计算）
        """
        try:
            # 规范化路径
            norm_path = PathUtils.normalize_path(path)
            norm_base = PathUtils.normalize_path(base_path)
            
            # 计算相对路径
            relative_path = os.path.relpath(norm_path, norm_base)
            
            # 确保路径分隔符一致
            if sys.platform == 'win32':
                relative_path = relative_path.replace('/', '\\')
            else:
                relative_path = relative_path.replace('\\', '/')
            
            return relative_path
        except Exception as e:
            logger.error(f"计算相对路径失败 {path} -> {base_path}: {str(e)}")
            return path
    
    @staticmethod
    def sanitize_filename(filename, replacement='_'):
        """清理文件名中的非法字符
        
        Args:
            filename (str): 文件名
            replacement (str): 替换字符
            
        Returns:
            str: 清理后的文件名
        """
        if not filename:
            return ''
        
        try:
            # 移除或替换非法字符
            if sys.platform == 'win32':
                # Windows非法字符
                illegal_chars = '"*:<>?|\\/'
                for char in illegal_chars:
                    filename = filename.replace(char, replacement)
            else:
                # Unix/Linux非法字符
                filename = re.sub(r'[/\\]', replacement, filename)
            
            # 移除控制字符
            filename = ''.join(c for c in filename if ord(c) >= 32)
            
            # 移除多余的替换字符
            filename = re.sub(rf'{re.escape(replacement)}+', replacement, filename)
            
            # 移除首尾的替换字符
            filename = filename.strip(replacement)
            
            # 确保文件名不为空
            if not filename:
                filename = 'unnamed'
            
            return filename
        except Exception as e:
            logger.error(f"清理文件名失败 {filename}: {str(e)}")
            return filename

# 导出常用函数
def normalize_path(path):
    return PathUtils.normalize_path(path)

def is_excluded(path, exclude_list):
    return PathUtils.is_excluded(path, exclude_list)

def verify_path(path, test_env=False):
    return PathUtils.verify_path(path, test_env)

def is_docker_environment():
    return PathUtils.is_docker_environment()

def get_file_encoding(file_path, default_encoding='utf-8'):
    return PathUtils.get_file_encoding(file_path, default_encoding)

def ensure_directory(directory):
    return PathUtils.ensure_directory(directory)

def get_relative_path(path, base_path):
    return PathUtils.get_relative_path(path, base_path)

def sanitize_filename(filename, replacement='_'):
    return PathUtils.sanitize_filename(filename, replacement)