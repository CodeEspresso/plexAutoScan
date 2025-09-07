#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import json
import logging
import subprocess
from pathlib import Path
import time

# 确保Python使用UTF-8编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('plex_compare.log', encoding='utf-8'),
        logging.StreamHandler(stream=sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def info(msg):
    logger.info(msg)

def warn(msg):
    logger.warning(msg)

def error(msg):
    logger.error(msg)

def debug(msg):
    logger.debug(msg)

class PlexCompare:
    def __init__(self, target_dir, library_cache, min_file_size_mb=10):
        # 确保路径是UTF-8编码的字符串
        if isinstance(target_dir, bytes):
            target_dir = target_dir.decode('utf-8')
        if isinstance(library_cache, bytes):
            library_cache = library_cache.decode('utf-8')
        self.target_dir = os.path.abspath(target_dir)
        self.library_cache = os.path.abspath(library_cache)
        self.plex_libraries = self.load_plex_libraries()
        self.local_files = set()
        self.skipped_files = set()
        # 使用传入的最小文件大小，默认为10MB
        self.min_file_size = float(min_file_size_mb) * 1024 * 1024

    def load_plex_libraries(self):
        """加载Plex媒体库缓存"""
        try:
            with open(self.library_cache, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            error(f"加载Plex媒体库缓存失败: {str(e)}")
            return {}

    def scan_local_files(self):
        """扫描本地文件系统"""
        info(f"开始扫描本地目录: {self.target_dir}")
        start_time = time.time()
        count = 0
        skipped_count = 0

        try:
            for root, _, files in os.walk(self.target_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        # 过滤小文件
                        if os.path.getsize(file_path) >= self.min_file_size:
                            # 提取文件名（不含路径）作为比较依据
                            file_name = os.path.basename(file_path)
                            self.local_files.add(file_name.lower())
                            count += 1
                        else:
                            skipped_file = os.path.basename(file_path)
                            self.skipped_files.add(skipped_file.lower())
                            skipped_count += 1
                    except Exception as e:
                        warn(f"无法访问文件: {file_path} - {str(e)}")
        except Exception as e:
            error(f"扫描本地文件时发生错误: {str(e)}")

        elapsed = time.time() - start_time
        info(f"本地文件扫描完成，找到 {count} 个符合大小要求的文件 (耗时: {elapsed:.2f} 秒)")
        if skipped_count > 0:
            info(f"跳过了 {skipped_count} 个小于最小文件大小的文件")
        debug(f"本地文件集合大小: {len(self.local_files)}")

    def compare_with_plex(self):
        """比较本地文件与Plex媒体库"""
        if not self.plex_libraries:
            error("没有加载到Plex媒体库数据，无法进行比较")
            return False

        if not self.local_files:
            error("没有扫描到本地文件，无法进行比较")
            return False

        info("开始比较本地文件与Plex媒体库...")
        missing_in_plex = []

        # 注意：由于Plex媒体库缓存只包含库信息而没有文件列表
        # 我们无法直接比较文件。这里我们简单地将所有本地文件标记为
        # 需要添加到Plex，然后触发扫描。在实际应用中，应该实现
        # 从Plex API获取每个库的文件列表的功能
        missing_in_plex = list(self.local_files)

        # 输出比较结果
        total_local = len(self.local_files)
        total_missing = len(missing_in_plex)
        total_skipped = len(self.skipped_files)

        info(f"比较结果: 本地文件总数={total_local}, 标记为需要扫描的文件数={total_missing}, 跳过的小文件数={total_skipped}")

        if total_missing > 0:
            info(f"需要触发Plex扫描的文件数量: {total_missing}")
            self.trigger_plex_scan()
        else:
            info("没有发现需要扫描的新文件")

        return True

    def trigger_plex_scan(self):
        """触发Plex扫描"""
        info("触发Plex媒体库扫描...")
        try:
            # 从环境变量获取Plex配置
            plex_url = os.environ.get('PLEX_URL', 'http://localhost:32400')
            plex_token = os.environ.get('PLEX_TOKEN', '')

            if not plex_token:
                error("未找到Plex Token，请在环境变量中设置PLEX_TOKEN")
                return

            # 构建Plex扫描命令
            scan_command = [
                "curl",
                "-X", "POST",
                f"{plex_url}/library/sections/all/refresh",
                "-H", f"X-Plex-Token: {plex_token}"
            ]

            # 执行扫描命令
            result = subprocess.run(
                scan_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode == 0:
                info("Plex扫描命令已发送成功")
            else:
                warn(f"Plex扫描命令执行失败: {result.stderr}")

        except Exception as e:
            error(f"触发Plex扫描时发生错误: {str(e)}")

    def run(self):
        """运行完整的比较流程"""
        self.scan_local_files()
        return self.compare_with_plex()

if __name__ == "__main__":
    # 确保命令行参数被正确解码为UTF-8
    for i in range(len(sys.argv)):
        if isinstance(sys.argv[i], bytes):
            sys.argv[i] = sys.argv[i].decode('utf-8')

    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("用法: compare.py <target_dir> <library_cache> [min_file_size_mb]")
        sys.exit(1)

    target_dir = sys.argv[1]
    library_cache = sys.argv[2]
    min_file_size_mb = float(sys.argv[3]) if len(sys.argv) == 4 else 10.0

    # 验证参数
    if not os.path.isdir(target_dir):
        error(f"目标目录不存在或不是有效的目录: {target_dir}")
        sys.exit(1)

    if not os.path.isfile(library_cache):
        error(f"Plex媒体库缓存文件不存在: {library_cache}")
        sys.exit(1)

    # 创建比较对象并运行
    comparator = PlexCompare(target_dir, library_cache, min_file_size_mb)
    success = comparator.run()

    sys.exit(0 if success else 1)