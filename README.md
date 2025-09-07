# Plex Auto Scan 本地环境配置指南

# PlexAutoScan

自动扫描和更新Plex媒体库的工具，可监控目录变化并触发Plex媒体服务器进行扫描。

> **注意**：此版本已从Bash完全迁移到Python

## 功能特性

- 监控媒体目录变化并生成目录快照
- 自动触发Plex媒体服务器进行扫描
- 支持Docker环境下的路径映射
- 跨平台兼容（Windows、macOS、Linux）
- 支持配置文件和环境变量
- 完整的日志系统
- 依赖自动管理

## 系统要求

- Python 3.8+ （推荐3.10+）
- Plex媒体服务器
- 可选：Docker环境

## 安装

### 方法1：使用pip安装

```bash
# 从源代码安装
cd /path/to/plexAutoScan
pip install -e .
```

### 方法2：直接运行

```bash
cd /path/to/plexAutoScan/src
python main.py
```

### 安装依赖

```bash
# 安装所有依赖
pip install -r requirements.txt

# 或者使用程序自带的依赖管理功能
python src/main.py --install-deps
```

## 配置

### 配置文件

程序会按以下顺序查找配置文件：
1. 命令行参数指定的路径
2. 当前目录下的`config.json`或`config.sh`
3. `~/.config/plex-autoscan/config.json`
4. 环境变量

### 主要配置项

```json
{
  "PLEX_URL": "http://localhost:32400",
  "PLEX_TOKEN": "YOUR_PLEX_TOKEN",
  "MOUNT_PATHS": {
    "/local/path": "/container/path"
  },
  "MONITORED_DIRECTORIES": [
    "/path/to/movies",
    "/path/to/tvshows"
  ],
  "SNAPSHOT_DIR": "/path/to/snapshots",
  "CACHE_DIR": "/path/to/cache",
  "SNAPSHOT_RETENTION_DAYS": 7,
  "MAX_SNAPSHOTS": 10,
  "LOG_LEVEL": "INFO",
  "LOG_FILE": "plex-autoscan.log",
  "ENABLE_PLEX": true,
  "WAIT_FOR_SCAN_COMPLETION": false,
  "SCAN_TIMEOUT": 300,
  "TEST_ENV": false
}
```

### 环境变量

所有配置项都可以通过环境变量设置，环境变量名格式为`PLEX_AUTOSCAN_`+配置项名称的大写形式。

例如：`PLEX_AUTOSCAN_PLEX_URL=http://localhost:32400`

## 使用方法

### 基本使用

```bash
# 基本运行
python src/main.py

# 指定配置文件
python src/main.py -c /path/to/config.json

# 启用调试模式
python src/main.py -d

# 仅验证配置文件
python src/main.py --validate-config

# 安装缺失的依赖
python src/main.py --install-deps
```

### 命令行参数

- `-c, --config`: 指定配置文件路径
- `-d, --debug`: 启用调试模式，输出更详细的日志
- `--validate-config`: 仅验证配置文件是否有效
- `--install-deps`: 安装缺失的Python依赖

## Docker使用

### 构建镜像

```bash
docker build -t plex-autoscan .
```

### 运行容器

```bash
docker run -d \
  --name plex-autoscan \
  -v /path/to/config.json:/app/config.json \
  -v /path/to/media:/media \
  -v /path/to/snapshots:/app/snapshots \
  -e PLEX_URL=http://plex:32400 \
  -e PLEX_TOKEN=YOUR_PLEX_TOKEN \
  plex-autoscan
```

## 项目结构

```
├── src/                  # 源代码目录
│   ├── main.py           # 主入口文件
│   ├── dependencies.py   # 依赖管理模块
│   ├── utils/            # 工具模块
│   │   ├── config.py     # 配置管理
│   │   ├── logger.py     # 日志系统
│   │   ├── path_utils.py # 路径处理工具
│   │   └── snapshot.py   # 快照管理
│   └── plex/             # Plex集成模块
│       ├── api.py        # Plex API交互
│       └── library.py    # 媒体库管理
├── requirements.txt      # Python依赖列表
├── setup.py              # 安装配置文件
└── README.md             # 项目文档
```

## 常见问题

### 1. 如何获取Plex Token？

请参考[Plex官方文档](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)获取Plex Token。

### 2. Docker环境下的路径映射问题

在Docker环境中，请确保正确设置`MOUNT_PATHS`配置，将宿主机路径映射到容器内的路径。

### 3. 如何检查日志？

默认情况下，日志会输出到控制台。您可以通过`LOG_FILE`配置项指定日志文件路径。

## 开发说明

### 代码风格

项目遵循PEP 8代码风格指南。建议使用以下工具进行代码检查：

- `flake8`：检查代码风格
- `black`：自动格式化代码
- `mypy`：类型检查

### 贡献指南

1. Fork项目仓库
2. 创建功能分支
3. 提交代码更改
4. 提交Pull Request

## 许可证

本项目采用MIT许可证。详情请见LICENSE文件。