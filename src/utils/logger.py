#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志管理模块
"""

import logging
import sys
import os
import traceback
from datetime import datetime
import io

# 确保UTF-8编码设置
os.environ['LANG'] = 'zh_CN.UTF-8'
os.environ['LC_ALL'] = 'zh_CN.UTF-8'

# 日志级别映射
# 删除: export 关键字 (Python不支持)
# 新增: 直接声明LOG_LEVELS变量
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARN': logging.WARNING,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# 颜色代码（终端输出时使用）
COLORS = {
    'DEBUG': '\033[36m',      # 青色
    'INFO': '\033[32m',       # 绿色
    'WARN': '\033[33m',       # 黄色
    'ERROR': '\033[31m',      # 红色
    'CRITICAL': '\033[35m',   # 紫色
    'RESET': '\033[0m'        # 重置
}

class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    
    def __init__(self, fmt=None, datefmt=None, use_color=True):
        super().__init__(fmt, datefmt)
        self.use_color = use_color
    
    def format(self, record):
        """格式化日志记录"""
        if self.use_color and record.levelname in COLORS:
            # 添加颜色代码
            record.levelname = f"{COLORS[record.levelname]}{record.levelname}{COLORS['RESET']}"
        
        return super().format(record)

class RobustLogger(logging.Logger):
    """增强版日志记录器"""
    
    def __init__(self, name, level=logging.INFO):
        super().__init__(name, level)
    
    def _safe_encode(self, message):
        """安全编码日志消息，确保中文和特殊字符正确显示"""
        if isinstance(message, bytes):
            try:
                return message.decode('utf-8', errors='replace')
            except:
                return str(message)
        elif not isinstance(message, str):
            return str(message)
        return message
    
    def debug(self, message, *args, **kwargs):
        """调试日志"""
        safe_message = self._safe_encode(message)
        super().debug(safe_message, *args, **kwargs)
    
    def info(self, message, *args, **kwargs):
        """信息日志"""
        safe_message = self._safe_encode(message)
        super().info(safe_message, *args, **kwargs)
    
    def warning(self, message, *args, **kwargs):
        """警告日志"""
        safe_message = self._safe_encode(message)
        super().warning(safe_message, *args, **kwargs)
    
    def error(self, message, *args, **kwargs):
        """错误日志"""
        safe_message = self._safe_encode(message)
        super().error(safe_message, *args, **kwargs)
    
    def critical(self, message, *args, **kwargs):
        """严重错误日志"""
        safe_message = self._safe_encode(message)
        super().critical(safe_message, *args, **kwargs)
    
    # 兼容旧的warn方法
    warn = warning

# 注册自定义日志器类
logging.setLoggerClass(RobustLogger)


def get_log_level_from_env():
    """从环境变量获取日志级别"""
    # 默认日志级别
    default_level = 'INFO'
    
    # 从环境变量获取日志级别
    log_level_env = os.environ.get('LOG_LEVEL', default_level)
    
    # 清理日志级别，只保留字母和数字
    log_level_env = ''.join(c for c in log_level_env if c.isalnum())
    
    # 转换为大写以忽略大小写
    log_level_env = log_level_env.upper()
    
    # 检查是否启用调试模式
    debug_mode = os.environ.get('DEBUG', '0') == '1'
    if debug_mode:
        log_level_env = 'DEBUG'
    
    # 验证日志级别是否有效
    if log_level_env not in LOG_LEVELS:
        print(f"[ERROR] 无效的日志级别: {log_level_env}，使用默认: {default_level}", file=sys.stderr)
        log_level_env = default_level
    
    return LOG_LEVELS[log_level_env]


def setup_logger(name='PlexAutoScan', log_file=None, level=None):
    """设置日志记录器"""
    # 创建日志记录器
    logger = logging.getLogger(name)
    
    # 设置日志级别
    if level is None:
        level = get_log_level_from_env()
    logger.setLevel(level)
    
    # 清空现有的处理器
    if logger.handlers:
        logger.handlers.clear()
    
    # 日志格式
    log_format = '%(asctime)s [%(levelname)s] %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # 检查是否支持颜色输出
    use_color = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    console_formatter = ColoredFormatter(log_format, date_format, use_color)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（如果指定了日志文件）
    if log_file:
        try:
            # 确保日志文件目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            # 创建文件处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(level)
            file_formatter = logging.Formatter(log_format, date_format)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.error(f"创建日志文件处理器失败: {str(e)}")
    
    # 设置propagate为False，避免日志重复输出
    logger.propagate = False
    
    return logger


def safe_log(message, level='INFO', log_file=None):
    """安全的日志输出函数，用于简单的日志记录"""
    try:
        # 获取当前时间戳
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 构建日志消息
        log_message = f"[{timestamp}] [{level}] {message}"
        
        # 输出到控制台
        if level in ['ERROR', 'CRITICAL']:
            print(log_message, file=sys.stderr)
        else:
            print(log_message)
        
        # 输出到文件（如果指定）
        if log_file:
            try:
                # 确保日志文件目录存在
                log_dir = os.path.dirname(log_file)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir, exist_ok=True)
                
                # 写入日志文件
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(log_message + '\n')
            except Exception:
                # 文件写入失败，忽略错误
                pass
    except Exception:
        # 日志输出失败，忽略错误
        pass


def debug(message, log_file=None):
    """输出调试日志"""
    safe_log(message, 'DEBUG', log_file)


def info(message, log_file=None):
    """输出信息日志"""
    safe_log(message, 'INFO', log_file)


def warn(message, log_file=None):
    """输出警告日志"""
    safe_log(message, 'WARN', log_file)


def error(message, log_file=None):
    """输出错误日志"""
    safe_log(message, 'ERROR', log_file)


def critical(message, log_file=None):
    """输出严重错误日志"""
    safe_log(message, 'CRITICAL', log_file)