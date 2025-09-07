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
from .timeout_decorator import run_with_timeout

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
        
        增强版：通过执行shell脚本来处理配置文件中的条件逻辑
        """
        # 检查是否在Docker环境中
        is_docker = self.is_docker
        # 设置超时时间：Docker环境300秒，非Docker环境600秒
        timeout_seconds = 300 if is_docker else 600
        
        def _parse_env_file_core():
            """核心解析逻辑"""
            try:
                # 创建一个临时shell脚本，包含配置文件中的所有内容和打印配置的命令
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_script:
                    # 添加shebang
                    temp_script.write('#!/bin/bash\n')
                    # 添加配置文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        temp_script.write(f.read())
                    
                    # 确保所有变量都被导出，并添加打印所有变量的命令
                    temp_script.write('\n\n# 导出所有设置的变量并打印\nfor var in $(set -o posix; set | grep -v "^_=" | cut -d= -f1); do\n    export $var\ndone\n\nenv | grep -v "^_="')
                    
                    temp_script_path = temp_script.name
                
                # 执行临时脚本并获取输出
                import subprocess
                result = subprocess.run(
                    ['bash', temp_script_path],
                    capture_output=True,
                    text=True
                )
                
                # 清理临时文件
                os.unlink(temp_script_path)
                
                # 解析输出结果
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        line = line.strip()
                        if not line:
                            continue
                        
                        # 解析键值对
                        if '=' in line:
                            key, value = line.split('=', 1)
                            # 移除引号
                            value = value.strip('"')
                            value = value.strip("'")
                            self._config[key] = value
                    
                    # 打印加载的配置以供调试
                    self.logger.debug(f"从配置文件加载了 {len(self._config)} 个配置项")
                    for key, value in self._config.items():
                        # 不打印敏感信息
                        if 'TOKEN' not in key and 'PASSWORD' not in key:
                            self.logger.debug(f"  {key}={value}")
                else:
                    self.logger.error(f"执行配置脚本失败: {result.stderr}")
                    # 回退到简单解析
                    self._simple_parse_env_file(file_path)
            except Exception as e:
                self.logger.error(f"解析配置文件失败 {file_path}: {str(e)}")
                # 回退到简单解析
                self._simple_parse_env_file(file_path)
        
        # 使用超时控制执行核心解析逻辑
        try:
            run_with_timeout(
                _parse_env_file_core,
                timeout_seconds=timeout_seconds,
                default=False,
                error_message=f"解析配置文件 {file_path} 超时"
            )
        except TimeoutError:
            self.logger.error(f"解析配置文件超时({timeout_seconds}秒)，使用回退方案")
            self._simple_parse_env_file(file_path)
            
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
            'TEST_ENV': '0',
            'ENABLE_PLEX': '1',
            'WAIT_FOR_SCAN_COMPLETION': '0',
            'SCAN_TIMEOUT': '300',
            'MIN_FILE_SIZE_MB': '10',
            'MAX_FILES_PER_SCAN': '500',
            'SMB_MAX_WORKERS': '5',  # SMB连接的最大并行线程数，默认为3以避免连接过载
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
        self.logger.debug(f"  测试环境: {'开启' if self.is_test_env else '关闭'}")
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
    def is_test_env(self):
        """是否为测试环境"""
        return self.get_bool('TEST_ENV', False)
    
    @property
    def is_docker(self):
        """是否在Docker环境中"""
        # 检查环境变量
        if self.get_bool('DOCKER_ENV', False):
            return True
        # 检查Docker特有的文件
        if os.path.exists('/.dockerenv'):
            return True
        # 检查cgroup信息
        try:
            with open('/proc/1/cgroup', 'r') as f:
                if 'docker' in f.read():
                    return True
        except Exception:
            pass
        return False
    
    @property
    def enable_plex(self):
        """是否启用Plex集成"""
        # 根据_set_defaults中的设置，ENABLE_PLEX默认为'1'，所以这里也应该默认返回True
        return self.get_bool('ENABLE_PLEX', True)
    
    def get_mount_paths(self):
        """获取挂载路径列表"""
        # 检查是否为测试环境
        if self.is_test_env:
            # 测试环境返回测试路径
            test_base_path = self.get('TEST_BASE_PATH', '')
            if test_base_path and os.path.exists(test_base_path):
                # 返回TEST_BASE_PATH下的所有子目录作为挂载点
                subdirs = []
                try:
                    for item in os.listdir(test_base_path):
                        item_path = os.path.join(test_base_path, item)
                        if os.path.isdir(item_path):
                            subdirs.append(item_path)
                    # 如果没有子目录，返回TEST_BASE_PATH本身
                    if not subdirs and os.path.isdir(test_base_path):
                        subdirs.append(test_base_path)
                    return subdirs
                except Exception as e:
                    self.logger.error(f"读取测试路径失败: {str(e)}")
                    return [test_base_path]
            # 如果TEST_BASE_PATH不存在，使用固定的测试路径
            fixed_test_path = '/Volumes/PSSD/项目/plexAutoScan/test_files'
            if os.path.exists(fixed_test_path):
                self.logger.warning(f"TEST_BASE_PATH不存在，使用固定测试路径: {fixed_test_path}")
                # 返回fixed_test_path下的所有子目录作为挂载点
                subdirs = []
                try:
                    for item in os.listdir(fixed_test_path):
                        item_path = os.path.join(fixed_test_path, item)
                        if os.path.isdir(item_path):
                            subdirs.append(item_path)
                    # 如果没有子目录，返回fixed_test_path本身
                    if not subdirs and os.path.isdir(fixed_test_path):
                        subdirs.append(fixed_test_path)
                    return subdirs
                except Exception as e:
                    self.logger.error(f"读取固定测试路径失败: {str(e)}")
                    return [fixed_test_path]
            # 如果都不存在，返回空列表
            self.logger.error("测试路径不存在")
            return []
        
        # 生产环境优先使用MOUNT_PATHS配置
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
        
        # 如果MOUNT_PATHS未配置，再检查是否在Docker环境中
        if self.is_docker:
            # Docker环境中使用PROD_BASE_PATH（如果配置了）
            prod_base_path = self.get('PROD_BASE_PATH', '')
            if prod_base_path:
                # 如果PROD_BASE_PATH是单个路径，直接返回
                if prod_base_path.strip() and not any(sep in prod_base_path for sep in [',', ';', '\n', ' ']):
                    # 尝试直接返回PROD_BASE_PATH下的所有子目录作为挂载点，添加异常处理
                    try:
                        if os.path.exists(prod_base_path):
                            subdirs = []
                            # 使用超时控制来防止目录遍历卡死
                            def list_dir_safely():
                                for item in os.listdir(prod_base_path):
                                    try:
                                        item_path = os.path.join(prod_base_path, item)
                                        if os.path.isdir(item_path):
                                            subdirs.append(item_path)
                                    except Exception as e:
                                        self.logger.warning(f"无法访问目录项 {item}: {str(e)}")

                            # 30秒超时控制
                            run_with_timeout(
                                list_dir_safely,
                                timeout_seconds=30,
                                logger=self.logger,
                                operation_name=f"遍历目录 {prod_base_path}"
                            )
                            # 如果成功获取到子目录，返回子目录列表
                            if subdirs:
                                return subdirs
                            # 如果没有获取到子目录（可能是空目录或遍历超时），返回PROD_BASE_PATH本身
                            self.logger.warning(f"未找到PROD_BASE_PATH子目录，返回PROD_BASE_PATH本身")
                            return [prod_base_path]
                    except Exception as e:
                        self.logger.error(f"获取PROD_BASE_PATH子目录失败: {str(e)}")
                        # 发生异常时也返回PROD_BASE_PATH本身作为回退
                        return [prod_base_path]
                # 否则按分隔符处理
        
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