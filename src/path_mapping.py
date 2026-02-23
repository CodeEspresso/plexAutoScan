#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import tempfile
import unicodedata
import locale

# 确保Python使用UTF-8编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 检查系统编码
current_locale = locale.getpreferredencoding()
print(f'系统编码: {current_locale}', file=sys.stderr)

# 导入日志模块 - 使用相对导入以适应Docker环境
from .robust_logger import setup_robust_logging
from .utils.environment import env_detector

# 配置健壮日志
try:
    logger = setup_robust_logging(log_level=os.environ.get('LOG_LEVEL', 'DEBUG'))
except Exception as e:
    print(f'日志初始化失败: {str(e)}', file=sys.stderr)
    sys.exit(1)

# 确保标准输出使用UTF-8编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')

# 从环境变量中读取路径前缀配置
PATH_PREFIX = os.environ.get('PATH_PREFIX', '')
LOCAL_PATH_PREFIX = os.environ.get('LOCAL_PATH_PREFIX', '')
TEST_LOCAL_PATH_PREFIX = os.environ.get('TEST_LOCAL_PATH_PREFIX', '')
PROD_BASE_PATH = os.environ.get('PROD_BASE_PATH', '/vol02/CloudDrive/WebDAV')
TEST_BASE_PATH = os.environ.get('TEST_BASE_PATH', '/Volumes/PSSD/项目/plexAutoScan/test_files')
DOCKER_ENV = os.environ.get('DOCKER_ENV', '0')
TEST_ENV = os.environ.get('TEST_ENV', '0')

# 使用统一的环境检测器
IS_DOCKER = env_detector.is_docker()

# 确保路径编码正确
PATH_PREFIX = PATH_PREFIX.encode('utf-8').decode('utf-8') if PATH_PREFIX else PROD_BASE_PATH
LOCAL_PATH_PREFIX = LOCAL_PATH_PREFIX.encode('utf-8').decode('utf-8') if LOCAL_PATH_PREFIX else PROD_BASE_PATH
TEST_LOCAL_PATH_PREFIX = TEST_LOCAL_PATH_PREFIX.encode('utf-8').decode('utf-8') if TEST_LOCAL_PATH_PREFIX else TEST_BASE_PATH
PROD_BASE_PATH = PROD_BASE_PATH.encode('utf-8').decode('utf-8')
TEST_BASE_PATH = TEST_BASE_PATH.encode('utf-8').decode('utf-8')

logger.info('Current environment: %s, Docker: %s' % ('test' if TEST_ENV == '1' else 'production', IS_DOCKER))
logger.info('PATH_PREFIX: %s' % PATH_PREFIX)
logger.info('LOCAL_PATH_PREFIX: %s' % LOCAL_PATH_PREFIX)
logger.info('TEST_LOCAL_PATH_PREFIX: %s' % TEST_LOCAL_PATH_PREFIX)
logger.info('PROD_BASE_PATH: %s' % PROD_BASE_PATH)
logger.info('TEST_BASE_PATH: %s' % TEST_BASE_PATH)

# 强制测试环境使用测试路径前缀
if TEST_ENV == '1':
    logger.info('强制使用测试路径前缀')
    # 重要修正：在测试环境下同时更新PATH_PREFIX和LOCAL_PATH_PREFIX
    PATH_PREFIX = TEST_BASE_PATH
    LOCAL_PATH_PREFIX = TEST_BASE_PATH
    logger.info('更新后 PATH_PREFIX: %s' % PATH_PREFIX)
    logger.info('更新后 LOCAL_PATH_PREFIX: %s' % LOCAL_PATH_PREFIX)
else:
    # 确保生产环境使用正确的路径前缀
    LOCAL_PATH_PREFIX = os.environ.get('LOCAL_PATH_PREFIX', PROD_BASE_PATH)







def map_path(input_path):
    """路径映射函数"""
    # 确保输入路径是UTF-8编码的字符串
    if isinstance(input_path, bytes):
        input_path = input_path.decode('utf-8')
    logger.debug(f'原始输入路径: {input_path}')

    # 标准化Unicode字符
    normalized_path = unicodedata.normalize('NFC', input_path)
    logger.debug(f'标准化后路径: {normalized_path}')

    # 替换路径前缀
    mapped_path = normalized_path

    # 打印路径映射前的调试信息
    logger.info(f'路径映射前 - PATH_PREFIX: {PATH_PREFIX}')
    logger.info(f'路径映射前 - LOCAL_PATH_PREFIX: {LOCAL_PATH_PREFIX}')
    logger.info(f'路径映射前 - normalized_path: {normalized_path}')
    logger.info(f'路径映射前 - normalized_path.startswith(PATH_PREFIX): {normalized_path.startswith(PATH_PREFIX)}')

    # 生产环境下的路径映射逻辑
    if TEST_ENV != '1':
        # 在Docker环境中，保留原始挂载路径，避免错误映射
        if IS_DOCKER:
            # 直接使用原始路径，Docker环境中的路径应该已经是正确挂载的
            mapped_path = normalized_path
            logger.debug(f'Docker环境中使用原始路径: {mapped_path}')
        else:
            # 非Docker环境下的路径规范化处理
            if normalized_path.startswith(PROD_BASE_PATH):
                mapped_path = normalized_path
                logger.debug(f'生产环境规范化路径: {mapped_path}')
            else:
                logger.warning(f'路径格式不符合预期: {normalized_path}')
                if normalized_path.startswith('/'):
                    mapped_path = os.path.join(PROD_BASE_PATH, normalized_path.lstrip('/'))
                else:
                    mapped_path = os.path.join(PROD_BASE_PATH, normalized_path)
                logger.info(f'尝试规范化为: {mapped_path}')
    else:
        # 测试环境下的路径映射逻辑
        if IS_DOCKER:
            logger.debug(f'In Docker environment, using input path directly: {normalized_path}')
            mapped_path = normalized_path
        else:
            # 非Docker环境下的路径映射逻辑
            if normalized_path.startswith(PATH_PREFIX):
                logger.debug(f'Path starts with PATH_PREFIX: {PATH_PREFIX}')
                # 替换为本地路径前缀
                mapped_path = LOCAL_PATH_PREFIX + normalized_path[len(PATH_PREFIX):]
                logger.debug(f'Mapped path to: {mapped_path}')
            else:
                # 尝试兼容旧路径格式
                if normalized_path.startswith('/Volumes/PSSD'):
                    # Replace with test environment path
                    mapped_path = LOCAL_PATH_PREFIX + normalized_path[len('/Volumes/PSSD'):]
                    logger.debug(f'In test environment, mapped old path to: {mapped_path}')
                else:
                    logger.debug(f'Path does not start with PATH_PREFIX, returning directly: {normalized_path}')
                    mapped_path = normalized_path

    # 确保映射后的路径是UTF-8编码
    if isinstance(mapped_path, bytes):
        mapped_path = mapped_path.decode('utf-8')

    # 打印路径映射后的调试信息
    logger.info(f'路径映射后 - mapped_path: {mapped_path}')

    # 验证映射后的路径是否存在
    if IS_DOCKER:
        # 在Docker环境中，检查路径是否存在
        if not os.path.exists(mapped_path):
            logger.warning(f'Docker环境中路径不存在: {mapped_path}')
            # 检查是否是只读文件系统
            try:
                # 尝试创建临时文件以测试是否可写
                test_file = os.path.join(tempfile.gettempdir(), 'test_write.txt')
                try:
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    is_writable = True
                except OSError as e:
                    if 'Read-only file system' in str(e):
                        is_writable = False
                    else:
                        raise
            except OSError as e:
                if 'Read-only file system' in str(e):
                    is_writable = False
                else:
                    raise

            if not is_writable:
                # 只读文件系统，创建临时路径
                temp_dir_env = os.environ.get('TEMP_DIR', '/data/temp')
                temp_dir = os.path.join(temp_dir_env, 'scan_path')
                os.makedirs(temp_dir, exist_ok=True)
                logger.warning(f'检测到只读文件系统，使用临时路径: {temp_dir}')
                mapped_path = temp_dir
            else:
                # 尝试创建路径
                try:
                    os.makedirs(mapped_path, exist_ok=True)
                    logger.info(f'成功创建路径: {mapped_path}')
                except Exception as e:
                    logger.error(f'创建路径失败: {str(e)}')
    else:
        # 非Docker环境
        if not os.path.exists(mapped_path):
            logger.warning(f'映射后的路径不存在: {mapped_path}')
            # 建议创建对应的媒体库路径
            current_dir = mapped_path
            suggestions = []
            while True:
                parent_dir = os.path.dirname(current_dir)
                if parent_dir == current_dir:  # 到达根目录
                    break
                if os.path.exists(parent_dir):
                    # 找到存在的父目录
                    relative_path = os.path.relpath(mapped_path, parent_dir)
                    suggestions.append(f'在 {parent_dir} 下创建 {relative_path}')
                    break
                current_dir = parent_dir
            if suggestions:
                logger.warning(f'建议: {suggestions[0]}')
            else:
                logger.warning('未找到可创建路径的父目录')

    return mapped_path


if __name__ == '__main__':
    # 确保命令行参数被正确解码为UTF-8
    for i in range(len(sys.argv)):
        if isinstance(sys.argv[i], bytes):
            sys.argv[i] = sys.argv[i].decode('utf-8')

    if len(sys.argv) > 1:
        input_path = sys.argv[1]
        result = map_path(input_path)
        print(result)
    else:
        logger.error('未提供输入路径')
        sys.exit(1)