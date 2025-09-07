#!/usr/bin/env python3
import sys
import os
import time
import socket

# 设置socket默认超时时间
socket.setdefaulttimeout(30)

# 导入新的SMBManager类 - 使用相对导入以适应Docker环境
from .smb_api import SMBManager

def extract_local_files(snap_file):
    """从快照文件中提取本地文件路径"""
    with open(snap_file, 'rb') as f:
        files = set(f.read().split(b'\x00')) - {b''}
    for f in files:
        if f:
            parts = f.split(b'|')
            if len(parts) >= 1:
                path = parts[0].decode('utf-8', errors='ignore')
                print(path)


# 导入超时控制工具函数
from .utils.timeout_decorator import run_with_timeout
from .utils.path_utils import PathUtils

def generate_full_snapshot(target_dir, output_file, scan_delay):
    """生成包含所有文件的完整快照（不应用大小过滤）"""
    # 核心逻辑函数
    def _generate_full_snapshot_core():
        target_dir = os.path.normpath(target_dir)
        # 新增：获取排除路径并规范化
        exclude_paths = os.environ.get('EXCLUDE_PATHS', '').split()
        exclude_paths = [os.path.normpath(p).replace('\\', '/').lower() for p in exclude_paths]
        
        files = []
        file_count = 0
        dir_count = 0
        
        for root, dirs, file_names in os.walk(target_dir, topdown=True, followlinks=False):
            # 规范化当前目录路径
            normalized_root = os.path.normpath(root).replace('\\', '/').lower()
            # 检查是否需要排除当前目录
            if any(normalized_root == ep or normalized_root.startswith(f"{ep}/") for ep in exclude_paths):
                print(f"跳过排除目录: {root}", file=sys.stderr)
                dirs[:] = []  # 清空子目录列表，停止递归扫描
                continue
            
            dir_count += 1
            print(f"扫描目录 [{dir_count}]: {root}（{len(file_names)}个文件）", file=sys.stderr)
            
            for file_name in file_names:
                file_path = os.path.join(root, file_name)
                info = file_info(file_path)
                if info:
                    files.append(info)
                    file_count += 1
                    if file_count % 100 == 0:
                        print(f"已收集 {file_count} 个文件...", file=sys.stderr)
            
            time.sleep(scan_delay)
        
        files.sort()
        
        temp_output = output_file + ".tmp"
        with open(temp_output, 'wb') as f:
            if files:
                f.write(b'\x00'.join(files) + b'\x00')
        
        os.rename(temp_output, output_file)
        
        print(f"快照生成完成：{dir_count} 个目录，{file_count} 个文件", file=sys.stderr)
        return len(files)
    
    # 直接运行核心生成快照逻辑，超时控制由调用方管理
    result = _generate_full_snapshot_core()
    
    return result

def file_info(path, max_retries=3, timeout=30):
    """获取文件信息，使用SMBManager处理SMB错误并重试
    
    Args:
        path (str): 文件路径
        max_retries (int): 最大重试次数
        timeout (int): 操作超时时间（秒）
        
    Returns:
        bytes: 文件信息编码的字节串，格式为 "路径|大小|修改时间"
    """
    # 使用单例模式获取SMBManager实例
    smb_manager = SMBManager.get_instance()
    
    retry_count = 0
    while retry_count <= max_retries:
        try:
            # 保存原始超时设置并设置新的超时
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(timeout)
            
            try:
                # 尝试使用SMBManager获取文件信息
                # 注意：这里需要适配smb_api.py中修改后的参数
                file_info, err = smb_manager.get_file_info(path, timeout=timeout)
                if not err and file_info:
                    return f"{path}|{file_info['size']}|{file_info['mtime']}".encode('utf-8')
                else:
                    if err:
                        print(f"无法获取文件信息: {path} - {err}", file=sys.stderr)
                    else:
                        print(f"无法获取文件信息: {path}", file=sys.stderr)
            except Exception as e:
                # 捕获可能的异常
                print(f"获取文件信息异常: {path} - {str(e)}", file=sys.stderr)
            finally:
                # 恢复原始超时设置
                socket.setdefaulttimeout(original_timeout)
            
            # 如果是第一次失败且是SMB相关错误，重试
            if retry_count < max_retries:
                retry_count += 1
                wait_time = min(2 ** retry_count, 8)  # 指数退避，最大8秒
                print(f"文件访问错误，将在{wait_time}秒后重试（第{retry_count}次）: {path}", file=sys.stderr)
                time.sleep(wait_time)
            else:
                # 达到最大重试次数
                print(f"达到最大重试次数，无法访问文件: {path}", file=sys.stderr)
                break
        
        except socket.timeout:
            retry_count += 1
            if retry_count <= max_retries:
                wait_time = min(2 ** retry_count, 8)
                print(f"文件访问超时，将在{wait_time}秒后重试（第{retry_count}次）: {path}", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"文件访问超时（{timeout}秒），无法访问: {path}", file=sys.stderr)
                break
        except Exception as e:
            print(f"无法访问文件: {path} - {str(e)}", file=sys.stderr)
            retry_count += 1
            if retry_count <= max_retries:
                time.sleep(1)
            else:
                break
    
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: file_utils.py <command> [args]", file=sys.stderr)
        sys.exit(1)
    
    command = sys.argv[1]
    if command == "extract_local_files":
        if len(sys.argv) != 3:
            print("用法: file_utils.py extract_local_files <snap_file>", file=sys.stderr)
            sys.exit(1)
        
        snap_file = sys.argv[2]
        extract_local_files(snap_file)
    elif command == "generate_full_snapshot":
        if len(sys.argv) != 5:
            print("用法: file_utils.py generate_full_snapshot <dir> <output> <scan_delay>", file=sys.stderr)
            sys.exit(1)
        
        dir = sys.argv[2]
        output = sys.argv[3]
        scan_delay = float(sys.argv[4])
        
        generate_full_snapshot(dir, output, scan_delay)
    else:
        print(f"未知命令: {command}", file=sys.stderr)
        sys.exit(1)