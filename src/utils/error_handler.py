#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一错误处理模块
"""

import logging
import functools
import traceback
from typing import Optional, Callable, Any, Dict, Type, Tuple
from enum import Enum


class ErrorCategory(Enum):
    """错误类别枚举"""
    CONFIGURATION = "configuration"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    PLEX_API = "plex_api"
    DEPENDENCY = "dependency"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class PlexAutoScanError(Exception):
    """PlexAutoScan 基础异常类"""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        """初始化异常
        
        Args:
            message (str): 错误消息
            category (ErrorCategory): 错误类别
            details (dict): 错误详情
            original_exception (Exception): 原始异常
        """
        super().__init__(message)
        self.message = message
        self.category = category
        self.details = details or {}
        self.original_exception = original_exception
    
    def __str__(self):
        """返回错误信息的字符串表示"""
        result = f"[{self.category.value.upper()}] {self.message}"
        if self.details:
            result += f" | Details: {self.details}"
        if self.original_exception:
            result += f" | Caused by: {type(self.original_exception).__name__}: {str(self.original_exception)}"
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典
        
        Returns:
            dict: 异常信息的字典表示
        """
        return {
            'category': self.category.value,
            'message': self.message,
            'details': self.details,
            'original_exception': {
                'type': type(self.original_exception).__name__,
                'message': str(self.original_exception)
            } if self.original_exception else None
        }


class ConfigurationError(PlexAutoScanError):
    """配置错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.CONFIGURATION, details, original_exception)


class NetworkError(PlexAutoScanError):
    """网络错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.NETWORK, details, original_exception)


class FilesystemError(PlexAutoScanError):
    """文件系统错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.FILESYSTEM, details, original_exception)


class PlexAPIError(PlexAutoScanError):
    """Plex API 错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.PLEX_API, details, original_exception)


class DependencyError(PlexAutoScanError):
    """依赖错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.DEPENDENCY, details, original_exception)


class TimeoutError(PlexAutoScanError):
    """超时错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.TIMEOUT, details, original_exception)


class ValidationError(PlexAutoScanError):
    """验证错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.VALIDATION, details, original_exception)


def handle_errors(
    default_return: Any = None,
    error_categories: Optional[Tuple[ErrorCategory, ...]] = None,
    reraise: bool = False,
    log_level: int = logging.ERROR
):
    """错误处理装饰器
    
    Args:
        default_return: 发生错误时的默认返回值
        error_categories: 要捕获的错误类别元组，None 表示捕获所有
        reraise: 是否重新抛出异常
        log_level: 日志级别
        
    Returns:
        function: 装饰后的函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            
            try:
                return func(*args, **kwargs)
            except PlexAutoScanError as e:
                # 检查是否在要捕获的错误类别中
                if error_categories is None or e.category in error_categories:
                    logger.log(log_level, f"函数 {func.__name__} 发生错误: {e}")
                    if reraise:
                        raise
                    return default_return
                else:
                    raise
            except Exception as e:
                # 将普通异常转换为 PlexAutoScanError
                error = PlexAutoScanError(
                    message=f"函数 {func.__name__} 发生未预期的错误: {str(e)}",
                    original_exception=e
                )
                logger.log(log_level, f"函数 {func.__name__} 发生未预期的错误: {str(e)}")
                logger.debug(traceback.format_exc())
                
                if reraise:
                    raise error
                return default_return
        
        return wrapper
    return decorator


def safe_execute(
    func: Callable,
    *args,
    default_return: Any = None,
    error_categories: Optional[Tuple[ErrorCategory, ...]] = None,
    reraise: bool = False,
    log_level: int = logging.ERROR,
    **kwargs
) -> Any:
    """安全执行函数
    
    Args:
        func: 要执行的函数
        args: 位置参数
        default_return: 发生错误时的默认返回值
        error_categories: 要捕获的错误类别元组，None 表示捕获所有
        reraise: 是否重新抛出异常
        log_level: 日志级别
        kwargs: 关键字参数
        
    Returns:
        Any: 函数返回值或默认返回值
    """
    logger = logging.getLogger(func.__module__)
    
    try:
        return func(*args, **kwargs)
    except PlexAutoScanError as e:
        # 检查是否在要捕获的错误类别中
        if error_categories is None or e.category in error_categories:
            logger.log(log_level, f"函数 {func.__name__} 发生错误: {e}")
            if reraise:
                raise
            return default_return
        else:
            raise
    except Exception as e:
        # 将普通异常转换为 PlexAutoScanError
        error = PlexAutoScanError(
            message=f"函数 {func.__name__} 发生未预期的错误: {str(e)}",
            original_exception=e
        )
        logger.log(log_level, f"函数 {func.__name__} 发生未预期的错误: {str(e)}")
        logger.debug(traceback.format_exc())
        
        if reraise:
            raise error
        return default_return


def wrap_exception(
    original_exception: Exception,
    message: str,
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    details: Optional[Dict[str, Any]] = None
) -> PlexAutoScanError:
    """将普通异常包装为 PlexAutoScanError
    
    Args:
        original_exception (Exception): 原始异常
        message (str): 错误消息
        category (ErrorCategory): 错误类别
        details (dict): 错误详情
        
    Returns:
        PlexAutoScanError: 包装后的异常
    """
    if isinstance(original_exception, PlexAutoScanError):
        # 如果已经是 PlexAutoScanError，直接返回
        return original_exception
    
    # 根据原始异常类型选择合适的错误类别
    if category == ErrorCategory.UNKNOWN:
        if isinstance(original_exception, (ConnectionError, TimeoutError)):
            category = ErrorCategory.NETWORK
        elif isinstance(original_exception, (FileNotFoundError, PermissionError, OSError)):
            category = ErrorCategory.FILESYSTEM
        elif isinstance(original_exception, (ValueError, KeyError)):
            category = ErrorCategory.VALIDATION
    
    return PlexAutoScanError(
        message=message,
        category=category,
        details=details,
        original_exception=original_exception
    )


class ErrorHandler:
    """错误处理器类"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """初始化错误处理器
        
        Args:
            logger (logging.Logger): 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
        self.error_counts: Dict[ErrorCategory, int] = {}
        self.error_history: list = []
    
    def handle(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        reraise: bool = False
    ) -> Optional[PlexAutoScanError]:
        """处理错误
        
        Args:
            error (Exception): 错误对象
            context (dict): 错误上下文
            reraise (bool): 是否重新抛出异常
            
        Returns:
            PlexAutoScanError: 处理后的错误对象
        """
        # 包装错误
        if not isinstance(error, PlexAutoScanError):
            wrapped_error = wrap_exception(error, str(error))
        else:
            wrapped_error = error
        
        # 添加上下文信息
        if context:
            wrapped_error.details.update(context)
        
        # 记录错误
        self.logger.error(f"错误处理: {wrapped_error}")
        self.logger.debug(traceback.format_exc())
        
        # 统计错误
        self._count_error(wrapped_error)
        self._record_error(wrapped_error)
        
        # 重新抛出异常
        if reraise:
            raise wrapped_error
        
        return wrapped_error
    
    def _count_error(self, error: PlexAutoScanError):
        """统计错误
        
        Args:
            error (PlexAutoScanError): 错误对象
        """
        category = error.category
        self.error_counts[category] = self.error_counts.get(category, 0) + 1
    
    def _record_error(self, error: PlexAutoScanError):
        """记录错误历史
        
        Args:
            error (PlexAutoScanError): 错误对象
        """
        import time
        self.error_history.append({
            'timestamp': time.time(),
            'category': error.category.value,
            'message': error.message,
            'details': error.details
        })
        
        # 限制历史记录数量
        if len(self.error_history) > 1000:
            self.error_history = self.error_history[-1000:]
    
    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计信息
        
        Returns:
            dict: 错误统计信息
        """
        return {
            'error_counts': {cat.value: count for cat, count in self.error_counts.items()},
            'total_errors': sum(self.error_counts.values()),
            'recent_errors': len(self.error_history)
        }
    
    def clear_history(self):
        """清除错误历史"""
        self.error_history.clear()
        self.error_counts.clear()
