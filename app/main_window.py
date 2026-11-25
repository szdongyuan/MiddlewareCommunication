"""PLC 到希听的简单桥接界面。"""
import json
import queue
import select
import socket
import threading
import time
from pathlib import Path
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMainWindow, QMessageBox,
                             QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from app.service.plc_bridge_service import PlcService
from app.service.log_manager import LogManager
from app.utils import load_config, save_config, PLC_CONFIG_PATH, TCP_CONFIG_PATH
from app.style import STYLESHEET
from app.plc_results import encode_station_results
from app.plc_layout import SN_START_BYTE, TESTER_STATUS_BYTE, RESULTS_BYTE, DB_LAYOUT_END
from app.tcp_messages import encode_station_sn_codes

FIELDS = [
    ('plc_ip', 'PLC IP', ''), ('rack', '机架号 Rack', '0'),
    ('slot', '槽号 Slot', '1'), ('db', 'DB 块号', '1'),
    ('heartbeat_byte', '心跳 INT 字节偏移', '0'), ('command_byte', '指令 INT 字节偏移', '2'),
    ('interval', '轮询间隔（毫秒）', '200'),
    ('a_host', '希听地址', '127.0.0.1'), ('a_port', '希听端口', '9000'),
]
PLC_KEYS = tuple(key for key, _, _ in FIELDS[:7])
TCP_KEYS = tuple(key for key, _, _ in FIELDS[7:])
HEARTBEAT_TIMEOUT_SECONDS = 300


class HeartbeatMonitor:
    def __init__(self, timeout=HEARTBEAT_TIMEOUT_SECONDS):
        self.timeout = timeout
        self.last_value = None
        self.last_change = None

    def observe(self, value, now):
        if value not in (0, 1):
            raise ValueError(f'PLC 心跳值异常: {value}，应为 0 或 1')
        if self.last_change is None or value != self.last_value:
            self.last_value = value
            self.last_change = now
        elif now - self.last_change >= self.timeout:
            raise TimeoutError(f'PLC 心跳超过 {self.timeout} 秒未变化')


class RoundResults:
    """按希听的轮次收集四个工位的完整判定，不混合不同轮次。"""
    def __init__(self):
        self.round_id = None
        self.stations = {}
        self.reported = False

    def add(self, message):
        round_id, station = message.get('round_id'), message.get('station')
        if not isinstance(round_id, str) or not round_id or type(station) is not int or station not in (1, 2, 3, 4):
            return None
        if self.round_id != round_id:
            self.round_id, self.stations, self.reported = round_id, {}, False
        if all(message.get(key) in ('OK', 'NG') for key in ('forward', 'reverse', 'result')):
            self.stations[station] = dict(message)
        if len(self.stations) == 4 and not self.reported:
            self.reported = True
            return [self.stations[i] for i in range(1, 5)]
        return None


def parse_config(values):
    result = dict(values)
    for name in ('rack', 'slot', 'db', 'heartbeat_byte', 'command_byte', 'interval', 'a_port'):
        try:
            result[name] = int(values[name])
        except ValueError:
            raise ValueError(f'{name} 必须填写整数') from None
    if not values['plc_ip'].strip() or not values['a_host'].strip():
        raise ValueError('PLC 和希听地址不能为空')
    if any(result[x] < 0 for x in ('rack', 'slot', 'heartbeat_byte', 'command_byte')) or result['db'] < 1:
        raise ValueError('DB 块号必须大于 0，机架、槽号和字节偏移不能为负数')
    if abs(result['heartbeat_byte'] - result['command_byte']) < 2:
        raise ValueError('心跳和指令的 INT 地址不能重叠')
    if any(result[name] < DB_LAYOUT_END and result[name] + 2 > SN_START_BYTE
           for name in ('heartbeat_byte', 'command_byte')):
        raise ValueError(f'心跳和指令地址不能与 SN、状态或结果区 DBB{SN_START_BYTE}–DBB{DB_LAYOUT_END - 1} 重叠')
    if not 1 <= result['a_port'] <= 65535 or result['interval'] < 50:
        raise ValueError('端口为 1–65535，轮询间隔至少 50 毫秒')
    return result

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PLC 通信桥接')
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / 'resources' / 'ting.ico')))
        self.resize(780, 680)
        self.setMinimumSize(680, 580)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.inputs = {}
        self.closing = False
        self.logger = LogManager.set_log_handler('core')
        try:
            saved = load_config(PLC_KEYS, TCP_KEYS)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, '配置读取失败', str(exc))
            saved = {}
        central = QWidget()
        central.setObjectName('centralWidget')
        self.setCentralWidget(central)
        self.setStyleSheet(STYLESHEET)
        outer = QVBoxLayout(central)
        plc = QGroupBox('PLC（西门子 S7）')
        a = QGroupBox('希听（TCP 服务端）')
        plc_grid, a_grid = QGridLayout(plc), QGridLayout(a)
        outer.addWidget(plc)
        outer.addWidget(a)
        for i, (key, label, default) in enumerate(FIELDS):
            grid = plc_grid if i < 7 else a_grid
            index = i if i < 7 else i - 7
            row, col = divmod(index, 2)
            field = QLineEdit(str(saved.get(key, default)))
            self.inputs[key] = field
            grid.addWidget(QLabel(label), row, col * 2)
            grid.addWidget(field, row, col * 2 + 1)
            grid.setColumnStretch(col * 2 + 1, 1)
        self.plc_save_button = QPushButton('保存 PLC 配置')
        self.plc_save_button.clicked.connect(lambda: self.save(PLC_KEYS, PLC_CONFIG_PATH, 'PLC'))
        plc_grid.addWidget(self.plc_save_button, 4, 0, 1, 4, Qt.AlignLeft)
        self.tcp_save_button = QPushButton('保存希听配置')
        self.tcp_save_button.clicked.connect(lambda: self.save(TCP_KEYS, TCP_CONFIG_PATH, '希听'))
        a_grid.addWidget(self.tcp_save_button, 1, 0, 1, 4, Qt.AlignLeft)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('启动连接和监听')
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton('停止')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        self.status = QLabel('未运行')
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        buttons.addWidget(self.status)
        outer.addLayout(buttons)
        outer.addWidget(QLabel('日志'))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log.customContextMenuRequested.connect(self.show_log_menu)
        outer.addWidget(self.log, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.drain)
        self.timer.start(100)

    def show_log_menu(self, pos):
        menu = self.log.createStandardContextMenu()
        menu.addSeparator()
        menu.addAction('清空日志', self.log.clear)
        menu.exec_(self.log.mapToGlobal(pos))

    def emit(self, kind, text):
        if kind == 'log':
            self.logger.info(text)
        self.events.put((kind, text))

    def save(self, keys, path, name):
        values = {key: self.inputs[key].text().strip() for key in keys}
        try:
            save_config(values, path, keys)
        except OSError as exc:
            QMessageBox.critical(self, '保存失败', str(exc))
            return
        self.log.appendPlainText(time.strftime('%H:%M:%S ') + f'{name} 配置已保存')
        self.logger.info('%s 配置已保存', name)

    def start(self):
        try:
            values = {key: field.text().strip() for key, field in self.inputs.items()}
            config = parse_config(values)
        except ValueError as exc:
            QMessageBox.critical(self, '配置错误', str(exc))
            return
        self.stop_event.clear()
        self.start_button.setEnabled(False)
        self.plc_save_button.setEnabled(False)
        self.tcp_save_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        for field in self.inputs.values():
            field.setEnabled(False)
        self.worker = threading.Thread(target=self.run_bridge, args=(config,), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.stop_button.setEnabled(False)
        self.status.setText('正在停止，等待当前操作结束')

    def closeEvent(self, event):
        if self.worker and self.worker.is_alive():
            self.closing = True
            self.stop()
            event.ignore()
        else:
            event.accept()

    def run_bridge(self, c):
        plc = None
        sock = None
        try:
            self.emit('status', '正在连接 PLC')
            plc = PlcService(c['plc_ip'], c['rack'], c['slot'], c['db'],
                             c['heartbeat_byte'], c['command_byte'])
            plc.connect()
            self.emit('log', 'PLC 已连接')
            if self.stop_event.is_set():
                return
            self.emit('status', 'PLC 已连接；正在连接希听')
            sock = socket.create_connection((c['a_host'], c['a_port']), timeout=5)
            sock.settimeout(5)
            self.emit('log', '希听已连接')
            self.emit('status', 'PLC 已连接；希听已连接；监听中')
            received = bytearray()
            heartbeat_monitor = HeartbeatMonitor()
            round_results = RoundResults()
            phase = 'await_reset'
            test_may_be_running = False
            start_acknowledged = False
            forward_round = None
            forward_stations = set()
            completed_rounds = set()
            while not self.stop_event.is_set():
                heartbeat, command, changed, first = plc.poll_once()
                heartbeat_monitor.observe(heartbeat, time.monotonic())
                if first:
                    self.emit('log', f'PLC 心跳初始值 {heartbeat}，指令初始值 {command}；等待指令变化')
                if changed or (first and command == 12):
                    self.emit('log', f'PLC 指令变为 {command}')
                    if command == 12:
                        if test_may_be_running:
                            plc.write_int(TESTER_STATUS_BYTE, 12)
                            phase = 'alarm'
                            self.emit('log', '测试中收到复位，无法确认希听已停止；已报警')
                        else:
                            plc.write_int(TESTER_STATUS_BYTE, 10)
                            phase = 'ready'
                            round_results = RoundResults()
                            self.emit('log', '复位后 TCP 已连接，测试用就绪：TesterStatus = 10')
                    elif command == 10:
                        if phase not in ('ready', 'complete'):
                            plc.write_int(TESTER_STATUS_BYTE, 12)
                            phase = 'alarm'
                            self.emit('log', '未就绪时收到启动，TesterStatus = 12')
                        else:
                            sn_codes = plc.read_station_sn_codes()
                            plc.write_int(TESTER_STATUS_BYTE, 0)
                            phase = 'running'
                            test_may_be_running = True
                            start_acknowledged = False
                            forward_round = None
                            forward_stations = set()
                            round_results = RoundResults()
                            self.emit('log', '收到启动指令，TesterStatus = 0，向希听发送 true')
                            sock.sendall(b'true\n')
                            sn_message = encode_station_sn_codes(sn_codes)
                            sock.sendall(sn_message)
                    elif command == 11:
                        plc.write_int(TESTER_STATUS_BYTE, 12)
                        phase = 'alarm'
                        self.emit('log', '收到停止指令，但希听停止接口尚未接入；TesterStatus = 12')
                if select.select([sock], [], [], 0)[0]:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise ConnectionError('希听断开连接')
                    received.extend(chunk)
                    while b'\n' in received:
                        line, _, remainder = received.partition(b'\n')
                        received[:] = remainder
                        message = json.loads(line.decode('utf-8'))
                        if isinstance(message, dict) and message.get('type') == 'station_result':
                            self.emit('log', f"工位 {message.get('station')}：正转 {message.get('forward')}，反转 {message.get('reverse')}，总结果 {message.get('result')}")
                            if 'forward_spl' in message or 'reverse_spl' in message:
                                self.emit('log', f"工位 {message.get('station')} 声压级：正转 {message.get('forward_spl') if message.get('forward_spl') is not None else '--'}，反转 {message.get('reverse_spl') if message.get('reverse_spl') is not None else '--'}")
                            if phase == 'running' and start_acknowledged:
                                rid, station = message.get('round_id'), message.get('station')
                                if (isinstance(rid, str) and rid and rid not in completed_rounds
                                        and type(station) is int and station in (1, 2, 3, 4)
                                        and message.get('forward') in ('OK', 'NG')
                                        and message.get('reverse') == '--'):
                                    if forward_round is None:
                                        forward_round = rid
                                    if rid == forward_round:
                                        forward_stations.add(station)
                                if rid == forward_round and len(forward_stations) == 4:
                                    complete = round_results.add(message)
                                    if complete is not None:
                                        try:
                                            data = encode_station_results(complete)
                                        except ValueError as exc:
                                            round_results.reported = False
                                            self.emit('log', f'结果尚不能写入 PLC：{exc}')
                                        else:
                                            plc.write_results(RESULTS_BYTE, data)
                                            plc.write_int(TESTER_STATUS_BYTE, 11)
                                            completed_rounds.add(rid)
                                            phase = 'complete'
                                            test_may_be_running = False
                                            self.emit('log', '四工位正反转数据已写入 PLC，TesterStatus = 11')
                        else:
                            self.emit('log', f'希听回复: {json.dumps(message, ensure_ascii=False)}')
                            if isinstance(message, dict) and message.get('success') is False:
                                plc.write_int(TESTER_STATUS_BYTE, 12)
                                phase = 'alarm'
                                self.emit('log', '希听拒绝指令，TesterStatus = 12')
                            elif isinstance(message, dict) and message.get('success') is True and phase == 'running':
                                start_acknowledged = True
                    if len(received) > 65536:
                        raise ValueError('希听响应过长')
                self.stop_event.wait(c['interval'] / 1000)
        except Exception as exc:
            self.logger.exception('通信中断')
            if plc is not None and plc.client is not None:
                try:
                    plc.write_int(TESTER_STATUS_BYTE, 12)
                    self.emit('log', '已尝试写入报警状态 TesterStatus = 12')
                except Exception as alarm_exc:
                    self.emit('log', f'无法写入 PLC 报警状态: {alarm_exc}')
            self.emit('log', f'通信中断: {exc}。请检查后重新启动；本次请求不会自动重试。')
        finally:
            if sock:
                sock.close()
            if plc:
                try:
                    plc.disconnect()
                except Exception:
                    pass
            self.emit('done', '已停止')

    def drain(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == 'log':
                    self.log.appendPlainText(time.strftime('%H:%M:%S ') + text)
                elif kind == 'status':
                    self.status.setText(text)
                elif kind == 'done':
                    self.status.setText(text)
                    self.start_button.setEnabled(True)
                    self.plc_save_button.setEnabled(True)
                    self.tcp_save_button.setEnabled(True)
                    self.stop_button.setEnabled(False)
                    for field in self.inputs.values():
                        field.setEnabled(True)
                    if self.closing:
                        QTimer.singleShot(100, self.close)
        except queue.Empty:
            pass

