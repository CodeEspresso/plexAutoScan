#!/usr/bin/env python3
import sys
import os
import logging
from .robust_logger import setup_robust_logging

# 设置安全日志，根据环境变量动态设置日志文件路径
test_env = os.environ.get('TEST_ENV', '0')
if test_env == '1':
    log_file = '/Volumes/PSSD/项目/plexAutoScan/debug.log'
else:
    log_file = '/tmp/debug.log'
logger = setup_robust_logging(log_file=log_file)

def log_from_bash(level, message):
    """从Bash脚本接收日志级别和消息，并记录到安全日志系统"""
    if level.lower() == 'debug':
        logger.debug(message)
    elif level.lower() == 'info':
        logger.info(message)
    elif level.lower() == 'warn':
        logger.warning(message)
    elif level.lower() == 'error':
        logger.error(message)
    else:
        logger.info(f"[未知级别] {message}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: $PYTHON_EXEC bash_logger_wrapper.py <日志级别> <日志消息>")
        sys.exit(1)
    log_level = sys.argv[1]
    log_message = ' '.join(sys.argv[2:])
    log_from_bash(log_level, log_message)