"""希听模拟端：供 PLC 通信桥连接，所有测试结果均为随机数据。

运行：python client.py [--host 0.0.0.0] [--port 9000]
先启动本程序，再在桥梁中填写本机 IP 和端口并连接。
"""
import argparse
import json
import random
import socket
import uuid


def send_json(conn, data):
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    conn.sendall((text + '\n').encode('utf-8'))
    print('发送:', text, flush=True)


def simulate(conn, codes):
    round_id = uuid.uuid4().hex
    results = []
    for station in range(1, 5):
        forward = random.choice(['OK', 'NG'])
        reverse = random.choice(['OK', 'NG'])
        results.append({'type': 'station_result', 'round_id': round_id,
                        'station': station, 'forward': forward, 'reverse': reverse,
                        'result': 'OK' if forward == reverse == 'OK' else 'NG',
                        'forward_spl': round(random.uniform(45, 85), 2),
                        'reverse_spl': round(random.uniform(45, 85), 2)})
    print('模拟轮次:', round_id, 'SN:', codes, flush=True)
    # 桥梁要求先收到全部四个正转事件，然后才能处理完整结果。
    for result in results:
        send_json(conn, {**result, 'reverse': '--', 'result': '--', 'reverse_spl': None})
    for result in results:
        send_json(conn, result)


def handle(conn):
    pending = False
    with conn.makefile('rb') as stream:
        while True:
            line = stream.readline(65537)
            if not line:
                return
            if len(line) > 65536 or not line.endswith(b'\n'):
                raise ValueError('消息过长或缺少换行')
            text = line.decode('utf-8').strip()
            print('收到:', text, flush=True)
            if text == 'true':
                pending = True
                send_json(conn, {'success': True})
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                print('忽略无法解析的消息', flush=True)
                continue
            if isinstance(message, dict) and message.get('type') == 'station_sn_codes':
                codes = message.get('sn_codes')
                if pending and isinstance(codes, list) and len(codes) == 4 and all(isinstance(x, str) for x in codes):
                    pending = False
                    simulate(conn, codes)
                else:
                    send_json(conn, {'success': False, 'message': '启动状态或四工位 SN 无效'})


def main():
    parser = argparse.ArgumentParser(description='模拟希听 TCP 服务，返回随机工位结果')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址，默认所有网卡')
    parser.add_argument('--port', type=int, default=9000, help='监听端口，默认 9000')
    args = parser.parse_args()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(1)
        print(f'模拟希听正在监听 {args.host}:{args.port}，等待桥梁连接。Ctrl+C 退出。', flush=True)
        while True:
            conn, address = server.accept()
            print('桥梁已连接:', address, flush=True)
            try:
                with conn:
                    handle(conn)
            except (OSError, UnicodeError, ValueError) as error:
                print('连接结束:', error, flush=True)
            print('等待下一个连接', flush=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n模拟端已停止')
