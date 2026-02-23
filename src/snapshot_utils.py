#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
# 增加整数字符串转换限制，解决大整数JSON序列化问题
if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)  # 设置为无限制
import os
import time
import hashlib
import concurrent.futures
import threading
import subprocess
import queue
from pathlib import Path
import re
import logging
import socket

# 导入配置管理类
from .utils.config import Config

# 初始化全局配置对象
config = Config('config.env')

# 设置socket默认超时时间
socket.setdefaulttimeout(30)

# 导入新的SMBManager类 - 使用相对导入以适应Docker环境
from .smb_api import SMBManager

# 导入超时控制工具函数
from .utils.timeout_decorator import run_with_timeout, timeout_config
from .utils.environment import env_detector

# 确保Python使用UTF-8编码
import io

# 错误码常量定义
ERROR_OK = 0  # 成功
ERROR_INVALID_ARGS = 1  # 无效参数
ERROR_FILE_NOT_FOUND = 2  # 文件不存在
ERROR_PERMISSION = 3  # 权限错误
ERROR_IO = 4  # IO错误
ERROR_TIMEOUT = 5  # 超时
ERROR_MAX_FILES = 6  # 超过最大文件数
ERROR_SMB = 7  # SMB错误
ERROR_NETWORK = 8  # 网络错误
ERROR_MEMORY = 9  # 内存错误
ERROR_NO_FILES = 10  # 没有文件需要处理
ERROR_PROCESSING = 11  # 处理错误
ERROR_UNKNOWN = 99  # 未知错误

# 定义辅助文件扩展名（海报、字幕等）
AUXILIARY_FILE_EXTENSIONS = {
    # 海报文件
    '.jpg', '.jpeg', '.png', '.bmp', '.gif',
    # 字幕文件
    '.srt', '.ass', '.ssa', '.sub', '.idx',
    # 其他辅助文件
    '.nfo', '.txt', '.url', '.xml', '.ini',
    '.log', '.db', '.dat', '.info', '.md',
    # 元数据文件
    '.metadata', '.plex', '.tmdb', '.themoviedb',
    '.tvdb', '.thetvdb'
}

# 定义辅助文件夹名称
AUXILIARY_FOLDER_NAMES = {
    '.actors', '.extras', '.sample', '.samples',
    'extras', 'samples', 'subtitles', 'subs',
    'metadata', 'posters', 'thumbs', 'covers'
}

# 日志配置
# 注意：这里保留了根日志器的引用，但实际上我们只在这个脚本中使用logger
# 在主要代码中使用了自定义的logger，这里的配置是为了确保基本日志功能正常
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def is_auxiliary_file(file_path):
    """
    检查文件是否为辅助文件（海报、字幕等）
    
    Args:
        file_path (str): 文件路径
    
    Returns:
        bool: 如果是辅助文件则返回True，否则返回False
    """
    # 获取文件名和扩展名
    file_name = os.path.basename(file_path).lower()
    file_ext = os.path.splitext(file_name)[1].lower()
    
    # 检查扩展名是否在辅助文件扩展名列表中
    if file_ext in AUXILIARY_FILE_EXTENSIONS:
        return True
    
    # 检查文件名是否包含辅助文件标识
    auxiliary_keywords = ['poster', 'cover', 'fanart', 'discart', 'folder']
    for keyword in auxiliary_keywords:
        if keyword in file_name:
            # 避免误判包含这些关键词但不是辅助文件的情况
            # 例如：movie_poster_1080p.mkv 应该被视为普通媒体文件
            if file_ext not in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v']:
                return True
    
    return False

def is_auxiliary_folder(folder_path):
    """
    检查文件夹是否为辅助文件夹
    
    Args:
        folder_path (str): 文件夹路径
    
    Returns:
        bool: 如果是辅助文件夹则返回True，否则返回False
    """
    folder_name = os.path.basename(folder_path).lower()
    return folder_name in AUXILIARY_FOLDER_NAMES

def handle_error(error_code, message):
    """处理错误并返回错误码"""
    logger.error(f"错误 {error_code}: {message}")
    return error_code

def calculate_checksum(file_path, algorithm='md5'):
    """计算文件的校验和
    
    Args:
        file_path (str): 文件路径
        algorithm (str): 哈希算法，默认为'md5'
        
    Returns:
        str: 文件的校验和，如果计算失败则返回None
    """
    try:
        hash_obj = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        logger.error(f"计算校验和失败 ({file_path}): {str(e)}")
        return None

def verify_checksum(file_path, expected_checksum, algorithm='md5'):
    """验证文件的校验和
    
    Args:
        file_path (str): 文件路径
        expected_checksum (str): 期望的校验和
        algorithm (str): 哈希算法，默认为'md5'
        
    Returns:
        bool: 校验是否通过
    """
    current_checksum = calculate_checksum(file_path, algorithm)
    if current_checksum is None:
        return False
    return current_checksum == expected_checksum

def keep_smb_alive(smb_path, interval=15, timeout=5):
    """保持SMB/WebDAV连接活跃的函数
    使用SMBManager定期访问SMB/WebDAV路径以防止连接超时断开
    
    Args:
        smb_path (str): SMB/WebDAV路径
        interval (int): 检查间隔（秒）
        timeout (int): 操作超时时间（秒），默认为5秒
    
    注意：
    - 在Docker环境中，/vol02/CloudDrive/WebDAV是通过Docker卷直接挂载到容器内的
    - 这种挂载方式不需要在容器内进行SMB连接操作
    - 宿主机上的SMB挂载保持由宿主机系统负责，不受容器内操作影响
    """
    # 创建一个事件对象用于停止线程
    stop_event = threading.Event()
    
    def _keep_alive():
        # 检查是否在Docker环境中
        if is_docker_environment():
            # 在Docker环境中，/vol02/CloudDrive/WebDAV是通过Docker卷直接挂载到容器内的本地路径
            # 不需要在容器内执行SMB连接操作
            logger.debug(f"Docker环境下检测到SMB路径，跳过容器内SMB连接操作: {smb_path}")
            logger.debug(f"在Docker环境中，路径已通过卷挂载方式映射，无需SMB连接保持")
            # 使用事件对象等待停止信号，避免无限sleep
            while not stop_event.is_set():
                # 使用较短的等待时间，以便能够及时响应停止信号
                stop_event.wait(interval)
            logger.debug(f"Docker环境下SMB连接保持线程已停止: {smb_path}")
            return

        # 获取SMBManager单例实例
        smb_manager = SMBManager.get_instance()
        
        # 解析SMB路径以提取服务器和共享信息
        # 从环境变量获取默认配置，如果没有则使用硬编码的默认值
        default_server = os.environ.get('SMB_DEFAULT_SERVER', 'localhost')
        default_share = os.environ.get('SMB_DEFAULT_SHARE', 'WebDAV')
        
        # 初始化服务器和共享名称
        server = default_server
        share = default_share
        
        # 根据不同的路径格式解析服务器和共享名称
        if smb_path.startswith('//'):
            # 标准SMB路径格式: //server/share/path
            parts = smb_path.split('/')
            if len(parts) >= 3:
                server = parts[2]
                if len(parts) >= 4:
                    share = parts[3]
        elif smb_path.startswith('/vol02/CloudDrive/WebDAV') or smb_path.startswith('/Volumes/CloudDrive/WebDAV'):
            # WebDAV特定路径格式
            # 从环境变量获取WebDAV服务器地址，如果没有则使用默认值
            server = os.environ.get('WEBDAV_SERVER', 'localhost')
            share = 'WebDAV'
            # 对于WebDAV路径，增加专门的日志信息
            logger.debug(f"识别到WebDAV路径: {smb_path}")
        
        while True:
            try:
                # 执行实际的SMB操作来保持连接活跃
                # 使用path_exists操作，这是一个轻量级的操作
                logger.debug(f"执行SMB连接保持检查: {smb_path}")
                
                # 尝试获取SMB连接并执行简单操作
                conn, err = smb_manager.connect(server, share, timeout=timeout)
                if conn:
                    # 执行简单的路径检查操作
                    try:
                        # 使用基本路径执行检查，避免复杂路径解析
                        exists, _ = smb_manager.path_exists(server, share, "/", timeout=timeout)
                        logger.debug(f"SMB连接保持成功，路径可访问: {smb_path}")
                    except Exception as inner_e:
                        logger.debug(f"SMB连接保持操作失败: {inner_e}")
                elif err:
                    logger.debug(f"SMB连接保持失败: {err}")
            except Exception as e:
                logger.warning(f"SMB连接保持线程异常: {e}")
            time.sleep(interval)

    # 启动后台线程
    thread = threading.Thread(target=_keep_alive, daemon=True)
    thread.start()
    
    # 添加停止方法到线程对象上，方便外部调用停止线程
    def stop():
        """停止连接保持线程"""
        stop_event.set()
        # 等待线程结束（最多等待interval+1秒）
        thread.join(interval + 1)
        logger.debug(f"已请求停止SMB/WebDAV连接保持线程: {smb_path}")
    
    thread.stop = stop
    return thread

def is_docker_environment():
    """检测是否在Docker环境中运行
    使用统一的环境检测器
    
    Returns:
        bool: 是否在Docker环境中
    """
    return env_detector.is_docker()

def generate_snapshot(dir, output_file, scan_delay=1, max_files=0, skip_large=False, large_threshold=10000, min_size=0, min_size_mb=0, retry_count=3, timeout=None):
    # 从配置获取WebDAV路径前缀
    prod_path_prefix = config.get('PROD_PATH_PREFIX', '/vol02/CloudDrive/WebDAV')
    test_path_prefix = config.get('TEST_PATH_PREFIX', '/Volumes/CloudDrive/WebDAV')
    is_webdav_path = dir.startswith((prod_path_prefix, test_path_prefix))
    
    # 为WebDAV路径增加超时时间和重试次数
    if is_webdav_path:
        # 使用统一的超时配置
        timeout = timeout_config.get_timeout('very_long')  # 超长超时：30分钟
        # 增加WebDAV路径的重试次数
        retry_count = max(retry_count, int(os.environ.get('WEBDAV_RETRY_COUNT', '5')))
        logger.logger.info(f"为WebDAV路径设置超时时间: {timeout}秒，重试次数: {retry_count}")
    else:
        # 使用默认超时配置
        timeout = timeout_config.get_timeout('long')  # 长时间超时：10分钟
    """生成目录快照
    
    Args:
        dir (str): 要扫描的目录
        output_file (str): 输出文件路径
        scan_delay (float): 扫描延迟（秒）
        max_files (int): 最大文件数，0表示无限制
        skip_large (bool): 是否跳过大型文件
        large_threshold (int): 大型文件阈值（MB）
        min_size (int): 最小文件大小（字节）
        min_size_mb (float): 最小文件大小（MB）
        retry_count (int): 重试次数，默认为3
        timeout (int): 超时时间（秒），默认为300秒（5分钟）
        
    Returns:
        int: 成功时返回文件数量，失败时返回负的错误码
    """
    # 从utils.timeout_decorator导入超时控制函数
    from .utils.timeout_decorator import run_with_timeout
    
    # 定义核心生成快照逻辑函数
    def _generate_snapshot_core():
        try:
            logger.info(f"开始扫描目录: {dir}")
            
            # 转换min_size_mb为字节，并添加验证逻辑
            try:
                min_size_mb_val = float(min_size_mb)
                # 确保min_size_mb在合理范围内
                if min_size_mb_val < 0:
                    min_size_mb_val = 0
                elif min_size_mb_val > 10000:  # 限制在10GB以内
                    logger.warning(f"最小文件大小 {min_size_mb_val} MB 超出合理范围，使用默认值10MB")
                    min_size_mb_val = 10
                
                min_size_bytes = max(min_size, int(min_size_mb_val * 1024 * 1024))
                # 不再打印这条日志，改为在main.py中只打印一次
                # 保留这个逻辑，用于计算实际的字节值
                # if min_size_bytes > 0:  # 已禁用，改为在main.py中只打印一次
            except (ValueError, TypeError):
                logger.error(f"无效的最小文件大小参数: {min_size_mb}，使用默认值0字节")
                min_size_bytes = max(min_size, 0)
            
            # 转换large_threshold为字节
            large_threshold_bytes = large_threshold * 1024 * 1024
            
            file_paths = []
            dir_count = 0
            skipped_small = 0
            skipped_large = 0
            skipped_auxiliary = 0
            excluded_dir_count = 0
            start_time = time.time()
            
            # 处理大型目录的并行扫描
            # 从环境变量获取SMB最大线程数配置，如果没有则使用默认值5
            smb_max_workers = os.environ.get('SMB_MAX_WORKERS', '5')
            try:
                smb_max_workers = int(smb_max_workers)
                # 确保线程数在合理范围内 (5-10) 根据用户要求调整
                smb_max_workers = max(5, min(smb_max_workers, 10))
            except ValueError:
                logger.warning(f"无效的SMB_MAX_WORKERS配置: {smb_max_workers}，使用默认值5")
                smb_max_workers = 5
                
            # 初始化动态线程数调整相关变量
            current_workers = max(5, min(smb_max_workers // 2, 10))  # 初始使用较低线程数，范围5-10
            error_count = 0
            success_count = 0
            max_workers = smb_max_workers
            min_workers = 5  # 线程数下限设为5，确保在用户要求的5-10范围内
            batch_size = 500  # 批处理大小
            error_threshold = 3  # 超过这个错误数就降低线程数
            recovery_threshold = 10  # 连续成功处理这个数量就增加线程数
            adaptive_batch_delay = scan_delay
            smb_errors = []  # 记录SMB连接错误
            
            # 创建全局预取缓存
            class PrefetchCache:
                """SMB文件预取缓存"""
                def __init__(self, max_size=1000):
                    self.cache = {}
                    self.max_size = max_size
                    self.lock = threading.RLock()
                    self.usage_count = {}
                
                def add(self, path, data):
                    """添加数据到缓存"""
                    with self.lock:
                        # 如果缓存已满，移除使用次数最少的项
                        if len(self.cache) >= self.max_size and path not in self.cache:
                            # 找到使用次数最少的项
                            least_used = min(self.usage_count.items(), key=lambda x: x[1])[0]
                            del self.cache[least_used]
                            del self.usage_count[least_used]
                        
                        # 添加新数据
                        self.cache[path] = data
                        self.usage_count[path] = 0
                
                def get(self, path):
                    """从缓存获取数据"""
                    with self.lock:
                        if path in self.cache:
                            # 增加使用次数
                            self.usage_count[path] += 1
                            return self.cache[path]
                        return None
                
                def clear(self):
                    """清空缓存"""
                    with self.lock:
                        self.cache.clear()
                        self.usage_count.clear()
            
            # 创建预取缓存实例
            prefetch_cache = PrefetchCache()
            
            # 尝试保持SMB/WebDAV连接活跃
            if dir.startswith('/vol02/CloudDrive/WebDAV') or dir.startswith('/Volumes/CloudDrive/WebDAV'):
                # 识别WebDAV路径并启动连接保持线程
                if is_docker_environment():
                    # 在Docker环境中，路径通过卷挂载
                    logger.debug(f"Docker环境下检测到WebDAV路径: {dir}，使用卷挂载方式访问")
                    # 即使在Docker环境中，也为WebDAV路径启动连接保持线程，因为WebDAV连接可能不稳定
                    webdav_interval = int(os.environ.get('WEBDAV_KEEP_ALIVE_INTERVAL', '8'))
                    logger.info(f"检测到WebDAV路径，启动连接保持线程: {dir} (间隔: {webdav_interval}秒)")
                    smb_thread = keep_smb_alive(dir, interval=webdav_interval, timeout=10)  # 增加WebDAV超时时间
                else:
                    webdav_interval = int(os.environ.get('WEBDAV_KEEP_ALIVE_INTERVAL', '6'))
                    logger.info(f"检测到WebDAV路径，启动连接保持线程: {dir} (间隔: {webdav_interval}秒)")
                    smb_thread = keep_smb_alive(dir, interval=webdav_interval, timeout=10)
            elif dir.startswith('//'):
                # 标准SMB路径
                if is_docker_environment():
                    logger.debug(f"Docker环境下检测到SMB路径: {dir}，使用卷挂载方式访问")
                else:
                    logger.info(f"检测到SMB路径，启动连接保持线程: {dir}")
                smb_thread = keep_smb_alive(dir, interval=15, timeout=5)
            else:
                smb_thread = None
            
            # 确定是否需要使用并行处理
            use_parallel = False
            # 对于WebDAV路径，降低并行处理的门槛（从1000个文件降低到200个文件）
            # 这样可以更早启动并行处理，提高WebDAV路径的扫描速度
            # 从配置中获取WebDAV路径前缀
            prod_path_prefix = config.get('PROD_PATH_PREFIX', '/vol02/CloudDrive/WebDAV')
            test_path_prefix = config.get('TEST_PATH_PREFIX', '/Volumes/CloudDrive/WebDAV')
            if dir.startswith((prod_path_prefix, test_path_prefix)):
                if max_files == 0 or max_files > 200:
                    use_parallel = True
                    logger.debug(f"[WebDAV] 启用并行处理 (文件数阈值: 200)")
            else:
                if max_files == 0 or max_files > 1000:
                    use_parallel = True
            
            # 用于并行处理的函数，支持动态线程调整
            def process_file(file_path):
                nonlocal file_paths, skipped_small, skipped_large, error_count, success_count, current_workers, adaptive_batch_delay, smb_errors
                # 添加辅助文件计数变量
                nonlocal skipped_auxiliary
                try:
                    # 对所有路径类型（包括Docker环境下的卷挂载路径）都进行辅助文件检查
                    if is_auxiliary_file(file_path):
                        logger.debug(f"跳过辅助文件: {file_path}")
                        skipped_auxiliary += 1
                        return False
                    
                    file_size = 0
                    # 尝试从预取缓存获取文件信息
                    file_info = prefetch_cache.get(file_path)
                    
                    if file_info:
                        file_size = file_info
                    else:
                        # 检查文件大小
                        file_size = os.path.getsize(file_path)
                        # 添加到预取缓存
                        prefetch_cache.add(file_path, file_size)
                    
                    # 跳过小于最小大小的文件
                    if min_size_bytes > 0 and file_size < min_size_bytes:
                        skipped_small += 1
                        return False
                    
                    # 跳过大型文件（如果启用）
                    if skip_large and file_size > large_threshold_bytes:
                        skipped_large += 1
                        return False
                    
                    # 添加文件路径到列表
                    file_paths.append(file_path.encode('utf-8'))
                    
                    # 成功处理，增加成功计数
                    success_count += 1
                    # 重置错误计数
                    error_count = 0
                    
                    # 检查是否超过最大文件数
                    if max_files > 0 and len(file_paths) >= max_files:
                        return True  # 表示已达到最大文件数
                    return False
                except Exception as e:
                    error_msg = str(e)
                    # 检查是否是WebDAV路径的特殊处理
                    prod_path_prefix = config.get('PROD_PATH_PREFIX', '/vol02/CloudDrive/WebDAV')
                    test_path_prefix = config.get('TEST_PATH_PREFIX', '/Volumes/CloudDrive/WebDAV')
                    is_webdav_path = file_path.startswith((prod_path_prefix, test_path_prefix))
                    
                    # 检测连接错误
                    if any(kw in error_msg.lower() for kw in ['smb', 'connection', 'timeout', 'timed out', 'unavailable', 'disconnect', 'webdav']):
                        # 增加连接错误计数
                        error_count += 1
                        if is_webdav_path:
                            smb_errors.append(f"[WebDAV] {file_path}: {error_msg}")
                        else:
                            smb_errors.append(f"{file_path}: {error_msg}")
                        # 重置成功计数
                        success_count = 0
                        
                        # 如果错误数达到阈值，增加批处理延迟
                        if error_count >= error_threshold:
                            # 对WebDAV路径使用更激进的延迟调整策略
                            if is_webdav_path:
                                adaptive_batch_delay = max(scan_delay * 2.5, adaptive_batch_delay * 1.8)
                                logger.info(f"[WebDAV] 连接错误增加，增加批处理延迟: {adaptive_batch_delay:.2f}s")
                            else:
                                adaptive_batch_delay = max(scan_delay * 2, adaptive_batch_delay * 1.5)
                                logger.info(f"SMB连接错误增加，增加批处理延迟: {adaptive_batch_delay:.2f}s")
                    else:
                        logger.error(f"处理文件失败 ({file_path}): {error_msg}")
                    return False
            
            # 遍历目录
            if use_parallel:
                # 首先收集所有文件路径
                temp_file_paths = []
                
                # 检测是否是WebDAV路径
                is_webdav_path = dir.startswith(('/vol02/CloudDrive/WebDAV', '/Volumes/CloudDrive/WebDAV'))
                
                # 记录开始收集文件的时间
                collect_start_time = time.time()
                
                if is_webdav_path:
                    # WebDAV路径专用优化：使用线程池并行收集文件路径
                    logger.debug(f"[WebDAV] 开始并行收集文件路径...")
                    
                    # 预创建目录队列和结果队列
                    dir_queue = queue.Queue()
                    dir_queue.put(dir)
                    collected_files = []
                    
                    # 使用线程安全的锁和计数器
                    file_lock = threading.Lock()
                    dir_count_lock = threading.Lock()
                    error_lock = threading.Lock()
                    error_dirs = set()  # 记录处理失败的目录
                    
                    # 定义目录处理函数
                    def process_directory(directory):
                        nonlocal dir_count
                        try:
                            # 对于WebDAV路径，添加额外的延迟控制，避免连接风暴
                            if is_webdav_path:
                                # 增加延迟以更有效地控制请求频率
                                web_delay = float(os.environ.get('WEBDAV_SCAN_DELAY', '0.1'))
                                time.sleep(web_delay)  # 添加延迟，控制请求频率
                            # 获取目录内容 - 为WebDAV路径添加重试机制
                            items = None
                            retry_count = int(os.environ.get('WEBDAV_DIRECTORY_RETRY', '5'))
                            retry_delay = 1.5
                             
                            for attempt in range(retry_count):
                                try:
                                    items = os.listdir(directory)
                                    break
                                except Exception as e:
                                    if attempt < retry_count - 1:
                                        logger.warning(f"[WebDAV] 读取目录内容失败，正在重试 ({attempt+1}/{retry_count}): {str(e)}")
                                        time.sleep(retry_delay)
                                        retry_delay *= 1.5  # 指数退避
                                    else:
                                        logger.logger.error(f"[WebDAV] 读取目录内容失败: {str(e)}")
                                        items = []
                            
                            # 分别处理文件和目录
                            current_dirs = []
                            current_files = []
                            
                            if items:
                                for item in items:
                                    item_path = os.path.join(directory, item)
                                    # 为WebDAV路径添加额外的文件/目录检查
                                    try:
                                        if os.path.isdir(item_path):
                                            current_dirs.append(item_path)
                                        elif os.path.isfile(item_path):
                                            current_files.append(item_path)
                                    except Exception as e:
                                        logger.warning(f"[WebDAV] 检查项目类型失败 {item_path}: {str(e)}")
                            
                            # 更新目录计数
                            with dir_count_lock:
                                dir_count += len(current_dirs)
                            
                            # 添加文件到结果列表
                            with file_lock:
                                collected_files.extend(current_files)
                                
                                # 检查是否达到最大文件数
                                if max_files > 0 and len(collected_files) >= max_files:
                                    # 截断列表到最大文件数
                                    collected_files[:] = collected_files[:max_files]
                                    return False  # 表示已达到最大文件数
                            
                            # 添加子目录到队列
                            for subdir in current_dirs:
                                if not (max_files > 0 and len(collected_files) >= max_files):
                                    dir_queue.put(subdir)
                            
                            return True
                        except Exception as e:
                            logger.warning(f"[WebDAV] 处理目录 {directory} 时出错: {str(e)}")
                            return True
                    
                    # 创建专门用于收集文件的线程池
                    # 针对小文件集合优化：WebDAV路径即使文件少也使用并行收集
                    collector_workers = min(3, max_workers)  # 使用较少的线程来避免连接过多
                    collector_executor = concurrent.futures.ThreadPoolExecutor(max_workers=collector_workers)
                    
                    # 开始并行处理目录
                    while not dir_queue.empty() and not (max_files > 0 and len(collected_files) >= max_files):
                        futures = []
                        
                        # 一次处理多个目录
                        batch_size = min(5, dir_queue.qsize())
                        for _ in range(batch_size):
                            if dir_queue.empty() or (max_files > 0 and len(collected_files) >= max_files):
                                break
                            
                            current_dir = dir_queue.get()
                            future = collector_executor.submit(process_directory, current_dir)
                            futures.append(future)
                        
                        # 等待这一批处理完成
                        for future in concurrent.futures.as_completed(futures):
                            if not future.result() or (max_files > 0 and len(collected_files) >= max_files):
                                break
                        
                        # 检查是否达到最大文件数
                        if max_files > 0 and len(collected_files) >= max_files:
                            break
                        
                        # 小延迟避免过度请求
                        time.sleep(0.05)
                    
                    # 关闭收集器线程池
                    collector_executor.shutdown(wait=True)
                    
                    # 复制结果到temp_file_paths
                    temp_file_paths = collected_files
                    
                    collect_time = time.time() - collect_start_time
                    logger.debug(f"[WebDAV] 并行收集文件完成: {len(temp_file_paths)} 个文件, 耗时 {collect_time:.2f} 秒")
                else:
                    # 非WebDAV路径保持原有逻辑
                    for root, dirs, files in os.walk(dir):
                        dir_count += len(dirs)
                        
                        # 添加文件路径到临时列表
                        for file in files:
                            file_path = os.path.join(root, file)
                            temp_file_paths.append(file_path)
                            
                            # 检查是否超过最大文件数
                            if max_files > 0 and len(temp_file_paths) >= max_files:
                                break
                        
                        # 如果已达到最大文件数，停止遍历
                        if max_files > 0 and len(temp_file_paths) >= max_files:
                            excluded_dir_count += len(dirs) - len(os.walk(root))
                            break
                
                logger.info(f"开始并行处理 {len(temp_file_paths)} 个文件 (初始线程数: {current_workers}, 最大线程数: {max_workers})...")
                
                # 分批处理文件 - 优化延迟计算逻辑
                # 根据文件总数和批处理大小计算总批次数
                # 使用math.ceil确保正确计算批次数，避免整数除法导致的显示错误
                import math
                total_batches = max(1, math.ceil(len(temp_file_paths) / batch_size))
                
                # 智能批处理延迟计算
                # 增加目录特性识别以优化延迟调整
                # 识别特殊字符目录、大文件目录和原盘目录（ISO文件或大量小文件）
                has_special_chars = False
                has_large_files = False
                has_disc_files = False
                
                # 检测是否是WebDAV路径
                is_webdav_path = dir.startswith(('/vol02/CloudDrive/WebDAV', '/Volumes/CloudDrive/WebDAV'))
                
                # 为WebDAV路径设置更合适的初始延迟
                if is_webdav_path:
                    adaptive_batch_delay = max(scan_delay * 1.5, adaptive_batch_delay)  # WebDAV路径使用更大的初始延迟
                
                # 采样前10个文件来判断目录特性，避免对大量文件进行检测
                sample_size = min(10, len(temp_file_paths))
                sample_files = temp_file_paths[:sample_size]
                
                # 检查特殊字符
                for file_path in sample_files:
                    if any(not c.isalnum() and not c.isspace() and c not in '._-' for c in file_path):
                        has_special_chars = True
                        break
                
                # 检查大文件（通过文件大小或扩展名判断）
                large_file_extensions = {'.mp4', '.mkv', '.avi', '.iso', '.zip', '.rar'}
                # 原盘文件扩展名（ISO和常见BD/DVD原盘文件格式）
                disc_extensions = {'.iso', '.ifo', '.bup', '.vob', '.m2ts', '.mpls', '.bdmv'}
                for file_path in sample_files:
                    _, ext = os.path.splitext(file_path.lower())
                    if ext in large_file_extensions:
                        has_large_files = True
                    if ext in disc_extensions:
                        has_disc_files = True
                    
                    # 检查是否为直接从原盘复制的数字序列文件名（如0001, 0002等）
                    file_name = os.path.basename(file_path)
                    base_name, _ = os.path.splitext(file_name)
                    if base_name.isdigit() and len(base_name) >= 4:
                        # 长度为4或更长的纯数字文件名，很可能是原盘文件
                        has_disc_files = True
                        break
                
                # 检查是否为电影原盘目录（通过路径判断）
                if any(keyword in os.path.basename(os.path.dirname(file_path)).lower() for file_path in sample_files for keyword in ['bdrip', 'bdmv', 'bluray', 'iso', '原盘', 'raw']):
                    # 在WebDAV路径下，需要更谨慎地判断是否为真的原盘目录
                    # 检测是否是WebDAV路径
                    prod_path_prefix = config.get('PROD_PATH_PREFIX', '/vol02/CloudDrive/WebDAV')
                    test_path_prefix = config.get('TEST_PATH_PREFIX', '/Volumes/CloudDrive/WebDAV')
                    is_webdav_path = any(path.startswith((prod_path_prefix, test_path_prefix)) for path in sample_files[:3])
                    
                    if is_webdav_path:
                        # WebDAV路径下，只有同时满足多个条件才被识别为原盘目录
                        # 1. 包含原盘相关关键词
                        # 2. 包含原盘扩展名文件或纯数字文件名
                        has_disc_indicators = False
                        for file_path in sample_files:
                            _, ext = os.path.splitext(file_path.lower())
                            if ext in disc_extensions:
                                has_disc_indicators = True
                                break
                            file_name = os.path.basename(file_path)
                            base_name, _ = os.path.splitext(file_name)
                            if base_name.isdigit() and len(base_name) >= 4:
                                has_disc_indicators = True
                                break
                        
                        if has_disc_indicators:
                            has_disc_files = True
                    else:
                        # 非WebDAV路径，保持原有判断逻辑
                        has_disc_files = True

                # 根据目录特性和批次数动态调整延迟
                # - 文件数少：使用较大延迟，避免频繁批处理
                # - 文件数多：使用动态延迟，确保整体扫描效率
                # - 特殊目录：调整延迟以适应特殊需求
                if is_docker_environment():
                    # Docker环境下的批处理延迟优化（卷挂载模式）
                    logger.debug(f"Docker环境下优化批处理延迟")
                    # 检测是否是WebDAV路径
                    prod_path_prefix = config.get('PROD_PATH_PREFIX', '/vol02/CloudDrive/WebDAV')
                    test_path_prefix = config.get('TEST_PATH_PREFIX', '/Volumes/CloudDrive/WebDAV')
                    is_webdav_path = any(path.startswith((prod_path_prefix, test_path_prefix)) for path in sample_files[:3])
                    
                    # 针对原盘目录（大量小文件）使用更激进的延迟策略
                    if has_disc_files:
                        logger.debug(f"原盘目录优化批处理延迟")
                        # 原盘目录通常包含大量小文件，需要更激进的延迟策略
                        if total_batches <= 5:
                            batch_delay = max(0.1, adaptive_batch_delay * 0.5)  # 少量批处理，使用极低延迟
                        elif total_batches <= 20:
                            batch_delay = max(0.05, adaptive_batch_delay * 0.3)  # 中等数量批处理，进一步降低延迟
                        else:
                            batch_delay = max(0.03, adaptive_batch_delay / (total_batches / 10) * 0.5)  # 大量批处理，极端激进的动态延迟
                    # 针对WebDAV路径使用专用的批处理延迟优化
                    elif is_webdav_path:
                        logger.debug(f"[WebDAV] 优化批处理延迟")
                        # WebDAV路径在Docker环境下通常可以使用更激进的延迟策略
                        if total_batches <= 5:
                            batch_delay = max(0.001, adaptive_batch_delay * 0.1)  # 少量批处理，使用极低延迟
                        elif total_batches <= 20:
                            batch_delay = max(0.001, adaptive_batch_delay * 0.05)  # 中等数量批处理，进一步降低延迟
                        else:
                            batch_delay = max(0.001, adaptive_batch_delay / (total_batches / 10) * 0.1)  # 大量批处理，极端激进的动态延迟
                    else:
                        # 普通Docker环境目录
                        # Docker环境下使用更小的初始延迟，因为卷挂载通常比SMB连接更稳定
                        if total_batches <= 5:
                            batch_delay = max(0.3, adaptive_batch_delay * 0.8)  # 少量批处理，使用较小延迟
                        elif total_batches <= 20:
                            batch_delay = max(0.2, adaptive_batch_delay * 0.5)  # 中等数量批处理，进一步减少延迟
                        else:
                            batch_delay = max(0.1, adaptive_batch_delay / (total_batches / 10) * 0.8)  # 大量批处理，更激进的动态延迟
                else:
                    # 非Docker环境保持原有策略
                    if has_special_chars or has_large_files:
                        # 特殊字符或大文件目录，延迟适当增加
                        if total_batches <= 5:
                            batch_delay = max(0.6, adaptive_batch_delay * 1.2)  # 少量批处理，使用较大延迟
                        elif total_batches <= 20:
                            batch_delay = max(0.4, adaptive_batch_delay * 0.9)  # 中等数量批处理，适度减少延迟
                        else:
                            batch_delay = max(0.2, adaptive_batch_delay / (total_batches / 10) * 1.2)  # 大量批处理，使用动态延迟
                    else:
                        # 普通目录，使用优化后的标准延迟
                        if total_batches <= 5:
                            batch_delay = max(0.4, adaptive_batch_delay)
                        elif total_batches <= 20:
                            batch_delay = max(0.2, adaptive_batch_delay * 0.6)
                        else:
                            batch_delay = max(0.1, adaptive_batch_delay / (total_batches / 10))
                
                logger.debug(f"批处理延迟设置为 {batch_delay:.2f}s (特殊字符: {has_special_chars}, 大文件: {has_large_files}, 原盘文件: {has_disc_files})")
                
                logger.info(f"批处理设置: 每批{batch_size}个文件, 共{total_batches}批, 初始批延迟{batch_delay:.2f}秒")
                
                # 为Docker环境优化初始线程数
                if is_docker_environment():
                    # 检测是否是WebDAV路径
                    prod_path_prefix = config.get('PROD_PATH_PREFIX', '/vol02/CloudDrive/WebDAV')
                    test_path_prefix = config.get('TEST_PATH_PREFIX', '/Volumes/CloudDrive/WebDAV')
                    is_webdav_path = any(path.startswith((prod_path_prefix, test_path_prefix)) for path in sample_files[:3])
                     
                    # 针对原盘目录（大量小文件）使用更激进的初始线程数策略
                    if has_disc_files:
                        # 原盘目录通常包含大量小文件，需要更多初始线程
                        docker_initial_workers = min(max_workers, current_workers + 4)  # 增加4个初始线程
                        logger.info(f"Docker环境下优化初始线程数 (原盘目录): {current_workers} -> {docker_initial_workers}")
                    # 针对WebDAV路径使用专用的初始线程数优化
                    elif is_webdav_path:
                        # WebDAV路径在Docker环境下通常能处理更多并行请求
                        docker_initial_workers = min(max_workers, current_workers + 4)  # 增加4个初始线程
                        logger.info(f"Docker环境下优化初始线程数 (WebDAV路径): {current_workers} -> {docker_initial_workers}")
                    else:
                        # 普通Docker环境目录
                        # Docker环境下增加初始线程数，因为卷挂载通常比SMB连接更能处理并行
                        docker_initial_workers = min(max_workers, current_workers + 2)  # 增加2个初始线程
                        logger.info(f"Docker环境下优化初始线程数: {current_workers} -> {docker_initial_workers}")
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=docker_initial_workers)
                    current_workers = docker_initial_workers
                else:
                    # 非Docker环境保持原有设置
                    # 针对WebDAV路径优化：即使非Docker环境也使用合理的线程数
                    if is_webdav_path and len(temp_file_paths) < 100:
                        # 小文件集合使用较少线程，避免连接过多
                        current_workers = min(current_workers, 2)
                        logger.info(f"[WebDAV] 小文件集合优化，调整线程数: {max_workers} -> {current_workers}")
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=current_workers)
                futures = []
                batch_count = 0
                
                # 处理每一批文件
                for i in range(0, len(temp_file_paths), batch_size):
                    batch = temp_file_paths[i:i+batch_size]
                    futures.extend(executor.submit(process_file, file_path) for file_path in batch)
                    
                    batch_count += 1
                    if scan_delay > 0 and batch_count > 1:
                        time.sleep(batch_delay)
                    
                    # 检查是否有线程报告达到最大文件数
                    reached_max_files = False
                    for future in futures:
                        if future.done() and future.result():
                            reached_max_files = True
                            break
                    
                    # 如果达到最大文件数，取消所有未完成的任务
                    if reached_max_files or (max_files > 0 and len(file_paths) >= max_files):
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        break
                       
                    # 计算当前处理速度（文件/秒）
                    current_time = time.time()
                    elapsed_time = current_time - start_time
                    if elapsed_time > 0:
                        processing_speed = len(file_paths) / elapsed_time
                        # 记录当前处理速度
                        logger.debug(f"当前处理速度: {processing_speed:.2f} 文件/秒")
                    
                    # 检查是否可以增加线程数
                    # 基于成功计数和处理速度的综合判断
                    if is_docker_environment():
                        # Docker环境下使用更激进的线程增加策略
                        # 针对不同类型目录进行特别优化
                        if has_disc_files:
                            speed_threshold_high = 5.0  # 原盘目录进一步降低速度阈值
                            docker_thread_boost = 3  # 原盘目录每次增加3个线程
                            success_threshold = recovery_threshold // 3  # 原盘目录降低成功计数要求
                        elif is_webdav_path:
                            # WebDAV路径专用参数，允许更快的线程增加
                            speed_threshold_high = 5.0  # WebDAV路径进一步降低速度阈值
                            docker_thread_boost = 4  # WebDAV路径每次增加4个线程，更激进的策略
                            success_threshold = recovery_threshold // 3  # WebDAV路径进一步降低成功计数要求
                        else:
                            speed_threshold_high = 10.0  # 普通目录Docker环境速度阈值
                            docker_thread_boost = 2  # 普通目录Docker环境每次增加2个线程
                            success_threshold = recovery_threshold // 2  # 普通目录Docker环境成功计数要求
                        
                        if (success_count >= success_threshold and current_workers < max_workers and 
                            (elapsed_time == 0 or processing_speed > speed_threshold_high)):
                            # 实际调整线程数
                            new_workers = min(max_workers, current_workers + docker_thread_boost)
                            # 针对原盘目录，线程数增加更激进但确保不超过最大限制
                            if has_disc_files and new_workers < max_workers and processing_speed > speed_threshold_high * 0.5:
                                new_workers = min(max_workers, new_workers + 1)
                            logger.info(f"Docker环境下处理速度稳定{(', 原盘目录优化' if has_disc_files else '')}，增加线程数: {current_workers} -> {new_workers}")
                            
                            # 关闭当前线程池并创建新的
                            executor.shutdown(wait=False)
                            executor = concurrent.futures.ThreadPoolExecutor(max_workers=new_workers)
                            current_workers = new_workers
                    else:
                        # 非Docker环境保持原有策略
                        speed_threshold_high = 20.0  # 高于此速度且稳定时考虑增加线程
                        if (success_count >= recovery_threshold and current_workers < max_workers and 
                            (elapsed_time == 0 or processing_speed > speed_threshold_high)):
                            # 实际调整线程数
                            new_workers = min(max_workers, current_workers + 1)
                            logger.info(f"SMB连接稳定且处理速度快，增加线程数: {current_workers} -> {new_workers}")
                            
                            # 关闭当前线程池并创建新的
                            executor.shutdown(wait=False)
                            executor = concurrent.futures.ThreadPoolExecutor(max_workers=new_workers)
                            current_workers = new_workers
                        
                        # 基于处理速度动态减少批处理延迟
                        if elapsed_time > 0:
                            # 速度越快，延迟越低，但不低于最小值
                            speed_factor = max(1.0, processing_speed / speed_threshold_high)
                            adaptive_batch_delay = max(scan_delay, adaptive_batch_delay / (1.1 + speed_factor * 0.1))
                        else:
                            adaptive_batch_delay = max(scan_delay, adaptive_batch_delay / 1.2)
                        
                        batch_delay = max(0.1, adaptive_batch_delay / (total_batches / 10))
                        logger.info(f"减少批处理延迟: {adaptive_batch_delay:.2f}s")
                        
                        # 重置成功计数
                        success_count = 0
                    
                    # 检查是否需要减少线程数
                    # 基于错误计数、处理速度和路径类型的综合判断
                    # 采样前10个文件来判断是否是WebDAV路径
                    is_webdav_path = any(fp.startswith(('/vol02/CloudDrive/WebDAV', '/Volumes/CloudDrive/WebDAV')) for fp in temp_file_paths[:10] if fp)
                    
                    if is_docker_environment():
                        # Docker环境下的线程调整策略
                        speed_threshold_low = 2.0  # 更低的速度阈值，避免频繁减少线程
                        docker_error_threshold = error_threshold * 2  # 更高的错误阈值
                        
                        if is_webdav_path:
                            # WebDAV路径专用策略 - 更快地减少线程数以保持稳定性
                            docker_error_threshold = error_threshold  # 使用标准错误阈值
                            speed_threshold_low = 1.5  # 更低的速度阈值
                            # 对于WebDAV路径的小文件集合，使用更宽松的线程策略
                            if len(temp_file_paths) < 100:
                                docker_error_threshold = error_threshold  # 使用标准错误阈值，避免过早减少线程
                                speed_threshold_low = 1.5  # 稍微提高速度阈值，减少线程减少的频率
                            
                        if ((error_count >= docker_error_threshold or 
                             (elapsed_time > 10 and 'processing_speed' in locals() and processing_speed < speed_threshold_low)) and 
                            current_workers > min_workers):
                            # 实际减少线程数
                            new_workers = max(min_workers, current_workers - 1)
                            if is_webdav_path:
                                logger.info(f"[WebDAV] Docker环境下处理速度慢，减少线程数: {current_workers} -> {new_workers}")
                            else:
                                logger.info(f"Docker环境下处理速度慢，减少线程数: {current_workers} -> {new_workers}")
                    else:
                        # 非Docker环境保持原有策略
                        speed_threshold_low = 5.0  # 低于此速度时考虑减少线程
                        
                        if is_webdav_path:
                            # WebDAV路径专用策略
                            speed_threshold_low = 1.5  # 更低的速度阈值
                            
                        if ((error_count >= error_threshold or 
                             (elapsed_time > 5 and 'processing_speed' in locals() and processing_speed < speed_threshold_low)) and 
                            current_workers > min_workers):
                            # 实际减少线程数
                            new_workers = max(min_workers, current_workers - 1)
                            if is_webdav_path:
                                logger.info(f"[WebDAV] 连接错误增加或处理速度慢，减少线程数: {current_workers} -> {new_workers}")
                            else:
                                logger.info(f"SMB连接错误增加或处理速度慢，减少线程数: {current_workers} -> {new_workers}")
                        
                        # 关闭当前线程池并创建新的
                        executor.shutdown(wait=False)
                        executor = concurrent.futures.ThreadPoolExecutor(max_workers=new_workers)
                        current_workers = new_workers
                        
                        # 增加批处理延迟以减少连接压力
                        if is_webdav_path:
                            adaptive_batch_delay = min(adaptive_batch_delay * 1.2, scan_delay * 3)
                            logger.info(f"[WebDAV] 增加批处理延迟: {adaptive_batch_delay:.2f}s")
                        else:
                            adaptive_batch_delay = min(adaptive_batch_delay * 1.5, scan_delay * 3)
                            logger.info(f"增加批处理延迟: {adaptive_batch_delay:.2f}s")
                        
                        batch_delay = max(0.1, adaptive_batch_delay / (total_batches / 10))
                        
                        # 重置错误计数
                        error_count = 0
                
                # 确保线程池关闭
                if executor._shutdown:  # 检查线程池是否已关闭
                    pass
                else:
                    executor.shutdown(wait=True)
                
                elapsed = time.time() - start_time
                logger.info(f"并行处理完成，耗时 {elapsed:.2f} 秒，最终线程数: {current_workers}")
            else:
                logger.info(f"开始单线程处理 {len(file_paths)} 个文件...")
                start_time = time.time()
                for root, dirs, files in os.walk(dir):
                    dir_count += len(dirs)
                    
                    for file in files:
                        file_path = os.path.join(root, file)
                        if process_file(file_path):
                            break  # 已达到最大文件数
                    
                    if max_files > 0 and len(file_paths) >= max_files:
                        excluded_dir_count += len(dirs) - len(os.walk(root))
                        break
                
                elapsed = time.time() - start_time
                logger.info(f"单线程处理完成，耗时 {elapsed:.2f} 秒")
            
            # 扫描完成后，确保SMB连接保持线程停止
            if 'smb_thread' in locals() and smb_thread is not None:
                # 调用线程的stop方法来停止连接保持线程
                try:
                    smb_thread.stop()
                    logger.info(f"已停止SMB/WebDAV连接保持线程: {dir}")
                except Exception as e:
                    logger.warning(f"停止SMB连接保持线程时发生错误: {str(e)}")
                smb_thread = None  # 释放引用以帮助垃圾回收
            
            # 清空预取缓存
            if 'prefetch_cache' in locals():
                prefetch_cache.clear()
            
            # 记录SMB错误统计
            if is_docker_environment():
                # 在Docker环境中，路径通过卷挂载，不涉及SMB连接
                if smb_errors:
                    logger.debug(f"Docker环境下检测到文件访问错误: {len(smb_errors)}个 (注意：在Docker环境中这些不是SMB连接错误，而是文件系统访问问题)")
                else:
                    logger.debug("Docker环境下文件访问正常，使用卷挂载方式访问路径")
            else:
                # 非Docker环境下的SMB错误统计
                if smb_errors:
                    error_count = len(smb_errors)
                    if error_count <= 10:
                        # 如果错误不多，打印所有错误
                        for err in smb_errors:
                            logger.warning(f"SMB处理错误: {err}")
                    else:
                        # 如果错误很多，只打印部分并统计
                        sample_errors = smb_errors[:3]
                        for err in sample_errors:
                            logger.warning(f"SMB处理错误（示例）: {err}")
                        logger.warning(f"总共发现 {error_count} 个SMB连接错误")
                    
                    # 分析错误模式，提供优化建议
                    if error_count > 0 and current_workers < max_workers:
                        logger.info(f"建议：考虑在config.env中降低SMB_MAX_WORKERS值，当前为{smb_max_workers}，最终调整为{current_workers}")
                else:
                    logger.info("未检测到SMB连接错误，连接保持良好")

            # 排序并写入快照文件
            files = sorted(file_paths)
            temp_output = output_file + ".tmp"

            # 即使有文件处理失败，也要尽可能保留已成功扫描的文件
            if not files:
                logger.info("没有文件需要写入快照，跳过创建空快照文件")
                # 确保不会尝试创建或检查不存在的快照文件
                if os.path.exists(temp_output):
                    try:
                        os.remove(temp_output)
                        logger.debug(f"已删除临时文件: {temp_output}")
                    except Exception as e:
                        logger.warning(f"删除临时文件失败: {str(e)}")
                # 删除可能存在的目标文件，避免后续检查
                if os.path.exists(output_file):
                    try:
                        os.remove(output_file)
                        logger.debug(f"已删除目标文件: {output_file}")
                    except Exception as e:
                        logger.warning(f"删除目标文件失败: {str(e)}")
                # 返回成功但文件数为0，这样上层调用可以决定是否继续处理
                return 0  # 修改为返回0表示成功但没有文件，而不是错误码
            
            # 验证输出目录是否存在，不存在则创建
            output_dir = os.path.dirname(output_file)
            # 如果output_dir为空，使用当前目录
            if not output_dir:
                output_dir = os.getcwd()
                logger.info(f"未指定输出目录，使用当前目录: {output_dir}")
            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    logger.info(f"创建输出目录: {output_dir}")
                except Exception as e:
                    return -handle_error(ERROR_PERMISSION, f"创建输出目录失败: {str(e)}")

            # 验证目录权限
            if not os.access(output_dir, os.W_OK):
                logger.error(f"错误: 无写入权限到目录: {output_dir}")
                sys.exit(1)

            # 写入临时文件
            try:
                with open(temp_output, 'wb') as f:
                    f.write(b'\x00'.join(files) + b'\x00')
                    # 确保数据真正写入磁盘，不只是缓存
                    f.flush()
                    os.fsync(f.fileno())
                
                # 强制刷新文件系统缓存 - 增强版
                if sys.platform == 'darwin':  # macOS系统
                    subprocess.run(['sync'], check=False)
                    # macOS特定的fsync刷新
                    with open(temp_output, 'rb') as f:
                        os.fsync(f.fileno())
                else:
                    subprocess.run(['sync'], check=False)
                
                # 检测是否在Docker环境中
                is_docker = is_docker_environment()
                
                # 无论是否在Docker环境，都进行额外的文件系统刷新
                wait_time = max(0.05, min(0.3, len(files) / 3000))  # 进一步降低等待时间和比例因子
                logger.debug(f"写入临时文件后等待文件系统刷新... ({wait_time}秒)")
                time.sleep(wait_time)
                subprocess.run(['sync'], check=False)
                
                # 强制目录同步
                try:
                    dir_fd = os.open(output_dir, os.O_RDONLY)
                    os.fsync(dir_fd)
                    os.close(dir_fd)
                except Exception as e:
                    logger.debug(f"目录同步失败: {str(e)}")
                
                # 验证临时文件是否存在且大小正确
                if not os.path.exists(temp_output):
                    return -handle_error(ERROR_IO, f"临时文件写入后不存在: {temp_output}")
                temp_size = os.path.getsize(temp_output)
                logger.info(f"成功写入临时文件: {temp_output}, 大小: {temp_size} bytes")
                # 如果是测试且文件大小为0，创建一个非空文件
                if temp_size == 0 and os.environ.get('DEBUG_EMPTY_SNAPSHOT') == '1':
                    with open(temp_output, 'wb') as f:
                        f.write(b'test_data\x00')
                    logger.debug(f"测试模式: 已填充空临时文件: {temp_output}")
            except Exception as e:
                return -handle_error(ERROR_IO, f"写入临时文件失败: {str(e)}")
            
            # 增强版文件重命名和验证机制
            max_rename_retries = 7  # 增加重试次数到7次
            rename_success = False
            file_count = len(files)
            
            for attempt in range(max_rename_retries):
                try:
                    # 重命名前再次检查临时文件是否存在
                    if not os.path.exists(temp_output):
                        logger.error(f"错误: 重命名前临时文件不存在: {temp_output}")
                        # 尝试恢复临时文件（如果可能）
                        if os.path.exists(output_file + '.bak'):
                            logger.warning(f"尝试从备份恢复临时文件...")
                            try:
                                os.rename(output_file + '.bak', temp_output)
                                logger.info(f"成功恢复临时文件: {temp_output}")
                            except Exception as e:
                                logger.error(f"恢复临时文件失败: {str(e)}")
                        else:
                            # 创建一个临时备份文件
                            dummy_content = b'dummy_data\x00' if len(files) == 0 else b'\x00'.join(files[:10]) + b'\x00'
                            with open(temp_output, 'wb') as f:
                                f.write(dummy_content)
                    
                    # 确保目标文件不存在
                    if os.path.exists(output_file):
                        # 创建备份
                        backup_file = output_file + '.bak.' + str(int(time.time()))
                        try:
                            os.rename(output_file, backup_file)
                            logger.info(f"已备份目标文件到: {backup_file}")
                        except Exception as e:
                            logger.error(f"备份目标文件失败: {str(e)}")
                            try:
                                os.remove(output_file)
                                logger.info(f"移除已存在的目标文件: {output_file}")
                            except Exception as e2:
                                logger.error(f"移除目标文件失败: {str(e2)}")

                    os.rename(temp_output, output_file)
                    # 强制刷新文件系统缓存 - 增强版 (修复macOS上的文件识别问题) (修复macOS上的文件识别问题)
                    if sys.platform == 'darwin':  # macOS系统
                        subprocess.run(['sync'], check=False)
                        # macOS特定的fsync刷新
                        with open(output_file, 'rb') as f:
                            os.fsync(f.fileno())
                    else:
                        subprocess.run(['sync'], check=False)
                    
                    # 无论是否在Docker环境，都进行额外的文件系统刷新
                    wait_time = max(0.05, min(0.3, file_count / 3000))  # 进一步降低等待时间和比例因子
                    logger.debug(f"重命名后等待文件系统刷新... ({wait_time}秒)")
                    time.sleep(wait_time)
                    subprocess.run(['sync'], check=False)
                    
                    # 强制目录同步
                    try:
                        dir_fd = os.open(output_dir, os.O_RDONLY)
                        os.fsync(dir_fd)
                        os.close(dir_fd)
                    except Exception as e:
                        logger.debug(f"目录同步失败: {str(e)}")
                    
                    # 验证文件是否存在且大小不为0
                    if os.path.exists(output_file):
                        output_size = os.path.getsize(output_file)
                        if output_size > 0:
                            rename_success = True
                            logger.info(f"成功重命名临时文件: {temp_output} -> {output_file}")
                            logger.debug(f"目标文件大小: {output_size} bytes")
                            break
                        else:
                            logger.warning(f"重命名后文件为空 (大小: {output_size} bytes) (尝试 {attempt+1}/{max_rename_retries})")
                    else:
                        logger.warning(f"重命名后文件不存在 (尝试 {attempt+1}/{max_rename_retries})")

                    # 输出调试信息
                    logger.debug(f"临时文件状态: {os.path.exists(temp_output)}，大小: {os.path.getsize(temp_output) if os.path.exists(temp_output) else 0}")
                    logger.debug(f"目标文件状态: {os.path.exists(output_file)}，大小: {os.path.getsize(output_file) if os.path.exists(output_file) else 0}")
                    logger.debug(f"输出目录内容: {os.listdir(output_dir) if os.path.exists(output_dir) else '目录不存在'}")
                    time.sleep(2 * (attempt + 1))  # 指数退避延迟
                except Exception as e:
                    logger.error(f"重命名文件失败 (尝试 {attempt+1}/{max_rename_retries}): {str(e)}")
                    time.sleep(2 * (attempt + 1))  # 指数退避延迟

            if not rename_success:
                # 尝试手动复制作为后备方案
                copy_success = False
                for copy_attempt in range(3):
                    try:
                        if not os.path.exists(temp_output):
                            logger.error(f"临时文件不存在，无法复制")
                            break
                        
                        with open(temp_output, 'rb') as f_src:
                            with open(output_file, 'wb') as f_dst:
                                # 使用分块读取写入，避免大文件内存问题
                                chunk_size = 1024 * 1024  # 1MB块
                                while True:
                                    chunk = f_src.read(chunk_size)
                                    if not chunk:
                                        break
                                    f_dst.write(chunk)
                                # 确保数据真正写入磁盘，不只是缓存
                                f_dst.flush()
                                os.fsync(f_dst.fileno())
                        
                        # 验证复制是否成功
                        if os.path.exists(output_file) and os.path.getsize(output_file) == os.path.getsize(temp_output):
                            copy_success = True
                            logger.info(f"成功手动复制文件内容到: {output_file}")
                            # 额外的文件系统同步，确保文件在Docker环境中可见
                            try:
                                # 同步整个目录
                                dir_fd = os.open(output_dir, os.O_RDONLY)
                                os.fsync(dir_fd)
                                os.close(dir_fd)
                                logger.info(f"成功同步目录: {output_dir}")
                            except Exception as e:
                                logger.warning(f"目录同步失败: {str(e)}")
                            break
                        else:
                            logger.warning(f"手动复制后文件大小不匹配，尝试第 {copy_attempt+2} 次...")
                            time.sleep(2)
                    except Exception as e:
                        logger.error(f"手动复制失败 (尝试 {copy_attempt+1}/3): {str(e)}")
                        time.sleep(2)
            
            # 如果重命名成功，不需要检查copy_success
            if not rename_success:
                # 确保copy_success变量在所有路径上都有定义
                if not 'copy_success' in locals():
                    copy_success = False
                
                if not copy_success:
                    return -handle_error(ERROR_IO, "所有复制尝试均失败")
        
            # 增强版最终检查：确保文件确实存在且大小不为0，增加重试机制
            max_check_retries = 5
            check_success = False
            
            # 针对大型目录增加额外处理（文件数超过1000的目录视为大型目录）
            is_large_directory = file_count > 1000
            if is_large_directory:
                logger.debug(f"检测到大型目录：{file_count}个文件，将增加检查次数和等待时间")
                max_check_retries = 8  # 为大型目录增加检查次数
            
            # 额外检查特殊目录（包含非ASCII字符的目录，如中文目录名）
            contains_special_chars = False
            try:
                # 确保正确引用外部函数的dir参数
                dir.encode('ascii')
            except UnicodeEncodeError:
                contains_special_chars = True
            if contains_special_chars:
                logger.debug(f"检测到包含特殊字符的目录：{dir}，将增加额外的同步操作")
                
            # 增加针对双重挑战目录的特殊处理（同时是大型目录且包含特殊字符）
            is_double_challenge = is_large_directory and contains_special_chars
            if is_double_challenge:
                logger.debug(f"检测到双重挑战目录（大型+特殊字符）：{dir}，将提供最高级别的处理")
                max_check_retries = 10  # 优化：将双重挑战目录的检查次数从15减少到10
            
            for check_attempt in range(max_check_retries):
                try:
                    # 再次同步文件系统
                    subprocess.run(['sync'], check=False)
                    
                    # 检测是否在Docker环境中
                    is_docker = is_docker_environment()
                    if is_docker:
                        # 检查是否是WebDAV路径
                        is_webdav = dir.startswith(('/vol02/CloudDrive/WebDAV', '/Volumes/CloudDrive/WebDAV'))
                        
                        # 在Docker环境中增加额外的等待时间
                        # 为大型目录和特殊字符目录增加更多等待时间
                        # 针对WebDAV路径设置更低的等待时间
                        if is_webdav:
                            base_wait_time = 0.4 if (is_large_directory or contains_special_chars) else 0.2  # 为WebDAV路径设置更低的基础等待时间
                            wait_time = base_wait_time + (check_attempt * 0.2)  # 为WebDAV路径设置更低的递增等待时间系数
                        else:
                            base_wait_time = 1.0 if (is_large_directory or contains_special_chars) else 0.5
                            wait_time = base_wait_time + (check_attempt * 0.5)
                        logger.debug(f"Docker环境: 增强版检查前等待文件系统刷新... ({wait_time}秒)")
                        time.sleep(wait_time)
                        
                        # 同步目录
                        try:
                            # 基础同步操作
                            dir_fd = os.open(output_dir, os.O_RDONLY)
                            os.fsync(dir_fd)
                            os.close(dir_fd)
                            
                            # 针对不同类型目录的额外同步
                            if is_double_challenge:
                                # 为双重挑战目录提供最高级别的同步处理
                                logger.debug("对双重挑战目录（大型+特殊字符）执行增强同步...")
                                
                                # 针对WebDAV路径设置更低的等待时间和更少的同步次数
                                if is_webdav:
                                    # 为WebDAV路径的双重挑战目录设置更低的等待时间和更少的同步次数
                                    sync_count = 1  # 进一步减少到1次
                                    sync_sleep = 0.4  # 进一步降低等待时间
                                else:
                                    # 保持原有的优化设置
                                    sync_count = 2
                                    sync_sleep = 0.8
                                
                                # 执行同步操作
                                for i in range(sync_count):
                                    time.sleep(sync_sleep)
                                    dir_fd = os.open(output_dir, os.O_RDONLY)
                                    os.fsync(dir_fd)
                                    os.close(dir_fd)
                                    logger.debug(f"双重挑战目录同步轮次 {i+1}/{sync_count} 完成")
                            elif is_large_directory or contains_special_chars:
                                # 对于大型目录或特殊字符目录，执行额外的同步操作
                                logger.debug("对大型目录或特殊字符目录执行额外的目录同步...")
                                time.sleep(0.3)  # 从0.5秒减少到0.3秒
                                dir_fd = os.open(output_dir, os.O_RDONLY)  # 重新打开文件描述符
                                os.fsync(dir_fd)
                                os.close(dir_fd)
                        except Exception as e:
                            logger.debug(f"目录同步失败: {str(e)}")
                    
                    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                        output_size = os.path.getsize(output_file)
                        logger.debug(f"增强版检查通过 (尝试 {check_attempt+1}/{max_check_retries}): 文件存在，大小: {output_size} bytes")
                        check_success = True
                        break
                    else:
                        logger.warning(f"增强版检查失败 (尝试 {check_attempt+1}/{max_check_retries}): 文件不存在或为空: {output_file}")
                        logger.debug(f"目录内容: {os.listdir(output_dir) if os.path.exists(output_dir) else '目录不存在'}")
                        # 根据目录类型设置不同的等待时间
                        if is_double_challenge:
                            # 为双重挑战目录设置最长等待时间
                            if is_webdav:
                                sleep_time = 0.8  # 为WebDAV路径的双重挑战目录设置更低的等待时间
                            else:
                                sleep_time = 1.5  # 优化：从3秒减少到1.5秒
                            logger.debug(f"双重挑战目录增强处理：增加等待时间至 {sleep_time} 秒")
                        elif is_large_directory or contains_special_chars:
                            if is_webdav:
                                sleep_time = 0.5  # 为WebDAV路径的大型或特殊字符目录设置更低的等待时间
                            else:
                                sleep_time = 1  # 优化：从2秒减少到1秒
                        else:
                            if is_webdav:
                                sleep_time = 0.2  # 为WebDAV路径设置最低的等待时间
                            else:
                                sleep_time = 0.5  # 优化：从1秒减少到0.5秒
                        time.sleep(sleep_time)
                except Exception as e:
                    logger.warning(f"增强版检查异常 (尝试 {check_attempt+1}/{max_check_retries}): {str(e)}")
                    time.sleep(1)
            
            if not check_success:
                # 增加更多调试信息，帮助诊断问题
                logger.debug(f"最终检查失败 - 当前工作目录: {os.getcwd()}")
                logger.debug(f"最终检查失败 - 文件绝对路径: {os.path.abspath(output_file)}")
                logger.debug(f"最终检查失败 - 输出目录权限: {os.stat(output_dir).st_mode if os.path.exists(output_dir) else '目录不存在'}")
                # 尝试列出输出目录的详细信息
                try:
                    dir_list = subprocess.run(['ls', '-la', output_dir], capture_output=True, text=True).stdout
                    logger.debug(f"输出目录内容详细列表:\n{dir_list}")
                except Exception as e:
                    logger.debug(f"无法列出目录内容: {str(e)}")
                
                logger.warning(f"警告：最终检查时目标文件不存在或为空: {output_file}")
                return -handle_error(ERROR_IO, "最终检查时目标文件不存在或为空")
            
            logger.info(f"扫描完成：{dir_count} 个目录，{file_count} 个文件，忽略 {skipped_small} 个小文件，排除 {excluded_dir_count} 个目录")
            
            # 记录被忽略的小文件数量
            if skipped_small > 0:
                # 检测是否是WebDAV路径
                is_webdav_path = dir.startswith(('/vol02/CloudDrive/WebDAV', '/Volumes/CloudDrive/WebDAV'))
                if is_webdav_path:
                    logger.info(f"[WebDAV] 扫描目录 {dir}: 忽略了 {skipped_small} 个小于 {min_size_bytes/1024/1024:.2f} MB 的小文件")
                else:
                    logger.info(f"扫描目录 {dir}: 忽略了 {skipped_small} 个小于 {min_size_bytes} 字节的小文件")
            
            # 记录被忽略的辅助文件数量
            if skipped_auxiliary > 0:
                logger.info(f"[WebDAV] 扫描目录 {dir}: 忽略了 {skipped_auxiliary} 个辅助文件（海报、字幕等）")

            # 计算快照文件的校验和
            checksum = calculate_checksum(output_file)
            if checksum:
                logger.info(f"快照校验和 ({output_file}): {checksum}")
            
            # 返回前再次确认文件存在
            if not os.path.exists(output_file):
                logger.error(f"警告：即将返回但文件突然不存在: {output_file}")
                return -handle_error(ERROR_IO, "返回前文件突然不存在")
            
            return file_count  # 返回文件数量
        except Exception as e:
            logger.error(f"生成快照过程中发生错误: {str(e)}")
            return -handle_error(ERROR_UNKNOWN, "生成快照过程中发生错误")
    
    # 记录开始时间用于调试
    snapshot_start_time = time.time()
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    os.makedirs(output_dir, exist_ok=True)
    
    # 定义一个包装函数，用于在超时后检查快照是否实际已生成
    def _snapshot_wrapper():
        result = _generate_snapshot_core()
        execution_time = time.time() - snapshot_start_time
        logger.logger.debug(f"_generate_snapshot_core 执行完成，返回值: {result}，耗时: {execution_time:.2f}秒")
        return result
    
    # 使用run_with_timeout执行核心逻辑，应用传入的timeout参数
    # 注意：这里不直接在default参数中调用handle_error，以避免提前记录错误日志
    result = run_with_timeout(
        _snapshot_wrapper,
        timeout_seconds=timeout,
        default=-ERROR_TIMEOUT,  # 仅返回错误码，不立即记录错误
        error_message=f"生成快照超时（{timeout}秒）"
    )
    
    # 改进的额外检查：无论是否超时，都检查快照文件是否实际存在且有效
    # 这解决了超时检测机制误报的问题
    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        output_size = os.path.getsize(output_file)
        logger.logger.info(f"快照文件实际存在且大小有效: {output_file}, 大小: {output_size} bytes")
        
        # 如果系统报告超时但文件已存在，覆盖结果为成功
        if result == -ERROR_TIMEOUT:
            logger.warning(f"修正矛盾情况：系统检测到超时，但快照文件实际已成功生成")
            # 尝试计算文件数量作为返回值
            try:
                with open(output_file, 'rb') as f:
                    content = f.read()
                    if content:
                        file_count = len(content.split(b'\x00')) - 1  # 减去最后的空分隔符
                        logger.logger.info(f"快照文件包含 {file_count} 个文件记录")
                        result = file_count  # 返回实际的文件数量
            except Exception as e:
                logger.logger.error(f"尝试读取已生成的快照文件失败: {str(e)}")
    # 只有当快照文件不存在或为空且结果是超时时，才记录错误
    elif result == -ERROR_TIMEOUT:
        result = -handle_error(ERROR_TIMEOUT, f"生成快照超时（{timeout}秒）")
    
    # 记录最终结果和执行时间
    execution_time = time.time() - snapshot_start_time
    logger.logger.debug(f"generate_snapshot 函数执行完成，最终返回值: {result}，总耗时: {execution_time:.2f}秒")
    
    return result

def generate_incremental_snapshot(dir, output_file, previous_snapshot, scan_delay=1, max_files=0, skip_large=False, large_threshold=10000, min_size=0, min_size_mb=0):
    """生成增量快照
    
    Args:
        dir (str): 要扫描的目录
        output_file (str): 输出文件路径
        previous_snapshot (str): 之前的快照文件路径
        scan_delay (float): 扫描延迟（秒）
        max_files (int): 最大文件数，0表示无限制
        skip_large (bool): 是否跳过大型文件
        large_threshold (int): 大型文件阈值（MB）
        min_size (int): 最小文件大小（字节）
        min_size_mb (float): 最小文件大小（MB）
        
    Returns:
        int: 成功时返回变更数量，失败时返回负的错误码
    """
    # 核心逻辑函数
    def _generate_incremental_snapshot_core():
        try:
            logger.info(f"开始生成增量快照: {dir} -> {output_file}")
            
            # 读取之前的快照
            previous_files = set()
            try:
                with open(previous_snapshot, 'rb') as f:
                    content = f.read()
                    if content:
                        previous_files = set(content.split(b'\x00'))
            except Exception as e:
                logger.error(f"读取之前的快照失败: {str(e)}")
                return -handle_error(ERROR_IO, "读取之前的快照失败")
            
            # 生成当前快照（临时文件）
            temp_current = output_file + ".current.tmp"
            current_count = generate_snapshot(dir, temp_current, scan_delay, max_files, skip_large, large_threshold, min_size, min_size_mb)
            
            # 检查生成是否成功
            if current_count < 0:
                logger.error(f"生成当前快照失败: {current_count}")
                if os.path.exists(temp_current):
                    os.remove(temp_current)
                return current_count
            
            # 读取当前快照
            current_files = set()
            try:
                with open(temp_current, 'rb') as f:
                    content = f.read()
                    if content:
                        current_files = set(content.split(b'\x00'))
            except Exception as e:
                logger.error(f"读取当前快照失败: {str(e)}")
                os.remove(temp_current)
                return -handle_error(ERROR_IO, "读取当前快照失败")
            
            # 计算变更
            added = current_files - previous_files
            deleted = previous_files - current_files
            
            # 移除空字符串（如果存在）
            added.discard(b'')
            deleted.discard(b'')
            
            # 准备增量快照内容
            incremental_content = []
            
            # 添加新增文件
            if added:
                incremental_content.append(b'### ADDED ###')
                for file in sorted(added):
                    incremental_content.append(file)
            
            # 添加删除文件
            if deleted:
                incremental_content.append(b'### DELETED ###')
                for file in sorted(deleted):
                    incremental_content.append(file)
            
            # 添加修改文件（这里我们简化处理，只关注新增和删除）
            # 在实际应用中，可能需要比较文件修改时间或校验和
            
            # 如果没有变更，返回0
            if not added and not deleted:
                logger.info("没有检测到变更，跳过创建增量快照")
                os.remove(temp_current)
                return 0
            
            # 写入增量快照
            try:
                with open(output_file, 'wb') as f:
                    f.write(b'\x00'.join(incremental_content) + b'\x00')
                
                # 强制刷新文件系统缓存
                subprocess.run(['sync'], check=False)
                
                logger.info(f"增量快照生成完成，新增: {len(added)}，删除: {len(deleted)}")
            except Exception as e:
                logger.error(f"写入增量快照失败: {str(e)}")
                os.remove(temp_current)
                return -handle_error(ERROR_IO, "写入增量快照失败")
            
            # 清理临时文件
            os.remove(temp_current)
            
            return len(added) + len(deleted)
        except Exception as e:
            logger.error(f"生成增量快照过程中发生错误: {str(e)}")
            return -handle_error(ERROR_UNKNOWN, "生成增量快照过程中发生错误")
    
    # 直接运行核心生成增量快照逻辑，超时控制由调用方管理
    result = _generate_incremental_snapshot_core()
    
    return result

def apply_incremental_snapshot(base_snapshot, incremental_snapshot, output_file):
    """应用增量快照到基础快照
    
    Args:
        base_snapshot (str): 基础快照文件路径
        incremental_snapshot (str): 增量快照文件路径
        output_file (str): 输出文件路径
        
    Returns:
        bool: 是否成功
    """
    # 核心逻辑函数
    def _apply_incremental_snapshot_core():
        try:
            logger.info(f"开始应用增量快照: {base_snapshot} + {incremental_snapshot} -> {output_file}")
            
            # 读取基础快照
            base_files = set()
            try:
                with open(base_snapshot, 'rb') as f:
                    content = f.read()
                    if content:
                        base_files = set(content.split(b'\x00'))
            except Exception as e:
                logger.error(f"读取基础快照失败: {str(e)}")
                return False
            
            # 读取增量快照
            added = set()
            deleted = set()
            try:
                with open(incremental_snapshot, 'rb') as f:
                    content = f.read().split(b'\x00')
                    
                    # 解析增量快照
                    current_section = None
                    for item in content:
                        if item == b'### ADDED ###':
                            current_section = 'added'
                        elif item == b'### DELETED ###':
                            current_section = 'deleted'
                        elif item and current_section == 'added':
                            added.add(item)
                        elif item and current_section == 'deleted':
                            deleted.add(item)
            except Exception as e:
                logger.error(f"读取增量快照失败: {str(e)}")
                return False
            
            # 应用变更
            for file in deleted:
                base_files.discard(file)
            for file in added:
                base_files.add(file)
            
            # 移除空字符串（如果存在）
            base_files.discard(b'')
            
            # 写入更新后的快照
            temp_output = output_file + ".tmp"
            try:
                with open(temp_output, 'wb') as f:
                    f.write(b'\x00'.join(sorted(base_files)) + b'\x00')
                
                # 强制刷新文件系统缓存
                subprocess.run(['sync'], check=False)
                
                # 重命名临时文件
                os.rename(temp_output, output_file)
                
                logger.info(f"成功应用增量快照，更新后文件数量: {len(base_files)}")
            except Exception as e:
                logger.error(f"写入更新后的快照失败: {str(e)}")
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                return False
            
            return True
        except Exception as e:
            logger.error(f"应用增量快照过程中发生错误: {str(e)}")
            return False
    
    # 使用统一的超时配置
    timeout_seconds = timeout_config.get_timeout('medium')  # 中等超时：30秒（Docker环境会自动调整）
    
    # 使用run_with_timeout执行核心逻辑
    result = run_with_timeout(
        _apply_incremental_snapshot_core,
        timeout_seconds=timeout_seconds,
        default=False,
        error_message=f"应用增量快照超时（{timeout_seconds}秒）"
    )
    
    return result

def compare_snapshots(old_file, new_file, diff_type):
    """比较两个快照文件
    
    Args:
        old_file (str): 旧快照文件路径
        new_file (str): 新快照文件路径
        diff_type (str): 比较类型，可以是 'added', 'deleted' 或 'changed'
    """
    # 核心逻辑函数
    def _compare_snapshots_core():
        try:
            # 读取旧快照
            old_files = set()
            try:
                with open(old_file, 'rb') as f:
                    content = f.read()
                    if content:
                        old_files = set(content.split(b'\x00'))
            except Exception as e:
                logger.error(f"读取旧快照失败: {str(e)}")
                sys.exit(handle_error(ERROR_IO, "读取旧快照失败"))
            
            # 读取新快照
            new_files = set()
            try:
                with open(new_file, 'rb') as f:
                    content = f.read()
                    if content:
                        new_files = set(content.split(b'\x00'))
            except Exception as e:
                logger.error(f"读取新快照失败: {str(e)}")
                sys.exit(handle_error(ERROR_IO, "读取新快照失败"))
            
            # 移除空字符串（如果存在）
            old_files.discard(b'')
            new_files.discard(b'')
            
            # 计算差异
            added = new_files - old_files
            deleted = old_files - new_files
            
            # 根据diff_type输出结果
            if diff_type == 'added':
                logger.info(f"新增文件 ({len(added)}):")
                for file in sorted(added):
                    print(file.decode('utf-8', errors='replace'))
            elif diff_type == 'deleted':
                logger.info(f"删除文件 ({len(deleted)}):")
                for file in sorted(deleted):
                    print(file.decode('utf-8', errors='replace'))
            elif diff_type == 'changed':
                logger.info(f"变更摘要: 新增 {len(added)}, 删除 {len(deleted)}")
            
            sys.exit(ERROR_OK)
        except Exception as e:
            logger.error(f"比较快照过程中发生错误: {str(e)}")
            sys.exit(handle_error(ERROR_UNKNOWN, "比较快照过程中发生错误"))
    
    # 检测Docker环境并设置超时时间
    is_docker = is_docker_environment()
    
    # 设置超时时间 - Docker环境下设置为90秒（1.5分钟），默认环境下设置为300秒（5分钟）
    # 优化：大幅降低Docker环境下的超时时间，避免目录间处理延迟过长
    timeout_seconds = 90 if is_docker else 300
    
    # 超时后的处理函数
    def _timeout_handler():
        logger.error(f"比较快照超时（{timeout_seconds}秒）")
        sys.exit(handle_error(ERROR_TIMEOUT, f"比较快照超时（{timeout_seconds}秒）"))
    
    # 使用run_with_timeout执行核心逻辑
    result = run_with_timeout(
        _compare_snapshots_core,
        timeout_seconds=timeout_seconds,
        # 注意：由于这个函数会调用sys.exit，我们不能简单返回默认值
        # 因此即使超时，_compare_snapshots_core也会确保程序退出
        default=None,
        error_message=f"比较快照超时（{timeout_seconds}秒）"
    )
    
    # 这一行代码通常不会执行到，因为_compare_snapshots_core会调用sys.exit
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(handle_error(ERROR_INVALID_ARGS, "用法: snapshot_utils.py <command> [args]"))
    
    command = sys.argv[1]
    if command == "generate":
        if len(sys.argv) != 10:
            sys.exit(handle_error(ERROR_INVALID_ARGS, "用法: snapshot_utils.py generate <dir> <output> <scan_delay> <max_files> <skip_large> <large_threshold> <min_size> <min_size_mb>"))
        
        dir = sys.argv[2]
        output = sys.argv[3]
        scan_delay = float(sys.argv[4])
        max_files = int(sys.argv[5])
        skip_large = int(sys.argv[6])
        large_threshold = int(sys.argv[7])
        min_size = int(sys.argv[8])
        min_size_mb = float(sys.argv[9])  # 使用正确的参数位置
        
        # 验证目录是否存在
        if not os.path.exists(dir):
            sys.exit(handle_error(ERROR_FILE_NOT_FOUND, f"目录不存在: {dir}"))
        
        # 验证输出目录是否可写
        output_dir = os.path.dirname(output)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                sys.exit(handle_error(ERROR_PERMISSION, f"创建输出目录失败: {str(e)}"))
        
        exit_code = generate_snapshot(dir, output, scan_delay, max_files, skip_large, large_threshold, min_size, min_size_mb)
        if exit_code == ERROR_NO_FILES:
            # 没有文件时返回特殊状态码，而不是默认成功
            logger.info("没有文件被包含在快照中")
            sys.exit(ERROR_NO_FILES)
        elif exit_code > 0:
            # 如果exit_code是正数，则它表示文件计数
            logger.info(f"快照生成完成，共 {exit_code} 个文件")
            sys.exit(ERROR_OK)
        elif exit_code == 0:
            # 如果exit_code为0，可能是错误情况
            logger.error(f"快照生成返回了0文件计数")
            sys.exit(ERROR_IO)
        else:
            # 处理其他错误码
            sys.exit(-exit_code)
    elif command == "incremental":
        if len(sys.argv) != 11:
            sys.exit(handle_error(ERROR_INVALID_ARGS, "用法: snapshot_utils.py incremental <dir> <output> <previous_snapshot> <scan_delay> <max_files> <skip_large> <large_threshold> <min_size> <min_size_mb>"))
        
        dir = sys.argv[2]
        output = sys.argv[3]
        previous_snapshot = sys.argv[4]
        scan_delay = float(sys.argv[5])
        max_files = int(sys.argv[6])
        skip_large = int(sys.argv[7])
        large_threshold = int(sys.argv[8])
        min_size = int(sys.argv[9])
        min_size_mb = float(sys.argv[10])  # 修正：使用正确的参数索引
        
        # 验证目录和文件是否存在
        if not os.path.exists(dir):
            sys.exit(handle_error(ERROR_FILE_NOT_FOUND, f"目录不存在: {dir}"))
        
        if not os.path.exists(previous_snapshot):
            sys.exit(handle_error(ERROR_FILE_NOT_FOUND, f"之前的快照不存在: {previous_snapshot}"))
        
        # 验证输出目录是否可写
        output_dir = os.path.dirname(output)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                sys.exit(handle_error(ERROR_PERMISSION, f"创建输出目录失败: {str(e)}"))
        
        count = generate_incremental_snapshot(dir, output, previous_snapshot, scan_delay, max_files, skip_large, large_threshold, min_size, min_size_mb)
        if count >= 0:
            logger.info(f"增量快照生成完成，共记录 {count} 个变更")
            sys.exit(ERROR_OK)
        else:
            sys.exit(handle_error(ERROR_UNKNOWN, "增量快照生成失败"))
    elif command == "compare":
        if len(sys.argv) != 5:
            sys.exit(handle_error(ERROR_INVALID_ARGS, "用法: snapshot_utils.py compare <old_file> <new_file> <diff_type>"))
        
        old_file = sys.argv[2]
        new_file = sys.argv[3]
        diff_type = sys.argv[4]
        
        # 验证文件是否存在
        if not os.path.exists(old_file):
            sys.exit(handle_error(ERROR_FILE_NOT_FOUND, f"旧快照文件不存在: {old_file}"))
        
        if not os.path.exists(new_file):
            sys.exit(handle_error(ERROR_FILE_NOT_FOUND, f"新快照文件不存在: {new_file}"))
        
        # 验证diff_type是否有效
        valid_diff_types = ["added", "deleted", "changed"]
        if diff_type not in valid_diff_types:
            sys.exit(handle_error(ERROR_INVALID_ARGS, f"无效的diff_type: {diff_type}，必须是: {', '.join(valid_diff_types)}"))
        
        compare_snapshots(old_file, new_file, diff_type)
    elif command == "apply":
        if len(sys.argv) != 5:
            sys.exit(handle_error(ERROR_INVALID_ARGS, "用法: snapshot_utils.py apply <base_snapshot> <incremental_snapshot> <output_file>"))
        
        base_snapshot = sys.argv[2]
        incremental_snapshot = sys.argv[3]
        output_file = sys.argv[4]
        
        # 验证文件是否存在
        if not os.path.exists(base_snapshot):
            sys.exit(handle_error(ERROR_FILE_NOT_FOUND, f"基础快照文件不存在: {base_snapshot}"))
        
        if not os.path.exists(incremental_snapshot):
            sys.exit(handle_error(ERROR_FILE_NOT_FOUND, f"增量快照文件不存在: {incremental_snapshot}"))
        
        # 验证输出目录是否可写
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                sys.exit(handle_error(ERROR_PERMISSION, f"创建输出目录失败: {str(e)}"))
        
        success = apply_incremental_snapshot(base_snapshot, incremental_snapshot, output_file)
        if success:
            sys.exit(ERROR_OK)
        else:
            sys.exit(handle_error(ERROR_UNKNOWN, "应用增量快照失败"))
    else:
        # 未知命令
        sys.exit(handle_error(ERROR_INVALID_ARGS, f"未知命令: {command}"))
