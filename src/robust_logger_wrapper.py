#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import logging
import traceback

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # 尝试使用相对导入
    from .robust_logger import setup_robust_logging
    ROBUST_LOGGING_AVAILABLE = True
except ImportError:
    try:
        # 尝试直接导入（不使用src前缀）
        # 注意：这里故意重复导入以适应不同环境
        from .robust_logger import setup_robust_logging
        ROBUST_LOGGING_AVAILABLE = True
    except ImportError as e:
        # 导入失败
        ROBUST_LOGGING_AVAILABLE = False
        logging.warning(f"[WARNING] 无法导入robust_logger模块: {e}")

# 检查DEBUG环境变量
debug_mode = os.environ.get('DEBUG', '0') == '1'

def main():
    if len(sys.argv) < 2:
        print("用法: robust_logger_wrapper.py <日志级别> <日志消息>", file=sys.stderr)
        sys.exit(1)

    # 确保命令行参数被正确解码为UTF-8
    # 首先处理日志级别，增强健壮性
    raw_log_level = sys.argv[1]
    try:
        # 尝试正确解码日志级别
        decoded_log_level = raw_log_level.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
        log_level = decoded_log_level.upper()
    except Exception as e:
        # 如果解码失败，使用默认的INFO级别
        log_level = 'INFO'
        print(f"[ERROR] 日志级别解码失败: {str(e)}，使用默认级别INFO", file=sys.stderr)
    
    # 处理命令行参数中的编码问题
    log_message_parts = []
    for part in sys.argv[2:]:
        try:
            # 尝试将参数解码为UTF-8
            decoded_part = part.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
            log_message_parts.append(decoded_part)
        except Exception as e:
            log_message_parts.append(f'[ENCODING_ERROR: {str(e)}]')
    log_message = ' '.join(log_message_parts)
    debug_mode = os.environ.get('DEBUG', '0') == '1'

    # 配置日志
    if ROBUST_LOGGING_AVAILABLE:
        # 使用robust_logger
        # 当DEBUG模式开启时设置为DEBUG级别，否则根据LOG_LEVEL环境变量设置，默认为INFO
        log_level_env = os.environ.get('LOG_LEVEL', 'INFO').upper()
        logger = setup_robust_logging(
            log_file=os.environ.get('LOG_FILE', 'app.log'),
            log_level=logging.DEBUG if debug_mode else getattr(logging, log_level_env, logging.INFO),
            fallback_log_file=os.environ.get('FALLBACK_LOG_FILE', 'fallback.log')
        )
    else:
        # 使用基本日志配置
        # 当DEBUG模式开启时设置为DEBUG级别，否则根据LOG_LEVEL环境变量设置，默认为INFO
        log_level_env = os.environ.get('LOG_LEVEL', 'INFO').upper()
        log_level_setting = logging.DEBUG if debug_mode else getattr(logging, log_level_env, logging.INFO)
        logging.basicConfig(
            level=log_level_setting,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(os.environ.get('LOG_FILE', 'app.log')),
                logging.StreamHandler()
            ]
        )
        logger = logging.getLogger()

    # 不再记录重复的日志级别设置信息
    # 这行日志会在每次调用时重复输出，已经移除以避免日志冗余

    # 根据日志级别记录消息
    if log_level == 'DEBUG':
        logger.debug(log_message)
    elif log_level == 'INFO':
        logger.info(log_message)
    elif log_level == 'WARN' or log_level == 'WARNING':
        logger.warning(log_message)
    elif log_level == 'ERROR':
        logger.error(log_message)
    elif log_level == 'CRITICAL':
        logger.critical(log_message)
    else:
        logger.info(log_message)

if __name__ == '__main__':
    main()