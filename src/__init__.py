# -*- coding: utf-8 -*-
"""
PlexAutoScan 包初始化文件
"""

__version__ = '1.0.0'
__author__ = 'PlexAutoScan Team'
__description__ = '自动扫描和更新Plex媒体库的工具'

# 导出工具模块
from .utils.config import Config
from .utils.logger import setup_logger, RobustLogger
from .utils.path_utils import normalize_path, verify_path, ensure_directory
from .utils.snapshot import SnapshotManager

# 导出Plex相关模块
from .plex.api import PlexAPI
from .plex.library import PlexLibraryManager

# 注意：不再直接导出main模块，以避免导入顺序警告
# 如需使用main模块，请直接导入: from src.main import PlexAutoScan