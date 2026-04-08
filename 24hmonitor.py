import sys
import requests
import json
from datetime import datetime, timedelta, UTC
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QTextEdit, QLabel, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

# 禁用SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 核心功能：过去24小时全球≥6级地震（UTC时间）
# ==========================================
def get_recent_6_earthquakes_utc():
    try:
        # 时间范围：现在UTC -24h（新版标准写法）
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=168)

        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S")

        # USGS 官方API
        url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
        params = {
            "format": "geojson",
            "starttime": start_str,
            "endtime": end_str,
            "minmagnitude": 6.0,
            "orderby": "time",
            "limit": 50
        }

        session = requests.Session()
        session.verify = False
        resp = session.get(url, params=params, timeout=20)
        data = resp.json()

        result = []
        for feature in data["features"]:
            prop = feature["properties"]
            coord = feature["geometry"]["coordinates"]

            # 原始 UTC 时间
            utc_time = datetime.fromtimestamp(prop["time"] / 1000, tz=UTC)
            mag = prop["mag"]
            place = prop["place"]
            lon = coord[0]
            lat = coord[1]
            depth = round(coord[2] / 1000, 1) if len(coord) >= 3 else 0.0

            line = (
                f"【6级以上地震】\n"
                f"UTC时间：{utc_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"经纬度：({lon:.3f},{lat:.3f})\n"  # 这里已修改
                f"震级(Mw)：{mag:.1f}\n"
                f"深度：{depth} km\n"
                f"位置：{place}\n"
                + "-" * 60
            )
            result.append(line)

        if not result:
            return ["✅ 过去24小时全球无6.0级以上地震（UTC）"]

        return result

    except Exception as e:
        return [f"❌ 获取失败：{str(e)}"]

# ==========================================
# GUI 界面（Mac/Windows 通用）
# ==========================================
class QuakeMonitorUTC(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("过去24小时全球≥6级地震 | UTC时间版 | 比赛专用")
        self.setGeometry(100, 100, 750, 600)
        self.setStyleSheet("background-color:#f5f5f5;")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        title = QLabel("🌍 全球6级以上地震实时监测（UTC时间）")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color:#d32f2f; padding:10px;")
        layout.addWidget(title)

        self.refresh_btn = QPushButton("🔄 立即查询最新地震")
        self.refresh_btn.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f; color: white;
                padding: 10px; border-radius:6px;
            }
            QPushButton:hover { background-color:#b71c1c; }
        """)
        self.refresh_btn.clicked.connect(self.refresh_data)
        layout.addWidget(self.refresh_btn)

        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setStyleSheet("""
            QTextEdit {
                background-color:#1e1e1e;
                color:#f1f1f1;
                font-family: Monaco, Consolas, monospace;
                font-size:13px;
                padding:10px;
            }
        """)
        layout.addWidget(self.result_box)

        self.refresh_data()

    def refresh_data(self):
        self.refresh_btn.setText("🔄 查询中...")
        self.refresh_btn.setEnabled(False)
        QApplication.processEvents()

        lines = get_recent_6_earthquakes_utc()
        self.result_box.clear()
        self.result_box.append("\n".join(lines))

        self.refresh_btn.setText("🔄 立即查询最新地震")
        self.refresh_btn.setEnabled(True)

        if any("【6级以上地震】" in line for line in lines):
            QMessageBox.warning(self, "⚠️ 地震警报", "检测到 6.0级以上地震！")

# ==========================================
# 运行
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QuakeMonitorUTC()
    window.show()
    sys.exit(app.exec())