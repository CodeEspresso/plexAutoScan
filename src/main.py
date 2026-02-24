#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PlexAutoScan - 自动扫描和更新Plex媒体库
"""

import os
import sys
import json
import time
import logging
import argparse
import subprocess
import hashlib
from datetime import datetime

# 导入超时控制模块
from .utils.timeout_decorator import timeout, run_with_timeout, TimeoutContext, timeout_config

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入自定义模块
from .utils.config import Config
from .utils.logger import setup_logger, RobustLogger
from .utils.path_utils import normalize_path, verify_path, ensure_directory
from .utils.snapshot import SnapshotManager
from .snapshot_utils import calculate_checksum
from .plex.api import PlexAPI
from .plex.library import PlexLibraryManager
from .dependencies import DependencyManager

class PlexAutoScan:
    """PlexAutoScan主类"""
    
    def __init__(self, config_path=None, debug=False):
        """初始化PlexAutoScan
        
        Args:
            config_path (str): 配置文件路径
            debug (bool): 是否启用调试模式
        """
        # 设置调试模式
        self.debug = debug
        
        # 保存配置文件路径
        self.config_path = config_path
        
        # 初始化配置
        self.config = Config(config_path)
        
        # 根据debug参数覆盖配置中的日志级别
        if self.debug:
            # 直接访问_config字典，因为Config类没有set方法
            self.config._config['LOG_LEVEL'] = 'DEBUG'
        
        # 初始化日志
        setup_logger(
            name='plex_autoscan',
            level=self.config.get('LOG_LEVEL', 'INFO'),
            log_file=self.config.get('LOG_FILE', '')
        )
        self.logger = RobustLogger('plex_autoscan')
        
        # 初始化依赖管理器
        self.dependency_manager = DependencyManager(self.config)
        
        # 初始化快照管理器
        self.snapshot_manager = SnapshotManager(self.config)
        
        # 检查是否启用Plex集成
        enable_plex = self.config.enable_plex
        self.logger.info(f"Plex集成状态: {'启用' if enable_plex else '禁用'}")
        
        # 初始化Plex API客户端
        self.plex_api = None
        self.library_manager = None
        
        if enable_plex:
            try:
                self.plex_api = PlexAPI(self.config)
                self.logger.info("Plex API客户端初始化成功")
                
                # [MOD] 2026-02-24 将 Plex API 设置到 SnapshotManager，支持首次扫描对比 by AI
                self.snapshot_manager.set_plex_api(self.plex_api)
                
                # 只有在Plex API初始化成功后才初始化媒体库管理器
                try:
                    self.library_manager = PlexLibraryManager(self.config, self.plex_api)
                    self.logger.info("Plex媒体库管理器初始化成功")
                except Exception as e:
                    self.logger.error(f"初始化媒体库管理器失败: {str(e)}")
                    self.library_manager = None
            except ValueError as e:
                self.logger.error(f"初始化Plex API失败: {str(e)}")
                self.plex_api = None
                self.library_manager = None
        else:
            self.logger.info("Plex集成已禁用，跳过Plex相关组件的初始化")
        
        # 初始化计数器
        self.success_count = 0
        self.failure_count = 0
        self.skipped_count = 0
        
        # 守护模式配置
        self.daemon_mode = self.config.get('DAEMON_MODE', '1') == '1'
        self.check_interval = int(self.config.get('CHECK_INTERVAL', '600'))
        self.skipped_directories = []
        self._shutdown_requested = False
    
    def _setup_signal_handlers(self):
        """设置信号处理器，支持优雅退出"""
        import signal
        def signal_handler(signum, frame):
            self.logger.info(f"收到信号 {signum}，准备优雅退出...")
            self._shutdown_requested = True
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        self.logger.debug("信号处理器已设置")
    
    def run(self):
        """运行PlexAutoScan主程序"""
        self.logger.info("=== PlexAutoScan 启动 ===")
        
        # 设置信号处理器
        self._setup_signal_handlers()
        
        # 显示运行模式
        if self.daemon_mode:
            self.logger.info(f"运行模式: 守护模式，检查间隔: {self.check_interval}秒")
        else:
            self.logger.info("运行模式: 单次运行")
        
        # 收集环境信息
        self.logger.info(f"环境信息: DOCKER_ENV={os.environ.get('DOCKER_ENV', '0')}, DEBUG={self.debug}")
        
        # 打印最小文件大小（只在启动时打印一次，以MB为单位）
        min_file_size_mb = self.config.get('MIN_FILE_SIZE_MB', 10)
        try:
            min_file_size_mb_val = float(min_file_size_mb)
            if min_file_size_mb_val < 0:
                min_file_size_mb_val = 0
            elif min_file_size_mb_val > 10000:
                min_file_size_mb_val = 10
            self.logger.info(f"使用最小文件大小: {min_file_size_mb_val} MB")
        except (ValueError, TypeError):
            self.logger.warning(f"无效的最小文件大小配置: {min_file_size_mb}，使用默认值10MB")
        
        # 检查依赖
        self.logger.info("正在检查依赖...")
        dependency_check = self.dependency_manager.check_all_dependencies()
        
        if not dependency_check['success']:
            # 尝试自动安装缺失的依赖
            self.logger.warning("核心依赖缺失，尝试自动安装...")
            missing_deps = self.dependency_manager.get_missing_core_dependencies()
            if missing_deps:
                self.logger.info(f"开始安装缺失的依赖: {', '.join(missing_deps)}")
                
                # 先尝试清理pip缓存
                try:
                    self.logger.debug("尝试清理pip缓存...")
                    subprocess.run(
                        [sys.executable, '-m', 'pip', 'cache', 'purge'],
                        capture_output=True,
                        text=True
                    )
                except Exception as e:
                    self.logger.warning(f"清理pip缓存失败: {str(e)}")
                
                install_success = self.dependency_manager.install_python_dependencies()
                if not install_success:
                    self.logger.error("依赖安装失败，尝试修复模式继续运行")
                    if self._try_repair_mode():
                        self.logger.warning("进入修复模式继续运行")
                    else:
                        self.logger.error("无法进入修复模式，程序无法继续运行")
                        return False
                # 重新检查依赖
                self.logger.info("依赖安装完成，重新检查...")
                dependency_check = self.dependency_manager.check_all_dependencies()
                if not dependency_check['success']:
                    self.logger.error("依赖安装后仍有缺失，尝试识别关键依赖")
                    critical_missing = [dep for dep in ['pysmb'] if dep in self.dependency_manager.get_missing_core_dependencies()]
                    if critical_missing:
                        self.logger.error(f"关键依赖缺失: {', '.join(critical_missing)}，程序无法继续运行")
                        return False
                    else:
                        self.logger.warning("非关键依赖缺失，尝试以降级模式继续运行")
        
        # 检查Python版本
        self.logger.info("正在检查Python版本...")
        if not self.dependency_manager.check_python_version((3, 8, 0)):
            self.logger.warning("Python版本可能不兼容，可能会出现问题")
        
        # 守护循环
        cycle_count = 0
        while True:
            cycle_count += 1
            cycle_start_time = time.time()
            
            if self.daemon_mode:
                self.logger.info(f"=== 开始第 {cycle_count} 次扫描周期 ===")
            
            try:
                # 加载配置
                self.logger.info("正在加载配置...")
                
                # 清理旧快照
                self.logger.info("正在清理旧快照...")
                self.snapshot_manager.clean_old_snapshots(
                    max_age_days=self.config.get('SNAPSHOT_RETENTION_DAYS', 7),
                    max_count=self.config.get('MAX_SNAPSHOTS', 10)
                )
                
                # 更新媒体库缓存
                if self.library_manager:
                    self.logger.info("正在更新媒体库缓存...")
                    self.library_manager.refresh_libraries()
                else:
                    self.logger.warning("媒体库管理器不可用，跳过媒体库缓存更新")
                
                # 获取需要处理的目录列表
                directories = self._get_directories_to_process()
                
                if not directories:
                    self.logger.warning("没有找到需要处理的目录")
                else:
                    self.logger.info(f"找到{len(directories)}个需要处理的目录")
                    
                    # 处理目录
                    self._process_directories(directories)
                
                # 计算本次周期耗时
                cycle_elapsed = time.time() - cycle_start_time
                
                # 打印本次周期统计
                self.logger.info(f"=== 第 {cycle_count} 次扫描周期统计 ===")
                self.logger.info(f"成功处理: {self.success_count}")
                self.logger.info(f"处理失败: {self.failure_count}")
                self.logger.info(f"已跳过: {self.skipped_count}")
                self.logger.info(f"跳过的目录: {len(self.skipped_directories)}")
                self.logger.info(f"本次耗时: {cycle_elapsed:.2f}秒")
                
            except Exception as e:
                self.logger.error(f"扫描周期出错: {str(e)}")
                import traceback
                self.logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            # 检查是否请求退出
            if self._shutdown_requested:
                self.logger.info("收到退出请求，结束运行")
                break
            
            # 非守护模式则退出
            if not self.daemon_mode:
                self.logger.info("单次运行模式，退出程序")
                break
            
            # 守护模式：等待下次检查
            self.logger.info(f"等待 {self.check_interval} 秒后进行下次检查...")
            
            # 分段等待，以便响应退出信号
            wait_remaining = self.check_interval
            while wait_remaining > 0 and not self._shutdown_requested:
                wait_time = min(10, wait_remaining)
                time.sleep(wait_time)
                wait_remaining -= wait_time
            
            if self._shutdown_requested:
                self.logger.info("收到退出请求，结束运行")
                break
            
            # 重置计数器
            self.success_count = 0
            self.failure_count = 0
            self.skipped_count = 0
        
        self.logger.info("=== PlexAutoScan 结束 ===")
        return True
        
    def _try_repair_mode(self):
        """尝试以修复模式运行程序
        
        Returns:
            bool: 是否成功进入修复模式
        """
        try:
            self.logger.info("=== 尝试进入修复模式 ===")
            
            # 重新检查关键依赖
            missing_core = self.dependency_manager.get_missing_core_dependencies()
            
            # 检查是否有至少一些核心依赖可用
            if not missing_core:
                self.logger.warning("没有检测到缺失的核心依赖，但之前的检查失败了，尝试重新初始化")
                return True
            
            self.logger.info(f"缺失的核心依赖: {', '.join(missing_core)}")
            
            # 检查是否有关键依赖可用
            available_core = [dep for dep in self.dependency_manager.core_dependencies.values() \
                             if dep not in missing_core]
            
            if available_core:
                self.logger.info(f"可用的核心依赖: {', '.join(available_core)}")
            else:
                self.logger.error("没有可用的核心依赖，无法进入修复模式")
                return False
            
            # 根据可用依赖调整功能
            self.logger.info("根据可用依赖调整功能...")
            
            # 重新尝试初始化基本组件
            try:
                # 尝试重新初始化配置，使用之前的配置文件路径或默认路径
                config_path = getattr(self, 'config_path', None) or '/data/config.env'
                self.config = Config(config_path)
                self.logger.info(f"配置重新初始化成功: {config_path}")
                
                # 尝试重新初始化日志
                setup_logger(
                    name='plex_autoscan',
                    level=self.config.get('LOG_LEVEL', 'INFO'),
                    log_file=self.config.get('LOG_FILE', '')
                )
                self.logger = RobustLogger('plex_autoscan')
                self.logger.info("日志重新初始化成功")
                
                # 提供修复建议
                self.logger.info("修复建议:")
                for dep in missing_core:
                    self.logger.info(f"- 手动安装依赖: python -m pip install {dep} --user --upgrade")
                
                return True
            except Exception as e:
                self.logger.error(f"重新初始化组件失败: {str(e)}")
                return False
        except Exception as e:
            self.logger.error(f"进入修复模式时出错: {str(e)}")
            return False
    
    def _get_directories_to_process(self):
        """获取需要处理的目录列表
        
        Returns:
            list: 目录路径列表
        """
        # 使用Config类提供的get_mount_paths方法获取目录列表
        directories = self.config.get_mount_paths()
        
        # 调试：打印原始目录列表
        self.logger.info(f"原始目录列表数量: {len(directories)}")
        for i, d in enumerate(directories):
            self.logger.debug(f"  原始目录[{i}]: [{d}]")
        
        # 去重和规范化
        normalized_dirs = []
        
        for directory in directories:
            if directory:
                norm_dir = normalize_path(directory)
                self.logger.debug(f"规范化: [{directory}] -> [{norm_dir}]")
                if norm_dir and norm_dir not in normalized_dirs:
                    normalized_dirs.append(norm_dir)
                elif not norm_dir:
                    self.logger.warning(f"规范化后为空，跳过: [{directory}]")
        
        self.logger.info(f"获取到{len(normalized_dirs)}个需要处理的目录")
        for i, d in enumerate(normalized_dirs):
            self.logger.info(f"  处理目录[{i}]: [{d}]")
        return normalized_dirs
    
    def _process_directories(self, directories):
        """处理目录列表
        
        Args:
            directories (list): 目录路径列表
        """
        # 记录所有无效路径的详细信息
        invalid_paths = []
        
        # 优先检查之前跳过的目录是否已恢复
        if self.skipped_directories:
            self.logger.info(f"检查 {len(self.skipped_directories)} 个之前跳过的目录是否已恢复...")
            recovered_dirs = []
            for skipped_dir in self.skipped_directories[:]:
                verified_dir, is_valid = verify_path(skipped_dir)
                if is_valid:
                    self.logger.info(f"目录已恢复: {skipped_dir}")
                    recovered_dirs.append(verified_dir)
                    self.skipped_directories.remove(skipped_dir)
            
            if recovered_dirs:
                self.logger.info(f"发现 {len(recovered_dirs)} 个恢复的目录，优先处理")
                for recovered_dir in recovered_dirs:
                    try:
                        result = self._process_directory(recovered_dir)
                        if result:
                            self.success_count += 1
                            self.logger.info(f"恢复的目录 {recovered_dir} 处理成功")
                        else:
                            self.logger.warning(f"恢复的目录 {recovered_dir} 处理完成但没有更新媒体库")
                            self.success_count += 1
                    except Exception as e:
                        self.logger.error(f"处理恢复的目录失败 {recovered_dir}: {str(e)}")
                        self.failure_count += 1
        
        # 检查是否有可用的目录
        any_valid_dir = False
        for directory in directories:
            # 验证目录
            verified_dir, is_valid = verify_path(directory)
            
            if not is_valid:
                self.logger.warning(f"跳过无效目录: {directory} (验证结果: {verified_dir})")
                invalid_paths.append(f"{directory} -> {verified_dir}")
                self.skipped_count += 1
                # 记录跳过的目录，以便下次检查
                if directory not in self.skipped_directories:
                    self.skipped_directories.append(directory)
                continue
            
            any_valid_dir = True
            break
        
        # 如果没有可用的目录，记录详细警告并退出
        if not any_valid_dir:
            self.logger.error("=" * 60)
            self.logger.error("所有目录都不可用！")
            self.logger.error(f"配置的目录数量: {len(directories)}")
            self.logger.error(f"无效路径详情:")
            for invalid_path in invalid_paths:
                self.logger.error(f"  - {invalid_path}")
            self.logger.error("=" * 60)
            if self.daemon_mode:
                self.logger.warning(f"将在 {self.check_interval} 秒后重试")
            return
        
        # 处理可用的目录
        for directory in directories:
            # 验证目录
            verified_dir, is_valid = verify_path(directory)
            
            if not is_valid:
                self.logger.warning(f"跳过无效目录: {directory}")
                self.skipped_count += 1
                # 记录跳过的目录，以便下次检查
                if directory not in self.skipped_directories:
                    self.skipped_directories.append(directory)
                continue
            
            # 处理目录
            try:
                result = self._process_directory(verified_dir)
                if result:
                    self.success_count += 1
                    self.logger.info(f"目录 {verified_dir} 处理成功")
                else:
                    self.logger.warning(f"目录 {verified_dir} 处理完成但没有更新媒体库")
                    # 不算作失败，而是"部分成功"
                    self.success_count += 1  # 或者考虑添加一个partial_success_count计数器
            except Exception as e:
                self.logger.error(f"处理目录失败 {verified_dir}: {str(e)}")
                self.failure_count += 1
                # 记录异常堆栈信息以便调试
                import traceback
                self.logger.error(f"异常详情: {traceback.format_exc()}")
    
    # 即将修改的符号: _process_directory方法（调用generate_snapshot时传递test_env参数）
    
    def _process_directory(self, directory):
        """处理单个目录

        Args:
            directory (str): 目录路径
        """
        self.logger.info(f"开始扫描目录: {directory}")

        # 记录开始时间
        start_time = time.time()

        # 定义核心处理逻辑函数，用于超时控制
        def _process_directory_core():
            try:
                # 生成目录快照并获取新增文件列表
                # 变更理由：使用新增文件列表判断是否触发Plex扫描，比"首次扫描"标志更可靠
                snapshot_path, snapshot_content, is_success, added_files = self.snapshot_manager.generate_snapshot(
                    directory
                )

                if not is_success:
                    self.logger.error(f"生成快照过程中出现问题: {directory}")
                    if not snapshot_content or not snapshot_content.get('files'):
                        self.logger.warning("没有可用的文件数据，跳过媒体库更新")
                        return False

                # 如果没有新增文件，跳过 Plex 扫描
                if not added_files:
                    self.logger.info(f"目录 {directory} 无新增文件，跳过 Plex 媒体库扫描")
                    return True

                self.logger.info(f"目录 {directory} 发现 {len(added_files)} 个新增文件，准备触发 Plex 扫描")

                # 获取最小文件大小配置
                min_file_size_mb = self.config.get('MIN_FILE_SIZE_MB', 10)
                try:
                    min_file_size_mb_val = float(min_file_size_mb)
                    min_file_size_bytes = min_file_size_mb_val * 1024 * 1024
                except (ValueError, TypeError):
                    min_file_size_bytes = 10 * 1024 * 1024
                
                # 过滤新增文件中的小文件
                filtered_added_files = []
                for file_path in added_files:
                    try:
                        if os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)
                            if file_size >= min_file_size_bytes:
                                filtered_added_files.append(file_path)
                    except Exception as e:
                        self.logger.warning(f"检查文件失败 {file_path}: {str(e)}")
                
                self.logger.info(f"过滤后新增文件数量: {len(filtered_added_files)}")
                
                if not filtered_added_files:
                    self.logger.warning(f"新增文件均小于 {min_file_size_mb} MB，跳过媒体库更新")
                    return True

                # 更新媒体库
                self.logger.info(f"准备更新媒体库: library_manager={self.library_manager is not None}")
                if self.library_manager:
                    self.logger.info(f"媒体库管理器已创建，检查初始化状态")
                    is_initialized = self.library_manager.is_initialized()
                    self.logger.info(f"媒体库管理器初始化状态: {is_initialized}")
                    if is_initialized:
                        self.logger.info(f"正在触发Plex媒体库扫描... 目录={directory}, 新增文件数量={len(filtered_added_files)}")
                        updated_files_count = self.library_manager.update_library_with_files(
                            directory, 
                            filtered_added_files
                        )
                        if updated_files_count > 0:
                            self.logger.info(f"✅ 媒体库扫描已触发，将处理 {updated_files_count} 个文件")
                        else:
                            self.logger.info("媒体库扫描请求已发送，但未成功触发扫描")
                    else:
                        self.logger.warning("媒体库管理器未初始化，跳过媒体库扫描")
                else:
                    self.logger.warning("媒体库管理器不可用，跳过媒体库更新")

                elapsed_time = time.time() - start_time
                self.logger.info(f"目录 {directory} 处理完成，耗时 {elapsed_time:.2f} 秒")
                return True
            except Exception as e:
                self.logger.error(f"处理目录时发生错误: {str(e)}")
                raise
        
        # 根据环境设置不同的超时时间
        timeout_seconds = timeout_config.get_timeout('very_long')  # 超长超时：30分钟
        self.logger.info(f"目录处理超时设置: {timeout_seconds}秒")
        
        # 使用带超时的方式运行核心处理逻辑
        success = run_with_timeout(
            _process_directory_core,
            timeout_seconds=timeout_seconds,
            default=False,
            error_message=f"目录 {directory} 处理超时 ({timeout_seconds}秒)",
        )
        
        if not success:
            self.logger.error(f"目录 {directory} 处理失败或超时")
            raise Exception(f"目录 {directory} 处理失败或超时")


# 添加主程序入口点，使src/main.py可以作为模块执行
if __name__ == "__main__":
    import sys
    import os
    
    # 解析命令行参数
    debug_mode = False
    config_path = None
    test_plex_scan = False
    
    for arg in sys.argv[1:]:
        if arg == '--debug':
            debug_mode = True
        elif arg.startswith('--config='):
            config_path = arg.split('=', 1)[1]
        elif arg == '--test-plex-scan':
            test_plex_scan = True
    
    # 在Docker环境中默认使用/data/config.env配置文件
    if config_path is None and os.path.exists('/data/config.env'):
        print("[INFO] 使用默认Docker配置文件路径: /data/config.env")
        config_path = '/data/config.env'
    
    # 执行Plex扫描测试模式
    if test_plex_scan:
        print("===== 启动Plex扫描测试模式 =====")
        
        # 设置简化的测试环境，避免使用完整的PlexAutoScan初始化
        try:
            # 设置临时目录路径，在任何环境中都使用安全路径
            temp_dir = '/tmp/plex_autoscan_test'
            os.makedirs(temp_dir, exist_ok=True)
            snapshots_dir = os.path.join(temp_dir, 'snapshots')
            cache_dir = os.path.join(temp_dir, 'cache')
            
            # 确保这些目录存在
            os.makedirs(snapshots_dir, exist_ok=True)
            os.makedirs(cache_dir, exist_ok=True)
            
            print(f"[INFO] 使用临时测试目录: {temp_dir}")
            print(f"[INFO] 快照目录: {snapshots_dir}")
            print(f"[INFO] 缓存目录: {cache_dir}")
            
            # 设置环境变量
            os.environ['SNAPSHOT_DIR'] = snapshots_dir
            os.environ['CACHE_DIR'] = cache_dir
            os.environ['PLEX_CACHE_DIR'] = cache_dir
            
            # 初始化日志
            from src.utils.logger import setup_logger, RobustLogger
            setup_logger(name='plex_autoscan_test', level='INFO')
            logger = RobustLogger('plex_autoscan_test')
            
            # 加载配置
            from src.utils.config import Config
            # 使用自定义配置文件路径
            if config_path is None:
                # 尝试使用默认配置文件路径
                default_paths = [
                    './config.env',
                    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.env'),
                    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'config.env')
                ]
                for path in default_paths:
                    if os.path.exists(path):
                        config_path = path
                        logger.info(f"使用默认配置文件: {config_path}")
                        break
            
            config = Config(config_path)
            
            # 直接覆盖配置中的路径设置
            if hasattr(config, '_config'):
                config._config['SNAPSHOT_DIR'] = snapshots_dir
                config._config['CACHE_DIR'] = cache_dir
                config._config['PLEX_CACHE_DIR'] = cache_dir
                logger.info("已强制设置配置路径")
            
            # 检查是否启用Plex集成
            enable_plex = config.get('ENABLE_PLEX', '1') == '1'
            if not enable_plex:
                logger.error("Plex集成已禁用，请设置ENABLE_PLEX=1")
                sys.exit(1)
            
            # 初始化Plex API和LibraryManager
            from src.plex.api import PlexAPI
            from src.plex.library import PlexLibraryManager
            
            # 修改PlexAPI类的cache_dir属性
            plex_api = None
            try:
                # 直接设置默认参数，避免使用Config中的设置
                original_init = PlexAPI.__init__
                
                def custom_init(self, config=None):
                    # 调用原始初始化
                    original_init(self, config)
                    # 强制覆盖缓存目录
                    self.cache_dir = cache_dir
                    logger.info(f"Plex API缓存目录已设置为: {self.cache_dir}")
                    # 确保缓存目录存在
                    os.makedirs(self.cache_dir, exist_ok=True)
                
                # 临时替换初始化方法
                PlexAPI.__init__ = custom_init
                
                # 创建PlexAPI实例
                plex_api = PlexAPI(config)
                logger.info("Plex API初始化成功")
                
                # 创建LibraryManager实例
                library_manager = PlexLibraryManager(config, plex_api)
                logger.info("Plex媒体库管理器初始化成功")
                
                # 测试特定目录的Plex扫描
                test_directory = "/vol02/CloudDrive/WebDAV/电影/动画电影"
                test_files = ["dummy_file1.mkv", "dummy_file2.mp4"]
                
                logger.info(f"[测试] 准备扫描目录: {test_directory}")
                logger.info(f"[测试] 模拟文件数量: {len(test_files)}")
                
                # 执行扫描测试
                result = library_manager.update_library_with_files(test_directory, test_files)
                
                logger.info(f"[测试] 扫描结果: {result} 个文件更新请求已处理")
                logger.info("===== Plex扫描测试模式结束 =====")
                sys.exit(0)
            except Exception as e:
                logger.error(f"测试失败: {str(e)}")
                import traceback
                logger.error(f"异常堆栈: {traceback.format_exc()}")
                sys.exit(1)
            finally:
                # 恢复原始初始化方法
                if 'original_init' in locals():
                    PlexAPI.__init__ = original_init
        except Exception as e:
            print(f"[ERROR] 测试环境设置失败: {str(e)}")
            import traceback
            print(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
            sys.exit(1)
    
    # 创建PlexAutoScan实例并运行
    try:
        autoscan = PlexAutoScan(config_path=config_path, debug=debug_mode)
        success = autoscan.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"程序运行失败: {str(e)}")
        sys.exit(1)