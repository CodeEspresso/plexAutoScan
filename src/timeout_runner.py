#!/usr/bin/env python3
import subprocess
import sys
import time
import os

# 超时运行器：执行命令并在超时时终止

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: $PYTHON_EXEC timeout_runner.py <timeout_seconds> <command> [args...]", file=sys.stderr)
        sys.exit(1)

    timeout = int(sys.argv[1])
    command = sys.argv[2:]

    # 启动进程
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    start_time = time.time()

    # 等待进程完成或超时
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        print(f"命令超时（{timeout}秒）", file=sys.stderr)
        sys.exit(124)

    # 输出结果
    print(stdout.decode(), end='')
    print(stderr.decode(), end='', file=sys.stderr)

    # 返回命令的退出码
    sys.exit(proc.returncode)