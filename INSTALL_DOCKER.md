# 安装Docker指南

根据当前系统检查，Docker命令不可用。要继续构建和测试Docker镜像，请按照以下步骤安装Docker：

## macOS安装步骤
1. 访问Docker官方网站下载[Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. 打开下载的.dmg文件并将Docker图标拖到Applications文件夹
3. 从Applications文件夹启动Docker
4. 完成初始设置和登录
5. 打开终端，运行`docker --version`验证安装成功

## 验证安装
安装完成后，在终端运行以下命令验证Docker是否正常工作：
```bash
docker --version
docker run hello-world
```

## 重新构建镜像
Docker安装完成后，可以再次运行以下命令构建镜像：
```bash
docker build -t plexautoscan:test .
```

## 注意事项
- 确保您的系统满足Docker的最低要求
- 安装过程中可能需要管理员权限
- 如果您使用的是Apple Silicon芯片(M1/M2等)，请下载适配ARM架构的Docker版本
- 首次运行Docker可能需要一些时间初始化