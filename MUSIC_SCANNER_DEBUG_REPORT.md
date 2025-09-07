# 音乐文件扫描问题调试报告

## 问题概述
根据用户反馈，Plex音乐库中大部分音乐已正常扫描，但仍有个别文件入库失败。通过创建专门的调试工具和测试环境，我们发现了问题并提供了解决方案。

## 调试过程与发现

### 1. 环境配置验证
- 验证了`config.env`文件中的路径配置，发现生产环境路径`/vol02/CloudDrive/WebDAV/音乐`无法访问（只读文件系统）
- 切换到测试环境，使用路径`/Volumes/PSSD/项目/plexAutoScan/test_files/音乐`进行调试

### 2. 测试文件创建
- 创建了`add_test_music.sh`脚本，在测试环境中生成了3个示例音乐文件
- 文件路径：
  ```
  /Volumes/PSSD/项目/plexAutoScan/test_files/音乐/示例艺术家/示例专辑/示例歌曲1.mp3
  /Volumes/PSSD/项目/plexAutoScan/test_files/音乐/示例艺术家/示例专辑/示例歌曲2.mp3
  /Volumes/PSSD/项目/plexAutoScan/test_files/音乐/示例艺术家/示例专辑/示例歌曲3.mp3
  ```

### 3. 问题检测
运行`debug_music_files.sh`脚本后发现：
- Plex音乐媒体库ID: 12
- 本地测试目录中存在3个音乐文件
- Plex媒体库中未找到这些文件（未入库）
- 文件格式正确（ID3标签已添加）
- 文件权限正常（可读）

### 4. 可能的原因分析
1. Plex媒体库路径映射问题
2. Plex扫描服务未正确识别新增文件
3. 音乐文件元数据不完整或格式不兼容

## 解决方案

### 1. 手动触发扫描
脚本已尝试手动触发Plex扫描未入库文件：
```
http://192.168.31.38:32400/library/sections/12/refresh?X-Plex-Token=1S3fZe4myyPqVzdGyuU9&path=%2FVolumes%2FPSSD%2F%E9%A1%B9%E7%9B%AE%2FplexAutoScan%2Ftest_files%2F%E9%9F%B3%E4%B9%90%2F%E7%A4%BA%E4%BE%8B%E8%89%BA%E6%9C%AF%E5%AE%B6%2F%E7%A4%BA%E4%BE%8B%E4%B8%93%E8%BE%91%2F%E7%A4%BA%E4%BE%8B%E6%AD%8C%E6%9B%B21.mp3
```

### 2. 检查Plex媒体库配置
1. 确认Plex媒体库路径设置正确
2. 验证媒体库扫描间隔设置
3. 检查是否有扫描限制或过滤器

### 3. 修复路径映射（针对生产环境）
1. 确保`/vol02/CloudDrive/WebDAV/音乐`路径可写
2. 如果路径不可访问，考虑修改`PROD_TARGET_PATH_PREFIX`为可访问的路径
3. 更新`MOUNT_PATHS`配置，确保包含音乐目录

## 后续操作建议
1. 等待几分钟，让Plex完成手动扫描
2. 运行`debug_music_files.sh`脚本再次检查：
   ```bash
   bash /Volumes/PSSD/项目/plexAutoScan/debug_music_files.sh
   ```
3. 查看详细日志：
   ```bash
   cat /Volumes/PSSD/项目/plexAutoScan/temp/music_debug/debug.log
   ```
4. 如果问题仍然存在，考虑重启Plex服务
5. 对于生产环境，确保音乐目录具有正确的权限和可访问性

## 工具列表
- `add_test_music.sh`: 添加测试音乐文件并更新缓存
- `debug_music_files.sh`: 排查音乐文件入库问题
- `MUSIC_LIBRARY_FIX.md`: 音乐库类型修复文档
- `MUSIC_SCANNER_DEBUG_REPORT.md`: 本调试报告

---
生成时间: $(date '+%Y-%m-%d %H:%M:%S')