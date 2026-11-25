"""不依赖界面或事件总线的西门子 S7 通信服务。"""
import snap7
import snap7.util
from app.service.log_manager import LogManager
from app.plc_layout import SN_START_BYTE, SN_FIELD_SIZE, SN_COUNT, SN_CAPACITY, RESULTS_SIZE


class PlcService:
    """由调用方在线程内依次使用；断线或读写错误交由调用方处理。"""

    def __init__(self, ip, rack, slot, db_number, heartbeat_byte, command_byte):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.db_number = db_number
        self.heartbeat_byte = heartbeat_byte
        self.command_byte = command_byte
        self.client = None
        self._last_value = None
        self.logger = LogManager.set_log_handler('core')

    def connect(self):
        if self.client is not None:
            return
        self.logger.info('连接 PLC: ip=%s rack=%s slot=%s DB%s', self.ip, self.rack, self.slot, self.db_number)
        client = snap7.client.Client()
        try:
            client.connect(self.ip, self.rack, self.slot)
        except Exception:
            self.logger.exception('PLC 连接失败')
            client.destroy()
            raise
        self.client = client
        self._last_value = None
        self.logger.info('PLC 连接成功: %s', self.ip)

    def disconnect(self):
        client, self.client = self.client, None
        self._last_value = None
        if client is not None:
            try:
                client.disconnect()
                self.logger.info('PLC 已断开: %s', self.ip)
            except Exception:
                self.logger.exception('PLC 断开失败: %s', self.ip)
                raise
            finally:
                client.destroy()

    def _connected_client(self):
        if self.client is None:
            raise RuntimeError('PLC 尚未连接')
        return self.client

    def poll_once(self):
        """读取心跳及命令；仅在命令变化时报告新命令。"""
        try:
            heartbeat = snap7.util.get_int(self._connected_client().db_read(self.db_number, self.heartbeat_byte, 2), 0)
            value = snap7.util.get_int(self._connected_client().db_read(self.db_number, self.command_byte, 2), 0)
        except Exception:
            self.logger.exception('读取 PLC 心跳或指令失败: DB%s', self.db_number)
            raise
        first = self._last_value is None
        changed = not first and self._last_value != value
        self._last_value = value
        return heartbeat, value, changed, first

    def read_real(self, byte_offset):
        try:
            data = self._connected_client().db_read(self.db_number, byte_offset, 4)
            value = snap7.util.get_real(data, 0)
        except Exception:
            self.logger.exception('读取 PLC REAL 失败: DB%s DBD%s', self.db_number, byte_offset)
            raise
        self.logger.info('读取 PLC REAL: DB%s DBD%s = %s', self.db_number, byte_offset, value)
        return value

    def read_station_sn_codes(self):
        """读取四个标准 S7 STRING[30]，拒绝格式错误的数据。"""
        data = self._connected_client().db_read(self.db_number, SN_START_BYTE, SN_FIELD_SIZE * SN_COUNT)
        if len(data) != SN_FIELD_SIZE * SN_COUNT:
            raise ValueError('PLC SN 码数据长度不正确')
        codes = []
        for index in range(SN_COUNT):
            field = data[index * SN_FIELD_SIZE:(index + 1) * SN_FIELD_SIZE]
            if field[0] != SN_CAPACITY or field[1] > SN_CAPACITY:
                raise ValueError(f'工位 {index + 1} 的 PLC STRING[30] 格式无效')
            codes.append(snap7.util.get_string(field, 0))
        return codes

    def write_int(self, byte_offset, value):
        data = bytearray(2)
        snap7.util.set_int(data, 0, value)
        self._connected_client().db_write(self.db_number, byte_offset, data)
        self.logger.info('写入 PLC INT: DB%s DBW%s = %s', self.db_number, byte_offset, value)

    def write_results(self, byte_offset, data):
        if len(data) != RESULTS_SIZE:
            raise ValueError('工位结果数据必须为 48 字节')
        self._connected_client().db_write(self.db_number, byte_offset, bytearray(data))
        self.logger.info('写入 PLC 工位结果: DB%s DBB%s 起 48 字节', self.db_number, byte_offset)

    def write_real(self, byte_offset, value):
        try:
            data = bytearray(4)
            snap7.util.set_real(data, 0, float(value))
            self._connected_client().db_write(self.db_number, byte_offset, data)
        except Exception:
            self.logger.exception('写入 PLC REAL 失败: DB%s DBD%s', self.db_number, byte_offset)
            raise
        self.logger.info('写入 PLC REAL: DB%s DBD%s = %s', self.db_number, byte_offset, value)
