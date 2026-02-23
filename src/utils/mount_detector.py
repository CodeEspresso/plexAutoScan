#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
挂载类型管理模块

变更理由：支持多种挂载方式（WebDAV、NFS、SMB），不同挂载类型有不同的特性和权限处理方式。
"""

import os
import re
import logging
from enum import Enum
from typing import Optional, Dict, List, Tuple
from .environment import env_detector

logger = logging.getLogger(__name__)


class MountType(Enum):
    """挂载类型枚举"""
    WEBDAV = "webdav"
    NFS = "nfs"
    SMB = "smb"
    LOCAL = "local"
    UNKNOWN = "unknown"


class MountInfo:
    """挂载信息类"""
    
    def __init__(self, mount_type: MountType, mount_point: str, source: str = "", 
                 options: Dict[str, str] = None):
        """
        初始化挂载信息
        
        Args:
            mount_type: 挂载类型
            mount_point: 挂载点路径
            source: 挂载源（如服务器地址）
            options: 挂载选项
        """
        self.mount_type = mount_type
        self.mount_point = mount_point
        self.source = source
        self.options = options or {}
    
    def __repr__(self):
        return f"MountInfo(type={self.mount_type.value}, point={self.mount_point}, source={self.source})"


class MountDetector:
    """挂载类型检测器"""
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化挂载检测器"""
        if self._initialized:
            return
        
        self._initialized = True
        self._mount_cache: Dict[str, MountInfo] = {}
        self._mounts_loaded = False
        self.logger = logging.getLogger(__name__)
        
        # 飞牛OS特定的挂载路径前缀
        self.feiniu_webdav_prefixes = [
            '/vol02/CloudDrive/WebDAV',
            '/vol01/CloudDrive/WebDAV',
        ]
        
        # 常见的NFS挂载路径前缀
        self.nfs_prefixes = [
            '/mnt/nfs',
            '/vol',
            '/media/nfs',
        ]
        
        # 常见的SMB挂载路径前缀
        self.smb_prefixes = [
            '/mnt/smb',
            '/media/smb',
            '/vol',
        ]
    
    def detect_mount_type(self, path: str) -> MountType:
        """
        检测路径的挂载类型
        
        Args:
            path: 要检测的路径
            
        Returns:
            MountType: 挂载类型
        """
        # 首先检查缓存
        if path in self._mount_cache:
            return self._mount_cache[path].mount_type
        
        # 尝试从/proc/mounts检测
        mount_info = self._detect_from_proc_mounts(path)
        if mount_info:
            self._mount_cache[path] = mount_info
            return mount_info.mount_type
        
        # 尝试从路径特征检测
        mount_type = self._detect_from_path_pattern(path)
        
        # 缓存结果
        self._mount_cache[path] = MountInfo(
            mount_type=mount_type,
            mount_point=path
        )
        
        return mount_type
    
    def _detect_from_proc_mounts(self, path: str) -> Optional[MountInfo]:
        """
        从/proc/mounts检测挂载类型
        
        Args:
            path: 要检测的路径
            
        Returns:
            MountInfo: 挂载信息，如果检测失败返回None
        """
        try:
            if not os.path.exists('/proc/mounts'):
                return None
            
            with open('/proc/mounts', 'r') as f:
                mounts = f.readlines()
            
            # 查找最匹配的挂载点
            best_match = None
            best_match_len = 0
            
            for mount_line in mounts:
                parts = mount_line.split()
                if len(parts) < 3:
                    continue
                
                source, mount_point, fs_type = parts[0], parts[1], parts[2]
                
                # 检查路径是否在挂载点下
                if path.startswith(mount_point):
                    match_len = len(mount_point)
                    if match_len > best_match_len:
                        best_match_len = match_len
                        best_match = (source, mount_point, fs_type)
            
            if best_match:
                source, mount_point, fs_type = best_match
                
                # 根据文件系统类型判断挂载类型
                mount_type = MountType.UNKNOWN
                
                if fs_type.lower() in ['nfs', 'nfs4']:
                    mount_type = MountType.NFS
                elif fs_type.lower() in ['cifs', 'smb', 'smb2', 'smb3']:
                    mount_type = MountType.SMB
                elif 'webdav' in source.lower() or 'webdav' in mount_point.lower():
                    mount_type = MountType.WEBDAV
                elif fs_type.lower() in ['fuse', 'fuse.webdav']:
                    mount_type = MountType.WEBDAV
                elif fs_type.lower() in ['ext4', 'xfs', 'btrfs', 'zfs']:
                    mount_type = MountType.LOCAL
                
                return MountInfo(
                    mount_type=mount_type,
                    mount_point=mount_point,
                    source=source,
                    options={'fs_type': fs_type}
                )
        
        except Exception as e:
            self.logger.debug(f"从/proc/mounts检测挂载类型失败: {str(e)}")
        
        return None
    
    def _detect_from_path_pattern(self, path: str) -> MountType:
        """
        从路径特征检测挂载类型
        
        Args:
            path: 要检测的路径
            
        Returns:
            MountType: 挂载类型
        """
        path_lower = path.lower()
        
        # 检查飞牛OS WebDAV路径
        for prefix in self.feiniu_webdav_prefixes:
            if path.startswith(prefix):
                self.logger.debug(f"检测到飞牛OS WebDAV路径: {path}")
                return MountType.WEBDAV
        
        # 检查NFS路径
        for prefix in self.nfs_prefixes:
            if path.startswith(prefix):
                self.logger.debug(f"检测到NFS路径: {path}")
                return MountType.NFS
        
        # 检查SMB路径
        for prefix in self.smb_prefixes:
            if path.startswith(prefix):
                self.logger.debug(f"检测到SMB路径: {path}")
                return MountType.SMB
        
        # 检查路径中的关键字
        if 'webdav' in path_lower:
            return MountType.WEBDAV
        if 'nfs' in path_lower:
            return MountType.NFS
        if 'smb' in path_lower or 'cifs' in path_lower:
            return MountType.SMB
        
        # 默认为本地路径
        return MountType.LOCAL
    
    def get_mount_info(self, path: str) -> MountInfo:
        """
        获取路径的挂载信息
        
        Args:
            path: 要检测的路径
            
        Returns:
            MountInfo: 挂载信息
        """
        if path not in self._mount_cache:
            self.detect_mount_type(path)
        
        return self._mount_cache.get(path, MountInfo(MountType.UNKNOWN, path))
    
    def clear_cache(self):
        """清除挂载信息缓存"""
        self._mount_cache.clear()
        self._mounts_loaded = False


class MountConfigManager:
    """挂载配置管理器"""
    
    def __init__(self):
        """初始化挂载配置管理器"""
        self.logger = logging.getLogger(__name__)
        self.detector = MountDetector()
        self._path_configs: Dict[str, Dict[str, str]] = {}
    
    def configure_path(self, path: str, mount_type: Optional[str] = None, 
                      options: Optional[Dict[str, str]] = None):
        """
        配置路径的挂载类型和选项
        
        Args:
            path: 路径
            mount_type: 挂载类型（webdav/nfs/smb/local），None表示自动检测
            options: 挂载选项
        """
        config = {
            'mount_type': mount_type,
            'options': options or {}
        }
        
        self._path_configs[path] = config
        self.logger.info(f"配置路径挂载类型: {path} -> {mount_type or 'auto'}")
    
    def get_mount_type_for_path(self, path: str) -> MountType:
        """
        获取路径的挂载类型
        
        Args:
            path: 路径
            
        Returns:
            MountType: 挂载类型
        """
        # 检查是否有手动配置
        for config_path, config in self._path_configs.items():
            if path.startswith(config_path):
                mount_type_str = config.get('mount_type')
                if mount_type_str:
                    try:
                        return MountType(mount_type_str.lower())
                    except ValueError:
                        self.logger.warning(f"无效的挂载类型: {mount_type_str}")
        
        # 自动检测
        return self.detector.detect_mount_type(path)
    
    def get_mount_options(self, path: str) -> Dict[str, str]:
        """
        获取路径的挂载选项
        
        Args:
            path: 路径
            
        Returns:
            Dict: 挂载选项
        """
        # 检查是否有手动配置
        for config_path, config in self._path_configs.items():
            if path.startswith(config_path):
                return config.get('options', {})
        
        # 返回默认选项
        mount_type = self.get_mount_type_for_path(path)
        return self._get_default_options(mount_type)
    
    def _get_default_options(self, mount_type: MountType) -> Dict[str, str]:
        """
        获取挂载类型的默认选项
        
        Args:
            mount_type: 挂载类型
            
        Returns:
            Dict: 默认选项
        """
        defaults = {
            MountType.WEBDAV: {
                'retry_count': '5',
                'retry_delay': '10',
                'timeout': '30',
                'permission_check': 'relaxed'  # 宽松的权限检查
            },
            MountType.NFS: {
                'retry_count': '3',
                'retry_delay': '5',
                'timeout': '20',
                'permission_check': 'strict'  # 严格的权限检查
            },
            MountType.SMB: {
                'retry_count': '5',
                'retry_delay': '10',
                'timeout': '30',
                'permission_check': 'strict'  # 严格的权限检查
            },
            MountType.LOCAL: {
                'retry_count': '1',
                'retry_delay': '1',
                'timeout': '10',
                'permission_check': 'strict'  # 严格的权限检查
            },
            MountType.UNKNOWN: {
                'retry_count': '3',
                'retry_delay': '5',
                'timeout': '20',
                'permission_check': 'relaxed'  # 宽松的权限检查
            }
        }
        
        return defaults.get(mount_type, defaults[MountType.UNKNOWN])
    
    def parse_mount_config_from_env(self, env_var: str = 'MOUNT_CONFIGS'):
        """
        从环境变量解析挂载配置
        
        环境变量格式：
        MOUNT_CONFIGS="/path1:webdav,/path2:nfs,/path3:smb"
        
        Args:
            env_var: 环境变量名
        """
        config_str = os.environ.get(env_var, '')
        
        if not config_str:
            return
        
        try:
            # 解析配置项
            items = config_str.split(',')
            
            for item in items:
                item = item.strip()
                if not item:
                    continue
                
                # 解析路径和类型
                if ':' in item:
                    path, mount_type = item.split(':', 1)
                    path = path.strip()
                    mount_type = mount_type.strip().lower()
                    
                    # 验证挂载类型
                    try:
                        MountType(mount_type)
                        self.configure_path(path, mount_type)
                    except ValueError:
                        self.logger.warning(f"无效的挂载类型 '{mount_type}'，路径: {path}")
                else:
                    # 只有路径，自动检测
                    path = item.strip()
                    self.configure_path(path)
        
        except Exception as e:
            self.logger.error(f"解析挂载配置失败: {str(e)}")


# 全局挂载配置管理器实例
mount_config_manager = MountConfigManager()


def get_mount_type(path: str) -> MountType:
    """
    获取路径的挂载类型（便捷函数）
    
    Args:
        path: 路径
        
    Returns:
        MountType: 挂载类型
    """
    return mount_config_manager.get_mount_type_for_path(path)


def get_mount_info(path: str) -> MountInfo:
    """
    获取路径的挂载信息（便捷函数）
    
    Args:
        path: 路径
        
    Returns:
        MountInfo: 挂载信息
    """
    return mount_config_manager.detector.get_mount_info(path)


def get_mount_options(path: str) -> Dict[str, str]:
    """
    获取路径的挂载选项（便捷函数）
    
    Args:
        path: 路径
        
    Returns:
        Dict: 挂载选项
    """
    return mount_config_manager.get_mount_options(path)
