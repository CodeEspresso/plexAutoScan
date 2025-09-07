#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快照处理模块
"""

import os
import sys
# 增加整数字符串转换限制，解决大整数JSON序列化问题
if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)  # 设置为无限制
import json
import time
import hashlib
import subprocess
import shutil
from datetime import datetime
import logging
from pathlib import Path

# 删除: 使用错误路径的绝对导入
# 新增: 使用相对导入
from .config import Config
from .logger import RobustLogger
from .path_utils import ensure_directory, normalize_path, verify_path

# 初始化日志记录器
logger = RobustLogger('snapshot')


class SnapshotManager:
    """快照管理器类，负责生成、验证和管理目录快照"""
    
    def __init__(self, config=None):
        """初始化快照管理器
        
        Args:
            config (Config): 配置对象
        """
        self.config = config or Config('/Volumes/PSSD/项目/plexAutoScan/config.env')
        
        # 从配置中获取相关设置
        self.max_retries = self.config.get('MAX_RETRIES', 3)
        self.retry_delay = self.config.get('RETRY_DELAY', 2)
        self.snapshot_timeout = self.config.get('SNAPSHOT_TIMEOUT', 300)
        self.snapshot_dir = self.config.get('SNAPSHOT_DIR', '/tmp/snapshots')
        
        # 确保快照目录存在
        ensure_directory(self.snapshot_dir)
    
    # 即将修改的符号: generate_snapshot方法（参数和verify_path调用）
    
    def generate_snapshot(self, directory_path, force_update=False, test_env=False):
        """生成目录快照
        
        Args:
            directory_path (str): 目录路径
            force_update (bool): 是否强制更新快照
            test_env (bool): 是否为测试环境
            
        Returns:
            tuple: (快照文件路径, 快照内容, 是否成功)
        """
        # 导入超时控制函数
        from .timeout_decorator import run_with_timeout
        
        # 核心快照生成逻辑
        def _generate_snapshot_core():
            try:
                # 验证目录路径 - 传递test_env参数
                verified_path, is_valid = verify_path(directory_path, test_env)
                if not is_valid:
                    logger.error(f"无效的目录路径: {directory_path}")
                    return '', {}, False
                
                # 获取快照文件名
                snapshot_filename = self._get_snapshot_filename(verified_path)
                snapshot_path = os.path.join(self.snapshot_dir, snapshot_filename)
                
                # 检查是否需要生成新快照
                if os.path.exists(snapshot_path) and not force_update:
                    # 尝试读取现有快照
                    try:
                        with open(snapshot_path, 'r', encoding='utf-8') as f:
                            snapshot_content = json.load(f)
                        logger.debug(f"使用现有快照: {snapshot_path}")
                        return snapshot_path, snapshot_content, True
                    except Exception as e:
                        logger.error(f"读取现有快照失败 {snapshot_path}: {str(e)}")
                
                # 如果存在旧快照且不是强制更新，先备份旧快照
                # 先初始化snapshot_content变量
                snapshot_content = None
                
                if os.path.exists(snapshot_path):
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    backup_path = f"{snapshot_path}.{timestamp}.old"
                    try:
                        shutil.copy2(snapshot_path, backup_path)
                        logger.info(f"已备份旧快照到: {backup_path}")
                    except Exception as e:
                        logger.warning(f"备份旧快照失败: {str(e)}")
                
                # 调用Python模块生成快照
                # 确保可以导入snapshot_utils模块
                import sys
                # 添加项目根目录到Python路径
                sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from ..snapshot_utils import generate_snapshot
                
                # 准备快照输出路径
                temp_snapshot_path = os.path.join(self.snapshot_dir, f'temp_{hashlib.md5(verified_path.encode()).hexdigest()}.snapshot')
                
                # 获取配置中的最小文件大小（MB），并添加验证逻辑
                min_file_size_mb = self.config.get('MIN_FILE_SIZE_MB', 10)
                
                # 验证MIN_FILE_SIZE_MB是否为有效数字且在合理范围内
                try:
                    min_file_size_mb = float(min_file_size_mb)
                    # 设置合理的范围：0-10000 MB (10GB)
                    if min_file_size_mb < 0:
                        min_file_size_mb = 0
                    elif min_file_size_mb > 10000:
                        logger.warning(f"最小文件大小 {min_file_size_mb} MB 超出合理范围，使用默认值10MB")
                        min_file_size_mb = 10
                except (ValueError, TypeError):
                    logger.error(f"无效的最小文件大小配置: {min_file_size_mb}，使用默认值10MB")
                    min_file_size_mb = 10
                
                logger.info(f"使用最小文件大小过滤: {min_file_size_mb} MB")
                
                # 调用generate_snapshot函数，使用配置中的最小文件大小
                result = generate_snapshot(
                    dir=verified_path,
                    output_file=temp_snapshot_path,
                    scan_delay=0.1,
                    max_files=0,  # 无限制
                    skip_large=False,
                    large_threshold=10000,
                    min_size=0,
                    min_size_mb=min_file_size_mb
                )
                
                if result > 0:
                    # 读取生成的快照文件
                    try:
                        with open(temp_snapshot_path, 'rb') as f:
                            raw_data = f.read().split(b'\x00')
                            # 转换为字典格式的快照内容，包含文件详细信息
                        files_with_details = []
                        for f in raw_data:
                            if f:
                                file_path = f.decode('utf-8', errors='replace')
                                try:
                                    if os.path.isfile(file_path):
                                        file_size = os.path.getsize(file_path)
                                        file_mtime = os.path.getmtime(file_path)
                                        files_with_details.append({
                                            'path': file_path,
                                            'size': file_size,
                                            'mtime': file_mtime
                                        })
                                    else:
                                        # 对于非文件（目录或链接），添加基本信息
                                        files_with_details.append({
                                            'path': file_path,
                                            'size': 0,
                                            'mtime': 0
                                        })
                                except Exception as e:
                                    logger.warning(f"获取文件信息失败 {file_path}: {str(e)}")
                                    files_with_details.append({
                                        'path': file_path,
                                        'size': 0,
                                        'mtime': 0
                                    })
                        
                        snapshot_content = {
                            'files': files_with_details,
                            'directory': verified_path,
                            'timestamp': datetime.now().isoformat(),
                            'file_count': result,
                            'min_file_size_mb': min_file_size_mb  # 记录使用的最小文件大小
                        }
                        # 清理临时文件
                        try:
                            os.remove(temp_snapshot_path)
                        except:
                            pass
                        
                        # 输出扫描统计信息
                        logger.info(f"扫描目录 {verified_path}: 找到 {len(snapshot_content['files'])} 个文件 (忽略小于 {min_file_size_mb} MB 的文件)")
                    except Exception as e:
                        logger.error(f"读取快照文件失败: {str(e)}")
                        return '', {}, False
                else:
                    logger.error(f"生成快照失败，返回码: {result}")
                    return '', {}, False
                
                # 保存快照
                try:
                    if snapshot_content:
                        with open(snapshot_path, 'w', encoding='utf-8') as f:
                            json.dump(snapshot_content, f, ensure_ascii=False, indent=2)
                        logger.info(f"快照生成成功: {snapshot_path}")
                        return snapshot_path, snapshot_content, True
                    else:
                        logger.error(f"无法保存快照: snapshot_content为空")
                        return '', {}, False
                except Exception as e:
                    logger.error(f"保存快照失败 {snapshot_path}: {str(e)}")
                    return '', {}, False
            except Exception as e:
                logger.error(f"生成快照过程中发生错误: {str(e)}")
                return '', {}, False
        
        # 使用try-except捕获生成快照过程中的错误
        try:
            result = _generate_snapshot_core()
        except Exception as e:
            logger.error(f"生成快照过程中发生错误: {str(e)}")
            result = ('', {}, False)
        
        # 返回结果，错误处理由调用方统一管理
        snapshot_path, snapshot_content, is_success = result
        
        return result
    
    def _get_snapshot_filename(self, directory_path):
        """获取快照文件名
        
        Args:
            directory_path (str): 目录路径
            
        Returns:
            str: 快照文件名
        """
        try:
            # 规范化路径
            normalized_path = normalize_path(directory_path)
            
            # 使用路径的哈希值作为文件名的一部分
            path_hash = hashlib.md5(normalized_path.encode('utf-8')).hexdigest()[:10]
            
            # 添加时间戳以避免冲突
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            
            # 生成文件名
            filename = f'snapshot_{path_hash}_{timestamp}.json'
            
            return filename
        except Exception as e:
            logger.error(f"生成快照文件名失败 {directory_path}: {str(e)}")
            # 返回默认文件名作为后备方案
            return f'snapshot_default_{time.time()}.json'
    
    def verify_snapshot(self, snapshot_path):
        """验证快照文件的有效性
        
        Args:
            snapshot_path (str): 快照文件路径
            
        Returns:
            bool: 快照是否有效
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(snapshot_path):
                logger.warning(f"快照文件不存在: {snapshot_path}")
                return False
            
            # 检查文件大小
            file_size = os.path.getsize(snapshot_path)
            if file_size < 100:  # 至少需要100字节
                logger.warning(f"快照文件太小: {snapshot_path} ({file_size}字节)")
                return False
            
            # 尝试解析JSON
            try:
                with open(snapshot_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                
                # 检查必要字段
                required_fields = ['directory', 'timestamp', 'files']
                for field in required_fields:
                    if field not in content:
                        logger.warning(f"快照文件缺少必要字段 '{field}': {snapshot_path}")
                        return False
                
                # 检查文件列表是否为空
                if not content.get('files'):
                    logger.warning(f"快照文件的文件列表为空: {snapshot_path}")
                    return False
                
                return True
            except json.JSONDecodeError as e:
                logger.error(f"快照文件JSON格式错误 {snapshot_path}: {str(e)}")
                return False
            except Exception as e:
                logger.error(f"验证快照文件失败 {snapshot_path}: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"验证快照过程中发生错误: {str(e)}")
            return False
    
    def compare_snapshots(self, old_snapshot_path, new_snapshot_path):
        """比较两个快照文件
        
        Args:
            old_snapshot_path (str): 旧快照文件路径
            new_snapshot_path (str): 新快照文件路径
            
        Returns:
            dict: 比较结果
        """
        # 导入超时控制函数
        from .timeout_decorator import run_with_timeout
        
        # 核心比较逻辑
        def _compare_snapshots_core():
            try:
                # 验证两个快照文件
                if not self.verify_snapshot(old_snapshot_path):
                    logger.error(f"旧快照文件无效: {old_snapshot_path}")
                    return {'success': False, 'error': 'invalid_old_snapshot'}
                
                if not self.verify_snapshot(new_snapshot_path):
                    logger.error(f"新快照文件无效: {new_snapshot_path}")
                    return {'success': False, 'error': 'invalid_new_snapshot'}
                
                # 读取快照内容
                with open(old_snapshot_path, 'r', encoding='utf-8') as f:
                    old_snapshot = json.load(f)
                
                with open(new_snapshot_path, 'r', encoding='utf-8') as f:
                    new_snapshot = json.load(f)
                
                # 提取文件列表
                old_files = {f.get('path'): f for f in old_snapshot.get('files', [])}
                new_files = {f.get('path'): f for f in new_snapshot.get('files', [])}
                
                # 计算变更
                added_files = [f for path, f in new_files.items() if path not in old_files]
                removed_files = [f for path, f in old_files.items() if path not in new_files]
                
                # 检查修改的文件
                modified_files = []
                for path, new_file in new_files.items():
                    if path in old_files:
                        old_file = old_files[path]
                        # 比较文件大小和修改时间
                        if (new_file.get('size') != old_file.get('size') or 
                            new_file.get('mtime') != old_file.get('mtime')):
                            modified_files.append(new_file)
                
                # 构建结果
                result = {
                    'success': True,
                    'old_snapshot': old_snapshot.get('directory'),
                    'new_snapshot': new_snapshot.get('directory'),
                    'timestamp_old': old_snapshot.get('timestamp'),
                    'timestamp_new': new_snapshot.get('timestamp'),
                    'added': len(added_files),
                    'removed': len(removed_files),
                    'modified': len(modified_files),
                    'added_files': added_files,
                    'removed_files': removed_files,
                    'modified_files': modified_files
                }
                
                logger.info(f"快照比较结果: 添加{len(added_files)}个文件, 删除{len(removed_files)}个文件, 修改{len(modified_files)}个文件")
                return result
            except Exception as e:
                logger.error(f"比较快照过程中发生错误: {str(e)}")
                return {'success': False, 'error': str(e)}
        
        # 检测Docker环境并设置超时时间
        import os
        is_docker = os.environ.get('DOCKER_ENV') == '1' or os.path.exists('/.dockerenv')
        
        # 设置超时时间 - Docker环境下设置为300秒（5分钟），默认环境下设置为600秒（10分钟）
        timeout_seconds = 300 if is_docker else 600
        
        # 使用run_with_timeout执行核心逻辑
        result = run_with_timeout(
            _compare_snapshots_core,
            timeout_seconds=timeout_seconds,
            default={'success': False, 'error': f'比较快照超时（{timeout_seconds}秒）'},
            error_message=f'比较快照超时（{timeout_seconds}秒）'
        )
        
        return result
    
    def clean_old_snapshots(self, max_age_days=7, max_count=10):
        """清理旧快照文件
        
        Args:
            max_age_days (int): 最大保留天数
            max_count (int): 最多保留的快照数量
            
        Returns:
            dict: 清理结果
        """
        try:
            if not os.path.exists(self.snapshot_dir):
                logger.warning(f"快照目录不存在: {self.snapshot_dir}")
                return {'success': False, 'error': 'directory_not_exists'}
            
            # 获取所有快照文件
            snapshot_files = []
            for filename in os.listdir(self.snapshot_dir):
                if filename.startswith('snapshot_') and filename.endswith('.json'):
                    filepath = os.path.join(self.snapshot_dir, filename)
                    if os.path.isfile(filepath):
                        # 获取文件的修改时间和大小
                        mtime = os.path.getmtime(filepath)
                        size = os.path.getsize(filepath)
                        snapshot_files.append((filepath, mtime, size))
            
            # 按照修改时间排序（最新的在前）
            snapshot_files.sort(key=lambda x: x[1], reverse=True)
            
            # 计算删除的文件
            files_to_delete = []
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            # 保留最新的max_count个快照
            if len(snapshot_files) > max_count:
                files_to_delete.extend([f[0] for f in snapshot_files[max_count:]])
            
            # 删除超过最大保留天数的快照
            for filepath, mtime, _ in snapshot_files[:max_count]:  # 只检查保留的快照
                if current_time - mtime > max_age_seconds:
                    files_to_delete.append(filepath)
            
            # 去重
            files_to_delete = list(set(files_to_delete))
            
            # 执行删除
            deleted_count = 0
            failed_count = 0
            
            for filepath in files_to_delete:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.debug(f"已删除旧快照: {filepath}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"删除快照文件失败 {filepath}: {str(e)}")
            
            result = {
                'success': True,
                'total_snapshots': len(snapshot_files),
                'deleted_count': deleted_count,
                'failed_count': failed_count,
                'remaining_count': len(snapshot_files) - deleted_count
            }
            
            logger.info(f"清理快照完成: 删除{deleted_count}个文件, 失败{failed_count}个文件, 剩余{result['remaining_count']}个文件")
            return result
        except Exception as e:
            logger.error(f"清理快照过程中发生错误: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def run_command_with_timeout(self, command, timeout=None):
        """执行命令并设置超时
        
        Args:
            command (list): 命令及其参数
            timeout (int): 超时时间（秒）
            
        Returns:
            dict: 命令执行结果
        """
        if timeout is None:
            timeout = self.snapshot_timeout
        
        result = {
            'success': False,
            'stdout': '',
            'stderr': '',
            'returncode': None,
            'error': None
        }
        
        try:
            # 开始时间
            start_time = time.time()
            
            # 执行命令
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            
            # 等待命令完成或超时
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                result['stdout'] = stdout
                result['stderr'] = stderr
                result['returncode'] = process.returncode
                result['success'] = process.returncode == 0
            except subprocess.TimeoutExpired:
                # 超时，终止进程
                process.kill()
                stdout, stderr = process.communicate()
                result['stdout'] = stdout
                result['stderr'] = stderr
                result['error'] = f"Command timed out after {timeout} seconds"
            
            # 记录执行时间
            execution_time = time.time() - start_time
            logger.debug(f"Command executed in {execution_time:.2f} seconds: {command}")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"执行命令失败 {command}: {str(e)}")
        
        return result
    
    def create_smb_command(self, action, path, *args):
        """创建SMB命令
        
        Args:
            action (str): 操作类型 (list/exists/info)
            path (str): SMB路径
            *args: 额外参数
            
        Returns:
            list: 命令列表
        """
        try:
            # 这里应该根据不同的操作系统和SMB客户端选择合适的命令
            # 例如，在macOS上可以使用smbutil，在Linux上可以使用smbclient等
            
            if sys.platform == 'darwin':  # macOS
                if action == 'list':
                    return ['smbutil', 'view', '-g', path]
                elif action == 'exists':
                    # 在macOS上检查SMB路径是否存在的逻辑
                    return ['ls', '-la', path]
                else:
                    # 默认使用ls命令获取信息
                    return ['ls', '-la', path]
            else:
                # 其他平台，使用smbclient（需要安装）
                smbclient_cmd = ['smbclient', path]
                if action == 'list':
                    smbclient_cmd.extend(['-c', 'ls'])
                elif action == 'exists':
                    smbclient_cmd.extend(['-c', 'exists'])
                elif action == 'info':
                    smbclient_cmd.extend(['-c', 'allinfo'])
                
                # 添加额外参数
                smbclient_cmd.extend(args)
                
                return smbclient_cmd
        except Exception as e:
            logger.error(f"创建SMB命令失败: {str(e)}")
            return []
    
    def run_smb_command_with_retry(self, action, path, *args, retries=None):
        """运行SMB命令并带有重试机制
        
        Args:
            action (str): 操作类型
            path (str): SMB路径
            *args: 额外参数
            retries (int): 重试次数
            
        Returns:
            dict: 命令执行结果
        """
        # 导入超时控制函数
        from .timeout_decorator import run_with_timeout
        
        # 核心SMB命令执行逻辑
        def _run_smb_command_with_retry_core():
            if retries is None:
                local_retries = self.max_retries
            else:
                local_retries = retries
            
            # 指数退避策略：每次重试的延迟时间呈指数增长
            base_delay = self.retry_delay
            
            for attempt in range(local_retries + 1):
                # 创建命令
                command = self.create_smb_command(action, path, *args)
                if not command:
                    return {'success': False, 'error': 'failed_to_create_command'}
                
                # 执行命令
                result = self.run_command_with_timeout(command)
                
                # 如果成功，直接返回结果
                if result.get('success'):
                    return result
                
                # 如果是最后一次尝试，返回失败结果
                if attempt >= local_retries:
                    logger.error(f"SMB命令执行失败，已达到最大重试次数 {local_retries}: {command}")
                    return result
                
                # 计算退避时间
                delay = base_delay * (2 ** attempt)
                logger.warning(f"SMB命令执行失败，{delay}秒后重试 ({attempt + 1}/{local_retries}): {result.get('error') or result.get('stderr')}")
                
                # 等待退避时间
                time.sleep(delay)
            
            # 这行代码理论上不会执行到，但为了安全起见，添加返回
            return {'success': False, 'error': 'unexpected_error'}
        
        # 检测Docker环境并设置超时时间
        import os
        is_docker = os.environ.get('DOCKER_ENV') == '1' or os.path.exists('/.dockerenv')
        
        # 设置超时时间 - 考虑到重试机制，设置较长的超时时间
        # Docker环境下设置为300秒（5分钟），默认环境下设置为600秒（10分钟）
        timeout_seconds = 300 if is_docker else 600
        
        # 使用run_with_timeout执行核心逻辑
        result = run_with_timeout(
            _run_smb_command_with_retry_core,
            timeout_seconds=timeout_seconds,
            default={'success': False, 'error': f'SMB命令执行超时（{timeout_seconds}秒）'},
            error_message=f'SMB命令执行超时（{timeout_seconds}秒）'
        )
        
        return result