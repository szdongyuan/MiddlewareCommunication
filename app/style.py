"""界面配色沿用 SpeakerAnomalyDetection 的配置界面。"""

STYLESHEET = """
QMainWindow, QWidget#centralWidget { background-color: #F3F6FA; }
QWidget { font-family: 'SimSun'; font-size: 14px; color: #1F2937; }
QGroupBox {
    background: transparent; border: 1px solid #C9D6E8;
    border-radius: 5px; margin-top: 12px; padding: 14px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 8px; padding: 0 4px;
}
QLineEdit, QPlainTextEdit {
    border: 1px solid #AFC0D6; background-color: white;
    border-radius: 4px; padding: 4px 8px;
    selection-background-color: #3B6FB6;
}
QLineEdit:focus, QPlainTextEdit:focus { border-color: #3B6FB6; }
QLineEdit:disabled { background-color: #F7FAFE; color: #94A3B8; border-color: #C9D6E8; }
QPushButton {
    border: 1px solid #AFC0D6; background-color: #EEF3F8;
    border-radius: 5px; padding: 4px 10px;
}
QPushButton:hover { background-color: #E7EEF7; border-color: #3B6FB6; }
QPushButton:pressed { background-color: #DDE7F3; border-color: #2F5FA8; }
QPushButton:disabled { background-color: #EEF3F8; color: #94A3B8; border-color: #AFC0D6; }
"""
