# -*- coding: utf-8 -*-
import os
import signal
import functools
import threading
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from .environment import env_detector

# 日志配置
logger = logging.getLogger(__name__)


# 默认超时时间配置
DEFAULT_TIMEOUTS = {
    'short': 30,      # 短超时：30秒
    'medium': 300,     # 中超时：5分钟
    'long': 600,       # 长超时：10分钟
    'very_long': 1800   # 超长超时：30分钟
}


class TimeoutConfig:
    """超时配置类"""
    
    def __init__(self):
        """初始化超时配置"""
        self._timeouts = DEFAULT_TIMEOUTS.copy()
        self._docker_multiplier = 0.5  # Docker 环境下的超时倍数
    
    def get_timeout(self, category: str = 'medium', custom_timeout: Optional[int] = None) -> int:
        """获取超时时间
        
        Args:
            category (str): 超时类别 (short, medium, long, very_long)
            custom_timeout (int): 自定义超时时间，如果提供则忽略 category
            
        Returns:
            int: 超时时间（秒）
        """
        if custom_timeout is not None:
            timeout = custom_timeout
        else:
            timeout = self._timeouts.get(category, DEFAULT_TIMEOUTS['medium'])
        
        # Docker 环境下应用倍数
        if env_detector.is_docker():
            timeout = int(timeout * self._docker_multiplier)
        
        return timeout
    
    def set_timeout(self, category: str, timeout: int):
        """设置超时时间
        
        Args:
            category (str): 超时类别
            timeout (int): 超时时间（秒）
        """
        self._timeouts[category] = timeout
    
    def set_docker_multiplier(self, multiplier: float):
        """设置 Docker 环境下的超时倍数
        
        Args:
            multiplier (float): 超时倍数
        """
        self._docker_multiplier = multiplier


# 全局超时配置实例
timeout_config = TimeoutConfig()


def timeout(seconds=30, error_message="函数执行超时"):
    """函数执行超时装饰器
    
    Args:
        seconds (int): 超时时间（秒），默认为30秒
        error_message (str): 超时错误信息
        
    Returns:
        function: 装饰后的函数
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 使用超时配置获取实际超时时间
            actual_timeout = timeout_config.get_timeout(custom_timeout=seconds)
            
            # 使用ThreadPoolExecutor来执行函数
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    # 等待函数执行完成或超时
                    result = future.result(timeout=actual_timeout)
                    return result
                except TimeoutError:
                    # 函数执行超时
                    logger.error(f"函数 {func.__name__} 执行超时（{actual_timeout}秒） - Docker环境: {env_detector.is_docker()}")
                    raise TimeoutError(f"{error_message}（{actual_timeout}秒）")
        return wrapper
    return decorator


def run_with_timeout(func, *args, timeout_seconds=30, default=None, error_message=None, **kwargs):
    """在超时控制下运行函数的工具函数
    
    Args:
        func (callable): 要执行的函数
        args: 函数的位置参数
        timeout_seconds (int): 超时时间（秒），默认为30秒
        default: 超时或出错时返回的默认值
        error_message (str): 自定义错误信息
        kwargs: 函数的关键字参数
        
    Returns:
        函数的返回值或默认值
    """
    start_time = time.time()
    try:
        # 使用超时配置获取实际超时时间
        actual_timeout = timeout_config.get_timeout(custom_timeout=timeout_seconds)
        
        logger.debug(f"开始执行函数 {func.__name__}，超时设置: {actual_timeout}秒，Docker环境: {env_detector.is_docker()}")
        
        # 使用ThreadPoolExecutor来执行函数
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            # 等待函数执行完成或超时
            result = future.result(timeout=actual_timeout)
            execution_time = time.time() - start_time
            logger.debug(f"函数 {func.__name__} 执行完成，耗时: {execution_time:.2f}秒，未超时")
            return result
    except TimeoutError:
        # 函数执行超时
        execution_time = time.time() - start_time
        error_msg = error_message or f"函数 {func.__name__} 执行超时（{actual_timeout}秒）"
        logger.error(f"{error_msg} - Docker环境: {env_detector.is_docker()} - 实际执行时间: {execution_time:.2f}秒")
        return default
    except Exception as e:
        # 捕获其他异常
        execution_time = time.time() - start_time
        logger.error(f"函数 {func.__name__} 执行出错: {str(e)} - 执行时间: {execution_time:.2f}秒")
        return default


class TimeoutContext:
    """超时上下文管理器
    
    示例用法:
    with TimeoutContext(seconds=30):
        # 执行可能超时的操作
    """
    def __init__(self, seconds=30, error_message="操作超时"):
        self.seconds = seconds
        self.error_message = error_message
        self.timer = None
        self.timed_out = False
    
    def __enter__(self):
        # 检测是否在Docker环境中运行
        is_docker = os.environ.get('DOCKER_ENV') == '1' or os.path.exists('/.dockerenv')
        
        # 尊重调用者设置的超时值，不再强制限制Docker环境下的最大超时时间
        actual_timeout = self.seconds
        
        # 设置定时器
        self.timer = threading.Timer(actual_timeout, self._handle_timeout)
        self.timer.daemon = True  # 设置为守护线程，确保程序退出时定时器也会退出
        self.timer.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 取消定时器
        if self.timer:
            self.timer.cancel()
        
        # 如果是因为超时而退出，抛出TimeoutError
        if self.timed_out:
            raise TimeoutError(self.error_message)
        
        return False  # 不抑制其他异常
    
    def _handle_timeout(self):
        """处理超时事件"""
        self.timed_out = True
        logger.error(f"操作超时（{self.seconds}秒）")


# 导出常用函数
def get_timeout_decorator():
    """获取超时装饰器的便捷函数"""
    return timeout


def get_run_with_timeout():
    """获取带超时运行函数的便捷函数"""
    return run_with_timeout