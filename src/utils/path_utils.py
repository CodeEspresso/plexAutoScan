#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径处理工具模块
"""

import os
import sys
import re
import time
from pathlib import Path
import logging
from src.utils.config import Config
from .environment import env_detector
from .mount_detector import get_mount_type, get_mount_options, MountType

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
    def verify_path(path, test_env=False, max_retries=5, retry_delay=10):
        """验证路径是否可访问
        
        Args:
            path (str): 要验证的路径
            test_env (bool): 是否为测试环境
            max_retries (int): 最大重试次数（用于Docker环境下的挂载延迟）
            retry_delay (int): 重试间隔（秒）
            
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
                
                # 设置超时时间 - 针对飞牛OS优化
                check_timeout = 30  # 默认30秒
                if is_docker:
                    check_timeout = 45  # 飞牛OS Docker环境下延长超时时间
                
                # 路径存在性检查（带超时）
                def _check_path_exists(check_path):
                    return os.path.exists(check_path)
                    
                # 权限检查函数（优化版：添加实际读取测试）
                def _check_path_permission(check_path):
                    """
                    检查路径权限（增强版）
                    
                    变更理由：os.access()在某些文件系统上可能返回不准确的结果，
                    因此添加实际读取测试来确保权限检查的准确性。
                    """
                    try:
                        # 对于目录，检查读取和执行权限
                        if os.path.isdir(check_path):
                            # 1. 首先使用os.access检查基本权限
                            has_basic_access = os.access(check_path, os.R_OK | os.X_OK)
                            
                            if not has_basic_access:
                                # 记录详细的权限诊断信息
                                try:
                                    stat_info = os.stat(check_path)
                                    logger.warning(f"权限检查失败 - 路径: {check_path}")
                                    logger.warning(f"  所有者UID: {stat_info.st_uid}, GID: {stat_info.st_gid}")
                                    logger.warning(f"  权限模式: {oct(stat_info.st_mode)}")
                                    logger.warning(f"  当前进程UID: {os.getuid()}, GID: {os.getgid()}")
                                except Exception as e:
                                    logger.warning(f"无法获取路径权限信息: {str(e)}")
                                return False
                            
                            # 2. 尝试实际列出目录内容来验证读取权限
                            try:
                                # 尝试读取目录内容（只读取，不处理）
                                test_files = os.listdir(check_path)
                                logger.debug(f"权限验证成功 - 可以读取目录内容，文件数: {len(test_files)}")
                                return True
                            except PermissionError as pe:
                                logger.error(f"权限验证失败 - 无法读取目录内容: {str(pe)}")
                                logger.error(f"  这可能是因为Docker容器启动时目录未挂载，导致权限缓存不正确")
                                return False
                            except Exception as e:
                                logger.warning(f"权限验证时发生异常: {str(e)}")
                                # 如果是其他异常，仍然返回True，因为os.access通过了
                                return True
                        
                        # 对于文件，检查读取权限
                        else:
                            has_basic_access = os.access(check_path, os.R_OK)
                            
                            if not has_basic_access:
                                try:
                                    stat_info = os.stat(check_path)
                                    logger.warning(f"文件权限检查失败 - 路径: {check_path}")
                                    logger.warning(f"  所有者UID: {stat_info.st_uid}, GID: {stat_info.st_gid}")
                                    logger.warning(f"  权限模式: {oct(stat_info.st_mode)}")
                                except Exception as e:
                                    logger.warning(f"无法获取文件权限信息: {str(e)}")
                                return False
                            
                            # 尝试实际打开文件来验证读取权限
                            try:
                                with open(check_path, 'rb') as f:
                                    # 只读取前几个字节来验证权限
                                    f.read(1)
                                logger.debug(f"文件权限验证成功: {check_path}")
                                return True
                            except PermissionError as pe:
                                logger.error(f"文件权限验证失败 - 无法读取文件: {str(pe)}")
                                return False
                            except Exception as e:
                                logger.warning(f"文件权限验证时发生异常: {str(e)}")
                                return True
                                
                    except Exception as e:
                        logger.error(f"权限检查过程发生异常: {str(e)}")
                        return False
                
                # Docker环境: 根据挂载类型优化处理
                if is_docker:
                    # 检测挂载类型
                    mount_type = get_mount_type(verified_path)
                    mount_options = get_mount_options(verified_path)
                    
                    logger.debug(f"Docker环境：检测到挂载类型 {mount_type.value} - {verified_path}")
                    
                    # 根据挂载类型获取参数
                    retry_count = int(mount_options.get('retry_count', 5))
                    retry_delay = int(mount_options.get('retry_delay', 10))
                    permission_check = mount_options.get('permission_check', 'relaxed')
                    
                    # WebDAV挂载：飞牛OS优化处理
                    if mount_type == MountType.WEBDAV:
                        logger.debug(f"WebDAV挂载：特殊处理 {verified_path}")
                        
                        # 检查基础挂载点是否存在
                        base_mount_path = '/vol02/CloudDrive/WebDAV'
                        if verified_path.startswith('/vol01/CloudDrive/WebDAV'):
                            base_mount_path = '/vol01/CloudDrive/WebDAV'
                        
                        base_exists = run_with_timeout(
                            _check_path_exists,
                            base_mount_path,
                            timeout_seconds=check_timeout,
                            default=True,
                            error_message=f"Docker环境下检查WebDAV基础挂载点超时: {base_mount_path}"
                        )
                        
                        if base_exists:
                            logger.debug(f"WebDAV挂载：基础挂载点存在，继续验证子路径")
                            
                            # 对于WebDAV路径，使用宽松的权限检查
                            if permission_check == 'relaxed':
                                # 尝试列出目录内容
                                try:
                                    if os.path.isdir(verified_path):
                                        test_files = os.listdir(verified_path)
                                        logger.debug(f"WebDAV权限验证成功 - 文件数: {len(test_files)}")
                                        return verified_path, True
                                except PermissionError:
                                    logger.warning(f"WebDAV权限验证失败，但继续尝试")
                                except Exception as e:
                                    logger.warning(f"WebDAV权限验证异常: {str(e)}")
                                
                                # 即使权限检查失败，也返回True（宽松模式）
                                return verified_path, True
                            else:
                                # 严格的权限检查
                                has_permission = run_with_timeout(
                                    _check_path_permission,
                                    verified_path,
                                    timeout_seconds=check_timeout,
                                    default=False,
                                    error_message=f"Docker环境下检查WebDAV路径权限超时: {verified_path}"
                                )
                                return verified_path, has_permission
                        else:
                            logger.warning(f"WebDAV挂载：基础挂载点不存在 {base_mount_path}")
                            return verified_path, False
                    
                    # NFS挂载：使用标准验证
                    elif mount_type == MountType.NFS:
                        logger.debug(f"NFS挂载：标准验证 {verified_path}")
                        
                        path_exists = run_with_timeout(
                            _check_path_exists,
                            verified_path,
                            timeout_seconds=check_timeout,
                            default=False,
                            error_message=f"Docker环境下检查NFS路径存在性超时: {verified_path}"
                        )
                        
                        if path_exists:
                            # NFS使用严格的权限检查
                            has_permission = run_with_timeout(
                                _check_path_permission,
                                verified_path,
                                timeout_seconds=check_timeout,
                                default=False,
                                error_message=f"Docker环境下检查NFS路径权限超时: {verified_path}"
                            )
                            
                            if not has_permission:
                                # 执行详细诊断
                                logger.warning(f"NFS权限检查失败，执行详细诊断: {verified_path}")
                                exists, has_perm, diagnosis = PathUtils.check_mount_status_with_retry(
                                    verified_path, 
                                    max_retries=retry_count, 
                                    retry_delay=retry_delay
                                )
                                
                                if exists and has_perm:
                                    logger.info(f"重试后NFS权限验证成功: {verified_path}")
                                    return verified_path, True
                                else:
                                    logger.error(f"NFS权限验证最终失败，诊断信息: {diagnosis}")
                                    return verified_path, False
                            
                            return verified_path, has_permission
                        else:
                            logger.warning(f"NFS路径不存在: {verified_path}")
                            return verified_path, False
                    
                    # SMB挂载：使用标准验证
                    elif mount_type == MountType.SMB:
                        logger.debug(f"SMB挂载：标准验证 {verified_path}")
                        
                        path_exists = run_with_timeout(
                            _check_path_exists,
                            verified_path,
                            timeout_seconds=check_timeout,
                            default=False,
                            error_message=f"Docker环境下检查SMB路径存在性超时: {verified_path}"
                        )
                        
                        if path_exists:
                            # SMB使用严格的权限检查
                            has_permission = run_with_timeout(
                                _check_path_permission,
                                verified_path,
                                timeout_seconds=check_timeout,
                                default=False,
                                error_message=f"Docker环境下检查SMB路径权限超时: {verified_path}"
                            )
                            
                            if not has_permission:
                                # 执行详细诊断
                                logger.warning(f"SMB权限检查失败，执行详细诊断: {verified_path}")
                                exists, has_perm, diagnosis = PathUtils.check_mount_status_with_retry(
                                    verified_path, 
                                    max_retries=retry_count, 
                                    retry_delay=retry_delay
                                )
                                
                                if exists and has_perm:
                                    logger.info(f"重试后SMB权限验证成功: {verified_path}")
                                    return verified_path, True
                                else:
                                    logger.error(f"SMB权限验证最终失败，诊断信息: {diagnosis}")
                                    return verified_path, False
                            
                            return verified_path, has_permission
                        else:
                            logger.warning(f"SMB路径不存在: {verified_path}")
                            return verified_path, False
                    
                    # 本地路径或未知类型：使用默认验证
                    else:
                        logger.debug(f"本地/未知挂载类型：默认验证 {verified_path}")
                        
                        path_exists = run_with_timeout(
                            _check_path_exists,
                            verified_path,
                            timeout_seconds=check_timeout,
                            default=False,
                            error_message=f"Docker环境下检查路径存在性超时: {verified_path}"
                        )
                        
                        if path_exists:
                            has_permission = run_with_timeout(
                                _check_path_permission,
                                verified_path,
                                timeout_seconds=check_timeout,
                                default=False,
                                error_message=f"Docker环境下检查路径权限超时: {verified_path}"
                            )
                            
                            if not has_permission:
                                # 执行详细诊断
                                logger.warning(f"权限检查失败，执行详细诊断: {verified_path}")
                                exists, has_perm, diagnosis = PathUtils.check_mount_status_with_retry(
                                    verified_path, 
                                    max_retries=retry_count, 
                                    retry_delay=retry_delay
                                )
                                
                                if exists and has_perm:
                                    logger.info(f"重试后权限验证成功: {verified_path}")
                                    return verified_path, True
                                else:
                                    logger.error(f"权限验证最终失败，诊断信息: {diagnosis}")
                                    return verified_path, False
                            
                            return verified_path, has_permission
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
        
        # 对于Docker环境，添加重试机制
        is_docker = PathUtils.is_docker_environment()
        
        for retry in range(max_retries):
            # 直接运行核心路径验证逻辑
            result = _verify_path_core()
            
            verified_path, is_valid = result
            
            if is_valid:
                if retry > 0:
                    logger.info(f"路径验证成功（重试 {retry} 次后）: {verified_path}")
                return result
            
            # 如果是Docker环境且未达到最大重试次数，等待后重试
            if is_docker and retry < max_retries - 1:
                logger.warning(f"路径验证失败，{retry_delay}秒后重试 ({retry + 1}/{max_retries}): {path}")
                time.sleep(retry_delay)
            else:
                break
        
        logger.warning(f"路径验证最终失败: {path}")
        return verified_path, is_valid
    
    @staticmethod
    def is_docker_environment():
        """检测是否在Docker环境中运行
        
        Returns:
            bool: 是否在Docker环境中
        """
        return env_detector.is_docker()
    
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
    
    @staticmethod
    def diagnose_mount_point(path):
        """
        诊断挂载点状态和权限问题
        
        变更理由：提供详细的挂载点诊断信息，帮助用户理解权限问题的根源。
        
        Args:
            path (str): 要诊断的路径
            
        Returns:
            dict: 包含诊断信息的字典
        """
        diagnosis = {
            'path': path,
            'exists': False,
            'is_mount': False,
            'mount_point': None,
            'permissions': {},
            'owner': {},
            'errors': []
        }
        
        try:
            # 检查路径是否存在
            diagnosis['exists'] = os.path.exists(path)
            
            if diagnosis['exists']:
                # 获取文件状态信息
                stat_info = os.stat(path)
                diagnosis['owner'] = {
                    'uid': stat_info.st_uid,
                    'gid': stat_info.st_gid,
                    'mode': oct(stat_info.st_mode)
                }
                
                # 检查是否是挂载点
                diagnosis['is_mount'] = os.path.ismount(path)
                
                # 查找挂载点
                try:
                    with open('/proc/mounts', 'r') as f:
                        mounts = f.readlines()
                    for mount in mounts:
                        parts = mount.split()
                        if len(parts) >= 2:
                            mount_point = parts[1]
                            if path.startswith(mount_point):
                                diagnosis['mount_point'] = mount_point
                                break
                except Exception as e:
                    logger.debug(f"无法读取挂载信息: {str(e)}")
                
                # 检查权限
                diagnosis['permissions'] = {
                    'readable': os.access(path, os.R_OK),
                    'writable': os.access(path, os.W_OK),
                    'executable': os.access(path, os.X_OK),
                    'can_list': False
                }
                
                # 尝试列出目录内容
                if os.path.isdir(path):
                    try:
                        os.listdir(path)
                        diagnosis['permissions']['can_list'] = True
                    except PermissionError:
                        diagnosis['errors'].append("无法列出目录内容（权限被拒绝）")
                    except Exception as e:
                        diagnosis['errors'].append(f"列出目录内容时出错: {str(e)}")
            
            else:
                diagnosis['errors'].append("路径不存在")
                
        except Exception as e:
            diagnosis['errors'].append(f"诊断过程发生异常: {str(e)}")
        
        return diagnosis
    
    @staticmethod
    def check_mount_status_with_retry(path, max_retries=3, retry_delay=5):
        """
        检查挂载点状态（带重试）
        
        变更理由：在Docker环境下，挂载点可能需要时间才能就绪，
        添加重试机制确保能够正确检测到挂载点状态。
        
        Args:
            path (str): 要检查的路径
            max_retries (int): 最大重试次数
            retry_delay (int): 重试间隔（秒）
            
        Returns:
            tuple: (路径是否存在, 权限是否正常, 诊断信息)
        """
        is_docker = PathUtils.is_docker_environment()
        
        for retry in range(max_retries):
            # 执行诊断
            diagnosis = PathUtils.diagnose_mount_point(path)
            
            # 如果路径存在且权限正常
            if diagnosis['exists'] and diagnosis['permissions'].get('can_list', False):
                if retry > 0:
                    logger.info(f"挂载点检测成功（重试 {retry} 次后）: {path}")
                return True, True, diagnosis
            
            # 如果路径存在但权限有问题
            if diagnosis['exists'] and not diagnosis['permissions'].get('can_list', False):
                logger.warning(f"挂载点存在但权限有问题: {path}")
                logger.warning(f"  所有者: UID={diagnosis['owner'].get('uid')}, GID={diagnosis['owner'].get('gid')}")
                logger.warning(f"  当前进程: UID={os.getuid()}, GID={os.getgid()}")
                
                # 如果是Docker环境，提供修复建议
                if is_docker:
                    logger.warning("  Docker环境权限问题可能的原因:")
                    logger.warning("  1. 容器启动时挂载点未就绪，导致权限缓存不正确")
                    logger.warning("  2. 容器内的用户ID与挂载点的文件所有者ID不匹配")
                    logger.warning("  修复建议:")
                    logger.warning("  - 重启容器以刷新权限缓存")
                    logger.warning("  - 确保挂载点在容器启动前已就绪")
                    logger.warning("  - 检查Docker卷挂载配置")
                
                # 返回存在但权限有问题
                return True, False, diagnosis
            
            # 如果路径不存在，等待后重试
            if not diagnosis['exists'] and is_docker and retry < max_retries - 1:
                logger.warning(f"挂载点不存在，{retry_delay}秒后重试 ({retry + 1}/{max_retries}): {path}")
                time.sleep(retry_delay)
        
        # 所有重试都失败
        logger.error(f"挂载点检测最终失败: {path}")
        return False, False, diagnosis

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