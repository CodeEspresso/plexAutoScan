#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plex API交互模块
"""

import os
import sys
import json
import time
import requests
import logging
from urllib.parse import urljoin
from datetime import datetime, timedelta

# 删除: 使用错误路径的绝对导入
# 新增: 使用正确的相对导入
from ..utils.logger import RobustLogger
from ..utils.config import Config
from ..utils.path_utils import normalize_path, verify_path
from .xml_processor import extract_paths, parse_plex_libraries

# 初始化日志记录器，使用与主程序相同的名称以确保日志正确输出
logger = RobustLogger('plex_autoscan')


class PlexAPI:
    """Plex API交互类，负责与Plex媒体服务器进行通信"""
    
    def __init__(self, config=None):
        """初始化Plex API客户端
        
        Args:
            config (Config): 配置对象
        """
        self.config = config or Config()
        
        # 从配置中获取相关设置
        self.plex_url = self.config.get('PLEX_URL', 'http://localhost:32400')
        self.plex_token = self.config.get('PLEX_TOKEN', '')
        # 确保获取的配置值为正确的数值类型
        self.api_timeout = float(self.config.get('PLEX_API_TIMEOUT', 30))
        self.max_retries = int(self.config.get('MAX_RETRIES', 3))
        self.retry_delay = float(self.config.get('RETRY_DELAY', 2))
        
        # 缓存设置
        self.cache_dir = self.config.get('CACHE_DIR', '/tmp/plex_cache')
        self.cache_ttl = self.config.get('CACHE_TTL', 3600)  # 默认1小时
        
        # 验证必要的配置
        if not self.plex_token:
            logger.error("PLEX_TOKEN未设置，无法与Plex服务器通信")
            raise ValueError("PLEX_TOKEN未设置")
        
        # 会话设置
        self.session = requests.Session()
        self.session.headers = {
            'X-Plex-Token': self.plex_token,
            'Accept': 'application/json'
        }
        
        # 确保缓存目录存在
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _make_request(self, endpoint, method='GET', params=None, data=None, headers=None, retry=True):
        """发送HTTP请求到Plex API
        
        Args:
            endpoint (str): API端点
            method (str): HTTP方法
            params (dict): URL参数
            data (dict): 请求数据
            headers (dict): 额外的请求头
            retry (bool): 是否重试失败的请求
            
        Returns:
            dict: 响应数据
        """
        url = urljoin(self.plex_url, endpoint)
        
        # 合并请求头
        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)
        
        # 重试机制
        retries = 0
        while True:
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    headers=request_headers,
                    timeout=self.api_timeout
                )
                
                # 检查响应状态
                response.raise_for_status()
                
                # 尝试解析JSON响应
                try:
                    return response.json()
                except json.JSONDecodeError:
                    # 特殊处理refresh端点，这些端点通常返回空响应或XML而非JSON
                    if 'refresh' in endpoint:
                        logger.info(f"Plex refresh API返回非JSON响应，这是正常现象: {endpoint}")
                        # 检查响应是否为空或HTML/XML
                        if not response.text or response.text.strip().startswith('<?xml') or '<html' in response.text.lower():
                            # 对于refresh端点，只要HTTP状态码成功，就认为请求成功
                            return {'success': True}
                    
                    # 检查响应是否为XML格式
                    if response.text.strip().startswith('<?xml'):
                        logger.info(f"Plex API返回XML格式响应，尝试解析: {endpoint}")
                        try:
                            # 使用xml_processor模块提取路径信息
                            paths = extract_paths(response.text)
                            # 返回处理后的XML数据
                            return {'xml_data': True, 'paths': paths, 'raw_xml': response.text}
                        except Exception as xml_error:
                            logger.warning(f"XML解析失败: {str(xml_error)}")
                    
                    error_message = f"无法解析Plex API响应为JSON: {endpoint}"
                    logger.warning(error_message)
                    return {'error': error_message, 'raw_response': response.text}
                
            except requests.exceptions.RequestException as e:
                retries += 1
                
                if not retry or retries > self.max_retries:
                    logger.error(f"Plex API请求失败 {endpoint}: {str(e)}")
                    return {'error': str(e), 'status': 'failed'}
                
                # 计算退避时间
                delay = self.retry_delay * (2 ** (retries - 1))
                logger.warning(f"Plex API请求失败，{delay}秒后重试 ({retries}/{self.max_retries}): {str(e)}")
                
                # 等待退避时间
                time.sleep(delay)
    
    def get_plex_media_libraries(self):
        """获取所有Plex媒体库
        
        Returns:
            list: 媒体库列表
        """
        cache_key = 'media_libraries'
        
        # 尝试从缓存中获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        # 发送API请求
        result = self._make_request('/library/sections')
        
        if 'error' in result:
            return []
        
        # 解析响应
        media_libraries = []
        try:
            # 检查是否为XML响应
            if 'xml_data' in result:
                logger.info("处理Plex媒体库的XML响应")
                # 使用专门的XML解析函数解析媒体库信息
                media_libraries = parse_plex_libraries(result['raw_xml'])
                logger.info(f"从XML响应中解析出{len(media_libraries)}个媒体库")
            else:
                # 根据Plex API的JSON响应格式进行解析
                if 'MediaContainer' in result and 'Directory' in result['MediaContainer']:
                    for library in result['MediaContainer']['Directory']:
                        media_libraries.append({
                            'id': library.get('key'),
                            'name': library.get('title'),
                            'type': library.get('type'),
                            'path': library.get('path', '')
                        })
        except Exception as e:
            logger.error(f"解析Plex媒体库失败: {str(e)}")
        
        # 保存到缓存
        self._save_to_cache(cache_key, media_libraries)
        
        logger.info(f"获取到{len(media_libraries)}个Plex媒体库")
        return media_libraries
    
    def trigger_plex_scan(self, library_id, scan_path=None):
        """触发Plex媒体库扫描
        
        Args:
            library_id (str): 媒体库ID
            scan_path (str): 可选，要扫描的具体路径
        
        Returns:
            dict: 扫描结果
        """
        try:
            # 构建API端点
            endpoint = f'/library/sections/{library_id}/refresh'
            
            # 准备参数
            params = {}
            if scan_path:
                # 确保路径正确编码
                encoded_path = scan_path.encode('utf-8', errors='replace').decode('utf-8')
                params['path'] = encoded_path
                logger.info(f"触发Plex扫描: 媒体库ID={library_id}, 路径={encoded_path}")
            else:
                logger.info(f"触发Plex扫描: 整个媒体库ID={library_id}")
            
            # 发送请求
            result = self._make_request(endpoint, method='GET', params=params)
            
            # 检查响应
            if result.get('status_code') == 200 or 'error' not in result:
                logger.info(f"Plex扫描请求已发送成功: {library_id}")
                return {'success': True}
            else:
                logger.error(f"Plex扫描请求失败: {result.get('error', '未知错误')}")
                return {'success': False, 'error': result.get('error', '未知错误')}
        except Exception as e:
            logger.error(f"触发Plex扫描异常: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def scan_library(self, library_id, path=None):
        """触发Plex媒体库扫描
        
        Args:
            library_id (str): 媒体库ID
            path (str): 可选，要扫描的特定路径
            
        Returns:
            bool: 扫描请求是否成功发送
        """
        try:
            # 构建扫描端点
            endpoint = f'/library/sections/{library_id}/refresh'
            
            # 如果提供了路径参数，添加到请求中
            params = None
            if path:
                params = {'path': path}
                logger.info(f"触发媒体库 {library_id} 扫描特定路径: {path}")
            else:
                logger.info(f"触发媒体库 {library_id} 全面扫描")
            
            # 发送扫描请求
            result = self._make_request(endpoint, method='GET', params=params)
            
            # 检查请求是否成功
            if result and not result.get('error'):
                logger.info(f"成功触发Plex媒体库扫描: {library_id}")
                return True
            else:
                logger.error(f"触发Plex媒体库扫描失败: {result.get('error', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"触发Plex媒体库扫描时发生异常: {str(e)}")
            return False
            
    def wait_for_scan_completion(self, library_id, timeout=300):
        """等待Plex扫描完成
        
        Args:
            library_id (str): 媒体库ID
            timeout (int): 超时时间（秒）
            
        Returns:
            bool: 是否在超时前完成扫描
        """
        start_time = time.time()
        
        # 初始等待时间，给Plex服务器一些时间开始处理
        initial_wait = 5
        logger.debug(f"[PLEX扫描] 初始等待{initial_wait}秒让Plex服务器开始处理扫描请求")
        time.sleep(initial_wait)
        
        while time.time() - start_time < timeout:
            # 检查扫描状态
            endpoint = f'/library/sections/{library_id}'
            result = self._make_request(endpoint, retry=False)  # 不重试，避免等待时间过长
            
            if 'error' in result:
                logger.warning(f"检查扫描状态失败: {result['error']}")
                time.sleep(5)
                continue
            
            # 检查扫描状态（根据实际的Plex API响应格式调整）
            try:
                # 尝试多种可能的扫描状态表示
                scan_complete = False
                if 'MediaContainer' in result:
                    # 检查scannerState
                    if result['MediaContainer'].get('scannerState') == 'idle':
                        scan_complete = True
                    # 检查其他可能的完成标志
                    elif result['MediaContainer'].get('busy') == '0' or not result['MediaContainer'].get('busy'):
                        scan_complete = True
                        
                if scan_complete:
                    elapsed_time = int(time.time() - start_time)
                    logger.info(f"[PLEX扫描] ✅ 媒体库 {library_id} 扫描已完成，耗时 {elapsed_time}秒")
                    return True
            except Exception as e:
                logger.error(f"解析扫描状态失败: {str(e)}")
            
            # 等待一段时间后再次检查
            elapsed_time = int(time.time() - start_time)
            remaining_time = timeout - elapsed_time
            logger.debug(f"[PLEX扫描] 等待扫描完成... (已等待: {elapsed_time}秒，剩余: {remaining_time}秒)")
            
            # 动态调整检查间隔，避免过于频繁的检查
            check_interval = min(10, max(5, remaining_time // 10))
            time.sleep(check_interval)
        
        logger.warning(f"[PLEX扫描] ⏱️ 媒体库 {library_id} 扫描超时 ({timeout}秒)")
        return False
    
    def get_plex_server_info(self):
        """获取Plex服务器信息
        
        Returns:
            dict: 服务器信息
        """
        cache_key = 'server_info'
        
        # 尝试从缓存中获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        # 发送API请求
        result = self._make_request('/')
        
        if 'error' in result:
            return {'error': result['error']}
        
        # 解析响应
        server_info = {}
        try:
            if 'MediaContainer' in result:
                server_info = {
                    'friendly_name': result['MediaContainer'].get('friendlyName'),
                    'machine_identifier': result['MediaContainer'].get('machineIdentifier'),
                    'version': result['MediaContainer'].get('version'),
                    'platform': result['MediaContainer'].get('platform'),
                    'platform_version': result['MediaContainer'].get('platformVersion')
                }
        except Exception as e:
            logger.error(f"解析Plex服务器信息失败: {str(e)}")
        
        # 保存到缓存
        self._save_to_cache(cache_key, server_info)
        
        logger.info(f"获取Plex服务器信息成功: {server_info.get('friendly_name')} (v{server_info.get('version')})")
        return server_info
    
    def get_library_files(self, library_id):
        """获取媒体库中的所有文件
        
        Args:
            library_id (str): 媒体库ID
            
        Returns:
            list: 文件列表
            
        [MOD] 2026-02-24 修复：移除 type 参数限制，获取所有类型的媒体 by AI
        """
        cache_key = f'library_files_{library_id}'
        
        # 尝试从缓存中获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        # 发送API请求
        endpoint = f'/library/sections/{library_id}/all'
        # [MOD] 移除 type 参数限制，获取所有类型的媒体（电影、电视剧、音乐等）
        # 原来的 type: 1 只获取电影，导致电视剧目录返回空列表
        params = {
            'includeGuids': 1
        }
        
        result = self._make_request(endpoint, params=params)
        
        if 'error' in result:
            logger.error(f"Plex API 返回错误: {result.get('error')}")
            return []
        
        # [MOD] 调试：记录 API 响应结构（使用 INFO 级别便于排查问题）
        if 'MediaContainer' in result:
            mc = result['MediaContainer']
            logger.info(f"Plex API 响应: MediaContainer 包含键: {list(mc.keys())}")
            if 'Metadata' in mc:
                logger.info(f"Metadata 数量: {len(mc['Metadata'])}")
                if mc['Metadata']:
                    first_item = mc['Metadata'][0]
                    logger.info(f"第一个 Metadata 项的键: {list(first_item.keys())}")
                    logger.info(f"第一个 Metadata 项的 type: {first_item.get('type')}")
                    if 'Media' in first_item:
                        logger.info(f"第一个 Metadata 项包含 Media: {first_item['Media']}")
                    else:
                        logger.info(f"第一个 Metadata 项不包含 Media 键")
            else:
                logger.info("MediaContainer 不包含 Metadata 键")
        else:
            logger.info(f"Plex API 响应不包含 MediaContainer: {list(result.keys())}")
        
        # 解析响应
        files = []
        try:
            if 'MediaContainer' in result and 'Metadata' in result['MediaContainer']:
                for item in result['MediaContainer']['Metadata']:
                    item_type = item.get('type', '')
                    
                    # [MOD] 2026-02-24 支持电视剧类型 by AI
                    # 电影/音乐：直接从 Media > Part 获取文件路径
                    # 电视剧：需要从剧集获取季和集的信息
                    if item_type == 'show':
                        # 电视剧类型：需要获取每一集的文件信息
                        show_files = self._get_show_files(item.get('ratingKey'))
                        files.extend(show_files)
                    elif 'Media' in item and item['Media']:
                        # 电影/音乐类型：直接获取文件信息
                        media = item['Media'][0]
                        if 'Part' in media and media['Part']:
                            part = media['Part'][0]
                            files.append({
                                'id': item.get('ratingKey'),
                                'title': item.get('title'),
                                'type': item.get('type'),
                                'path': part.get('file'),
                                'size': part.get('size'),
                                'duration': media.get('duration'),
                                'added_at': self._convert_plex_timestamp(item.get('addedAt'))
                            })
        except Exception as e:
            logger.error(f"解析媒体库文件失败: {str(e)}")
        
        # 保存到缓存
        self._save_to_cache(cache_key, files)
        
        logger.info(f"获取到媒体库{library_id}中的{len(files)}个文件")
        return files
    
    def _get_show_files(self, show_rating_key):
        """[MOD] 获取电视剧剧集的文件列表
        
        Args:
            show_rating_key (str): 剧集的 ratingKey
            
        Returns:
            list: 文件列表
        """
        files = []
        try:
            # 获取剧集的所有季
            seasons_endpoint = f'/library/metadata/{show_rating_key}/children'
            seasons_result = self._make_request(seasons_endpoint)
            
            if 'error' in seasons_result:
                return files
            
            if 'MediaContainer' not in seasons_result or 'Metadata' not in seasons_result['MediaContainer']:
                return files
            
            # 遍历每一季
            for season in seasons_result['MediaContainer']['Metadata']:
                season_key = season.get('ratingKey')
                if not season_key:
                    continue
                
                # 获取这一季的所有集
                episodes_endpoint = f'/library/metadata/{season_key}/children'
                episodes_result = self._make_request(episodes_endpoint)
                
                if 'error' in episodes_result:
                    continue
                
                if 'MediaContainer' not in episodes_result or 'Metadata' not in episodes_result['MediaContainer']:
                    continue
                
                # 遍历每一集，获取文件信息
                for episode in episodes_result['MediaContainer']['Metadata']:
                    if 'Media' in episode and episode['Media']:
                        for media in episode['Media']:
                            if 'Part' in media and media['Part']:
                                for part in media['Part']:
                                    files.append({
                                        'id': episode.get('ratingKey'),
                                        'title': episode.get('title'),
                                        'type': 'episode',
                                        'path': part.get('file'),
                                        'size': part.get('size'),
                                        'duration': media.get('duration'),
                                        'added_at': self._convert_plex_timestamp(episode.get('addedAt'))
                                    })
            
            logger.debug(f"获取剧集 {show_rating_key} 的文件列表: {len(files)} 个文件")
            
        except Exception as e:
            logger.error(f"获取电视剧文件列表失败: {str(e)}")
        
        return files
    
    def _convert_plex_timestamp(self, timestamp):
        """转换Plex时间戳为可读日期时间
        
        Args:
            timestamp (int): Plex时间戳
            
        Returns:
            str: 格式化的日期时间字符串
        """
        if not timestamp:
            return ''
        
        try:
            # Plex使用的是Unix时间戳（秒）
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            logger.error(f"转换时间戳失败: {str(e)}")
            return ''
    
    def _get_from_cache(self, cache_key):
        """从缓存中获取数据
        
        Args:
            cache_key (str): 缓存键
            
        Returns:
            缓存数据或None
        """
        try:
            cache_file = os.path.join(self.cache_dir, f'{cache_key}.json')
            
            # 检查缓存文件是否存在
            if not os.path.exists(cache_file):
                return None
            
            # 检查缓存是否过期
            file_mtime = os.path.getmtime(cache_file)
            current_time = time.time()
            
            if current_time - file_mtime > self.cache_ttl:
                logger.debug(f"缓存已过期: {cache_key}")
                return None
            
            # 读取缓存数据
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            logger.debug(f"从缓存中获取数据: {cache_key}")
            return data
        except Exception as e:
            logger.error(f"从缓存中读取数据失败 {cache_key}: {str(e)}")
            return None
    
    def _save_to_cache(self, cache_key, data):
        """保存数据到缓存
        
        Args:
            cache_key (str): 缓存键
            data: 要保存的数据
        """
        try:
            cache_file = os.path.join(self.cache_dir, f'{cache_key}.json')
            
            # 确保缓存目录存在
            os.makedirs(self.cache_dir, exist_ok=True)
            
            # 保存数据到文件
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"数据已保存到缓存: {cache_key}")
        except Exception as e:
            logger.error(f"保存数据到缓存失败 {cache_key}: {str(e)}")
    
    def clear_cache(self, cache_key=None):
        """清理缓存
        
        Args:
            cache_key (str): 要清理的缓存键，None表示清理所有缓存
            
        Returns:
            int: 清理的缓存文件数量
        """
        try:
            if not os.path.exists(self.cache_dir):
                logger.warning(f"缓存目录不存在: {self.cache_dir}")
                return 0
            
            cleared_count = 0
            
            if cache_key:
                # 清理特定缓存
                cache_file = os.path.join(self.cache_dir, f'{cache_key}.json')
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    cleared_count += 1
                    logger.info(f"已清理特定缓存: {cache_key}")
            else:
                # 清理所有缓存
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.json'):
                        cache_file = os.path.join(self.cache_dir, filename)
                        os.remove(cache_file)
                        cleared_count += 1
                logger.info(f"已清理所有缓存文件: {cleared_count}个")
            
            return cleared_count
        except Exception as e:
            logger.error(f"清理缓存失败: {str(e)}")
            return 0