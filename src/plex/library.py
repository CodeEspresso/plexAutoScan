#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plex媒体库处理模块
"""

import os
import sys
import json
import time
import logging
import re
from pathlib import Path
from urllib.parse import quote

# 删除: 使用错误路径的绝对导入
# 新增: 使用正确的相对导入
from ..utils.logger import RobustLogger
from ..utils.config import Config
from ..utils.path_utils import normalize_path, verify_path, PathUtils
from ..utils.timeout_decorator import run_with_timeout
from .api import PlexAPI

# 初始化日志记录器，使用与主程序相同的名称以确保日志正确输出
logger = RobustLogger('plex_autoscan')


class PlexLibraryManager:
    """Plex媒体库管理器类，负责处理Plex媒体库相关操作"""
    
    def __init__(self, config=None, plex_api=None):
        """初始化Plex媒体库管理器
        
        Args:
            config (Config): 配置对象
            plex_api (PlexAPI, optional): 已初始化的PlexAPI实例
        """
        self.config = config or Config()
        
        # 优先使用传入的PlexAPI实例，如果没有则创建新实例
        if plex_api:
            self.plex_api = plex_api
        else:
            try:
                self.plex_api = PlexAPI(config)
            except ValueError as e:
                logger.error(f"在PlexLibraryManager中初始化Plex API失败: {str(e)}")
                self.plex_api = None
                self.libraries = []
                return
        
        # 从配置中获取相关设置
        # 修复: 使用get_mount_paths方法正确解析挂载路径列表
        self.mount_paths = self.config.get_mount_paths()
        self.media_types = ['movie', 'show', 'music', 'photo']
        
        # 缓存媒体库信息
        self.libraries = []
        self._load_libraries()
    
    def _load_libraries(self):
        """加载Plex媒体库信息"""
        try:
            self.libraries = self.plex_api.get_plex_media_libraries()
            logger.info(f"已加载{len(self.libraries)}个Plex媒体库")
        except Exception as e:
            logger.error(f"加载Plex媒体库失败: {str(e)}")
            self.libraries = []
    
    def refresh_libraries(self):
        """刷新媒体库信息
        
        Returns:
            int: 加载的媒体库数量
        """
        self._load_libraries()
        return len(self.libraries)
    
    def find_deepest_matching_library(self, path):
        """查找与给定路径最匹配的媒体库
        
        Args:
            path (str): 要匹配的路径
            
        Returns:
            dict: 匹配的媒体库信息，如无匹配则返回None
        """
        if not path or not self.libraries:
            return None
        
        # 规范化路径
        normalized_path = normalize_path(path)
        if not normalized_path:
            return None
        
        # 准备路径用于比较（使用Unix风格的路径分隔符）
        path_for_compare = normalized_path.replace('\\', '/')
        
        # 存储最佳匹配的媒体库
        best_match = None
        max_match_length = 0
        
        # 遍历所有媒体库
        for library in self.libraries:
            # 获取媒体库路径
            library_path = library.get('path', '')
            library_name = library.get('name', '').lower()
            
            # 1. 尝试基于路径的匹配
            if library_path:
                # 规范化媒体库路径
                normalized_lib_path = normalize_path(library_path)
                lib_path_for_compare = normalized_lib_path.replace('\\', '/')
                
                # 检查路径匹配
                # 1.1 检查目标路径是否是媒体库路径的子目录（不区分大小写）
                if path_for_compare.lower().startswith(lib_path_for_compare.lower() + '/'):
                    # 计算匹配长度
                    match_length = len(lib_path_for_compare)
                    
                    # 更新最佳匹配
                    if match_length > max_match_length:
                        max_match_length = match_length
                        best_match = library.copy()  # 深拷贝以避免修改原始数据
                        
                        # 添加匹配信息
                        best_match['match_score'] = match_length
                        best_match['relative_path'] = path_for_compare[match_length + 1:]
                
                # 1.2 检查媒体库路径是否是目标路径的子目录（不区分大小写）
                # 这种情况适用于目标路径是一个包含多个媒体库的父目录
                elif lib_path_for_compare.lower().startswith(path_for_compare.lower() + '/'):
                    match_length = len(path_for_compare)
                    
                    if match_length > max_match_length:
                        max_match_length = match_length
                        best_match = library.copy()
                        best_match['match_score'] = match_length
                        best_match['relative_path'] = lib_path_for_compare[match_length + 1:]
                
                # 1.3 检查路径映射
                for mount_path in self.mount_paths:
                    if isinstance(mount_path, dict) and 'host_path' in mount_path and 'container_path' in mount_path:
                        # 主机路径到容器路径的映射
                        host_path = normalize_path(mount_path['host_path']).replace('\\', '/')
                        container_path = normalize_path(mount_path['container_path']).replace('\\', '/')
                        
                        # 检查路径映射后的匹配（不区分大小写）
                        if path_for_compare.lower().startswith(host_path.lower() + '/'):
                            # 将主机路径映射到容器路径
                            mapped_path = container_path + path_for_compare[len(host_path):]
                            if mapped_path.lower().startswith(lib_path_for_compare.lower() + '/'):
                                match_length = len(lib_path_for_compare)
                                
                                if match_length > max_match_length:
                                    max_match_length = match_length
                                    best_match = library.copy()
                                    best_match['match_score'] = match_length
                                    best_match['relative_path'] = mapped_path[match_length + 1:]
                                    best_match['original_path'] = path_for_compare
                                    best_match['mapped_path'] = mapped_path
            
            # 2. 增强版名称匹配（作为主要匹配方式之一）
            # 无论是否已经有路径匹配，都考虑基于名称的匹配作为重要参考
            if library_name:
                # 将路径转换为小写用于比较
                path_lower = path_for_compare.lower()
                library_name_lower = library_name.lower()
                
                # 检查媒体库名称是否包含在路径中
                if library_name_lower in path_lower:
                    # 计算匹配分数（基于名称长度和位置）
                    match_score = len(library_name_lower) * 2  # 增加名称匹配的权重
                    
                    # 如果媒体库名称在路径的特定位置（如最后一级目录），给予额外分数
                    path_parts = path_lower.split('/')
                    if library_name_lower in path_parts[-1] or library_name_lower == path_parts[-1]:
                        match_score += 5  # 最后一级目录匹配额外加分
                    
                    # 如果没有路径匹配，或者名称匹配分数高于当前最佳路径匹配
                    if not best_match or match_score > best_match.get('match_score', 0):
                        max_match_length = match_score
                        best_match = library.copy()
                        best_match['match_score'] = match_score
                        # 尝试提取相对路径
                        name_index = path_lower.find(library_name_lower)
                        if name_index != -1:
                            relative_path = path_for_compare[name_index + len(library_name_lower):].strip('/')
                            best_match['relative_path'] = relative_path
                        best_match['match_type'] = 'enhanced_name_based'  # 标记这是增强的基于名称的匹配
        
        if best_match:
            logger.info(f"找到最匹配的媒体库: {best_match['name']} (ID: {best_match['id']}) 匹配分数: {best_match['match_score']}")
        else:
            logger.warning(f"未找到匹配的媒体库: {path}")
        
        return best_match
    
    def get_library_by_id(self, library_id):
        """通过ID获取媒体库信息
        
        Args:
            library_id (str): 媒体库ID
            
        Returns:
            dict: 媒体库信息，如无匹配则返回None
        """
        if not library_id or not self.libraries:
            return None
        
        for library in self.libraries:
            if library.get('id') == library_id:
                return library
        
        logger.warning(f"未找到ID为{library_id}的媒体库")
        return None
    
    def get_library_by_name(self, library_name):
        """通过名称获取媒体库信息
        
        Args:
            library_name (str): 媒体库名称
            
        Returns:
            dict: 媒体库信息，如无匹配则返回None
        """
        if not library_name or not self.libraries:
            return None
        
        for library in self.libraries:
            if library.get('name').lower() == library_name.lower():
                return library
        
        logger.warning(f"未找到名称为'{library_name}'的媒体库")
        return None
    
    def scan_path(self, path):
        """扫描指定路径并触发相应媒体库的扫描
        
        Args:
            path (str): 要扫描的路径
            
        Returns:
            dict: 扫描结果
        """
        # 检查Plex集成是否启用 - 修正: 使用enable_plex属性方法而不是直接get配置项
        if not self.config.enable_plex:
            logger.warning("Plex集成未启用，跳过扫描")
            return {'success': False, 'error': 'plex_integration_disabled'}
        
        # 验证路径
        verified_path, is_valid = verify_path(path)
        if not is_valid:
            logger.error(f"无效的路径: {path}")
            return {'success': False, 'error': 'invalid_path'}
        
        # 查找匹配的媒体库
        library = self.find_deepest_matching_library(verified_path)
        if not library:
            return {'success': False, 'error': 'no_matching_library'}
        
        # 触发Plex扫描
        scan_result = self.plex_api.trigger_plex_scan(library['id'], verified_path)
        
        if scan_result.get('success'):
            return {
                'success': True,
                'library_id': library['id'],
                'library_name': library['name'],
                'scanned_path': verified_path
            }
        else:
            return scan_result
    
    def get_library_path_mappings(self):
        """获取媒体库路径映射
        
        Returns:
            dict: 路径映射字典
        """
        path_mappings = {}
        
        for library in self.libraries:
            library_path = library.get('path', '')
            if library_path:
                normalized_path = normalize_path(library_path)
                path_mappings[normalized_path] = library
        
        return path_mappings
    
    def filter_libraries_by_type(self, media_type):
        """根据媒体类型过滤媒体库
        
        Args:
            media_type (str): 媒体类型
            
        Returns:
            list: 过滤后的媒体库列表
        """
        if not media_type or not self.libraries:
            return []
        
        filtered_libraries = [
            library for library in self.libraries 
            if library.get('type', '').lower() == media_type.lower()
        ]
        
        logger.info(f"根据媒体类型'{media_type}'过滤出{len(filtered_libraries)}个媒体库")
        return filtered_libraries
    
    def _download_and_extract_core(self, url, output_dir):
        """下载并提取文件的核心实现
        
        Args:
            url (str): 文件URL
            output_dir (str): 输出目录
            
        Returns:
            dict: 下载和提取结果
        """
        try:
            import requests
            import zipfile
            import tempfile
            
            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            # 发送下载请求
            logger.info(f"开始下载文件: {url}")
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            # 创建临时文件保存下载内容
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
                temp_file_path = temp_file.name
            
            logger.info(f"文件下载完成，保存至临时文件: {temp_file_path}")
            
            # 提取文件
            with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                zip_ref.extractall(output_dir)
            
            logger.info(f"文件提取完成，输出目录: {output_dir}")
            
            # 删除临时文件
            os.remove(temp_file_path)
            
            return {'success': True, 'output_dir': output_dir}
        except Exception as e:
            logger.error(f"下载并提取文件失败: {str(e)}")
            return {'success': False, 'error': str(e)}
            
    def download_and_extract(self, url, output_dir):
        """下载并提取文件
        
        Args:
            url (str): 文件URL
            output_dir (str): 输出目录
            
        Returns:
            dict: 下载和提取结果
        """
        # 根据是否在Docker环境设置不同的超时时间
        is_docker = PathUtils.is_docker_environment()
        timeout_seconds = 300 if is_docker else 600  # Docker环境300秒(5分钟)，默认环境600秒(10分钟)
        
        logger.info(f"开始下载并提取文件，超时设置为 {timeout_seconds} 秒")
        
        # 使用超时控制运行核心逻辑
        result = run_with_timeout(
            self._download_and_extract_core,
            args=(url, output_dir),
            timeout_seconds=timeout_seconds
        )
        
        if result['timed_out']:
            logger.error(f"下载并提取文件超时(> {timeout_seconds} 秒)")
            return {
                'success': False,
                'error': f'下载并提取文件超时(> {timeout_seconds} 秒)'
            }
        
        return result['result']
    
    def _download_paginated_xml_core(self, base_url, output_file, page_size=1000):
        """分页下载XML数据的核心实现
        
        Args:
            base_url (str): 基础URL
            output_file (str): 输出文件路径
            page_size (int): 每页大小
            
        Returns:
            dict: 下载结果
        """
        try:
            import requests
            import xml.etree.ElementTree as ET
            
            # 确保输出目录存在
            output_dir = os.path.dirname(output_file)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            # 初始化总页数和当前页
            total_pages = 1
            current_page = 1
            all_items = []
            
            logger.info(f"开始分页下载XML数据: {base_url}")
            
            # 分页下载数据
            while current_page <= total_pages:
                # 构建带分页参数的URL
                page_url = f"{base_url}?start={(current_page - 1) * page_size}&limit={page_size}"
                logger.info(f"下载第{current_page}/{total_pages}页: {page_url}")
                
                # 发送请求
                response = requests.get(page_url, timeout=60)
                response.raise_for_status()
                
                # 解析XML响应
                root = ET.fromstring(response.content)
                
                # 获取总项目数和计算总页数
                if current_page == 1:
                    total_size = int(root.get('totalSize', '0'))
                    total_pages = (total_size + page_size - 1) // page_size
                    logger.info(f"总项目数: {total_size}, 总页数: {total_pages}")
                
                # 收集项目
                items = root.findall('.//Directory') + root.findall('.//Metadata')
                all_items.extend(items)
                
                # 移动到下一页
                current_page += 1
            
            # 创建新的XML文档并保存所有项目
            new_root = ET.Element('MediaContainer', attrib={'totalSize': str(len(all_items))})
            for item in all_items:
                new_root.append(item)
            
            # 保存到文件
            tree = ET.ElementTree(new_root)
            tree.write(output_file, encoding='utf-8', xml_declaration=True)
            
            logger.info(f"XML数据已保存至: {output_file}")
            return {'success': True, 'output_file': output_file, 'item_count': len(all_items)}
        except Exception as e:
            logger.error(f"分页下载XML数据失败: {str(e)}")
            return {'success': False, 'error': str(e)}
            
    def download_paginated_xml(self, base_url, output_file, page_size=1000):
        """分页下载XML数据
        
        Args:
            base_url (str): 基础URL
            output_file (str): 输出文件路径
            page_size (int): 每页大小
            
        Returns:
            dict: 下载结果
        """
        # 根据是否在Docker环境设置不同的超时时间
        is_docker = PathUtils.is_docker_environment()
        timeout_seconds = 600 if is_docker else 1200  # Docker环境600秒(10分钟)，默认环境1200秒(20分钟)
        
        logger.info(f"开始分页下载XML数据，超时设置为 {timeout_seconds} 秒")
        
        # 使用超时控制运行核心逻辑
        result = run_with_timeout(
            self._download_paginated_xml_core,
            args=(base_url, output_file, page_size),
            timeout_seconds=timeout_seconds
        )
        
        if result['timed_out']:
            logger.error(f"分页下载XML数据超时(> {timeout_seconds} 秒)")
            return {
                'success': False,
                'error': f'分页下载XML数据超时(> {timeout_seconds} 秒)'
            }
        
        return result['result']
    
    def normalize_plex_path(self, path):
        """规范化Plex路径
        
        Args:
            path (str): 要规范化的路径
            
        Returns:
            str: 规范化后的路径
        """
        # 使用路径工具中的规范化函数
        normalized_path = normalize_path(path)
        
        # 针对Plex的特定处理
        # 1. 处理URL编码的路径
        try:
            from urllib.parse import unquote
            normalized_path = unquote(normalized_path)
        except ImportError:
            pass
        
        # 2. 处理Plex可能返回的特殊路径格式
        # 例如：本地路径可能以'file://'开头
        if normalized_path.startswith('file://'):
            normalized_path = normalized_path[7:]  # 移除'file://'
        
        return normalized_path
    
    def is_initialized(self):
        """检查媒体库管理器是否已初始化
        
        Returns:
            bool: 如果已初始化返回True，否则返回False
        """
        # 检查Plex API是否可用且媒体库已加载
        is_plex_api_valid = self.plex_api is not None
        is_libraries_valid = self.libraries is not None and len(self.libraries) > 0
        logger.debug(f"媒体库管理器初始化检查: Plex API可用={is_plex_api_valid}, 媒体库已加载={is_libraries_valid}")
        return is_plex_api_valid and is_libraries_valid
        
    def update_library_with_files(self, directory, file_paths):
        """使用文件列表更新媒体库，支持增量更新和单文件入库

        Args:
            directory (str): 目录路径
            file_paths (list): 文件路径列表
            
        Returns:
            int: 触发扫描的文件数量
        """
        # 检测是否是WebDAV路径
        is_webdav_path = directory.startswith(('/vol02/CloudDrive/WebDAV', '/Volumes/CloudDrive/WebDAV'))
        if is_webdav_path:
            logger.info(f"[PLEX更新] [WebDAV路径] 检测到WebDAV路径: {directory}")
        logger.info(f"[PLEX更新] 接收到更新请求: 目录={directory}, 文件数量={len(file_paths) if file_paths else 0}")
        
        if not self.is_initialized():
            logger.warning("[PLEX更新] 媒体库管理器未初始化，跳过更新")
            return 0
            
        if not file_paths:
            logger.info("[PLEX更新] 没有需要更新的文件，跳过更新")
            return 0
            
        # 从配置中获取小文件忽略阈值（默认为10MB）
        min_file_size = self.config.get_int('MIN_FILE_SIZE', 10 * 1024 * 1024)
        logger.info(f"[PLEX更新] 当前小文件忽略阈值: {min_file_size} 字节 ({min_file_size/1024/1024:.2f} MB)")
            
        try:
            updated_count = 0
            
            # 检查Plex API状态
            logger.info(f"[PLEX更新] Plex API状态: available={self.plex_api is not None}, has_scan_library={hasattr(self.plex_api, 'scan_library') if self.plex_api else False}")
            
            # 查找匹配的媒体库
            logger.info(f"[PLEX更新] 开始查找匹配的媒体库: {directory}")
            library = self.find_deepest_matching_library(directory)
            
            # 增强WebDAV路径的媒体库匹配逻辑
            if not library and is_webdav_path:
                logger.info(f"[PLEX更新] [WebDAV路径] 尝试针对WebDAV路径的增强匹配逻辑")
                # 针对WebDAV路径的特殊匹配逻辑
                # 1. 尝试直接匹配目录结构中的上层目录
                web_dav_path_parts = directory.split('/')
                # 提取主要分类（如'电影'、'电视剧'等）
                category_match = None
                for part in web_dav_path_parts:
                    if part in ['电影', '电视剧', '纪录片', '音乐']:
                        category_match = part
                        break
                
                if category_match:
                    logger.info(f"[PLEX更新] [WebDAV路径] 找到分类: {category_match}，尝试基于分类匹配媒体库")
                    for lib in self.libraries:
                        lib_name = lib.get('name', '').lower()
                        if category_match.lower() in lib_name:
                            logger.info(f"[PLEX更新] [WebDAV路径] 分类匹配成功：媒体库'{lib.get('name')}'与分类'{category_match}'匹配")
                            library = lib
                            break
                
                # 2. 如果分类匹配失败，尝试更宽松的目录名匹配
                if not library:
                    directory_name = os.path.basename(directory)
                    logger.info(f"[PLEX更新] [WebDAV路径] 尝试更宽松的目录名匹配: '{directory_name}'")
                    for lib in self.libraries:
                        lib_name = lib.get('name', '').lower()
                        # 对于WebDAV路径，允许更宽松的匹配，只要目录名包含在媒体库名中或媒体库名包含在目录名中
                        if directory_name.lower() in lib_name or lib_name in directory_name.lower():
                            logger.info(f"[PLEX更新] [WebDAV路径] 宽松匹配成功：媒体库'{lib.get('name')}'与目录名'{directory_name}'匹配")
                            library = lib
                            break
            
            if not library:
                logger.warning(f"[PLEX更新] 未找到匹配的媒体库: {directory}")
                # 打印已加载的媒体库信息，帮助调试
                logger.info(f"[PLEX更新] 当前已加载的媒体库数量: {len(self.libraries) if self.libraries else 0}")
                
                # 尝试一种备用方法：直接根据目录名查找匹配的媒体库
                directory_name = os.path.basename(directory)
                if directory_name:
                    logger.info(f"[PLEX更新] 尝试备用方法：根据目录名'{directory_name}'查找媒体库")
                    for lib in self.libraries:
                        lib_name = lib.get('name', '').lower()
                        if directory_name.lower() in lib_name:
                            logger.info(f"[PLEX更新] 备用匹配成功：媒体库'{lib.get('name')}'与目录名'{directory_name}'匹配")
                            library = lib
                            break
                
                # 如果仍然没有匹配，打印所有媒体库信息进行调试
                if not library and self.libraries:
                    logger.info("[PLEX更新] 所有已加载的媒体库信息：")
                    for lib in self.libraries:
                        logger.info(f"[PLEX更新] 媒体库: ID={lib.get('id')}, Name={lib.get('name')}, Path={lib.get('path')}")
                
                if not library:
                    return 0
                
            library_id = library.get('id')
            library_name = library.get('name')
            logger.info(f"[PLEX更新] 找到匹配的媒体库: '{library_name}' (ID: {library_id}), 路径: {library.get('path')}")
            
            # 过滤有效的文件路径
            # 优化：使用列表推导式和缓存结果来提高性能
            valid_file_paths = []
            ignored_small_files = 0
            
            # 如果文件数量很大，使用分块处理以避免内存问题
            if len(file_paths) > 1000:
                logger.info(f"[PLEX更新] 文件数量较大({len(file_paths)}个)，使用分块处理")
                # 分批处理文件列表
                chunk_size = 500
                for i in range(0, len(file_paths), chunk_size):
                    chunk = file_paths[i:i+chunk_size]
                    for f in chunk:
                        if f and isinstance(f, str) and os.path.exists(f):
                            try:
                                file_size = os.path.getsize(f)
                                if file_size >= min_file_size:
                                    valid_file_paths.append(f)
                                else:
                                    ignored_small_files += 1
                            except Exception as e:
                                logger.error(f"[PLEX更新] 获取文件大小失败: {f}, 错误: {str(e)}")
            else:
                # 小文件列表直接处理
                for f in file_paths:
                    if f and isinstance(f, str) and os.path.exists(f):
                        try:
                            file_size = os.path.getsize(f)
                            if file_size >= min_file_size:
                                valid_file_paths.append(f)
                            else:
                                ignored_small_files += 1
                        except Exception as e:
                            logger.error(f"[PLEX更新] 获取文件大小失败: {f}, 错误: {str(e)}")
            
            logger.info(f"[PLEX更新] 有效文件数量: {len(valid_file_paths)}, 忽略小文件数量: {ignored_small_files}")
            
            if not valid_file_paths:
                logger.warning("[PLEX更新] 没有有效的文件路径，跳过更新")
                return 0
            
            # 从配置中获取快照相关设置
            use_incremental_update = self.config.get('USE_INCREMENTAL_UPDATE', True)
            snapshot_dir = self.config.get('SNAPSHOT_DIR', '/tmp/plex_snapshots')
            
            # 使用Plex API触发扫描操作
            if self.plex_api and hasattr(self.plex_api, 'scan_library'):
                # 对于WebDAV路径，调整增量更新逻辑
                if is_webdav_path:
                    # 增加WebDAV路径的日志记录
                    logger.info(f"[PLEX更新] [WebDAV路径] 处理WebDAV路径: {directory}，媒体库: {library_name}")
                    
                    # 对于WebDAV路径，可以考虑降低增量更新的敏感度，增加强制扫描的概率
                    # 例如，每处理10次相同路径，就强制扫描一次
                    web_dav_path_key = f"webdav_path_{directory}"
                    web_dav_process_count = getattr(self, f"_{web_dav_path_key}_count", 0)
                    web_dav_process_count += 1
                    setattr(self, f"_{web_dav_path_key}_count", web_dav_process_count)
                    
                    if web_dav_process_count % 10 == 0:
                        logger.info(f"[PLEX更新] [WebDAV路径] 路径已处理10次，强制触发扫描以确保更新")
                        use_incremental_update = False
                
                # 如果启用了增量更新
                if use_incremental_update:
                    # 构造快照文件路径
                    library_snapshot_file = os.path.join(snapshot_dir, f"library_{library_id}_files.json")
                    current_files_checksum = self._calculate_files_checksum(valid_file_paths)
                    
                    # 检查是否有旧快照
                    has_old_snapshot = os.path.exists(library_snapshot_file)
                    
                    # 确定需要扫描的文件
                    files_to_scan = []
                    
                    if not has_old_snapshot:
                        # 情况1: 没有旧快照 - 从Plex获取文件列表，找出未入库的文件
                        logger.info("[PLEX更新] 没有旧快照，从Plex获取文件列表进行对比")
                        
                        # 确保snapshot_dir存在
                        os.makedirs(snapshot_dir, exist_ok=True)
                        
                        # 从Plex获取文件列表
                        if hasattr(self.plex_api, 'get_library_files'):
                            try:
                                plex_files = self.plex_api.get_library_files(library_id)
                                
                                # 创建Plex文件路径集合用于快速查找
                                plex_file_paths = set()
                                for item in plex_files:
                                    if 'path' in item:
                                        # 标准化路径以进行比较
                                        normalized_path = self._normalize_path_for_comparison(item['path'])
                                        plex_file_paths.add(normalized_path)
                                
                                # 找出未在Plex中的文件
                                for file_path in valid_file_paths:
                                    normalized_path = self._normalize_path_for_comparison(file_path)
                                    if normalized_path not in plex_file_paths:
                                        files_to_scan.append(file_path)
                                
                                logger.info(f"[PLEX更新] 从Plex获取到{len(plex_files)}个文件，发现{len(files_to_scan)}个未入库文件")
                            except Exception as e:
                                logger.error(f"[PLEX更新] 获取Plex文件列表失败: {str(e)}")
                                # 降级为扫描所有文件
                                files_to_scan = valid_file_paths
                        else:
                            logger.warning("[PLEX更新] Plex API缺少get_library_files方法，降级为扫描所有文件")
                            files_to_scan = valid_file_paths
                        
                        # 保存当前文件列表作为新快照
                        self._save_files_snapshot(library_snapshot_file, valid_file_paths, current_files_checksum)
                    else:
                        # 情况2: 有旧快照 - 先比较校验和，差异时再对比快照
                        logger.info("[PLEX更新] 有旧快照，先比较校验和")
                        
                        try:
                            # 读取旧快照
                            with open(library_snapshot_file, 'r') as f:
                                snapshot_data = json.load(f)
                                old_checksum = snapshot_data.get('checksum', '')
                                old_files = snapshot_data.get('files', [])
                            
                            # 比较校验和
                            if old_checksum and old_checksum == current_files_checksum:
                                # 校验和相同，文件没有变化
                                logger.info("[PLEX更新] 校验和相同，文件没有变化，跳过更新")
                                return 0
                            else:
                                # 校验和不同，需要比较文件列表
                                logger.info("[PLEX更新] 校验和不同，开始比较文件列表")
                                
                                # 找出新增的文件
                                old_files_set = set(self._normalize_path_for_comparison(f) for f in old_files)
                                for file_path in valid_file_paths:
                                    normalized_path = self._normalize_path_for_comparison(file_path)
                                    if normalized_path not in old_files_set:
                                        files_to_scan.append(file_path)
                                
                                logger.info(f"[PLEX更新] 比较文件列表后发现{len(files_to_scan)}个新增文件")
                            
                            # 更新快照
                            self._save_files_snapshot(library_snapshot_file, valid_file_paths, current_files_checksum)
                        except Exception as e:
                            logger.error(f"[PLEX更新] 处理快照失败: {str(e)}")
                            # 降级为扫描所有文件
                            files_to_scan = valid_file_paths
                    
                    # 处理需要扫描的文件
                    if files_to_scan:
                        # 对于WebDAV路径，调整单文件扫描参数
                        if is_webdav_path:
                            logger.info(f"[PLEX更新] [WebDAV路径] 调整WebDAV路径的扫描参数")
                            # 临时覆盖配置，为WebDAV路径使用更合适的参数
                            original_scan_delay = self.config._config.get('SCAN_DELAY_BETWEEN_FILES', '1.0')
                            original_batch_size = self.config._config.get('SCAN_BATCH_SIZE', '10')
                            
                            # 为WebDAV路径设置更小的批处理大小和更长的延迟
                            # 注意：Config类使用内部的_config字典存储配置
                            self.config._config['SCAN_BATCH_SIZE'] = '5'  # 更小的批处理大小
                            self.config._config['SCAN_DELAY_BETWEEN_FILES'] = '2.0'  # 更长的延迟
                            
                            # 触发扫描
                            updated_count = self._trigger_individual_file_scans(library_id, library_name, files_to_scan)
                            
                            # 恢复原始配置 - 直接使用原始字符串值，保持类型一致性
                            self.config._config['SCAN_DELAY_BETWEEN_FILES'] = original_scan_delay
                            self.config._config['SCAN_BATCH_SIZE'] = original_batch_size
                        else:
                            updated_count = self._trigger_individual_file_scans(library_id, library_name, files_to_scan)
                    else:
                        logger.info("[PLEX更新] 没有需要扫描的文件，跳过扫描请求")
                        updated_count = 0
                        return updated_count
                else:
                    # 不启用增量更新，使用原始的目录扫描方式
                    
                    # 即使不启用增量更新，也要检查文件是否有变化，避免不必要的扫描
                    # 正确初始化变量，避免变量未定义错误
                    library_snapshot_file = os.path.join(snapshot_dir, f"library_{library_id}_files.json")
                    current_files_checksum = self._calculate_files_checksum(valid_file_paths)
                    has_old_snapshot = os.path.exists(library_snapshot_file)
                    old_checksum = ''
                    
                    if has_old_snapshot:
                        try:
                            # 读取旧快照
                            with open(library_snapshot_file, 'r') as f:
                                snapshot_data = json.load(f)
                                old_checksum = snapshot_data.get('checksum', '')
                        except Exception as e:
                            logger.error(f"[PLEX更新] 读取旧快照失败: {str(e)}")
                            old_checksum = ''
                    
                    # 有旧快照，比较校验和
                    if has_old_snapshot and old_checksum and old_checksum == current_files_checksum:
                        # 校验和相同，文件没有变化
                        logger.info("[PLEX更新] 校验和相同，文件没有变化，跳过非增量模式下的扫描")
                        return 0
                    else:
                        logger.info("[PLEX更新] 校验和不同，执行非增量模式下的扫描")
                        # 更新快照
                        if use_incremental_update:
                            self._save_files_snapshot(library_snapshot_file, valid_file_paths, current_files_checksum)
                    
                    logger.info(f"[PLEX更新] 开始扫描媒体库 {library_id} 路径: {directory}")
                    
                    # 记录详细的请求信息
                    plex_url = getattr(self.plex_api, 'plex_url', 'unknown')
                    logger.info(f"[PLEX更新] 准备向Plex服务器发送请求: {plex_url}/library/sections/{library_id}/refresh?path={directory}")
                    
                    # 对于WebDAV路径，增加重试逻辑
                    max_retries = 3
                    retry_count = 0
                    scan_result = False
                    
                    while retry_count < max_retries and not scan_result:
                        # 执行扫描请求
                        scan_result = self.plex_api.scan_library(library_id, directory)
                        
                        if not scan_result and retry_count < max_retries - 1:
                            retry_count += 1
                            wait_time = 2 * retry_count  # 指数退避
                            logger.warning(f"[PLEX更新] [WebDAV路径] 扫描请求失败，{wait_time}秒后重试 (尝试 {retry_count}/{max_retries})")
                            time.sleep(wait_time)
                    
                    # 记录请求结果
                    if scan_result:
                        updated_count = len(file_paths)
                        logger.info(f"[PLEX更新] ✅ 已向Plex服务器发送扫描请求，媒体库'{library_name}'已触发扫描")
                        logger.info(f"[PLEX更新] 扫描目录: {directory}，相关文件数量: {updated_count}")
                        logger.debug(f"[PLEX更新] 文件示例: {file_paths[:3] if len(file_paths) > 3 else file_paths}")
                    else:
                        logger.warning(f"[PLEX更新] ❌ 扫描请求发送失败")
            else:
                logger.warning("[PLEX更新] Plex API不可用或缺少scan_library方法")
                # 降级方案：记录需要更新的文件
                updated_count = len(file_paths)
                logger.info(f"[PLEX更新] 使用降级方案，记录 {updated_count} 个需要更新的文件")
                
            return updated_count
        except Exception as e:
            logger.error(f"[PLEX更新] 处理异常: {str(e)}")
            import traceback
            logger.error(f"[PLEX更新] 异常堆栈: {traceback.format_exc()}")
            return 0
    
    def _calculate_files_checksum(self, file_paths):
        """计算文件列表的校验和
        
        Args:
            file_paths (list): 文件路径列表
            
        Returns:
            str: 校验和字符串
        """
        import hashlib
        
        try:
            # 排序文件路径以确保一致性
            sorted_paths = sorted(file_paths)
            
            # 创建一个包含所有文件路径的字符串
            paths_str = '\n'.join(sorted_paths).encode('utf-8')
            
            # 计算MD5校验和
            checksum = hashlib.md5(paths_str).hexdigest()
            return checksum
        except Exception as e:
            logger.error(f"[PLEX更新] 计算文件列表校验和失败: {str(e)}")
            return ''
    
    def _save_files_snapshot(self, snapshot_file, file_paths, checksum):
        """保存文件列表快照
        
        Args:
            snapshot_file (str): 快照文件路径
            file_paths (list): 文件路径列表
            checksum (str): 文件列表的校验和
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(snapshot_file), exist_ok=True)
            
            # 保存快照数据
            snapshot_data = {
                'timestamp': time.time(),
                'checksum': checksum,
                'files': file_paths
            }
            
            with open(snapshot_file, 'w') as f:
                json.dump(snapshot_data, f, indent=2)
            
            logger.info(f"[PLEX更新] 已保存文件列表快照: {snapshot_file}")
        except Exception as e:
            logger.error(f"[PLEX更新] 保存文件列表快照失败: {str(e)}")
    
    def _normalize_path_for_comparison(self, path):
        """标准化路径以进行比较
        
        Args:
            path (str): 原始路径
            
        Returns:
            str: 标准化后的路径
        """
        try:
            # 规范化路径
            normalized = os.path.normpath(path)
            # 转换为小写以确保大小写不敏感的比较
            normalized = normalized.lower()
            return normalized
        except Exception as e:
            logger.error(f"[PLEX更新] 标准化路径失败: {str(e)}")
            return path
    
    def _trigger_individual_file_scans(self, library_id, library_name, file_paths):
        """触发单个文件的扫描操作
        
        Args:
            library_id (str): 媒体库ID
            library_name (str): 媒体库名称
            file_paths (list): 文件路径列表
            
        Returns:
            int: 成功触发扫描的文件数量
        """
        success_count = 0
        
        if not hasattr(self.plex_api, 'scan_library'):
            logger.warning("[PLEX更新] Plex API缺少scan_library方法，无法触发单文件扫描")
            return 0
        
        # 检测是否包含WebDAV路径（更通用的检测方法）
        contains_webdav_path = any('webdav' in fp.lower() for fp in file_paths)
        if contains_webdav_path:
            logger.info(f"[PLEX更新] [WebDAV路径] 检测到包含WebDAV路径的文件列表，共{len(file_paths)}个文件")
        
        # 去重处理，避免重复扫描相同的文件路径
        unique_file_paths = list(set(file_paths))
        
        # 对于WebDAV路径，增加特殊的文件类型过滤
        if contains_webdav_path:
            # 定义常见的辅助文件扩展名（海报、字幕等）
            auxiliary_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.nfo', '.srt', '.ass', '.sub', '.idx'}
            
            # 过滤辅助文件，只扫描主要媒体文件
            main_media_files = []
            auxiliary_files = []
            
            for file_path in unique_file_paths:
                _, ext = os.path.splitext(file_path.lower())
                if ext in auxiliary_extensions:
                    auxiliary_files.append(file_path)
                else:
                    main_media_files.append(file_path)
            
            # 记录过滤信息
            logger.info(f"[PLEX更新] [WebDAV路径] 过滤辅助文件: 保留{len(main_media_files)}个媒体文件，忽略{len(auxiliary_files)}个辅助文件（海报、字幕等）")
            
            # 使用过滤后的文件列表
            unique_file_paths = main_media_files
        logger.info(f"[PLEX更新] 开始触发单文件扫描，文件数量: {len(unique_file_paths)} (原始数量: {len(file_paths)}, 去重后减少: {len(file_paths) - len(unique_file_paths)}个)")
        
        # 为了避免请求过于频繁，添加延迟和配置
        # 确保scan_delay是浮点数类型，避免类型比较错误
        scan_delay = float(self.config.get('SCAN_DELAY_BETWEEN_FILES', 1.0))  # 默认为1秒
        wait_for_completion = self.config.get('WAIT_FOR_SCAN_COMPLETION', False)  # 是否等待扫描完成
        scan_timeout = self.config.get('SCAN_TIMEOUT_SECONDS', 300)  # 扫描超时时间
        # 确保batch_size是整数类型，避免类型比较错误
        batch_size = int(self.config.get('SCAN_BATCH_SIZE', '10'))  # 每批处理的文件数量
        
        # 获取目录合并相关配置
        enable_directory_merging = self.config.get_bool('ENABLE_DIRECTORY_MERGING', True)
        # 增加最大目录深度以支持多层嵌套的动画片目录
        max_directory_depth = self.config.get_int('MAX_DIRECTORY_DEPTH', 8)
        
        # 快速路径：如果文件数量较少，跳过复杂的目录合并逻辑
        if len(unique_file_paths) < 50:
            logger.info("[PLEX更新] 文件数量较少，使用简化的目录处理逻辑")
            # 简单的目录去重
            directories_to_scan = set(os.path.dirname(file_path) for file_path in unique_file_paths)
            directories_list = [(dir_path, [f for f in unique_file_paths if os.path.dirname(f) == dir_path]) for dir_path in directories_to_scan]
        elif contains_webdav_path:
            # 对于包含WebDAV路径的大量文件，调整目录合并策略
            logger.info(f"[PLEX更新] [WebDAV路径] 针对WebDAV路径调整目录合并策略")
            # 直接按电影目录级别合并，而不是深入处理每个文件
            directory_map = {}
            
            # 统计信息
            processed_count = 0
            merged_count = 0
            
            for file_path in unique_file_paths:
                # 同时支持电影和剧集的目录结构
                # 电影路径格式: /vol02/CloudDrive/WebDAV/电影/类型/电影名/电影文件
                # 剧集路径格式: /vol02/CloudDrive/WebDAV/电视剧/剧名/第1季/剧集文件
                # 动画片多层结构: /vol02/CloudDrive/WebDAV/电视剧/动画片/日韩动画/片名/剧集文件
                path_parts = file_path.split('/')
                processed_count += 1
                
                # 确定目录类型（电影或剧集）
                is_movie_path = '电影' in path_parts
                is_tv_path = '电视剧' in path_parts
                is_anime_path = '动画片' in path_parts
                
                # 根据目录类型应用不同的合并策略
                if is_movie_path and len(path_parts) >= 6:
                    # 电影目录：提取倒数第二层目录
                    target_dir = '/'.join(path_parts[:-1])
                elif is_anime_path and len(path_parts) >= 8:
                    # 动画片多层目录：提取倒数第二层目录（片名目录）
                    target_dir = '/'.join(path_parts[:-1])
                elif is_tv_path and len(path_parts) >= 7:
                    # 标准剧集目录：提取倒数第二层目录（季目录）
                    target_dir = '/'.join(path_parts[:-1])
                else:
                    # 标准处理：使用直接父目录
                    target_dir = os.path.dirname(file_path)
                    
                # 记录目录映射
                if target_dir not in directory_map:
                    directory_map[target_dir] = []
                    logger.debug(f"[PLEX更新] [WebDAV路径] 添加新目录: {target_dir}")
                else:
                    merged_count += 1
                    logger.debug(f"[PLEX更新] [WebDAV路径] 合并到已有目录: {target_dir}")
                
                # 添加所有文件，而不仅是一个代表文件
                # 这确保了所有剧集文件都能被正确处理
                if file_path not in directory_map[target_dir]:
                    directory_map[target_dir].append(file_path)
                    logger.debug(f"[PLEX更新] [WebDAV路径] 添加文件到目录映射: {file_path}")
            
            # 将目录转换为列表
            directories_list = list(directory_map.items())
            logger.info(f"[PLEX更新] [WebDAV路径] 电影目录合并完成: 处理{processed_count}个文件，合并{merged_count}个重复目录，共{len(directories_list)}个电影目录需要扫描")
            
            # 对于WebDAV路径，应用专用批处理参数
            # 确保批处理大小不超过5，注意将配置值转换为整数
            scan_batch_size = min(int(self.config.get('SCAN_BATCH_SIZE', '10')), 5)
            logger.info(f"[PLEX更新] [WebDAV路径] 应用WebDAV专用批处理设置：每批{scan_batch_size}个目录，扫描延迟2秒")
        else:
            # 对于非WebDAV路径，使用标准批处理大小，注意将配置值转换为整数
            scan_batch_size = int(self.config.get('SCAN_BATCH_SIZE', '10'))
            
            # 智能目录合并：分析所有文件路径，找出最顶层的目录进行扫描
            directory_map = {}
            for file_path in unique_file_paths:
                dir_path = os.path.dirname(file_path)
                if dir_path not in directory_map:
                    directory_map[dir_path] = []
                directory_map[dir_path].append(file_path)
            
            # 如果启用了目录合并，尝试合并父目录
            if enable_directory_merging:
                # 预先计算所有目录的深度，避免重复计算
                dir_depths = {dir_path: len(dir_path.split(os.sep)) for dir_path in directory_map.keys()}
                
                # 按目录深度进行排序，优先扫描更深的目录
                sorted_directories = sorted(directory_map.items(), key=lambda x: dir_depths[x[0]], reverse=True)
                
                logger.info(f"[PLEX更新] 已分析文件路径结构，识别出{len(sorted_directories)}个需要扫描的目录")
                
                # 合并较深的子目录到其更高级别的父目录
                merged_directories = {}
                processed_files = set()
                
                # 优化：使用集合快速检查文件是否已处理
                for dir_path, files_in_dir in sorted_directories:
                    # 检查目录深度是否超过限制
                    if dir_depths[dir_path] > max_directory_depth:
                        # 对于过深的目录，使用父目录
                        parent_dir = os.path.dirname(dir_path)
                        if parent_dir not in merged_directories:
                            merged_directories[parent_dir] = []
                        # 只添加未处理的文件
                        new_files = [f for f in files_in_dir if f not in processed_files]
                        merged_directories[parent_dir].extend(new_files)
                        processed_files.update(new_files)
                    else:
                        # 检查当前目录是否已经被其父目录覆盖
                        skip_directory = False
                        # 优化：限制已处理目录的遍历数量，提高性能
                        processed_dirs = list(merged_directories.keys())
                        # 只检查最近添加的20个目录，平衡性能和准确性
                        for existing_dir in processed_dirs[-20:]:
                            if dir_path.startswith(existing_dir) and dir_path != existing_dir:
                                # 这个目录已经被其父目录覆盖
                                skip_directory = True
                                break
                        
                        if not skip_directory:
                            merged_directories[dir_path] = files_in_dir
                            processed_files.update(files_in_dir)
                
                # 更新目录映射为合并后的结果
                directory_map = merged_directories
                logger.info(f"[PLEX更新] 目录合并完成，减少了{len(sorted_directories) - len(directory_map)}个目录，剩余{len(directory_map)}个目录需要扫描")
            
            # 将目录转换为列表
            directories_list = list(directory_map.items())
        
        # 优化：如果文件数量很少，直接处理而不分批
        if len(unique_file_paths) <= 5:
            dir_batches = [directories_list]
        else:
            # 分组处理目录，避免过多的请求
            dir_batches = []
            current_batch = []
            current_file_count = 0
            
            for dir_path, files_in_dir in directories_list:
                if current_file_count + len(files_in_dir) > batch_size and current_batch:
                    dir_batches.append(current_batch)
                    current_batch = []
                    current_file_count = 0
                current_batch.append((dir_path, files_in_dir))
                current_file_count += len(files_in_dir)
            
            if current_batch:
                dir_batches.append(current_batch)
        
        logger.info(f"[PLEX更新] 将目录分为{len(dir_batches)}批进行处理")
        
        # 优化：根据文件数量和路径类型动态调整等待时间
        def get_adjusted_delay(file_count, is_webdav=False, is_multi_level=False):
            # 基础延迟策略
            base_delay = 0.5  # 默认0.5秒
            if file_count <= 5:
                base_delay = 0.5  # 少量文件
            elif file_count <= 20:
                base_delay = 1.0  # 中等数量文件
            else:
                base_delay = 2.0  # 大量文件
                
            # 对于WebDAV路径，增加延迟以适应网络延迟
            if is_webdav:
                base_delay *= 1.5  # WebDAV路径增加50%延迟
                
            # 对于多层目录，进一步增加延迟以确保稳定性
            if is_multi_level:
                base_delay *= 1.2  # 多层目录再增加20%延迟
                
            return base_delay
        
        # 处理每一批目录
        for batch_idx, dir_batch in enumerate(dir_batches):
            batch_total_files = sum(len(files) for _, files in dir_batch)
            logger.info(f"[PLEX更新] 处理批次 {batch_idx + 1}/{len(dir_batches)}，包含{len(dir_batch)}个目录，{batch_total_files}个文件")
            
            # 优化：减少每个目录的详细日志，只记录批次级别摘要
            batch_success_count = 0
            
            for dir_path, files_in_dir in dir_batch:
                try:
                    # 执行扫描请求
                    scan_result = self.plex_api.scan_library(library_id, dir_path)
                    
                    if scan_result:
                        success_count += len(files_in_dir)
                        batch_success_count += len(files_in_dir)
                        logger.debug(f"[PLEX更新] ✅ 已向Plex服务器发送扫描请求，媒体库'{library_name}'已触发扫描")
                        logger.debug(f"[PLEX更新] 扫描目录: {dir_path}，相关文件数量: {len(files_in_dir)}")
                        
                        # 如果配置了等待扫描完成且Plex API支持该方法
                        if wait_for_completion and hasattr(self.plex_api, 'wait_for_scan_completion'):
                            logger.info(f"[PLEX更新] 等待Plex服务器完成扫描，超时时间: {scan_timeout}秒")
                            completion_result = self.plex_api.wait_for_scan_completion(library_id, scan_timeout)
                            if completion_result:
                                logger.info(f"[PLEX更新] ✅ Plex服务器扫描完成")
                            else:
                                logger.warning(f"[PLEX更新] ⏱️ Plex服务器扫描超时或未完成")
                        else:
                            # 优化：根据文件数量和路径类型动态调整等待时间
                            # 检测当前目录是否包含WebDAV路径和多层结构
                            dir_is_webdav = any(pattern in dir_path.lower() for pattern in ['webdav'])
                            dir_is_multi_level = len(dir_path.split('/')) > 6
                            
                            adjusted_delay = get_adjusted_delay(
                                len(files_in_dir), 
                                is_webdav=dir_is_webdav, 
                                is_multi_level=dir_is_multi_level
                            )
                            
                            if adjusted_delay > 0:
                                logger.debug(f"[PLEX更新] 等待{adjusted_delay}秒让Plex服务器处理请求")
                                time.sleep(adjusted_delay)
                    else:
                        logger.warning(f"[PLEX更新] ❌ 扫描请求发送失败: {dir_path}")
                except Exception as e:
                    logger.error(f"[PLEX更新] 处理目录{dir_path}时发生错误: {str(e)}")
            
            # 批次处理完成后记录摘要
            logger.info(f"[PLEX更新] 批次 {batch_idx + 1} 处理完成，成功扫描{batch_success_count}个文件，累计成功: {success_count}/{len(unique_file_paths)}")
            
            # 在批次之间添加延迟
            if batch_idx + 1 < len(dir_batches):
                # 优化：根据当前批次大小、路径类型调整下一批次的等待时间
                # 检查当前批次是否包含WebDAV路径和多层结构目录
                batch_has_webdav = any(any(pattern in dir_path.lower() for pattern in ['webdav']) for dir_path, _ in dir_batch)
                batch_has_multi_level = any(len(dir_path.split('/')) > 6 for dir_path, _ in dir_batch)
                
                adjusted_batch_delay = min(
                    scan_delay, 
                    get_adjusted_delay(
                        batch_total_files, 
                        is_webdav=batch_has_webdav, 
                        is_multi_level=batch_has_multi_level
                    )
                )
                logger.info(f"[PLEX更新] 批次处理完成，等待{adjusted_batch_delay}秒后继续下一批次")
                time.sleep(adjusted_batch_delay)
        
        logger.info(f"[PLEX更新] 单文件扫描完成，成功触发{success_count}个文件的扫描")
        return success_count

    def get_library_stats(self):
        """获取媒体库统计信息
        
        Returns:
            dict: 媒体库统计信息
        """
        stats = {
            'total_libraries': len(self.libraries),
            'by_type': {},
            'libraries': []
        }
        
        # 按类型统计
        for library in self.libraries:
            library_type = library.get('type', 'unknown')
            if library_type not in stats['by_type']:
                stats['by_type'][library_type] = 0
            stats['by_type'][library_type] += 1
            
            # 收集每个媒体库的基本信息
            library_info = {
                'id': library.get('id'),
                'name': library.get('name'),
                'type': library_type,
                'path': library.get('path', '')
            }
            stats['libraries'].append(library_info)
        
        logger.info(f"获取媒体库统计信息完成: 共{stats['total_libraries']}个媒体库")
        return stats