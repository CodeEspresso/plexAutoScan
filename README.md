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
2. `/data/config.env`（Docker容器内路径）
3. 当前目录下的`config.env`
4. 环境变量

### 主要配置项

使用`.env`格式的配置文件，示例配置：

```bash
# 必需配置项
MOUNT_PATHS="/vol02/CloudDrive/WebDAV/电影/动画电影 /vol02/CloudDrive/WebDAV/电影/日韩电影"  # 监控目录列表，空格分隔
PLEX_URL="http://localhost:32400"  # Plex服务器URL
PLEX_TOKEN="your_plex_token_here"  # Plex访问令牌

# 可选配置项
EXCLUDE_PATHS=""  # 排除目录列表，空格分隔
DEBUG=0  # 调试模式 (0=关闭, 1=启用)
TEST_ENV=0  # 测试环境 (0=关闭, 1=启用)
ENABLE_PLEX=1  # 启用Plex集成 (0=关闭, 1=启用)

# 文件大小阈值配置
# MIN_FILE_SIZE=209715200  # 最小文件大小阈值 (200MB)
# MIN_FILE_SIZE_MB=200     # 最小文件大小阈值 (MB)
# SKIP_LARGE_FILES=1       # 是否跳过大型文件 (1=是)
# LARGE_FILE_THRESHOLD=104857600  # 大型文件阈值 (100MB)

# SMB优化参数
# SMB_SCAN_DELAY=2         # 目录扫描间隔 (秒)
# MAX_FILES_PER_SCAN=1000  # 单次扫描最大文件数

# 日志配置
# LOG_LEVEL=INFO           # 日志级别：DEBUG, INFO, WARNING, ERROR
# LOG_FILE=plex-autoscan.log  # 日志文件路径

# Docker环境特定配置
# DOCKER_ENV=1             # Docker环境标识 (1=启用)
# LOCAL_PATH_PREFIX=/vol02/CloudDrive/WebDAV  # 本地路径前缀
# PROD_TARGET_PATH_PREFIX=/vol02/CloudDrive/WebDAV  # 生产环境目标路径前缀
```

### 环境变量

所有配置项都可以通过环境变量直接设置，环境变量名与配置文件中的变量名一致。

例如：
```bash
export PLEX_URL=http://localhost:32400
export PLEX_TOKEN=YOUR_PLEX_TOKEN
export MOUNT_PATHS="/path/to/movies /path/to/tvshows"
```

## 使用方法

### 基本使用

```bash
# 基本运行
python src/main.py

# 指定配置文件
python src/main.py -c /path/to/config.env

# 启用调试模式
python src/main.py -d

# 仅验证配置文件
python src/main.py --validate-config

# 安装缺失的依赖
python src/main.py --install-deps
```

### 命令行参数

- `-c, --config`: 指定配置文件路径（支持.env格式）
- `-d, --debug`: 启用调试模式，输出更详细的日志
- `--validate-config`: 仅验证配置文件是否有效
- `--install-deps`: 安装缺失的Python依赖

## Docker使用

### 方法1：使用Docker Compose（推荐）

#### 步骤1：克隆项目

```bash
git clone https://github.com/yourusername/plexAutoScan.git
cd plexAutoScan
```

#### 步骤2：配置文件

复制配置文件示例并修改：

```bash
cp config.env.example config.env
```

编辑`config.env`文件，设置必要的配置项：

```bash
# 必需配置项
MOUNT_PATHS="/vol02/CloudDrive/WebDAV/电影/动画电影 /vol02/CloudDrive/WebDAV/电影/日韩电影"  # 监控目录列表，空格分隔
PLEX_URL="http://localhost:32400"  # Plex服务器URL
PLEX_TOKEN="your_plex_token_here"  # Plex访问令牌

# 可选配置项
DEBUG=0  # 调试模式 (0=关闭, 1=启用)
# 其他配置项...
```

#### 步骤3：自定义docker-compose.yml（可选）

根据您的环境修改`docker-compose.yml`文件，特别是挂载路径和网络设置：

```yaml
services:
  plex-auto-scan:
    build: .
    image: plex-auto-scan:latest
    container_name: plex-auto-scan
    restart: unless-stopped
    volumes:
      - ./config.env:/data/config.env
      - ./data/cache:/data/cache
      - ./data/snapshots:/data/snapshots
      - /vol02/CloudDrive/WebDAV:/vol02/CloudDrive/WebDAV:ro  # 替换为实际的媒体库路径
    environment:
      - TZ=Asia/Shanghai
      - DOCKER_ENV=1
      - DEBUG=0
      - LOCAL_PATH_PREFIX=/vol02/CloudDrive/WebDAV
      - PROD_TARGET_PATH_PREFIX=/vol02/CloudDrive/WebDAV
    network_mode: host  # 针对飞牛OS优化，避免网络权限问题
    # 其他配置项...
```

#### 步骤4：启动服务

```bash
docker compose up -d --build
```

#### 步骤5：访问和验证

服务将在后台运行，您可以通过以下方式验证：

```bash
# 查看容器状态
docker compose ps

# 查看日志
docker compose logs -f

# 检查健康状态
docker compose exec plex-auto-scan curl localhost:8090/health
```

### 方法2：使用Docker命令行

#### 构建镜像

```bash
docker build -t plex-autoscan .
```

#### 运行容器

```bash
docker run -d \
  --name plex-autoscan \
  -v ./config.env:/data/config.env \
  -v ./data/cache:/data/cache \
  -v ./data/snapshots:/data/snapshots \
  -v /vol02/CloudDrive/WebDAV:/vol02/CloudDrive/WebDAV:ro \
  -e TZ=Asia/Shanghai \
  -e DOCKER_ENV=1 \
  -e PLEX_URL=http://localhost:32400 \
  -e PLEX_TOKEN=YOUR_PLEX_TOKEN \
  --network host \
  plex-autoscan
```

### 方法3：使用预构建镜像

```bash
docker run -d \
  --name plex-autoscan \
  -v ./config.env:/data/config.env \
  -v ./data/cache:/data/cache \
  -v ./data/snapshots:/data/snapshots \
  -v /vol02/CloudDrive/WebDAV:/vol02/CloudDrive/WebDAV:ro \
  -e TZ=Asia/Shanghai \
  -e DOCKER_ENV=1 \
  --network host \
  yourusername/plex-autoscan:latest
```

## 项目结构

```
├── src/                  # 源代码目录
│   ├── main.py           # 主入口文件
│   ├── compare.py        # 比较功能模块
│   ├── dependencies.py   # 依赖管理
│   ├── file_utils.py     # 文件操作工具
│   ├── healthcheck.py    # 健康检查
│   ├── library_utils.py  # 媒体库工具
│   ├── path_mapping.py   # 路径映射
│   ├── snapshot_utils.py # 快照管理
│   ├── smb_api.py        # SMB API
│   ├── utils/            # 工具类目录
│   │   ├── config.py     # 配置管理
│   │   ├── path_utils.py # 路径处理工具
│   │   └── ...
│   ├── plex/             # Plex相关功能
│   └── ...
├── data/                 # 数据目录
│   ├── cache/            # 缓存文件
│   └── snapshots/        # 快照文件
├── docker-compose.yml    # Docker Compose配置
├── Dockerfile            # Docker构建文件
├── config.env.example    # 配置文件示例
├── requirements.txt      # Python依赖
├── setup.py              # 安装配置文件
└── README.md             # 项目说明文档
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