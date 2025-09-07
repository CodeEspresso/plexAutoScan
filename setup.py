#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PlexAutoScan 安装配置文件
"""

import os
from setuptools import setup, find_packages

# 读取README文件内容作为项目描述
with open(os.path.join(os.path.dirname(__file__), 'README.md'), 'r', encoding='utf-8') as f:
    long_description = f.read()

# 读取requirements.txt文件内容作为依赖列表
dependencies = []
requirements_file = os.path.join(os.path.dirname(__file__), 'requirements.txt')
if os.path.exists(requirements_file):
    with open(requirements_file, 'r', encoding='utf-8') as f:
        dependencies = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name='plex-autoscan',
    version='1.0.0',
    description='自动扫描和更新Plex媒体库的工具',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='PlexAutoScan Team',
    author_email='',
    url='',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    install_requires=dependencies,
    entry_points={
        'console_scripts': [
            'plex-autoscan=main:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Topic :: Multimedia :: Video',
        'Topic :: Utilities',
    ],
    python_requires='>=3.8',
)