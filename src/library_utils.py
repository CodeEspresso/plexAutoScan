#!/usr/bin/env python3
import sys
import os
import json
import subprocess
from .utils.timeout_decorator import run_with_timeout
from .utils.path_utils import PathUtils

# 确保Python使用UTF-8编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 检查是否启用调试模式
DEBUG = os.environ.get('DEBUG', '0') == '1'


# 路径映射函数 - 核心实现
def _map_path_core(path):
    # 确保路径是UTF-8编码的字符串
    if isinstance(path, bytes):
        path = path.decode('utf-8')
    # 调用外部shell脚本进行路径映射
    result = subprocess.run(['bash', '-c', 'source src/path_mapping.sh && map_path "$1"', '_', path],
                           capture_output=True, text=True, encoding='utf-8')
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        if DEBUG:
            print(f"[DEBUG] 路径映射失败: {result.stderr}", file=sys.stderr)
        return path

# 路径映射函数 - 直接执行核心逻辑
def map_path(path):
    """路径映射，直接执行核心逻辑"""
    try:
        # 直接执行核心映射逻辑
        return _map_path_core(path)
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] 路径映射出错: {str(e)}", file=sys.stderr)
        return path


def normalize_path(path):
    """规范化路径格式"""
    return os.path.normpath(path)

def extract_library_paths(cache_file):
    """从缓存文件中提取媒体库路径和类型"""
    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)
        for item in data:
            if 'path' not in item:
                print(f"警告: 媒体库 {item['library_id']} 缺少path字段", file=sys.stderr)
                continue
            lib_type = item.get('type', 'unknown')
            print(f"{item['library_id']}|{item['path']}|{lib_type}")
    except Exception as e:
        print(f"错误: {str(e)}", file=sys.stderr)
        sys.exit(1)


def find_deepest_matching_library(target_path, library_paths):
    """递归向上查找最深层匹配的媒体库，优先考虑媒体类型"""
    # 应用路径映射
    mapped_target_path = map_path(target_path)
    current_path = mapped_target_path
    best_match = ""
    best_depth = 0
    
    # 确定目标路径可能的媒体类型（根据路径特征）
    target_type = 'unknown'
    if '/音乐/' in mapped_target_path.lower() or 'music' in mapped_target_path.lower():
        target_type = 'music'
    elif '/电影/' in mapped_target_path.lower() or 'movie' in mapped_target_path.lower():
        target_type = 'movie'
    elif '/电视剧/' in mapped_target_path.lower() or 'show' in mapped_target_path.lower():
        target_type = 'show'
    
    if DEBUG:
        print(f"[DEBUG] 原始目标路径: {target_path}", file=sys.stderr)
        print(f"[DEBUG] 映射后目标路径: {mapped_target_path}", file=sys.stderr)
        print(f"[DEBUG] 推断的目标媒体类型: {target_type}", file=sys.stderr)
    
    # 规范化所有媒体库路径
    normalized_libs = []
    for lib in library_paths.split('\n'):
        if lib.strip():
            try:
                lib_id, lib_path, lib_type = lib.split('|', 2)
                # 应用路径映射到媒体库路径
                mapped_lib_path = map_path(lib_path)
                normalized_lib = f"{lib_id}|{normalize_path(mapped_lib_path)}|{lib_type}"
                normalized_libs.append(normalized_lib)
                if DEBUG:
                    print(f"[DEBUG] 原始媒体库路径: {lib_path}", file=sys.stderr)
                    print(f"[DEBUG] 映射后媒体库路径: {mapped_lib_path}", file=sys.stderr)
                    print(f"[DEBUG] 规范化媒体库路径: {normalized_lib}", file=sys.stderr)
            except ValueError:
                # 兼容旧格式（没有类型信息）
                lib_id, lib_path = lib.split('|', 1)
                mapped_lib_path = map_path(lib_path)
                normalized_lib = f"{lib_id}|{normalize_path(mapped_lib_path)}|unknown"
                normalized_libs.append(normalized_lib)
                if DEBUG:
                    print(f"[DEBUG] 旧格式媒体库路径（无类型）: {lib}", file=sys.stderr)
    
    # 打印所有规范化后的媒体库路径
    if DEBUG:
        print(f"[DEBUG] 共有 {len(normalized_libs)} 个媒体库路径")
        for lib in normalized_libs:
            print(f"[DEBUG] 媒体库: {lib}", file=sys.stderr)
    
    # 先尝试查找相同类型的媒体库
    while current_path and current_path != '/':
        norm_current = normalize_path(current_path)
        if DEBUG:
            print(f"[DEBUG] 当前路径: {norm_current}", file=sys.stderr)
        
        for lib in normalized_libs:
            lib_id, lib_path, lib_type = lib.split('|', 2)
            if DEBUG:
                print(f"[DEBUG] 比较: {norm_current} vs {lib_path} (类型: {lib_type})", file=sys.stderr)
            
            # 如果媒体类型匹配且路径匹配
            if (lib_type == target_type or target_type == 'unknown') and \
               (norm_current == lib_path or norm_current.startswith(f"{lib_path}/")):
                # 计算媒体库路径的深度
                lib_depth = len(lib_path.split('/'))
                if DEBUG:
                    print(f"[DEBUG] 找到匹配: {lib_id}|{lib_path}|{lib_type} (深度: {lib_depth})", file=sys.stderr)
                if lib_depth > best_depth:
                    best_match = f"{lib_id}|{lib_path}"
                    best_depth = lib_depth
        
        if best_match:
            break  # 找到匹配后退出循环
        current_path = os.path.dirname(current_path)
    
    # 如果没有找到相同类型的媒体库，尝试查找任何类型的媒体库
    if not best_match:
        current_path = mapped_target_path
        while current_path and current_path != '/':
            norm_current = normalize_path(current_path)
            if DEBUG:
                print(f"[DEBUG] 尝试查找任何类型的媒体库，当前路径: {norm_current}", file=sys.stderr)
            
            for lib in normalized_libs:
                lib_id, lib_path, lib_type = lib.split('|', 2)
                if norm_current == lib_path or norm_current.startswith(f"{lib_path}/"):
                    lib_depth = len(lib_path.split('/'))
                    if DEBUG:
                        print(f"[DEBUG] 找到任何类型匹配: {lib_id}|{lib_path}|{lib_type} (深度: {lib_depth})", file=sys.stderr)
                    if lib_depth > best_depth:
                        best_match = f"{lib_id}|{lib_path}"
                        best_depth = lib_depth
            
            if best_match:
                break
            current_path = os.path.dirname(current_path)
    
    if DEBUG:
        if best_match:
            print(f"[DEBUG] 最佳匹配: {best_match}", file=sys.stderr)
        else:
            print(f"[DEBUG] 未找到匹配的媒体库", file=sys.stderr)
            # 打印所有媒体库，帮助调试
            print(f"[DEBUG] 可用媒体库列表:", file=sys.stderr)
            for lib in normalized_libs:
                print(f"[DEBUG]   {lib}", file=sys.stderr)
    return best_match

def normalize_path(path):
    """规范化路径，移除尾部斜杠并替换多个斜杠为单个斜杠"""
    return path.rstrip('/').replace('//', '/')

if __name__ == "__main__":
    # 确保命令行参数被正确解码为UTF-8
    for i in range(len(sys.argv)):
        if isinstance(sys.argv[i], bytes):
            sys.argv[i] = sys.argv[i].decode('utf-8')
            
    if len(sys.argv) < 2:
        print("用法: library_utils.py <command> [args]", file=sys.stderr)
        sys.exit(1)
    
    command = sys.argv[1]
    if command == "extract_library_paths":
        if len(sys.argv) != 3:
            print("用法: library_utils.py extract_library_paths <cache_file>", file=sys.stderr)
            sys.exit(1)
        
        cache_file = sys.argv[2]
        extract_library_paths(cache_file)
    elif command == "find_deepest_matching_library":
        if len(sys.argv) != 4:
            print("用法: library_utils.py find_deepest_matching_library <target_path> <library_cache>", file=sys.stderr)
            sys.exit(1)
        
        target_path = sys.argv[2]
        cache_file = sys.argv[3]
        
        # 先提取媒体库路径
        import subprocess
        # 获取当前脚本的目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, "library_utils.py")
        result = subprocess.run(
            ["python3", script_path, "extract_library_paths", cache_file],
            capture_output=True, text=True, encoding='utf-8'
        )
        if result.returncode != 0:
            print(f"提取媒体库路径失败: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        
        library_paths = result.stdout
        match = find_deepest_matching_library(target_path, library_paths)
        print(match)
    else:
        print(f"未知命令: {command}", file=sys.stderr)
        sys.exit(1)