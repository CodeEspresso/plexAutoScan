#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
"""

import os
import re
import json
from pathlib import Path
import logging
from typing import Optional, Dict, Any, Union
from .timeout_decorator import run_with_timeout, timeout_config
from .environment import env_detector

class Config:
    """配置管理类"""
    
    def __init__(self, config_file, logger=None):
        """初始化配置"""
        self.config_file = config_file
        self.logger = logger or logging.getLogger(__name__)
        self._config = {}
        self._load_config()
        
    def _load_config(self):
        """加载配置文件"""
        self.logger.info(f"加载配置文件: {self.config_file}")
        
        # 尝试从多个位置加载配置
        config_paths = [self.config_file]
        
        # 添加默认配置路径
        if self.config_file != '/data/config.env':
            config_paths.append('/data/config.env')
        
        # 添加项目根目录下的配置
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_paths.append(os.path.join(project_root, 'config.env'))
        
        # 添加data目录下的配置
        config_paths.append(os.path.join(project_root, 'data', 'config.env'))
        
        # 查找存在的配置文件
        found_config = None
        for path in config_paths:
            if os.path.exists(path):
                found_config = path
                break
        
        if found_config:
            self.logger.info(f"找到配置文件: {found_config}")
            self._parse_env_file(found_config)
        else:
            self.logger.warning(f"未找到配置文件，使用环境变量和默认值")
        
        # 从环境变量中加载配置
        self._load_from_env()
        
        # 设置默认值
        self._set_defaults()
        
        # 导出配置到环境变量
        self._export_to_env()
        
        # 验证配置
        self.logger.debug("配置加载完成")
    
    def _parse_env_file(self, file_path):
        """解析.env格式的配置文件
        
        增强版：使用纯Python解析，避免命令注入风险
        """
        # 使用统一的超时配置
        timeout_seconds = timeout_config.get_timeout('long')  # 长时间超时：10分钟
        
        def _parse_env_file_core():
            """核心解析逻辑"""
            try:
                # 使用纯Python解析，避免命令注入风险
                with open(file_path, 'r', encoding='utf-8') as f:
                    # 先读取整个文件内容
                    content = f.read()
                    
                    # 处理反斜杠换行（将 \ 后跟换行符的情况合并）
                    # 变更理由：配置文件可能使用反斜杠换行来分割长路径，需要正确处理
                    content = re.sub(r'\\\s*\n\s*', ' ', content)
                    
                    # 按行处理
                    for line in content.split('\n'):
                        line = line.strip()
                        
                        # 跳过注释和空行
                        if not line or line.startswith('#'):
                            continue
                        
                        # 解析键值对
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # 移除引号
                            if value.startswith('"') and value.endswith('"'):
                                value = value[1:-1]
                            elif value.startswith("'") and value.endswith("'"):
                                value = value[1:-1]
                            
                            # 处理变量替换（如 ${VAR} 或 $VAR）
                            value = self._expand_variables(value)
                            
                            self._config[key] = value
                
                # 打印加载的配置以供调试
                self.logger.debug(f"从配置文件加载了 {len(self._config)} 个配置项")
                for key, value in self._config.items():
                    # 不打印敏感信息
                    if 'TOKEN' not in key and 'PASSWORD' not in key:
                        self.logger.debug(f"  {key}={value}")
            except Exception as e:
                self.logger.error(f"解析配置文件失败 {file_path}: {str(e)}")
        
        # 使用超时控制执行核心解析逻辑
        try:
            run_with_timeout(
                _parse_env_file_core,
                timeout_seconds=timeout_seconds,
                default=False,
                error_message=f"解析配置文件 {file_path} 超时"
            )
        except TimeoutError:
            self.logger.error(f"解析配置文件超时({timeout_seconds}秒)")
    
    def _expand_variables(self, value: str) -> str:
        """展开配置值中的环境变量引用
        
        Args:
            value (str): 配置值
            
        Returns:
            str: 展开后的值
        """
        import re
        
        # 匹配 ${VAR} 或 $VAR 格式
        pattern = r'\$\{([^}]+)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)'
        
        def replace_var(match):
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, '')
        
        return re.sub(pattern, replace_var, value)
            
    def _simple_parse_env_file(self, file_path):
        """简单解析.env格式的配置文件（回退方案）"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳过注释和空行
                    if not line or line.startswith('#'):
                        continue
                    
                    # 解析键值对
                    match = re.match(r'([^=]+)\s*=\s*(.*)', line)
                    if match:
                        key, value = match.groups()
                        # 移除引号
                        value = value.strip('"')
                        value = value.strip("'")
                        self._config[key] = value
        except Exception as e:
            self.logger.error(f"简单解析配置文件失败 {file_path}: {str(e)}")
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        for key in os.environ:
            if key not in self._config:
                self._config[key] = os.environ[key]
    
    def _set_defaults(self):
        """设置默认值"""
        # 默认值配置
        defaults = {
            'DEBUG': '0',
            'ENABLE_PLEX': '1',
            'WAIT_FOR_SCAN_COMPLETION': '0',
            'SCAN_TIMEOUT': '300',
            'MIN_FILE_SIZE_MB': '10',
            'MAX_FILES_PER_SCAN': '500',
            'SMB_MAX_WORKERS': '10',  # SMB连接的最大并行线程数
            'ENABLE_DIRECTORY_MERGING': '1',  # 是否启用目录合并功能
            'MAX_DIRECTORY_DEPTH': '5',  # 目录合并的最大深度
        }
        
        for key, default_value in defaults.items():
            if key not in self._config:
                self._config[key] = default_value
    
    def _export_to_env(self):
        """导出配置到环境变量"""
        for key, value in self._config.items():
            os.environ[key] = value
    
    def get(self, key, default=None):
        """获取配置项"""
        return self._config.get(key, default)
    
    def get_int(self, key, default=0):
        """获取整数类型的配置项"""
        try:
            return int(self.get(key, default))
        except (ValueError, TypeError):
            return default
    
    def get_bool(self, key, default=False):
        """获取布尔类型的配置项"""
        value = self.get(key, str(default))
        return value.lower() in ('true', 'yes', '1', 'y', 't')
    
    def get_list(self, key, default=None):
        """获取列表类型的配置项（支持空格、逗号、分号分隔）
        
        Args:
            key (str): 配置项名称
            default (list): 默认值
            
        Returns:
            list: 配置项列表
        """
        if default is None:
            default = []
        
        value = self.get(key, '')
        if not value:
            return default
        
        # 支持多种分隔符
        for separator in [',', ';', '\n', ' ']:
            if separator in value:
                return [item.strip() for item in value.split(separator) if item.strip()]
        
        # 如果没有分隔符，返回单个元素的列表
        return [value.strip()] if value.strip() else default
    
    def validate(self):
        """验证配置有效性"""
        self.logger.info("验证配置...")
        
        # 检查必需的配置项
        required_fields = []
        
        # 如果启用了Plex，检查Plex相关配置
        if self.enable_plex:
            required_fields.extend(['PLEX_URL', 'PLEX_TOKEN'])
        
        # 检查MOUNT_PATHS是否配置
        if not self.get('MOUNT_PATHS'):
            self.logger.warning('MOUNT_PATHS未配置，将无法处理任何目录')
        
        # 检查必需字段
        missing_fields = [field for field in required_fields if not self.get(field)]
        if missing_fields:
            self.logger.error(f"缺少必需的配置项: {', '.join(missing_fields)}")
            return False
        
        # 输出配置摘要
        self.logger.debug("配置摘要:")
        self.logger.debug(f"  调试模式: {'开启' if self.debug else '关闭'}")
        self.logger.debug(f"  Docker环境: {'是' if self.is_docker else '否'}")
        self.logger.debug(f"  启用Plex: {'是' if self.enable_plex else '否'}")
        if self.enable_plex:
            plex_url = self.get('PLEX_URL', '')
            # 隐藏Plex Token的部分信息
            plex_token = self.get('PLEX_TOKEN', '')
            masked_token = f"{plex_token[:3]}...{plex_token[-3:]}" if plex_token else ''
            self.logger.debug(f"  Plex URL: {plex_url}")
            self.logger.debug(f"  Plex Token: {masked_token}")
        
        mount_paths = self.get_mount_paths()
        self.logger.debug(f"  挂载路径数量: {len(mount_paths)}")
        
        return True
    
    @property
    def debug(self):
        """是否启用调试模式"""
        return self.get_bool('DEBUG', False)
    
    @property
    def is_docker(self):
        """是否在Docker环境中"""
        return env_detector.is_docker()
    
    @property
    def enable_plex(self):
        """是否启用Plex集成"""
        return self.get_bool('ENABLE_PLEX', True)
    
    def get_mount_paths(self):
        """获取挂载路径列表"""
        mount_paths_str = self.get('MOUNT_PATHS', '')
        if mount_paths_str:
            # 支持多种分隔符
            paths = []
            for separator in [',', ';', '\n', ' ']:
                if separator in mount_paths_str:
                    paths = mount_paths_str.split(separator)
                    break
            
            # 如果没有找到分隔符，整个字符串作为一个路径
            if not paths:
                paths = [mount_paths_str]
            
            # 清理并过滤空路径
            return [path.strip() for path in paths if path.strip()]
        
        # 如果都没有配置，返回空列表
        self.logger.warning("MOUNT_PATHS未配置，无法处理任何目录")
        return []
    
    def get_exclude_paths(self):
        """获取排除路径列表"""
        exclude_paths_str = self.get('EXCLUDE_PATHS', '')
        if not exclude_paths_str:
            return []
        
        # 支持多种分隔符
        paths = []
        for separator in [',', ';', '\n', ' ']:
            if separator in exclude_paths_str:
                paths = exclude_paths_str.split(separator)
                break
        
        # 如果没有找到分隔符，整个字符串作为一个路径
        if not paths:
            paths = [exclude_paths_str]
        
        # 清理并过滤空路径
        return [path.strip() for path in paths if path.strip()]