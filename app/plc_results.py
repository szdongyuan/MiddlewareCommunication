"""将完整测试轮次编码成标准 S7 DB 中的工位结果区。"""
import math
import struct


def encode_station_results(stations):
    """返回 48 字节：每工位正转/反转依次为 INT 判定、REAL 声压级。

    数据不完整或无效时拒绝编码，调用方不得据此发送完成状态。
    """
    if not isinstance(stations, (list, tuple)) or len(stations) != 4:
        raise ValueError('需要四个工位的结果')
    by_station = {}
    round_id = None
    for item in stations:
        if not isinstance(item, dict) or type(item.get('station')) is not int:
            raise ValueError('工位结果格式错误')
        number = item['station']
        if number not in (1, 2, 3, 4) or number in by_station:
            raise ValueError('工位编号无效或重复')
        current_round = item.get('round_id')
        if not isinstance(current_round, str) or not current_round:
            raise ValueError('缺少轮次标识')
        if round_id is not None and round_id != current_round:
            raise ValueError('不能混合不同轮次的结果')
        round_id = current_round
        by_station[number] = item

    data = bytearray()
    for number in range(1, 5):
        item = by_station[number]
        for direction in ('forward', 'reverse'):
            result = item.get(direction)
            value = item.get(direction + '_spl')
            if result not in ('OK', 'NG'):
                raise ValueError(f'工位 {number} 的 {direction} 判定未完成')
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'工位 {number} 的 {direction} 声压级无效')
            try:
                data.extend(struct.pack('>hf', 1 if result == 'OK' else 0, value))
            except (OverflowError, struct.error) as exc:
                raise ValueError(f'工位 {number} 的 {direction} 声压级超出 REAL 范围') from exc
    return data
