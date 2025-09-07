#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
依赖管理模块
"""

import os
import sys
import time
import importlib
import subprocess
import logging
from typing import Dict, List, Tuple, Optional

# 删除: 使用错误路径的绝对导入
# 新增: 使用正确的相对导入
from .utils.logger import RobustLogger
from .utils.config import Config

# 初始化日志记录器
logger = RobustLogger('dependencies')


class DependencyManager:
    """依赖管理器类，负责检查和安装项目依赖"""
    
    def __init__(self, config=None):
        """初始化依赖管理器
        
        Args:
            config (Config): 配置对象
        """
        self.config = config or Config()
        
        # 核心依赖列表
        self.core_dependencies = {
            'psutil': 'psutil',  # 进程和系统资源监控
            'smb': 'pysmb'     # SMB/CIFS协议支持（注意：包名为pysmb，但导入名称为smb）
        }
        
        # 可选依赖列表
        self.optional_dependencies = {
            'requests': 'requests',  # HTTP请求（Plex API需要）
            'yaml': 'pyyaml',        # YAML配置文件支持（导入名称为yaml，包名为pyyaml）
            'tqdm': 'tqdm'           # 进度条支持
        }
        
        # 系统依赖列表
        self.system_dependencies = {
            'curl': 'curl',       # 命令行HTTP工具
            'timeout': 'timeout', # 命令超时控制工具
            'find': 'find',       # 文件查找工具
            'ls': 'ls',           # 列表显示工具
            'mkdir': 'mkdir'      # 目录创建工具
        }
        
        # 保存检查结果
        self.check_results = {
            'core': {},
            'optional': {},
            'system': {}
        }
    
    def check_all_dependencies(self) -> Dict:
        """检查所有依赖项
        
        Returns:
            dict: 依赖检查结果
        """
        logger.info("开始检查所有依赖...")
        
        # 检查Python核心依赖
        self.check_results['core'] = self._check_python_dependencies(self.core_dependencies)
        
        # 检查Python可选依赖
        self.check_results['optional'] = self._check_python_dependencies(self.optional_dependencies)
        
        # 检查系统依赖
        self.check_results['system'] = self._check_system_dependencies(self.system_dependencies)
        
        # 验证结果
        is_core_complete = all(self.check_results['core'].values())
        is_all_complete = is_core_complete and all(self.check_results['optional'].values()) and all(self.check_results['system'].values())
        
        # 打印检查摘要
        self._print_dependency_summary()
        
        return {
            'success': is_core_complete,  # 只要求核心依赖完成
            'all_complete': is_all_complete,
            'results': self.check_results
        }
    
    def _check_python_dependencies(self, dependencies: Dict[str, str]) -> Dict[str, bool]:
        """检查Python依赖包
        
        Args:
            dependencies (dict): 依赖包名称映射字典 {导入名: 包名}
            
        Returns:
            dict: 依赖检查结果 {包名: 是否已安装}
        """
        results = {}
        
        # 打印Python环境信息用于调试
        logger.debug("=== Python环境诊断信息 ===")
        logger.debug(f"当前Python解释器: {sys.executable}")
        logger.debug(f"虚拟环境: {os.environ.get('VIRTUAL_ENV', '未设置')}")
        logger.debug(f"Python版本: {sys.version}")
        logger.debug(f"PATH环境变量: {os.environ.get('PATH', '未设置')}")
        logger.debug(f"PYTHONPATH: {os.environ.get('PYTHONPATH', '未设置')}")
        logger.debug(f"sys.prefix: {sys.prefix}")
        logger.debug(f"sys.base_prefix: {sys.base_prefix}")
        logger.debug(f"是否在虚拟环境中: {sys.prefix != sys.base_prefix}")
        logger.debug("=== sys.path内容 ===")
        for path in sys.path:
            logger.debug(f"  - {path}")
        logger.debug("=======================")
        
        for import_name, package_name in dependencies.items():
            try:
                # 特殊处理pysmb依赖 - 添加详细调试信息
                if package_name == 'pysmb':
                    logger.debug(f"[DEBUG] 检查依赖: {package_name} (导入名: {import_name})")
                    # 尝试使用pip show命令检查包信息
                    try:
                        result = subprocess.run(
                            [sys.executable, '-m', 'pip', 'show', package_name],
                            capture_output=True, text=True
                        )
                        if result.returncode == 0:
                            logger.debug(f"[DEBUG] pip show {package_name} 输出:\n{result.stdout}")
                        else:
                            logger.debug(f"[DEBUG] pip show {package_name} 失败:\n{result.stderr}")
                    except Exception as pip_err:
                        logger.debug(f"[DEBUG] 执行pip show命令出错: {pip_err}")
                
                importlib.import_module(import_name)
                results[package_name] = True
                logger.debug(f"Python依赖 '{package_name}' 已安装")
            except ImportError as e:
                results[package_name] = False
                logger.warning(f"Python依赖 '{package_name}' 未安装")
                logger.debug(f"[DEBUG] 导入 {import_name} 失败: {e}")
                # 尝试查找可能的模块位置
                try:
                    import site
                    logger.debug(f"[DEBUG] site-packages目录: {site.getsitepackages() if hasattr(site, 'getsitepackages') else '无法确定'}")
                except Exception as site_err:
                    logger.debug(f"[DEBUG] 获取site-packages失败: {site_err}")
            except Exception as e:
                results[package_name] = False
                logger.error(f"检查Python依赖 '{package_name}' 时发生未知错误: {str(e)}")
        
        return results
    
    def _check_system_dependencies(self, dependencies: Dict[str, str]) -> Dict[str, bool]:
        """检查系统依赖工具
        
        Args:
            dependencies (dict): 系统依赖工具映射字典 {工具名: 命令名}
            
        Returns:
            dict: 依赖检查结果 {工具名: 是否可用}
        """
        results = {}
        
        for tool_name, command_name in dependencies.items():
            try:
                # 使用subprocess检查命令是否存在
                if sys.platform == 'win32':
                    # Windows平台
                    result = subprocess.run(
                        ['where', command_name],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    is_available = result.returncode == 0
                else:
                    # Unix/Linux/macOS平台
                    result = subprocess.run(
                        ['which', command_name],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    is_available = result.returncode == 0
                
                results[tool_name] = is_available
                
                if is_available:
                    logger.debug(f"系统依赖 '{tool_name}' 已安装")
                else:
                    logger.warning(f"系统依赖 '{tool_name}' 未安装")
            except Exception as e:
                results[tool_name] = False
                logger.error(f"检查系统依赖 '{tool_name}' 失败: {str(e)}")
        
        return results
    
    def install_python_dependencies(self, dependencies: Optional[Dict[str, str]] = None) -> bool:
        """安装Python依赖
        
        Args:
            dependencies (dict): 要安装的依赖包映射字典，None表示安装所有缺失的核心依赖
            
        Returns:
            bool: 安装是否成功
        """
        # 强制重新检查核心依赖，确保获取最新状态
        logger.debug("强制重新检查核心依赖状态")
        self.check_results['core'] = self._check_python_dependencies(self.core_dependencies)
        
        # 如果未指定依赖，获取所有缺失的核心依赖
        if dependencies is None:
            dependencies = {}
            missing_count = 0
            for import_name, package_name in self.core_dependencies.items():
                if package_name in self.check_results.get('core', {}) and not self.check_results['core'][package_name]:
                    dependencies[import_name] = package_name
                    missing_count += 1
            logger.info(f"检测到 {missing_count} 个缺失的核心依赖")
        
        if not dependencies:
            logger.info("没有需要安装的Python依赖")
            return True
        
        logger.info(f"开始安装Python依赖: {', '.join(dependencies.values())}")
        
        # 检测是否在虚拟环境中
        is_venv = hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
        is_virtualenv = hasattr(sys, 'real_prefix')
        is_in_virtual_environment = is_venv or is_virtualenv
        
        # 构建pip安装命令，根据环境决定是否使用--user参数
        packages_to_install = list(dependencies.values())
        install_command = [sys.executable, '-m', 'pip', 'install', '--upgrade']
        
        # 仅在非虚拟环境中添加--user参数
        if not is_in_virtual_environment:
            install_command.append('--user')
        else:
            logger.debug("检测到虚拟环境，不使用--user参数")
        
        install_command += packages_to_install
        
        # 在容器环境中尝试使用--no-cache-dir参数和清华源
        if os.environ.get('DOCKER_ENV') == '1':
            install_command.append('--no-cache-dir')
            # 添加清华源以加速国内下载
            install_command.append('-i')
            install_command.append('https://pypi.tuna.tsinghua.edu.cn/simple')
            logger.info("检测到DOCKER_ENV=1，使用--no-cache-dir参数和清华源优化容器环境安装")
        
        # 在容器环境中，如果是pysmb依赖，添加特殊处理
        if 'pysmb' in packages_to_install and os.environ.get('DOCKER_ENV') == '1':
            logger.info("针对pysmb依赖添加特殊处理，确保正确安装")
            # 打印更多的环境信息
            logger.info(f"当前Python解释器: {sys.executable}")
            logger.info(f"当前pip版本: {self._get_pip_version()}")
            # 打印当前安装的pysmb版本（如果有）
            self._check_installed_package_version('pysmb')
        
        # 尝试安装依赖，最多重试2次
        max_retries = 2
        retry_count = 0
        install_successful = False
        
        while retry_count <= max_retries and not install_successful:
            if retry_count > 0:
                logger.info(f"第{retry_count}次重试安装依赖")
                # 暂停1秒再重试
                time.sleep(1)
            
            try:
                # 执行安装命令
                logger.debug(f"执行安装命令: {' '.join(install_command)}")
                result = subprocess.run(
                    install_command,
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                logger.info(f"Python依赖安装成功: {', '.join(packages_to_install)}")
                # 只记录部分输出以避免日志过长
                if result.stdout:
                    first_lines = result.stdout.split('\n')[:5]
                    logger.debug(f"安装输出(前5行): {chr(10).join(first_lines)}")
                
                install_successful = True
            except subprocess.CalledProcessError as e:
                logger.error(f"Python依赖安装失败: {str(e)}")
                if e.stderr:
                    logger.error(f"错误输出: {e.stderr}")
                retry_count += 1
            except Exception as e:
                logger.error(f"执行依赖安装命令失败: {str(e)}")
                retry_count += 1
        
        if not install_successful:
            logger.error(f"尝试{max_retries+1}次后，依赖安装仍失败")
            return False
        
        # 安装后重新检查依赖状态，添加更强大的验证机制
        logger.debug("依赖安装完成，重新检查依赖状态")
        
        # 强制刷新导入缓存
        importlib.invalidate_caches()
        
        # 打印当前Python路径
        logger.debug(f"当前Python路径: {sys.path}")
        
        # 安装后重新检查依赖，最多检查3次
        verification_success = False
        verify_count = 0
        max_verify_attempts = 3
        
        while verify_count < max_verify_attempts and not verification_success:
            verify_count += 1
            if verify_count > 1:
                logger.info(f"第{verify_count}次验证依赖安装状态")
                time.sleep(0.5)  # 短暂延迟后重试
            
            try:
                # 针对每个依赖单独验证
                all_verified = True
                for import_name, package_name in dependencies.items():
                    try:
                        # 尝试导入模块
                        module = importlib.import_module(import_name)
                        logger.info(f"成功导入 '{import_name}' 模块")
                        
                        # 尝试访问模块属性以确保完全加载
                        has_version = hasattr(module, '__version__')
                        logger.debug(f"模块 '{import_name}' 版本信息: {'可用' if has_version else '不可用'}")
                        
                        # 更新检查结果
                        self.check_results['core'][package_name] = True
                    except ImportError as e:
                        logger.warning(f"导入 '{import_name}' 失败: {str(e)}")
                        self.check_results['core'][package_name] = False
                        all_verified = False
                
                verification_success = all_verified
            except Exception as e:
                logger.error(f"验证依赖安装状态时出错: {str(e)}")
                import traceback
                logger.debug(f"错误堆栈: {traceback.format_exc()}")
        
        # 如果验证仍失败，尝试使用备用导入方式
        if not verification_success:
            logger.warning("标准验证失败，尝试备用导入验证...")
            for import_name, package_name in dependencies.items():
                if not self.check_results['core'].get(package_name, False):
                    try:
                        # 尝试直接使用import语句（通过exec）
                        exec(f"import {import_name}")
                        logger.info(f"备用验证: 成功导入 '{import_name}'")
                        self.check_results['core'][package_name] = True
                    except Exception as e:
                        logger.error(f"备用验证: 导入 '{import_name}' 仍失败: {str(e)}")
        
        # 再次检查是否所有依赖都已验证成功
        final_verification = all(self.check_results['core'].get(pkg, False) for pkg in dependencies.values())
        
        if final_verification:
            logger.info("所有依赖安装并验证成功")
            return True
        else:
            missing_after_install = [pkg for pkg in dependencies.values() if not self.check_results['core'].get(pkg, False)]
            logger.error(f"安装后仍有依赖缺失: {', '.join(missing_after_install)}")
            
            # 提供更多诊断信息
            logger.info("Python环境诊断:")
            logger.info(f"- Python版本: {sys.version}")
            logger.info(f"- Python可执行文件: {sys.executable}")
            logger.info(f"- 当前工作目录: {os.getcwd()}")
            
            return False
    
    def get_missing_core_dependencies(self) -> List[str]:
        """获取缺失的核心依赖列表
        
        Returns:
            list: 缺失的核心依赖名称列表
        """
        missing_deps = []
        
        for package_name, is_installed in self.check_results.get('core', {}).items():
            if not is_installed:
                missing_deps.append(package_name)
        
        return missing_deps
    
    def get_python_version(self) -> Tuple[int, int, int]:
        """获取当前Python版本
        
        Returns:
            tuple: (major, minor, micro) 版本号
        """
        return (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    
    def check_python_version(self, min_version: Tuple[int, int, int] = (3, 8, 0)) -> bool:
        """检查Python版本是否满足要求
        
        Args:
            min_version (tuple): 最低要求版本 (major, minor, micro)
            
        Returns:
            bool: 当前版本是否满足要求
        """
        current_version = self.get_python_version()
        is_satisfied = current_version >= min_version
        
        if is_satisfied:
            logger.info(f"Python版本符合要求: {'.'.join(map(str, current_version))} (最低要求: {'.'.join(map(str, min_version))})")
        else:
            logger.error(f"Python版本不符合要求: {'.'.join(map(str, current_version))} (需要至少: {'.'.join(map(str, min_version))})")
        
        return is_satisfied
    
    def _print_dependency_summary(self) -> None:
        """打印依赖检查摘要"""
        core_missing = [pkg for pkg, installed in self.check_results['core'].items() if not installed]
        optional_missing = [pkg for pkg, installed in self.check_results['optional'].items() if not installed]
        system_missing = [tool for tool, available in self.check_results['system'].items() if not available]
        
        logger.info("依赖检查摘要:")
        logger.info(f"- 核心依赖: {len(self.check_results['core']) - len(core_missing)}/{len(self.check_results['core'])} 已安装")
        
        if core_missing:
            logger.warning(f"  缺失的核心依赖: {', '.join(core_missing)}")
            logger.info(f"  请运行: python -m pip install {', '.join(core_missing)}")
        
        logger.info(f"- 可选依赖: {len(self.check_results['optional']) - len(optional_missing)}/{len(self.check_results['optional'])}")
        if optional_missing:
            logger.info(f"  缺失的可选依赖: {', '.join(optional_missing)}")
            logger.info(f"  安装建议: python -m pip install {', '.join(optional_missing)}")
        
        logger.info(f"- 系统依赖: {len(self.check_results['system']) - len(system_missing)}/{len(self.check_results['system'])}")
        if system_missing:
            logger.warning(f"  缺失的系统依赖: {', '.join(system_missing)}")
            self._print_system_dependency_install_guide(system_missing)
    
    def _print_system_dependency_install_guide(self, missing_tools: List[str]) -> None:
        """打印系统依赖安装指南
        
        Args:
            missing_tools (list): 缺失的系统工具列表
        """
        if not missing_tools:
            return
        
        logger.info("系统依赖安装指南:")
        
        if sys.platform == 'darwin':  # macOS
            logger.info("macOS用户可以使用Homebrew安装缺失的工具:")
            logger.info(f"  brew install {', '.join(missing_tools)}")
        elif sys.platform == 'linux':  # Linux
            # 检测Linux发行版
            distro = self._detect_linux_distro()
            
            if distro in ['debian', 'ubuntu', 'mint']:
                logger.info("Debian/Ubuntu/Mint用户可以使用apt安装缺失的工具:")
                logger.info(f"  sudo apt update && sudo apt install {', '.join(missing_tools)}")
            elif distro in ['fedora', 'centos', 'rhel']:
                logger.info("Fedora/CentOS/RHEL用户可以使用dnf安装缺失的工具:")
                logger.info(f"  sudo dnf install {', '.join(missing_tools)}")
            else:
                logger.info("请使用您的Linux发行版的包管理器安装缺失的工具")
        elif sys.platform == 'win32':  # Windows
            logger.info("Windows用户可以使用Chocolatey或Scoop安装缺失的工具:")
            logger.info(f"  Chocolatey: choco install {', '.join(missing_tools)}")
            logger.info(f"  Scoop: scoop install {', '.join(missing_tools)}")
        else:
            logger.info("请根据您的操作系统安装缺失的系统工具")
    
    def _detect_linux_distro(self) -> str:
        """检测Linux发行版
        
        Returns:
            str: 发行版名称
        """
        try:
            # 检查/etc/os-release文件
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    content = f.read()
                    
                    if 'ID=debian' in content or 'ID_LIKE=debian' in content:
                        return 'debian'
                    elif 'ID=fedora' in content:
                        return 'fedora'
                    elif 'ID=centos' in content or 'ID=rhel' in content:
                        return 'centos'
                    elif 'ID=arch' in content:
                        return 'arch'
            
            # 检查其他常见文件
            if os.path.exists('/etc/debian_version'):
                return 'debian'
            elif os.path.exists('/etc/fedora-release'):
                return 'fedora'
            elif os.path.exists('/etc/centos-release'):
                return 'centos'
        except Exception as e:
            logger.error(f"检测Linux发行版失败: {str(e)}")
        
        return 'unknown'
    
    def create_virtual_environment(self, venv_path: str = 'venv') -> bool:
        """创建Python虚拟环境
        
        Args:
            venv_path (str): 虚拟环境路径
            
        Returns:
            bool: 创建是否成功
        """
        logger.info(f"开始创建虚拟环境: {venv_path}")
        
        try:
            # 检查venv模块是否可用
            import venv
            
            # 创建虚拟环境
            builder = venv.EnvBuilder(with_pip=True)
            builder.create(venv_path)
            
            logger.info(f"虚拟环境创建成功: {venv_path}")
            
            # 打印激活指南
            if sys.platform == 'win32':
                activate_script = os.path.join(venv_path, 'Scripts', 'activate')
                logger.info(f"请运行以下命令激活虚拟环境: {activate_script}")
            else:
                activate_script = os.path.join(venv_path, 'bin', 'activate')
                logger.info(f"请运行以下命令激活虚拟环境: source {activate_script}")
            
            return True
        except ImportError:
            logger.error("venv模块不可用，请安装python3-venv包")
            return False
        except Exception as e:
            logger.error(f"创建虚拟环境失败: {str(e)}")
            return False
    
    def _get_pip_version(self) -> str:
        """获取当前pip版本
        
        Returns:
            str: pip版本号，如果无法获取则返回'unknown'
        """
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', '--version'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip().split()[1]  # 提取版本号
        except Exception as e:
            logger.error(f"获取pip版本失败: {str(e)}")
        return 'unknown'
    
    def _check_installed_package_version(self, package_name: str) -> None:
        """检查已安装包的版本
        
        Args:
            package_name (str): 包名
        """
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'show', package_name],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                # 提取版本信息和安装位置
                for line in result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        version = line.split(':', 1)[1].strip()
                        logger.info(f"已安装的{package_name}版本: {version}")
                    elif line.startswith('Location:'):
                        location = line.split(':', 1)[1].strip()
                        logger.info(f"{package_name}安装位置: {location}")
            else:
                logger.info(f"未检测到已安装的{package_name}包")
        except Exception as e:
            logger.error(f"检查{package_name}版本失败: {str(e)}")
    
    def get_dependency_report(self) -> Dict:
        """生成依赖报告
        
        Returns:
            dict: 依赖报告
        """
        report = {
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            'platform': sys.platform,
            'core_dependencies': {},
            'optional_dependencies': {},
            'system_dependencies': {}
        }
        
        # 收集核心依赖信息
        for import_name, package_name in self.core_dependencies.items():
            is_installed = self.check_results.get('core', {}).get(package_name, False)
            version = 'unknown'
            
            if is_installed:
                try:
                    module = importlib.import_module(import_name)
                    version = getattr(module, '__version__', 'unknown')
                except Exception:
                    pass
            
            report['core_dependencies'][package_name] = {
                'installed': is_installed,
                'version': version
            }
        
        # 收集可选依赖信息
        for import_name, package_name in self.optional_dependencies.items():
            is_installed = self.check_results.get('optional', {}).get(package_name, False)
            version = 'unknown'
            
            if is_installed:
                try:
                    module = importlib.import_module(import_name)
                    version = getattr(module, '__version__', 'unknown')
                except Exception:
                    pass
            
            report['optional_dependencies'][package_name] = {
                'installed': is_installed,
                'version': version
            }
        
        # 收集系统依赖信息
        for tool_name, command_name in self.system_dependencies.items():
            is_available = self.check_results.get('system', {}).get(tool_name, False)
            report['system_dependencies'][tool_name] = {
                'available': is_available,
                'command': command_name
            }
        
        return report