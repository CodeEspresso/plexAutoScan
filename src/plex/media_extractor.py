#!/usr/bin/env python3
"""Plex媒体提取器
用于从Plex XML响应中提取媒体文件路径
支持处理未转义双引号和复杂XML结构
用法：$PYTHON_EXEC media_extractor.py extract_paths < input.xml
"""
import sys
import re
import html
import os

# 从环境变量获取DEBUG模式设置
# 设置为1启用详细调试日志，0禁用
DEBUG = os.environ.get('DEBUG', '0') == '1'

# 控制是否输出媒体路径提取的DEBUG日志
DEBUG_PATH_EXTRACTION = os.environ.get('DEBUG_PATH_EXTRACTION', str(DEBUG)) == '1'

MEDIA_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".mpeg", ".mpg", ".m4v",
    ".ts", ".iso", ".m2ts", ".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma",
    ".aiff", ".ape", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
    ".pdf", ".epub", ".mobi", ".cbz", ".cbr"
}

def preprocess_xml(xml_str: str) -> str:
    """预处理XML字符串，修复未转义的双引号"""
    # 保护CDATA部分
    cdata_pattern = r'<!\[CDATA\[.*?\]\]>'
    cdata_map = {}
    def replace_cdata(match):
        key = f"__CDATA_{len(cdata_map)}__"
        cdata_map[key] = match.group(0)
        return key
    xml_str = re.sub(cdata_pattern, replace_cdata, xml_str, flags=re.DOTALL)

    # 修复属性值中的未转义双引号
    attr_pattern = r'(\w+)=\"([^\"]*?)(?:\"([^\"]*?))*\"'
    def fix_attr_quotes(match):
        key = match.group(1)
        value = match.group(2)
        if match.group(3):
            value += match.group(3).replace('"', '&quot;')
        # 先替换 &quot; 为双引号，再格式化字符串
        value = value.replace("&quot;", '"')
        return f'{key}="{value}"'
    xml_str = re.sub(attr_pattern, fix_attr_quotes, xml_str)

    # 还原CDATA部分
    for key, value in cdata_map.items():
        xml_str = xml_str.replace(key, value)

    return xml_str

def extract_paths(xml_str: str):
    """从XML字符串中提取媒体文件路径"""
    # 打印XML前1000字符和后100字符（调试用）
    if DEBUG:
        print(f"[DEBUG] XML响应前1000字符: {xml_str[:1000]}...", file=sys.stderr)
        print(f"[DEBUG] XML响应后100字符: {xml_str[-100:]}...", file=sys.stderr)
        print(f"[DEBUG] XML总长度: {len(xml_str)} 字符", file=sys.stderr)

    # 保存XML到临时文件供检查
    if DEBUG:
        with open('temp_xml_debug.xml', 'w', encoding='utf-8') as f:
            f.write(xml_str)
        print(f"[DEBUG] XML已保存到temp_xml_debug.xml", file=sys.stderr)

    # 使用更健壮的正则表达式匹配Part标签中的file属性
    # 匹配<Part ... file="..." ...>格式，确保捕获完整路径
    file_pattern = r'<Part\b[^>]*\bfile\s*=\s*"([^"]+)"'
    paths = []
    matches = re.finditer(file_pattern, xml_str, re.IGNORECASE)
    found_matches = list(matches)
    if DEBUG:
        print(f"[DEBUG] 找到 {len(found_matches)} 个Part标签中的file属性匹配", file=sys.stderr)

    # 如果没找到，尝试更宽松的匹配模式
    if not found_matches:
        file_pattern = r'file\s*=\s*"([^"]+)"'
        matches = re.finditer(file_pattern, xml_str, re.IGNORECASE)
        found_matches = list(matches)
        if DEBUG:
            print(f"[DEBUG] 使用宽松模式找到 {len(found_matches)} 个file属性匹配", file=sys.stderr)

    for match in found_matches:
        try:
            # 获取引号内的内容
            path = match.group(1)
            # 替换反斜杠为正斜杠
            path = path.replace('\\', '/')
            if DEBUG_PATH_EXTRACTION:
                print(f"[DEBUG] 提取到文件路径: {path}", file=sys.stderr)
            # 检查扩展名（不区分大小写）
            if any(path.lower().endswith(ext) for ext in MEDIA_EXTS):
                paths.append(path)
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] 处理匹配时出错: {str(e)}", file=sys.stderr)

    # 如果没找到，尝试匹配单引号
    if not paths:
        file_pattern = r'<Part\s+[^>]*file\s*=\s*\'([^\']+)\''
        matches = re.finditer(file_pattern, xml_str, re.IGNORECASE)
        found_matches = list(matches)
        if DEBUG:
            print(f"[DEBUG] 尝试单引号匹配，找到 {len(found_matches)} 个Part标签中的file属性匹配", file=sys.stderr)
        for match in found_matches:
            try:
                path = match.group(1).replace('\\', '/')
                if DEBUG:
                    if DEBUG_PATH_EXTRACTION:
                        print(f"[DEBUG] 单引号匹配提取到文件路径: {path}", file=sys.stderr)
                if any(path.lower().endswith(ext) for ext in MEDIA_EXTS):
                    paths.append(path)
            except Exception as e:
                  if DEBUG:
                      print(f"[DEBUG] 单引号匹配处理时出错: {str(e)}", file=sys.stderr)

    # 去重并排序
    unique_paths = sorted(set(paths))
    if DEBUG:
        print(f"[DEBUG] 共提取到 {len(unique_paths)} 个媒体文件路径", file=sys.stderr)
    return unique_paths

def extract_paths_from_library(library_id):
    # 根据媒体库ID从Plex服务器获取并提取文件路径
    import os
    import urllib.request
    import json

    # 从环境变量获取配置
    plex_url = os.environ.get('PLEX_URL')
    plex_token = os.environ.get('PLEX_TOKEN')

    # 检查配置
    if not all([plex_url, plex_token]):
        print(f"错误: 缺少PLEX_URL或PLEX_TOKEN环境变量", file=sys.stderr)
        print(f"请确保在config.env中设置了这些变量并通过config.sh加载", file=sys.stderr)
        sys.exit(1)

    # 构建API请求URL
    url = f'{plex_url}/library/sections/{library_id}/all?X-Plex-Token={plex_token}'

    try:
        # 发送请求
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status != 200:
                print(f"错误: Plex服务器响应状态码: {response.status}", file=sys.stderr)
                sys.exit(1)
            
            # 检查响应内容类型
            content_type = response.getheader('Content-Type', '')
            if DEBUG:
                print(f"[PYTHON] 响应内容类型: {content_type}", file=sys.stderr)
                if 'xml' not in content_type:
                    print(f"警告: Plex响应不是XML格式: {content_type}", file=sys.stderr)
            
            xml_in = response.read().decode('utf-8')
            if DEBUG:
                print(f"[PYTHON] 响应数据长度: {len(xml_in)} 字节", file=sys.stderr)
                print(f"[PYTHON] 响应前200字符: {xml_in[:200]}...", file=sys.stderr)
                print(f"[PYTHON] 响应后200字符: {xml_in[-200:]}...", file=sys.stderr)

            # 验证并尝试修复XML格式
            if not xml_in.startswith('<?xml') and DEBUG:
                print(f"[WARN] XML响应不是有效的XML格式，尝试修复...", file=sys.stderr)
                # 尝试找到第一个<标记并在之前添加XML声明
                first_tag_pos = xml_in.find('<')
                if first_tag_pos > 0:
                    xml_in = '<?xml version="1.0" encoding="UTF-8"?>' + xml_in[first_tag_pos:]
                    print(f"[DEBUG] 已添加XML声明", file=sys.stderr)

        # 保存XML响应到项目目录（调试用）
        if DEBUG:
            import os
            xml_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'output')
            os.makedirs(xml_dir, exist_ok=True)
            xml_path = os.path.join(xml_dir, f'plex_library_{library_id}_response.xml')
            with open(xml_path, 'w', encoding='utf-8') as f:
                f.write(xml_in)
            print(f"[DEBUG] Plex响应XML已保存到: {xml_path}", file=sys.stderr)

        # 提取路径
        paths = extract_paths(xml_in)
        for p in paths:
            print(p)
    except urllib.error.URLError as e:
        print(f"错误: URL请求失败: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: 处理媒体库ID {library_id} 时失败: {str(e)}", file=sys.stderr)
        sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("用法:", file=sys.stderr)
        print("  $PYTHON_EXEC media_extractor.py extract_paths < input.xml", file=sys.stderr)
        print("  $PYTHON_EXEC media_extractor.py extract_paths_from_library <library_id>", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "extract_paths":
        xml_in = sys.stdin.read()
        try:
            paths = extract_paths(xml_in)
            for p in paths:
                print(p)
        except Exception as e:
            print(f"错误: {str(e)}", file=sys.stderr)
            sys.exit(1)
    elif sys.argv[1] == "extract_paths_from_library":
        if len(sys.argv) < 3:
            print("用法: $PYTHON_EXEC media_extractor.py extract_paths_from_library <library_id>", file=sys.stderr)
            sys.exit(1)
        library_id = sys.argv[2]
        extract_paths_from_library(library_id)
    else:
        print("未知命令", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()