#!/usr/bin/env python3
import http.server
import socketserver
import os
import sys

class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            # 检查主脚本是否在运行
            with open('/proc/self/status', 'r') as f:
                status = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=8090):
    server_address = ('', port)
    httpd = socketserver.TCPServer(server_address, HealthCheckHandler)
    print(f'健康检查服务器启动在端口 {port}')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('健康检查服务器关闭')
        httpd.server_close()

if __name__ == '__main__':
    run_server()