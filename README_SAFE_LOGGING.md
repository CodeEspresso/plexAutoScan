# 安全日志系统使用指南

## 问题背景

在生产环境中，我们遇到了两个主要问题：
1. 无法导入健壮日志模块（`No module named 'src'`）
2. 日志缓冲区分离错误（`ValueError: underlying buffer has been detached`）

## 解决方案

我们创建了一个健壮的日志包装器 `robust_logger_wrapper.py`，它提供了以下功能：

1. **智能导入机制**：自动添加项目根目录到 Python 路径，确保在任何环境下都能正确导入安全日志模块
2. **优雅降级处理**：当安全日志模块无法导入时，提供增强的基本日志配置
3. **缓冲区分离检测与恢复**：主动检测缓冲区分离状态并尝试重置流
4. **多重日志保障**：当标准输出失败时，自动尝试写入日志文件

## 使用方法

### 基本使用

```python
# 导入日志包装器
import src.robust_logger_wrapper as logging_wrapper

# 设置日志配置
logger = logging_wrapper.setup_robust_logging('app.log')

# 使用日志
logger.debug('这是一条调试日志')
logger.info('这是一条信息日志')
logger.warning('这是一条警告日志')
logger.error('这是一条错误日志')
```

### 在脚本中使用

对于项目中的脚本，建议在开头添加以下代码：

```python
# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入并设置日志
import src.robust_logger_wrapper as logging_wrapper
logger = logging_wrapper.setup_robust_logging('app.log')
```

## 实现细节

### 1. 智能导入机制

```python
# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # 尝试导入健壮日志模块
from src.robust_logger import setup_robust_logging, RobustStreamHandler
ROBUST_LOGGING_AVAILABLE = True
except ImportError as e:
    # 导入失败，使用基本日志配置
ROBUST_LOGGING_AVAILABLE = False
    print(f"[WARNING] 无法导入安全日志模块: {e}，使用增强的基本日志配置")
```

### 2. 缓冲区分离处理

```python
except ValueError as e:
    if 'underlying buffer has been detached' in str(e):
        # 尝试重置流
        try:
            self.stream = open(sys.stdout.fileno(), 'w', encoding='utf-8') if hasattr(sys.stdout, 'fileno') else sys.stdout
            super().emit(record)
        except Exception as reset_e:
            # 重置失败，尝试写入文件
            self._write_to_file(record, f'Buffer detached (reset failed: {reset_e})')
```

## 测试

我们提供了 `test_production_environment.py` 脚本，用于模拟生产环境中的各种场景：

1. 模拟无法导入 src 模块的情况
2. 测试中文路径日志记录
3. 模拟缓冲区分离错误并验证恢复机制

运行测试：

```bash
python3 test_production_environment.py
```

查看测试结果：

```bash
tail -n 30 test_production.log
```

## 注意事项

1. 确保在生产环境中正确配置 Python 路径
2. 对于长期运行的服务，建议定期检查日志文件大小
3. 在容器化环境中，确保日志目录可写
4. 避免在日志中记录敏感信息

## 版本历史

- v1.0: 初始实现，提供基本的缓冲区分离检测与恢复
- v1.1: 增强导入机制，添加项目根目录自动配置
- v1.2: 完善降级处理，提供增强的基本日志配置