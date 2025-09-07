#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import traceback
import time
from typing import Optional

class RobustStreamHandler(logging.StreamHandler):
    def __init__(self, stream=None, fallback_log_file='fallback.log'):
        super().__init__(stream or sys.stdout)
        self.fallback_log_file = fallback_log_file
        # 跟踪流重置尝试次数
        self.reset_attempts = 0
        self.max_reset_attempts = 5
        # 记录最后一次重置时间
        self.last_reset_time = 0
        self.reset_cooldown = 0.5  # 重置冷却时间（秒）
        # 标记流是否已关闭
        self.stream_closed = False

    def emit(self, record):
        try:
            # 检查流状态
            if self.stream_closed or self.stream is None:
                self._write_to_fallback(record, 'Stream is closed or None')
                return

            # 格式化消息
            msg = self.format(record)
            # 确保消息可以被正确编码为字节
            if isinstance(msg, str):
                msg_bytes = msg.encode('utf-8', errors='replace')
            else:
                msg_bytes = str(msg).encode('utf-8', errors='replace')

            terminator = self.terminator
            if isinstance(terminator, str):
                terminator_bytes = terminator.encode('utf-8', errors='replace')
            else:
                terminator_bytes = str(terminator).encode('utf-8', errors='replace')

            # 尝试写入流
            try:
                # 检查流是否支持写入字节
                if hasattr(self.stream, 'buffer'):
                    self.stream.buffer.write(msg_bytes + terminator_bytes)
                else:
                    # 如果不支持，尝试直接写入字符串
                    self.stream.write((msg_bytes + terminator_bytes).decode('utf-8', errors='replace'))
                self.flush()
            except (ValueError, IOError, OSError) as e:
                error_msg = str(e).lower()
                if any(phrase in error_msg for phrase in ['buffer has been detached', 'i/o operation on closed file', 'broken pipe']):
                    self.stream_closed = True
                    current_time = time.time()
                    if current_time - self.last_reset_time >= self.reset_cooldown:
                        self.last_reset_time = current_time
                        if self.reset_attempts < self.max_reset_attempts:
                            self.reset_attempts += 1
                            if self._reset_stream():
                                try:
                                    self.stream.write(msg + terminator)
                                    self.flush()
                                    self.stream_closed = False
                                except Exception as re:
                                    self._write_to_fallback(record, f'Buffer detached (reset failed: {re})')
                            else:
                                self._write_to_fallback(record, 'Buffer detached (reset failed)')
                        else:
                            self._write_to_fallback(record, 'Buffer detached (max reset attempts reached)')
                    else:
                        self._write_to_fallback(record, 'Buffer detached (cooldown active)')
                else:
                    self._write_to_fallback(record, f'I/O error: {e}')
        except Exception as e:
            self._write_to_fallback(record, f'Unexpected error: {e}')

    def flush(self):
        """重写flush方法，处理流关闭的情况"""
        try:
            if not self.stream_closed:
                super().flush()
        except Exception:
            # 忽略flush错误
            pass

    def _reset_stream(self):
        """尝试重置流

        Returns:
            bool: 是否重置成功
        """
        try:
            # 方法1: 尝试重新打开stdout文件描述符
            if hasattr(sys.stdout, 'fileno'):
                try:
                    self.stream = open(sys.stdout.fileno(), 'w', encoding='utf-8')
                    return True
                except Exception as e1:
                    # 方法1失败，尝试方法2
                    pass

            # 方法2: 尝试使用sys.__stdout__
            if hasattr(sys, '__stdout__'):
                self.stream = sys.__stdout__
                return True

            # 方法3: 创建一个空流对象
            class NullStream:
                def write(self, *args, **kwargs):
                    pass
                def flush(self):
                    pass
            self.stream = NullStream()
            return True

        except Exception as e:
            # 所有方法都失败
            try:
                with open(self.fallback_log_file, 'a', encoding='utf-8') as f:
                    f.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] [ERROR] 无法重置流: {e}\n')
            except:
                pass
            return False
    def _write_to_fallback(self, record, error_msg):
        """写入到后备日志文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(self.fallback_log_file)), exist_ok=True)
            with open(self.fallback_log_file, 'a', encoding='utf-8') as f:
                formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
                msg = formatter.format(record)
                # 确保消息可以被正确编码
                if isinstance(msg, str):
                    msg_bytes = msg.encode('utf-8', errors='replace')
                else:
                    msg_bytes = str(msg).encode('utf-8', errors='replace')
                # 直接写入字节
                f.write(f'[FALLBACK] {error_msg}: '.encode('utf-8', errors='replace'))
                f.write(msg_bytes)
                f.write(b'\n')
        except Exception as e:
            # 如果写入后备日志也失败，尝试使用系统临时文件
            try:
                import tempfile
                temp_log_file = os.path.join(tempfile.gettempdir(), 'robust_logger_fallback.log')
                with open(temp_log_file, 'a', encoding='utf-8') as f:
                    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
                    msg = formatter.format(record)
                    f.write(f'[FALLBACK] {error_msg}: {msg} (Fallback to temp file failed: {e})\n')
            except:
                # 最后的选择，尝试忽略错误
                pass

class RobustFileHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding=None, delay=False):
        super().__init__(filename, mode, encoding, delay)
        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

    def emit(self, record):
        try:
            # 检查文件是否可写
            if not os.access(self.baseFilename, os.W_OK):
                # 尝试创建目录
                os.makedirs(os.path.dirname(os.path.abspath(self.baseFilename)), exist_ok=True)
                # 尝试重新打开文件
                self.stream = self._open()
            super().emit(record)
        except Exception as e:
            # 尝试写入到后备位置
            fallback_path = os.path.join(os.path.dirname(self.baseFilename), 'fallback_' + os.path.basename(self.baseFilename))
            try:
                with open(fallback_path, 'a', encoding=self.encoding or 'utf-8') as f:
                    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
                    msg = formatter.format(record)
                    f.write(f'[FILE ERROR] {e}: {msg}\n')
            except Exception:
                # 所有方法都失败，忽略错误
                pass

def setup_robust_logging(
    log_file: str = 'app.log',
    log_level: int = logging.DEBUG,
    fallback_log_file: str = 'fallback.log'
) -> logging.Logger:
    """设置健壮的日志配置

    Args:
        log_file: 主要日志文件路径
        log_level: 日志级别
        fallback_log_file: 后备日志文件路径

    Returns:
        配置好的根日志器
    """
    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 移除现有的处理器
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    # 添加健壮的StreamHandler
    stream_handler = RobustStreamHandler(sys.stdout, fallback_log_file)
    stream_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.addHandler(stream_handler)

    # 添加健壮的FileHandler
    try:
        file_handler = RobustFileHandler(log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        root_logger.addHandler(file_handler)
    except Exception as e:
        # 记录无法创建文件处理器的错误
        stream_handler._write_to_fallback(
            logging.LogRecord(
                name='robust_logger',
                level=logging.ERROR,
                pathname=__file__,
                lineno=135,
                msg=f'无法创建文件日志处理器: {e}',
                args=(),
                exc_info=None
            ),
            'FileHandler creation failed'
        )

    return root_logger

# 确保time模块可用
import time

# 示例用法
if __name__ == '__main__':
    # 设置日志
    logger = setup_robust_logging()
    logger.debug('健壮日志配置已初始化')
    logger.info('这是一条信息日志')
    logger.warning('这是一条警告日志')
    logger.error('这是一条错误日志')

    # 模拟缓冲区分离错误
    try:
        # 关闭stdout（模拟缓冲区分离）
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout.buffer.close()
        # 尝试记录日志
        logger.debug('缓冲区分离后的调试日志')
        logger.info('缓冲区分离后的信息日志')
        logger.warning('缓冲区分离后的警告日志')
        logger.error('缓冲区分离后的错误日志')
    except Exception as e:
        # 由于stdout可能已关闭，使用最后的后备机制
        try:
            with open('emergency.log', 'a') as f:
                f.write(f'[EMERGENCY] 模拟缓冲区分离错误: {e}\n')
        except:
            pass