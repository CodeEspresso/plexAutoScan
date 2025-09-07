#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMB性能测试工具
用于测试和分析SMB扫描性能，帮助优化SMB扫描功能。
"""
import sys
import os
import time
import logging
import json
import statistics
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from .smb_api import SMBManager
from .snapshot_utils import generate_snapshot

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class SMBPerformanceTester:
    def __init__(self):
        self.smb_manager = SMBManager()
        self.results = []
        
    def print_separator(self):
        print("=" * 80)
    
    def test_scan_speed(self, path, iterations=3):
        """测试SMB路径的扫描速度
        
        Args:
            path (str): 要扫描的SMB路径
            iterations (int): 测试迭代次数
        
        Returns:
            dict: 扫描性能结果
        """
        self.print_separator()
        logger.info(f"测试SMB路径扫描速度: {path}")
        logger.info(f"迭代次数: {iterations}")
        
        scan_times = []
        file_counts = []
        error_counts = []
        
        for i in range(iterations):
            logger.info(f"=== 迭代 {i+1}/{iterations} ===")
            
            # 创建临时快照文件
            temp_snapshot_path = f"/tmp/smb_perf_test_{int(time.time())}_{i}.snapshot"
            
            # 记录开始时间
            start_time = time.time()
            
            try:
                # 执行扫描
                file_count = generate_snapshot(
                    dir=path,
                    output_file=temp_snapshot_path,
                    scan_delay=0.1,
                    max_files=0,  # 无限制
                    skip_large=False,
                    large_threshold=10000,
                    min_size=0,
                    min_size_mb=0  # 不过滤小文件
                )
                
                # 记录结束时间
                end_time = time.time()
                scan_time = end_time - start_time
                
                scan_times.append(scan_time)
                file_counts.append(file_count)
                error_counts.append(0)  # 假设没有错误
                
                logger.info(f"扫描完成，耗时: {scan_time:.2f}秒")
                logger.info(f"找到文件数量: {file_count}")
                logger.info(f"每秒处理文件数: {file_count/scan_time:.2f}文件/秒")
                
            except Exception as e:
                logger.error(f"扫描失败: {str(e)}")
                error_counts.append(1)
                continue
            finally:
                # 清理临时文件
                if os.path.exists(temp_snapshot_path):
                    try:
                        os.remove(temp_snapshot_path)
                    except:
                        pass
        
        # 计算统计数据
        if scan_times:
            result = {
                'test': 'scan_speed',
                'path': path,
                'iterations': iterations,
                'avg_scan_time': statistics.mean(scan_times) if scan_times else 0,
                'min_scan_time': min(scan_times) if scan_times else 0,
                'max_scan_time': max(scan_times) if scan_times else 0,
                'std_dev_scan_time': statistics.stdev(scan_times) if len(scan_times) > 1 else 0,
                'avg_file_count': statistics.mean(file_counts) if file_counts else 0,
                'avg_files_per_second': statistics.mean([fc/st if st > 0 else 0 for fc, st in zip(file_counts, scan_times)]) if scan_times else 0,
                'error_count': sum(error_counts),
                'timestamp': datetime.now().isoformat()
            }
            
            self.results.append(result)
            
            # 打印汇总信息
            self.print_separator()
            logger.info("扫描速度测试汇总:")
            logger.info(f"平均扫描时间: {result['avg_scan_time']:.2f}秒")
            logger.info(f"最小扫描时间: {result['min_scan_time']:.2f}秒")
            logger.info(f"最大扫描时间: {result['max_scan_time']:.2f}秒")
            logger.info(f"扫描时间标准差: {result['std_dev_scan_time']:.2f}秒")
            logger.info(f"平均文件数量: {result['avg_file_count']:.0f}")
            logger.info(f"平均每秒处理文件数: {result['avg_files_per_second']:.2f}文件/秒")
            logger.info(f"错误次数: {result['error_count']}")
            
            return result
        else:
            logger.error("所有扫描迭代都失败了")
            return None
    
    def test_thread_pool_size(self, path, thread_sizes=[2, 4, 6, 8, 10], iterations=2):
        """测试不同线程池大小对SMB扫描性能的影响
        
        Args:
            path (str): 要扫描的SMB路径
            thread_sizes (list): 要测试的线程池大小列表
            iterations (int): 每个线程池大小的测试迭代次数
        
        Returns:
            list: 不同线程池大小的性能结果
        """
        self.print_separator()
        logger.info(f"测试不同线程池大小对SMB扫描的影响: {path}")
        logger.info(f"要测试的线程池大小: {thread_sizes}")
        
        thread_results = []
        
        for thread_size in thread_sizes:
            logger.info(f"=== 测试线程池大小: {thread_size} ===")
            
            # 保存原始线程池大小
            original_max_workers = os.environ.get('SMB_MAX_WORKERS')
            
            try:
                # 设置新的线程池大小
                os.environ['SMB_MAX_WORKERS'] = str(thread_size)
                logger.info(f"已设置SMB_MAX_WORKERS={thread_size}")
                
                # 运行扫描测试
                result = self.test_scan_speed(path, iterations=iterations)
                if result:
                    result['thread_size'] = thread_size
                    thread_results.append(result)
            finally:
                # 恢复原始线程池大小
                if original_max_workers is not None:
                    os.environ['SMB_MAX_WORKERS'] = original_max_workers
                else:
                    if 'SMB_MAX_WORKERS' in os.environ:
                        del os.environ['SMB_MAX_WORKERS']
        
        # 分析线程池大小对性能的影响
        if thread_results:
            self.print_separator()
            logger.info("线程池大小测试汇总:")
            
            # 按线程池大小排序
            thread_results.sort(key=lambda x: x['thread_size'])
            
            for result in thread_results:
                logger.info(f"线程池大小: {result['thread_size']}, 平均扫描时间: {result['avg_scan_time']:.2f}秒, 平均每秒处理文件数: {result['avg_files_per_second']:.2f}文件/秒")
            
            # 找出最佳线程池大小
            best_result = max(thread_results, key=lambda x: x['avg_files_per_second'])
            logger.info(f"最佳线程池大小: {best_result['thread_size']}, 性能: {best_result['avg_files_per_second']:.2f}文件/秒")
            
        return thread_results
    
    def test_batch_size(self, path, batch_sizes=[100, 250, 500, 1000], iterations=2):
        """测试不同批处理大小对SMB扫描性能的影响
        
        Args:
            path (str): 要扫描的SMB路径
            batch_sizes (list): 要测试的批处理大小列表
            iterations (int): 每个批处理大小的测试迭代次数
        
        Returns:
            list: 不同批处理大小的性能结果
        """
        self.print_separator()
        logger.info(f"测试不同批处理大小对SMB扫描的影响: {path}")
        logger.info(f"要测试的批处理大小: {batch_sizes}")
        
        import importlib
        importlib.reload(sys.modules.get('src.snapshot_utils'))
        from src.snapshot_utils import generate_snapshot
        
        batch_results = []
        original_batch_size = None
        
        try:
            # 保存原始批处理大小
            if hasattr(sys.modules.get('src.snapshot_utils'), 'SMB_BATCH_SIZE'):
                original_batch_size = sys.modules.get('src.snapshot_utils').SMB_BATCH_SIZE
            
            for batch_size in batch_sizes:
                logger.info(f"=== 测试批处理大小: {batch_size} ===")
                
                # 设置新的批处理大小
                if hasattr(sys.modules.get('src.snapshot_utils'), 'SMB_BATCH_SIZE'):
                    setattr(sys.modules.get('src.snapshot_utils'), 'SMB_BATCH_SIZE', batch_size)
                    logger.info(f"已设置批处理大小={batch_size}")
                else:
                    logger.warning("无法修改批处理大小，跳过此测试")
                    continue
                
                # 运行扫描测试
                result = self.test_scan_speed(path, iterations=iterations)
                if result:
                    result['batch_size'] = batch_size
                    batch_results.append(result)
        finally:
            # 恢复原始批处理大小
            if original_batch_size is not None and hasattr(sys.modules.get('src.snapshot_utils'), 'SMB_BATCH_SIZE'):
                setattr(sys.modules.get('src.snapshot_utils'), 'SMB_BATCH_SIZE', original_batch_size)
        
        # 分析批处理大小对性能的影响
        if batch_results:
            self.print_separator()
            logger.info("批处理大小测试汇总:")
            
            # 按批处理大小排序
            batch_results.sort(key=lambda x: x['batch_size'])
            
            for result in batch_results:
                logger.info(f"批处理大小: {result['batch_size']}, 平均扫描时间: {result['avg_scan_time']:.2f}秒, 平均每秒处理文件数: {result['avg_files_per_second']:.2f}文件/秒")
            
            # 找出最佳批处理大小
            best_result = max(batch_results, key=lambda x: x['avg_files_per_second'])
            logger.info(f"最佳批处理大小: {best_result['batch_size']}, 性能: {best_result['avg_files_per_second']:.2f}文件/秒")
            
        return batch_results
    
    def test_connection_keep_alive(self, path, intervals=[5, 10, 30, 60], duration=30, iterations=2):
        """测试不同连接保持间隔对SMB扫描性能的影响
        
        Args:
            path (str): 要扫描的SMB路径
            intervals (list): 要测试的连接保持间隔（秒）
            duration (int): 测试持续时间（秒）
            iterations (int): 每个间隔的测试迭代次数
        
        Returns:
            list: 不同连接保持间隔的性能结果
        """
        self.print_separator()
        logger.info(f"测试不同连接保持间隔对SMB扫描的影响: {path}")
        logger.info(f"要测试的连接保持间隔: {intervals}秒")
        
        keep_alive_results = []
        
        for interval in intervals:
            logger.info(f"=== 测试连接保持间隔: {interval}秒 ===")
            
            # 保存原始连接保持间隔
            original_interval = None
            if hasattr(self.smb_manager, 'keep_alive_interval'):
                original_interval = self.smb_manager.keep_alive_interval
            
            try:
                # 设置新的连接保持间隔
                if hasattr(self.smb_manager, 'keep_alive_interval'):
                    setattr(self.smb_manager, 'keep_alive_interval', interval)
                    logger.info(f"已设置连接保持间隔={interval}秒")
                
                # 启动连接保持
                logger.info(f"启动连接保持，持续{duration}秒")
                thread = self.smb_manager.keep_connection_alive(path, interval=interval)
                
                # 等待连接建立
                time.sleep(2)
                
                # 运行扫描测试
                result = self.test_scan_speed(path, iterations=iterations)
                if result:
                    result['keep_alive_interval'] = interval
                    keep_alive_results.append(result)
                
                # 等待连接保持测试完成
                time.sleep(duration)
                
            finally:
                # 恢复原始连接保持间隔
                if original_interval is not None and hasattr(self.smb_manager, 'keep_alive_interval'):
                    setattr(self.smb_manager, 'keep_alive_interval', original_interval)
        
        # 分析连接保持间隔对性能的影响
        if keep_alive_results:
            self.print_separator()
            logger.info("连接保持间隔测试汇总:")
            
            # 按连接保持间隔排序
            keep_alive_results.sort(key=lambda x: x['keep_alive_interval'])
            
            for result in keep_alive_results:
                logger.info(f"连接保持间隔: {result['keep_alive_interval']}秒, 平均扫描时间: {result['avg_scan_time']:.2f}秒, 平均每秒处理文件数: {result['avg_files_per_second']:.2f}文件/秒")
            
            # 找出最佳连接保持间隔
            best_result = max(keep_alive_results, key=lambda x: x['avg_files_per_second'])
            logger.info(f"最佳连接保持间隔: {best_result['keep_alive_interval']}秒, 性能: {best_result['avg_files_per_second']:.2f}文件/秒")
            
        return keep_alive_results
    
    def save_results(self, output_file=None):
        """保存测试结果到JSON文件
        
        Args:
            output_file (str): 输出文件路径
        
        Returns:
            str: 保存的文件路径
        """
        if not self.results:
            logger.warning("没有测试结果可保存")
            return None
        
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"/tmp/smb_perf_results_{timestamp}.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            logger.info(f"测试结果已保存到: {output_file}")
            return output_file
        except Exception as e:
            logger.error(f"保存测试结果失败: {str(e)}")
            return None
    
    def run_comprehensive_test(self, path, output_file=None):
        """运行全面的性能测试
        
        Args:
            path (str): 要扫描的SMB路径
            output_file (str): 输出文件路径
        
        Returns:
            dict: 综合测试结果
        """
        self.print_separator()
        logger.info("开始全面的SMB性能测试")
        logger.info(f"测试路径: {path}")
        
        # 记录开始时间
        start_time = time.time()
        
        # 运行各项测试
        base_result = self.test_scan_speed(path, iterations=3)
        thread_results = self.test_thread_pool_size(path, thread_sizes=[2, 4, 6, 8, 10], iterations=2)
        batch_results = self.test_batch_size(path, batch_sizes=[100, 250, 500, 1000], iterations=2)
        keep_alive_results = self.test_connection_keep_alive(path, intervals=[5, 10, 30], duration=20, iterations=2)
        
        # 记录结束时间
        end_time = time.time()
        total_time = end_time - start_time
        
        # 保存结果
        result_file = self.save_results(output_file)
        
        # 打印综合报告
        self.print_separator()
        logger.info("===== SMB性能测试综合报告 =====")
        logger.info(f"测试路径: {path}")
        logger.info(f"总测试时间: {total_time:.2f}秒")
        logger.info(f"测试结果已保存到: {result_file}")
        
        # 分析并提供优化建议
        self.print_separator()
        logger.info("===== 性能优化建议 =====")
        
        # 线程池大小建议
        if thread_results:
            best_thread = max(thread_results, key=lambda x: x['avg_files_per_second'])
            logger.info(f"建议的线程池大小: {best_thread['thread_size']} (环境变量 SMB_MAX_WORKERS={best_thread['thread_size']})")
        
        # 批处理大小建议
        if batch_results:
            best_batch = max(batch_results, key=lambda x: x['avg_files_per_second'])
            logger.info(f"建议的批处理大小: {best_batch['batch_size']}")
        
        # 连接保持间隔建议
        if keep_alive_results:
            best_keep_alive = max(keep_alive_results, key=lambda x: x['avg_files_per_second'])
            logger.info(f"建议的连接保持间隔: {best_keep_alive['keep_alive_interval']}秒")
        
        # 通用建议
        logger.info("其他优化建议:")
        logger.info("1. 考虑增加网络带宽或优化网络连接质量")
        logger.info("2. 确保SMB服务器配置优化，如增加最大连接数")
        logger.info("3. 对于大型目录，考虑使用增量扫描而不是全量扫描")
        logger.info("4. 定期清理缓存和临时文件以保持系统性能")
        
        return {
            'base_result': base_result,
            'thread_results': thread_results,
            'batch_results': batch_results,
            'keep_alive_results': keep_alive_results,
            'total_time': total_time,
            'result_file': result_file
        }

if __name__ == "__main__":
    # 检查参数
    if len(sys.argv) < 2:
        logger.error("用法: python smb_performance_test.py <测试路径> [选项]")
        logger.error("选项:")
        logger.error("  --test=scan_speed          只测试扫描速度")
        logger.error("  --test=thread_pool         只测试不同线程池大小")
        logger.error("  --test=batch_size          只测试不同批处理大小")
        logger.error("  --test=keep_alive          只测试不同连接保持间隔")
        logger.error("  --test=comprehensive       运行全面测试（默认）")
        logger.error("  --output=<文件路径>        指定结果输出文件")
        logger.error("  --iterations=<次数>        指定测试迭代次数")
        sys.exit(1)
    
    test_path = sys.argv[1]
    test_type = 'comprehensive'
    output_file = None
    iterations = 3
    
    # 解析其他参数
    for arg in sys.argv[2:]:
        if arg.startswith('--test='):
            test_type = arg.split('=', 1)[1]
        elif arg.startswith('--output='):
            output_file = arg.split('=', 1)[1]
        elif arg.startswith('--iterations='):
            try:
                iterations = int(arg.split('=', 1)[1])
            except ValueError:
                logger.error(f"无效的迭代次数: {arg.split('=', 1)[1]}")
                sys.exit(1)
    
    # 检查测试路径是否有效
    if not os.path.exists(test_path):
        logger.error(f"错误: 测试路径 '{test_path}' 不存在")
        sys.exit(1)
    
    # 创建测试器并运行测试
    tester = SMBPerformanceTester()
    
    try:
        if test_type == 'scan_speed':
            tester.test_scan_speed(test_path, iterations=iterations)
        elif test_type == 'thread_pool':
            tester.test_thread_pool_size(test_path, iterations=iterations)
        elif test_type == 'batch_size':
            tester.test_batch_size(test_path, iterations=iterations)
        elif test_type == 'keep_alive':
            tester.test_connection_keep_alive(test_path, iterations=iterations)
        elif test_type == 'comprehensive':
            tester.run_comprehensive_test(test_path, output_file=output_file)
        else:
            logger.error(f"无效的测试类型: {test_type}")
            sys.exit(1)
        
        # 保存结果（如果没有在comprehensive测试中保存）
        if test_type != 'comprehensive':
            tester.save_results(output_file)
            
        # 成功完成
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        # 保存已有的结果
        tester.save_results(output_file)
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试过程中发生错误: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        sys.exit(1)