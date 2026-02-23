FROM library/alpine:3.19

# 安装所有必要依赖，包括SMB支持、pip3和时区包
# 使用阿里云镜像源加速Alpine包安装
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories && \
    apk update && \
    apk add --no-cache \
        bash \
        curl \
        python3 \
        py3-pip \
        libxml2-utils \
        samba-client \
        coreutils \
        util-linux \
        tzdata \
        # 添加pysmb所需的额外系统依赖
        krb5-libs \
        libgcc \
        libstdc++ && \
    # 安装psutil构建依赖
    apk add --no-cache --virtual=build-deps \
        gcc \
        python3-dev \
        musl-dev \
        linux-headers \
        krb5-dev && \
    ln -sf python3 /usr/bin/python && \
    ln -sf pip3 /usr/bin/pip && \
    # 设置上海时区
    ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

# 设置工作目录
WORKDIR /data

# 复制依赖文件
COPY src/requirements.txt /data/

# 创建Python虚拟环境并安装依赖
RUN python3 -m venv /venv && \
    /venv/bin/pip install --upgrade pip setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    # 安装所有依赖，统一使用清华源
    /venv/bin/pip install -r /data/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制依赖验证脚本
COPY src/verify_dependencies.py /tmp/verify_dependencies.py

# 设置脚本执行权限
RUN chmod +x /tmp/verify_dependencies.py

# 验证依赖安装 - 使用单独的Python脚本进行验证
RUN /venv/bin/python /tmp/verify_dependencies.py

# 添加简化的健康检查，不强制要求pysmb导入成功
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
CMD ["/venv/bin/python", "/tmp/verify_dependencies.py"]

# 设置环境变量，确保使用虚拟环境
ENV PATH="/venv/bin:$PATH"
ENV VIRTUAL_ENV="/venv"

# 清理缓存，减小镜像体积
RUN rm -rf /var/cache/apk/*

# 复制项目文件
COPY . /data/

# 复制并设置entrypoint脚本
COPY src/entrypoint.sh /entrypoint.sh

# 赋予执行权限 - 针对飞牛OS优化权限设置
RUN chmod +x /data/src/healthcheck.py && \
    chmod +x /data/src/entrypoint.sh && \
    chmod +x /entrypoint.sh && \
    chmod -R 755 /data && \
    # 确保关键目录有适当的写权限
    mkdir -p /data/snapshots /data/logs /data/output && \
    chmod -R 777 /data/snapshots /data/logs /data/output

# 设置入口点和默认命令
ENTRYPOINT ["/entrypoint.sh"]
CMD []
