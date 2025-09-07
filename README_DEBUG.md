# Plex媒体提取器调试日志控制

本项目提供了灵活的调试日志控制选项，可以根据需要启用或禁用不同类型的调试信息。

## 环境变量控制

### 1. 全局调试模式 (DEBUG)
- 控制所有调试日志的开关
- 默认值: `0` (禁用)
- 取值:
  - `1`: 启用所有调试日志
  - `0`: 禁用所有调试日志

### 2. 路径提取调试模式 (DEBUG_PATH_EXTRACTION)
- 专门控制媒体文件路径提取的调试日志
- 默认值: 与 `DEBUG` 相同
- 取值:
  - `1`: 启用路径提取调试日志
  - `0`: 禁用路径提取调试日志

## 使用示例

### 启用所有调试日志
```bash
export DEBUG=1
python3 src/plex/media_extractor.py extract_paths < input.xml
```

### 启用常规调试但禁用路径调试
```bash
export DEBUG=1
export DEBUG_PATH_EXTRACTION=0
python3 src/plex/media_extractor.py extract_paths < input.xml
```

### 禁用常规调试但启用路径调试
```bash
export DEBUG=0
export DEBUG_PATH_EXTRACTION=1
python3 src/plex/media_extractor.py extract_paths < input.xml
```

### 禁用所有调试日志
```bash
export DEBUG=0
python3 src/plex/media_extractor.py extract_paths < input.xml
```

## 日志说明

- 当 `DEBUG=1` 时，会显示以下调试信息:
  - XML响应的前1000字符和后100字符
  - XML总长度
  - XML保存路径
  - 找到的Part标签匹配数量
  - 提取到的媒体文件路径数量

- 当 `DEBUG_PATH_EXTRACTION=1` 时，会额外显示:
  - 每个提取到的文件路径

## 在Docker中使用

如果您在Docker环境中运行，可以在Docker Compose文件或容器启动命令中设置这些环境变量。例如:

```yaml
environment:
  - DEBUG=0
  - DEBUG_PATH_EXTRACTION=1
```

或者在启动容器时:

```bash
docker run -e DEBUG=0 -e DEBUG_PATH_EXTRACTION=1 your-image-name
```