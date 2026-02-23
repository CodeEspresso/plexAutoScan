#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境检测模块 - 统一的环境检测工具
"""

import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class EnvironmentDetector:
    """环境检测器类，提供统一的环境检测接口"""
    
    _instance: Optional['EnvironmentDetector'] = None
    _cache: Dict[str, Any] = {}
    
    def __new__(cls):
        """单例模式，确保只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化环境检测器"""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._cache = {}
            logger.debug("EnvironmentDetector 初始化完成")
    
    def is_docker(self) -> bool:
        """检测是否在 Docker 环境中运行
        
        Returns:
            bool: 是否在 Docker 环境中
        """
        cache_key = 'is_docker'
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 方法1: 检查环境变量
        if os.environ.get('DOCKER_ENV') == '1':
            self._cache[cache_key] = True
            return True
        
        # 方法2: 检查 Docker 特有的文件
        if os.path.exists('/.dockerenv'):
            self._cache[cache_key] = True
            return True
        
        # 方法3: 检查 cgroup 信息
        try:
            with open('/proc/1/cgroup', 'r') as f:
                if 'docker' in f.read():
                    self._cache[cache_key] = True
                    return True
        except Exception:
            pass
        
        self._cache[cache_key] = False
        return False
    
    def is_test_env(self) -> bool:
        """检测是否为测试环境
        
        Returns:
            bool: 是否为测试环境
        """
        cache_key = 'is_test_env'
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 检查环境变量
        result = os.environ.get('TEST_ENV', '0') in ('1', 'true', 'yes', 'True', 'Yes')
        self._cache[cache_key] = result
        return result
    
    def is_debug_mode(self) -> bool:
        """检测是否为调试模式
        
        Returns:
            bool: 是否为调试模式
        """
        cache_key = 'is_debug_mode'
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 检查环境变量
        result = os.environ.get('DEBUG', '0') in ('1', 'true', 'yes', 'True', 'Yes')
        self._cache[cache_key] = result
        return result
    
    def get_platform(self) -> str:
        """获取当前平台信息
        
        Returns:
            str: 平台名称 (linux, darwin, win32)
        """
        cache_key = 'platform'
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        import sys
        self._cache[cache_key] = sys.platform
        return sys.platform
    
    def is_linux(self) -> bool:
        """检测是否为 Linux 系统
        
        Returns:
            bool: 是否为 Linux 系统
        """
        return self.get_platform() == 'linux'
    
    def is_macos(self) -> bool:
        """检测是否为 macOS 系统
        
        Returns:
            bool: 是否为 macOS 系统
        """
        return self.get_platform() == 'darwin'
    
    def is_windows(self) -> bool:
        """检测是否为 Windows 系统
        
        Returns:
            bool: 是否为 Windows 系统
        """
        return self.get_platform() == 'win32'
    
    def get_python_version(self) -> tuple:
        """获取 Python 版本
        
        Returns:
            tuple: (major, minor, micro) 版本号
        """
        import sys
        return (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    
    def is_python_version_at_least(self, min_version: tuple) -> bool:
        """检查 Python 版本是否满足要求
        
        Args:
            min_version (tuple): 最低要求版本 (major, minor, micro)
            
        Returns:
            bool: 当前版本是否满足要求
        """
        return self.get_python_version() >= min_version
    
    def get_timeout_multiplier(self) -> float:
        """根据环境获取超时时间倍数
        
        Returns:
            float: 超时时间倍数（Docker 环境下可能需要调整）
        """
        # Docker 环境下可能需要更短的超时时间
        return 0.5 if self.is_docker() else 1.0
    
    def get_environment_info(self) -> Dict[str, Any]:
        """获取完整的环境信息
        
        Returns:
            dict: 环境信息字典
        """
        return {
            'is_docker': self.is_docker(),
            'is_test_env': self.is_test_env(),
            'is_debug_mode': self.is_debug_mode(),
            'platform': self.get_platform(),
            'python_version': self.get_python_version(),
            'timeout_multiplier': self.get_timeout_multiplier()
        }
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        logger.debug("EnvironmentDetector 缓存已清除")


# 创建全局实例
env_detector = EnvironmentDetector()


# 便捷函数
def is_docker() -> bool:
    """便捷函数：检测是否在 Docker 环境中"""
    return env_detector.is_docker()


def is_test_env() -> bool:
    """便捷函数：检测是否为测试环境"""
    return env_detector.is_test_env()


def is_debug_mode() -> bool:
    """便捷函数：检测是否为调试模式"""
    return env_detector.is_debug_mode()


def get_platform() -> str:
    """便捷函数：获取当前平台信息"""
    return env_detector.get_platform()


def get_environment_info() -> Dict[str, Any]:
    """便捷函数：获取完整的环境信息"""
    return env_detector.get_environment_info()
