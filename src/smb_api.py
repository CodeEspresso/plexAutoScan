#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import threading
import socket
import sys
from smb.SMBConnection import SMBConnection
import logging

# 导入超时控制模块
from .utils.timeout_decorator import timeout, run_with_timeout, TimeoutContext
from .utils.environment import env_detector

# 设置socket超时时间
socket.setdefaulttimeout(30)

# 日志配置
logger = logging.getLogger(__name__)

# 平台检测
IS_WINDOWS = sys.platform == 'win32'
IS_LINUX = sys.platform == 'linux'
IS_DARWIN = sys.platform == 'darwin'

# Docker环境检测 - 使用统一的环境检测器
IS_DOCKER = env_detector.is_docker()

# 工具函数，用于获取平台特定路径分隔符
def get_path_separator(path):
    """根据平台和路径内容返回适当的路径分隔符"""
    if '\\' in path:
        return '\\'
    return '/' if not IS_WINDOWS else '\\'

# 工具函数，用于规范化路径分隔符
def normalize_path_separator(path):
    """根据当前平台规范化路径分隔符"""
    if not path:
        return path
    if IS_WINDOWS:
        return path.replace('/', '\\')
    else:
        return path.replace('\\', '/')

class SMBManager:
    """SMB连接管理类，提供SMB文件系统操作接口"""
    _instance = None
    _connections = {}
    _lock = threading.RLock()  # 添加可重入锁以确保线程安全

    @classmethod
    def get_instance(cls):
        """获取单例实例，确保线程安全"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = SMBManager()
            return cls._instance

    def __init__(self):
        """初始化SMB管理器"""
        self._connections = {}
        self._lock = threading.RLock()  # 实例级别的锁
        # 从环境变量获取SMB默认配置
        self.default_user = os.environ.get('SMB_USER', '')
        self.default_password = os.environ.get('SMB_PASSWORD', '')
        self.default_domain = os.environ.get('SMB_DOMAIN', '')
        
        # 网络状况监控
        self.network_health = 1.0  # 1.0表示最佳网络状况
        self.last_connection_attempts = []  # 记录最近连接尝试的结果
        self.max_attempts_history = 10  # 保留的连接尝试历史记录数
        
        # 根据平台和环境调整默认参数
        # 优化Docker环境下的参数
        self.default_timeout = 45 if IS_DOCKER else 30  # 减少Docker环境的默认超时
        self.default_keepalive_interval = 45 if IS_DOCKER else 30  # 减少Docker环境的默认保活间隔
        
        # 动态超时调整参数
        self.timeout_factor_high = 1.5  # 网络状况差时的超时因子
        self.timeout_factor_low = 0.7   # 网络状况好时的超时因子
        
        # 记录初始化信息
        logger.info(f"SMB管理器已初始化 - 平台: {sys.platform}, Docker环境: {IS_DOCKER}")

    @timeout(seconds=60, error_message="SMB连接超时")
    def connect(self, server, share, user=None, password=None, domain=None, timeout=None):
        """建立SMB连接

        Args:
            server (str): SMB服务器地址
            share (str): 共享名称
            user (str, optional): 用户名
            password (str, optional): 密码
            domain (str, optional): 域
            timeout (int): 连接超时时间（秒），默认为平台相关的默认值

        Returns:
            tuple: (连接成功的连接对象, 错误信息)
        """
        # 记录开始时间
        start_time = time.time()
        
        # 使用默认值或提供的值
        user = user or self.default_user
        password = password or self.default_password
        domain = domain or self.default_domain
        timeout = timeout or self.default_timeout

        # 检查是否已有连接
        conn_key = f"{server}:{share}:{user}"
        
        # 线程安全地检查和创建连接
        with self._lock:
            if conn_key in self._connections:
                conn = self._connections[conn_key]
                if conn.is_connected():
                    logger.debug(f"使用现有SMB连接: {server}\\{share}")
                    return conn, None
                else:
                    logger.debug(f"移除断开的SMB连接: {server}\\{share}")
                    del self._connections[conn_key]

        try:
            # 保存原始超时设置并设置新的超时
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(timeout)
            
            # 创建连接对象，根据环境调整参数
            conn = SMBConnection(
                username=user,
                password=password,
                my_name='plexAutoScan',
                remote_name=server,
                domain=domain,
                use_ntlm_v2=True,
                sign_options=2 if IS_DOCKER else 1,  # 在Docker环境中更严格的签名选项
                is_direct_tcp=True  # 始终使用直接TCP连接，提高连接稳定性
            )

            # 连接服务器，使用超时参数
            connected = conn.connect(server, 445)
            if not connected:
                logger.error(f"[SMB] 无法连接到SMB服务器: {server}\\{share}")
                return None, f"无法连接到SMB服务器: {server}\\{share}"

            # 线程安全地存储连接
            with self._lock:
                self._connections[conn_key] = conn
            
            logger.info(f"[SMB] 成功连接到SMB服务器: {server}\\{share}")
            return conn, None

        except socket.timeout:
            logger.error(f"[SMB] SMB连接超时: {server}\\{share}（{timeout}秒后）")
            return None, f"SMB连接超时: {server}\\{share}（{timeout}秒后）"
        except socket.error as e:
            logger.error(f"[SMB] SMB网络错误: {str(e)} - 服务器: {server}\\{share}")
            return None, f"SMB网络错误: {str(e)} - 服务器: {server}\\{share}"
        except Exception as e:
            logger.error(f"[SMB] SMB连接错误: {str(e)} - 服务器: {server}\\{share}")
            logger.error(f"[SMB] 错误详情 - 平台: {sys.platform}, Docker环境: {IS_DOCKER}")
            return None, f"SMB连接错误: {str(e)} - 服务器: {server}\\{share}"
        finally:
            # 恢复原始超时设置
            socket.setdefaulttimeout(original_timeout)
            
            # 更新网络健康状态
            if time.time() - start_time < timeout * 0.5:
                # 快速连接表示网络状况良好
                self._update_network_health(True)
            elif time.time() - start_time > timeout * 0.8:
                # 接近超时表示网络状况较差
                self._update_network_health(False)
            else:
                # 中等时间表示网络状况一般
                self._update_network_health(None)

    def disconnect(self, server, share, user=None):
        """断开SMB连接"""
        user = user or self.default_user
        conn_key = f"{server}:{share}:{user}"
        
        # 线程安全地断开连接
        with self._lock:
            if conn_key in self._connections:
                try:
                    self._connections[conn_key].close()
                    del self._connections[conn_key]
                    logger.debug(f"[SMB] 已断开SMB连接: {server}\\{share}")
                except Exception as e:
                    logger.warning(f"[SMB] 断开SMB连接时出错: {str(e)}")

    def is_connected(self, server, share, user=None):
        """检查SMB连接是否活跃"""
        user = user or self.default_user
        conn_key = f"{server}:{share}:{user}"
        
        with self._lock:
            if conn_key in self._connections:
                try:
                    return self._connections[conn_key].is_connected()
                except:
                    return False
        return False

    def get_active_connections_count(self):
        """获取当前活跃的连接数量"""
        with self._lock:
            active = 0
            for conn in self._connections.values():
                try:
                    if conn.is_connected():
                        active += 1
                except:
                    pass
            return active
    
    def _update_network_health(self, connection_success):
        """更新网络健康状态
        
        Args:
            connection_success: True表示连接良好，False表示连接较差，None表示一般
        """
        with self._lock:
            # 记录连接结果
            current_time = time.time()
            self.last_connection_attempts.append((current_time, connection_success))
            
            # 只保留最近的连接尝试记录
            self.last_connection_attempts = [(t, s) for t, s in self.last_connection_attempts 
                                           if current_time - t < 300]  # 只保留5分钟内的记录
            
            # 计算健康状态
            if len(self.last_connection_attempts) > 0:
                # 计算最近连接的成功率
                success_count = sum(1 for t, s in self.last_connection_attempts if s is True)
                failure_count = sum(1 for t, s in self.last_connection_attempts if s is False)
                total = success_count + failure_count
                
                if total > 0:
                    # 加权计算健康状态，近期的连接尝试权重更高
                    weighted_sum = 0
                    weight_sum = 0
                    for t, s in sorted(self.last_connection_attempts, key=lambda x: x[0], reverse=True):
                        age = current_time - t
                        weight = max(0.1, 1 - age / 300)  # 5分钟内权重从1降到0.1
                        if s is True:
                            weighted_sum += weight
                        elif s is False:
                            weighted_sum += weight * 0.3  # 连接差的情况权重较低
                        weight_sum += weight
                    
                    if weight_sum > 0:
                        self.network_health = min(1.0, max(0.1, weighted_sum / weight_sum))
                        
                        # 动态调整默认超时值
                        if self.network_health > 0.8:
                            # 网络状况好，减少超时
                            self.default_timeout = min(30, int(self.default_timeout * self.timeout_factor_low))
                        elif self.network_health < 0.4:
                            # 网络状况差，增加超时
                            self.default_timeout = max(120, int(self.default_timeout * self.timeout_factor_high))
                        
                        logger.debug(f"[SMB] SMB网络健康状态更新: {self.network_health:.2f}, 超时设置: {self.default_timeout}秒")
    
    def get_adaptive_timeout(self, base_timeout=None):
        """获取根据网络状况调整的超时值
        
        Args:
            base_timeout: 基础超时值，如果为None则使用默认超时
        
        Returns:
            int: 根据网络状况调整后的超时值
        """
        with self._lock:
            timeout = base_timeout or self.default_timeout
            # 根据网络健康状态调整超时
            if self.network_health > 0.8:
                # 网络状况好，减少超时
                return max(5, int(timeout * self.timeout_factor_low))
            elif self.network_health < 0.4:
                # 网络状况差，增加超时
                return min(180, int(timeout * self.timeout_factor_high))
            return timeout

    @timeout(seconds=180, error_message="SMB文件列表获取超时")
    def list_files(self, server, share, path, user=None, password=None, domain=None, timeout=None):
        """列出SMB共享中的文件和目录

        Args:
            server (str): SMB服务器地址
            share (str): 共享名称
            path (str): 路径
            user (str, optional): 用户名
            password (str, optional): 密码
            domain (str, optional): 域
            timeout (int): 操作超时时间（秒），默认为None，会使用自适应超时

        Returns:
            tuple: (文件列表, 目录列表, 错误信息)
        """
        # 使用自适应超时
        adaptive_timeout = self.get_adaptive_timeout(timeout)
        # 连接超时设置为操作超时的一半
        connect_timeout = max(5, int(adaptive_timeout * 0.5))
        conn, err = self.connect(server, share, user, password, domain, connect_timeout)
        if err:
            return [], [], err

        try:
            # 保存原始超时设置并设置新的超时
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(adaptive_timeout)
            
            # 规范化路径
            path = normalize_path_separator(path)
            
            # 确保路径以斜杠结尾
            if path and not path.endswith(get_path_separator(path)):
                path += get_path_separator(path)

            # 列出目录内容
            file_list = []
            dir_list = []
            for name, attrs in conn.listPath(share, path):
                if name in ('.', '..'):
                    continue
                if attrs.isDirectory:
                    dir_list.append(name)
                else:
                    file_list.append({
                        'name': name,
                        'size': attrs.file_size,
                        'mtime': attrs.last_write_time
                    })

            return file_list, dir_list, None

        except socket.timeout:
            logger.error(f"[SMB] 列出SMB文件超时: {server}\\{share}{path}（{timeout}秒后）")
            return [], [], f"列出SMB文件超时: {server}\\{share}{path}（{timeout}秒后）"
        except socket.error as e:
            logger.error(f"[SMB] SMB网络错误: {str(e)} - 列出文件: {server}\\{share}{path}")
            return [], [], f"SMB网络错误: {str(e)} - 列出文件: {server}\\{share}{path}"
        except Exception as e:
            logger.error(f"[SMB] 列出SMB文件时出错: {str(e)} - 路径: {server}\\{share}{path}")
            return [], [], f"列出SMB文件时出错: {str(e)} - 路径: {server}\\{share}{path}"
        finally:
            # 恢复原始超时设置
            socket.setdefaulttimeout(original_timeout)

    @timeout(seconds=120, error_message="SMB文件信息获取超时")
    def get_file_info(self, server, share, path, user=None, password=None, domain=None, timeout=None):
        """获取SMB文件的详细信息

        Args:
            server (str): SMB服务器地址
            share (str): 共享名称
            path (str): 文件路径
            user (str, optional): 用户名
            password (str, optional): 密码
            domain (str, optional): 域
            timeout (int): 操作超时时间（秒），默认为None，会使用自适应超时

        Returns:
            tuple: (文件信息字典, 错误信息)
        """
        # 使用自适应超时
        adaptive_timeout = self.get_adaptive_timeout(timeout)
        # 连接超时设置为操作超时的一半
        connect_timeout = max(5, int(adaptive_timeout * 0.5))
        conn, err = self.connect(server, share, user, password, domain, connect_timeout)
        if err:
            return None, err

        try:
            # 保存原始超时设置并设置新的超时
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(adaptive_timeout)
            
            # 规范化路径
            path = normalize_path_separator(path)
            
            # 解析路径
            dir_path = os.path.dirname(path)
            file_name = os.path.basename(path)

            # 确保目录路径以斜杠结尾
            if dir_path and not dir_path.endswith(get_path_separator(dir_path)):
                dir_path += get_path_separator(dir_path)

            # 查找文件
            for name, attrs in conn.listPath(share, dir_path):
                if name == file_name:
                    return {
                        'name': name,
                        'size': attrs.file_size,
                        'mtime': attrs.last_write_time,
                        'is_directory': attrs.isDirectory
                    }, None

            return None, f"文件不存在: {path}"

        except socket.timeout:
            logger.error(f"[SMB] 获取SMB文件信息超时: {server}\\{share}{path}（{timeout}秒后）")
            return None, f"获取SMB文件信息超时: {server}\\{share}{path}（{timeout}秒后）"
        except socket.error as e:
            logger.error(f"[SMB] SMB网络错误: {str(e)} - 获取文件信息: {server}\\{share}{path}")
            return None, f"SMB网络错误: {str(e)} - 获取文件信息: {server}\\{share}{path}"
        except Exception as e:
            logger.error(f"[SMB] 获取SMB文件信息时出错: {str(e)} - 路径: {server}\\{share}{path}")
            return None, f"获取SMB文件信息时出错: {str(e)} - 路径: {server}\\{share}{path}"
        finally:
            # 恢复原始超时设置
            socket.setdefaulttimeout(original_timeout)
            
    @timeout(seconds=60, error_message="SMB路径检查超时")
    def path_exists(self, server, share, path, user=None, password=None, domain=None, timeout=None):
        """检查SMB路径是否存在

        Args:
            server (str): SMB服务器地址
            share (str): 共享名称
            path (str): 要检查的路径
            user (str, optional): 用户名
            password (str, optional): 密码
            domain (str, optional): 域
            timeout (int): 操作超时时间（秒），默认为None，会使用自适应超时

        Returns:
            tuple: (布尔值表示路径是否存在, 错误信息)
        """
        # 使用自适应超时
        adaptive_timeout = self.get_adaptive_timeout(timeout)
        # 连接超时设置为操作超时的一半
        connect_timeout = max(5, int(adaptive_timeout * 0.5))
        conn, err = self.connect(server, share, user, password, domain, connect_timeout)
        if err:
            return False, err

        try:
            # 保存原始超时设置并设置新的超时
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(adaptive_timeout)
            
            # 规范化路径
            path = normalize_path_separator(path)
            
            # 处理根路径的特殊情况
            if path in ('', '/', '\\'):
                # 对于根路径，尝试列出内容来验证其存在
                try:
                    conn.listPath(share, '/')
                    return True, None
                except:
                    return False, f"无法访问根路径: {server}\{share}"
            
            # 解析路径为目录和文件名
            dir_path = os.path.dirname(path)
            file_name = os.path.basename(path)

            # 确保目录路径以斜杠结尾
            if dir_path and not dir_path.endswith(get_path_separator(dir_path)):
                dir_path += get_path_separator(dir_path)

            # 列出目录内容检查文件/目录是否存在
            try:
                for name, attrs in conn.listPath(share, dir_path):
                    if name == file_name:
                        return True, None
                return False, f"路径不存在: {path}"
            except Exception as e:
                return False, f"检查路径时出错: {str(e)} - {path}"

        except socket.timeout:
            logger.error(f"[SMB] SMB路径检查超时: {server}\\{share}{path}（{timeout}秒后）")
            return False, f"SMB路径检查超时: {server}\\{share}{path}（{timeout}秒后）"
        except socket.error as e:
            logger.error(f"[SMB] SMB网络错误: {str(e)} - 检查路径: {server}\\{share}{path}")
            return False, f"SMB网络错误: {str(e)} - 检查路径: {server}\\{share}{path}"
        except Exception as e:
            logger.error(f"[SMB] 检查SMB路径时出错: {str(e)} - 路径: {server}\\{share}{path}")
            return False, f"检查SMB路径时出错: {str(e)} - 路径: {server}\\{share}{path}"
        finally:
            # 恢复原始超时设置
            socket.setdefaulttimeout(original_timeout)

    def keep_alive(self, server, share, interval=None, user=None, password=None, domain=None, timeout=10):
        """保持SMB连接活跃

        Args:
            server (str): SMB服务器地址
            share (str): 共享名称
            interval (int): 检查间隔（秒）
            user (str, optional): 用户名
            password (str, optional): 密码
            domain (str, optional): 域
            timeout (int): 保持活跃操作的超时时间（秒），默认为10秒

        Returns:
            threading.Thread: 后台线程对象
        """
        # 使用环境相关的默认间隔
        interval = interval or self.default_keepalive_interval
        
        def _keep_alive():
            attempt = 0
            max_attempts = 3  # 连续失败后的连接尝试次数
            
            while True:
                try:
                    # 记录当前连接状态
                    conn_status = self.is_connected(server, share, user)
                    logger.debug(f"[SMB] 保活检查 - 当前连接状态: {conn_status} - {server}\\{share}")
                    
                    # 使用较短的超时时间进行保活操作
                    conn, err = self.connect(server, share, user, password, domain, timeout)
                    if conn:
                        # 重置尝试计数
                        attempt = 0
                        
                        # 执行简单操作以保持连接活跃
                        try:
                            # 使用超时装饰器提供的函数执行带超时的操作
                            def _keep_alive_operation():
                                # 保存原始超时设置并设置新的超时
                                original_timeout = socket.getdefaulttimeout()
                                socket.setdefaulttimeout(timeout)
                                
                                try:
                                    # 规范化路径
                                    test_path = normalize_path_separator('/')
                                    conn.listPath(share, test_path)
                                    
                                    # 在Docker环境中记录连接状态
                                    if IS_DOCKER:
                                        logger.debug(f"[SMB] SMB连接保持活跃: {server}\\{share} - 活跃连接数: {self.get_active_connections_count()}")
                                finally:
                                    # 恢复原始超时设置
                                    socket.setdefaulttimeout(original_timeout)
                            
                            # 执行带超时的保活操作
                            run_with_timeout(
                                _keep_alive_operation,
                                timeout_seconds=timeout,
                                default=False,
                                error_message=f"SMB保活操作超时: {server}\{share}"
                            )
                        except Exception as e:
                            logger.warning(f"[SMB] SMB保活操作失败: {str(e)} - {server}\\{share}")
                            # 在Docker环境中更频繁地重连
                            if IS_DOCKER:
                                logger.warning(f"[SMB] Docker环境下SMB连接异常，尝试重建连接...")
                                with self._lock:
                                    conn_key = f"{server}:{share}:{user or self.default_user}"
                                    if conn_key in self._connections:
                                        try:
                                            self._connections[conn_key].close()
                                            del self._connections[conn_key]
                                        except:
                                            pass
                    elif err:
                        attempt += 1
                        logger.warning(f"[SMB] SMB保活连接失败 ({attempt}/{max_attempts}): {err}")
                        
                        # 如果连续多次失败，可能需要更积极的重连策略
                        if attempt >= max_attempts and IS_DOCKER:
                            logger.warning(f"[SMB] Docker环境下连续{max_attempts}次SMB保活失败，清理所有连接并重建...")
                            with self._lock:
                                # 清理所有与该服务器相关的连接
                                keys_to_remove = []
                                for key in self._connections:
                                    if key.startswith(f"{server}:"):
                                        keys_to_remove.append(key)
                                for key in keys_to_remove:
                                    try:
                                        self._connections[key].close()
                                        del self._connections[key]
                                    except:
                                        pass
                            attempt = 0  # 重置尝试计数
                except Exception as e:
                    logger.warning(f"[SMB] SMB连接保持失败: {str(e)} - {server}\\{share}")
                
                # 根据环境调整休眠时间
                sleep_time = interval
                if attempt > 0:
                    # 失败时使用指数退避策略
                    sleep_time = min(interval * (2 ** (attempt - 1)), 300)  # 最多5分钟
                
                logger.debug(f"[SMB] SMB保活线程休眠: {sleep_time}秒 - {server}\\{share}")
                time.sleep(sleep_time)

        thread = threading.Thread(target=_keep_alive, daemon=True, name=f"SMB-KeepAlive-{server}-{share}")
        thread.start()
        logger.info(f"[SMB] 已启动SMB连接保持线程: {server}\\{share}（间隔: {interval}秒）")
        return thread

# 导出常用函数
def get_smb_manager():
    """获取SMB管理器实例的便捷函数"""
    return SMBManager.get_instance()