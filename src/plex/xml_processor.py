#!/usr/bin/env python3
"""
零依赖容错版
把 XML 当 HTML 解析，无需 ElementTree
用法：
  $PYTHON_EXEC xml_processor_final.py parse_xml < bad.xml
"""
import sys
import html
from html.parser import HTMLParser

# 支持的扩展名
MEDIA_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".mpeg", ".mpg", ".m4v",
    ".ts", ".iso", ".m2ts", ".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma",
    ".aiff", ".ape", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
    ".pdf", ".epub", ".mobi", ".cbz", ".cbr"
}

class FileExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == 'file' and v:
                path = html.unescape(v).replace('\\', '/').lower()
                if any(path.endswith(ext) for ext in MEDIA_EXTS):
                    self.paths.append(path)

class PlexLibraryExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.media_libraries = []
        self.current_library = None
        self.in_media_container = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        # 开始处理MediaContainer
        if tag.lower() == 'mediacontainer':
            self.in_media_container = True
        
        # 找到Directory元素（代表媒体库）
        elif tag.lower() == 'directory' and self.in_media_container:
            # 只处理一级Directory元素（直接在MediaContainer下的）
            if self.current_library is None:
                self.current_library = {
                    'id': attrs_dict.get('key'),
                    'name': attrs_dict.get('title'),
                    'type': attrs_dict.get('type'),
                    'path': ''  # 初始化为空，后面会更新
                }
        
        # 找到Location元素，提取路径信息
        elif tag.lower() == 'location' and self.current_library:
            location_path = attrs_dict.get('path', '')
            if location_path:
                # 如果已经有path，用分号分隔多个路径
                if self.current_library['path']:
                    self.current_library['path'] += ';' + location_path
                else:
                    self.current_library['path'] = location_path
        
        # 备选方案：如果Location元素不存在，尝试从Directory的path属性直接获取
        elif tag.lower() == 'directory' and self.in_media_container and self.current_library:
            dir_path = attrs_dict.get('path', '')
            if dir_path and not self.current_library['path']:
                self.current_library['path'] = dir_path
    
    def handle_endtag(self, tag):
        # 当Directory元素结束时，保存当前媒体库
        if tag.lower() == 'directory' and self.current_library:
            self.media_libraries.append(self.current_library)
            self.current_library = None
        
        # 当MediaContainer元素结束时，标记处理完成
        elif tag.lower() == 'mediacontainer':
            self.in_media_container = False

def extract_paths(xml_str: str):
    parser = FileExtractor()
    parser.feed(xml_str)
    parser.close()
    return sorted(set(parser.paths))

def parse_plex_libraries(xml_str: str):
    """解析Plex媒体库的XML响应
    
    Args:
        xml_str: XML格式的字符串
        
    Returns:
        list: 媒体库列表，每个媒体库包含id、name、type和path属性
    """
    parser = PlexLibraryExtractor()
    parser.feed(xml_str)
    parser.close()
    return parser.media_libraries

def main():
    if len(sys.argv) < 2 or sys.argv[1] != "parse_xml":
        print("用法: $PYTHON_EXEC xml_processor_final.py parse_xml < input.xml", file=sys.stderr)
        sys.exit(1)

    xml_in = sys.stdin.read()
    for p in extract_paths(xml_in):
        print(p)

if __name__ == "__main__":
    main()