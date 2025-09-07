# Dockerfile 优化说明

## 更改内容

我对Dockerfile进行了以下关键优化：

1. **构建依赖分组管理**：
   - 将`gcc`、`python3-dev`、`musl-dev`和`linux-headers`这些仅用于编译安装psutil的依赖项标记为临时构建依赖(`--virtual=build-deps`)
   - 这样可以清晰地区分运行时依赖和构建时依赖

2. **添加依赖清理步骤**：
   - 在成功安装Python依赖后，通过`apk del --purge build-deps`命令删除临时构建依赖
   - 这有助于减小最终Docker镜像的大小

3. **优化依赖结构**：
   - 保留了所有必要的运行时依赖(bash, curl, python3等)
   - 仅将编译psutil所需的特定依赖项作为临时依赖添加

## 优化原因

1. **减小镜像体积**：构建依赖通常较大，且在运行时不需要，删除它们可以显著减小镜像大小

2. **提高安全性**：减少不必要的包可以降低潜在的安全风险

3. **依赖清晰化**：明确区分运行时依赖和构建时依赖，提高Dockerfile的可维护性

## 验证方法

当Docker安装完成后，可以通过以下步骤验证优化效果：

1. 构建镜像：
   ```bash
   docker build -t plexautoscan:test .
   ```

2. 查看镜像大小：
   ```bash
   docker images plexautoscan:test
   ```

3. 与优化前的镜像大小对比，应该会有明显减小

## 注意事项

- `--virtual=build-deps`参数将一组依赖标记为一个虚拟包，便于后续一次性删除
- `--purge`参数确保删除依赖的配置文件和数据，进一步减小体积
- 这些更改不会影响应用程序的功能，因为psutil在安装完成后已经编译为二进制文件，不再需要构建依赖
- 如果将来需要添加其他需要编译的Python包，可以将它们的构建依赖也添加到`build-deps`组中