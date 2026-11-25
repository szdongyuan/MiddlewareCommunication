# PLC 通信桥梁

连接西门子 S7 PLC 和希听 TCP 服务，将 PLC 启动指令与四工位 SN 发给希听，并在收到同一轮四工位正反转完整结果后写入 PLC。

## 安装与运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

在界面填写 PLC 地址、DB 块、心跳与指令地址，以及希听 TCP 地址和端口。连接配置保存在本机 resources 目录中。

## 希听模拟程序

```powershell
.\.venv\Scripts\python.exe xiting_demo_client.py
```

模拟程序默认监听所有网卡的 9000 端口，可用 --host 和 --port 调整。它不录音，生成随机判定和声压级；先启动它，再连接桥梁。

## PLC 交互

PLC 指令为 10（启动）、11（停止）、12（复位）；桥梁状态为 0（测试中）、10（就绪）、11（完成）、12（报警）。桥梁收到四工位正反转结果后，写入结果区并设置完成状态。每个方向包含 INT 判定（1 为 OK，0 为 NG）和 REAL 声压级。DB 地址布局见 app/plc_layout.py。

TCP 采用 UTF-8 换行分隔消息。桥梁发送 true 和四个 SN；希听确认后先发送四个工位的正转事件，再发送正反转完整结果。模拟数据仅用于联调。
