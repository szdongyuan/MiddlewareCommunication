"""桥接端发送给希听的换行分隔消息。"""
import json


def encode_station_sn_codes(codes):
    if not isinstance(codes, (list, tuple)) or len(codes) != 4 or not all(isinstance(code, str) for code in codes):
        raise ValueError('需要四个工位的 SN 字符串')
    message = {'type': 'station_sn_codes', 'sn_codes': list(codes)}
    return (json.dumps(message, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
