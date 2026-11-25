"""PLC 和 TCP 配置文件的读取与保存。"""
import json
from pathlib import Path

RESOURCE_DIR = Path(__file__).resolve().parent.parent / 'resources'
PLC_CONFIG_PATH = RESOURCE_DIR / 'plcconfig.json'
TCP_CONFIG_PATH = RESOURCE_DIR / 'tcp.json'


def load_config(plc_keys, tcp_keys):
    saved = {}
    for path, keys in ((PLC_CONFIG_PATH, plc_keys), (TCP_CONFIG_PATH, tcp_keys)):
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError(f'{path.name} 必须是 JSON 对象')
            saved.update({key: data[key] for key in keys if key in data})
    return saved


def save_config(values, path, keys):
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    data = {key: values[key] for key in keys}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
