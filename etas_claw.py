import sys
import os
import requests
import csv
import math
import urllib3
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import geopandas as gpd
from shapely.geometry import Point
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton,
    QProgressBar, QTextEdit, QFileDialog, QMessageBox, QDoubleSpinBox,
    QSpinBox, QGroupBox, QGridLayout, QCheckBox
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont

# 导入obspy
HAS_OBSPY = True
try:
    from obspy import UTCDateTime
    from obspy.clients.fdsn import Client

    print("Info: obspy导入成功，使用ObsPy方式获取数据")
except ImportError:
    HAS_OBSPY = False
    print("Info: obspy导入失败，使用HTTP直接请求方式")


# 震级转换函数 - 转换为Mw震级
def mag_to_mw(magnitude, mag_type):
    """
    将不同类型的震级转换为Mw震级
    """
    mag_type = mag_type.upper()

    # Mw (矩震级) 保持不变
    if mag_type in ['MW', 'MWW', 'MWC', 'MWR']:
        return magnitude

    # Mb (体波震级) 转 Mw
    elif mag_type in ['MB', 'MB_LG', 'MB_BB']:
        # 参考公式: Mw = 0.63*mb + 2.76 (mb < 6.1)
        #          Mw = 1.02*mb - 0.12 (6.1 ≤ mb ≤ 8.0)
        if magnitude < 6.1:
            return 0.63 * magnitude + 2.76
        elif magnitude <= 8.0:
            return 1.02 * magnitude - 0.12
        else:
            return magnitude

    # ML (地方震级) 转 Mw
    elif mag_type in ['ML', 'MLv', 'MLc']:
        # 参考公式: Mw = 0.68*ML + 1.07
        return 0.68 * magnitude + 1.07

    # Ms (面波震级) 转 Mw
    elif mag_type in ['MS', 'MS_20', 'MS_16']:
        # 参考公式: Mw = 0.67*Ms + 2.07
        return 0.67 * magnitude + 2.07

    # 其他震级类型，暂时保持不变
    else:
        return magnitude


# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ======================== 全局配置（适配国内网络） ========================# 1. 国内代理配置（按需开启）
USE_PROXY = False  # 国内访问USGS失败时改为True
PROXY_CONFIG = {
    'http': 'http://127.0.0.1:7890',
    'https': 'http://127.0.0.1:7890'
}

# 2. 台网配置
networks_config = {
    'USGS': {
        'name': 'USGS',
        'region': '全球',
        'url': 'https://earthquake.usgs.gov/fdsnws/event/1/query',
        'mc_options': [4.0, 4.5],
        'timeout': 60,
        'obspy_client': 'USGS',
        'priority': 1
    },
    'IRIS': {
        'name': 'IRIS',
        'region': '全球',
        'url': 'https://service.iris.edu/fdsnws/event/1/query',
        'mc_options': [4.0, 4.5],
        'timeout': 60,
        'obspy_client': 'IRIS',
        'priority': 2
    },
    'GFZ': {
        'name': 'GFZ',
        'region': '全球',
        'url': 'https://geofon.gfz-potsdam.de/fdsnws/event/1/query',
        'mc_options': [4.0, 4.5],
        'timeout': 60,
        'obspy_client': 'GFZ',
        'priority': 3
    },
    'ISC': {
        'name': 'ISC',
        'region': '全球',
        'url': 'https://www.isc.ac.uk/fdsnws/event/1/query',
        'mc_options': [4.0, 4.5],
        'timeout': 60,
        'obspy_client': 'ISC',
        'priority': 4
    }
}


# ======================== 后端爬虫类（带Debug+防墙） ========================
class EarthquakeDataCrawler:
    def __init__(self, log_callback=None):
        # 日志回调（用于GUI输出Debug信息）
        self.log = log_callback if log_callback else print

        # 1. 数据源配置
        self.networks = networks_config

        # 2. 请求会话配置（适配国内网络）
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }

        # 配置代理（国内访问USGS用）
        if USE_PROXY:
            self.session.proxies.update(PROXY_CONFIG)
            self.log(f"[Debug] 已启用代理: {PROXY_CONFIG['https']}")

    def crawl_usgs(self, start_date: str, end_date: str, target_lat: float, target_lon: float,
                   radius: int = 100, min_magnitude: float = 4.0, zone_type: str = 'all') -> List[Dict]:
        """爬取USGS数据（带详细Debug）"""
        return self.crawl_data('USGS', start_date, end_date, target_lat, target_lon, radius, min_magnitude, zone_type)

    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算两点球面距离（km）"""
        R = 6371  # 地球半径(km)
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def crawl_fallback(self, network_id: str, start_date: str, end_date: str, target_lat: float,
                       target_lon: float, radius: int = 100, min_magnitude: float = 4.0) -> List[Dict]:
        """爬取方法（使用requests）"""
        self.log(f"[Debug] 爬取 {network_id} 数据")

        network_config = self.networks.get(network_id)
        if not network_config:
            raise Exception(f"不支持的台网: {network_id}")

        # 根据台网类型调整参数
        params = {
            'format': 'geojson',
            'starttime': start_date,
            'endtime': end_date,
            'latitude': target_lat,
            'longitude': target_lon,
            'minmagnitude': min_magnitude,
            'orderby': 'time-asc',
            'limit': 10000
        }

        # 不同台网的半径参数名不同
        if network_id == 'IRIS':
            # IRIS使用maxradius参数（度）
            params['maxradius'] = radius / 111.12
        else:
            # 其他台网使用maxradiuskm参数（公里）
            params['maxradiuskm'] = radius

        try:
            response = self.session.get(
                network_config['url'],
                params=params,
                timeout=network_config['timeout']
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for feature in data.get('features', []):
                props = feature['properties']
                coords = feature['geometry']['coordinates']

                if not props.get('mag') or not props.get('time'):
                    continue

                # 提取震级和震级类型
                magnitude = props['mag'] if props['mag'] else 0
                mag_type = props['magType'] if props['magType'] else 'ML'

                # 转换震级为Mw震级
                mw_magnitude = mag_to_mw(magnitude, mag_type)

                results.append({
                    '发震时间': datetime.fromtimestamp(props['time'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                    '纬度': round(coords[1], 4),
                    '经度': round(coords[0], 4),
                    '震级': round(mw_magnitude, 2),
                    '震级类型': 'Mw',
                    '深度(km)': coords[2] if len(coords) > 2 else '',
                    '位置': props['place'] if props['place'] else '',
                    '台网来源': network_id
                })

            return results

        except Exception as e:
            raise Exception(f"{network_id}爬取失败: {str(e)}")

    def crawl_data(self, network_id: str, start_date: str, end_date: str, target_lat: float,
                   target_lon: float, radius: int = 100, min_magnitude: float = 4.0, zone_type: str = 'all') -> List[
        Dict]:
        """统一爬取入口"""
        if HAS_OBSPY:
            try:
                return self.crawl_with_obspy(network_id, start_date, end_date, target_lat, target_lon, radius,
                                             min_magnitude)
            except Exception as e:
                self.log(f"[Warning] ObsPy爬取失败，使用备用方法: {str(e)}")
                return self.crawl_fallback(network_id, start_date, end_date, target_lat, target_lon, radius,
                                           min_magnitude)
        else:
            return self.crawl_fallback(network_id, start_date, end_date, target_lat, target_lon, radius, min_magnitude)

    def crawl_with_obspy(self, network_id: str, start_date: str, end_date: str, target_lat: float,
                         target_lon: float, radius: int = 100, min_magnitude: float = 4.0) -> List[Dict]:
        """使用ObsPy爬取数据"""
        self.log(f"[Debug] 使用ObsPy爬取 {network_id} 数据")

        # 处理网络ID映射
        obspy_client_map = {
            'USGS': 'USGS',
            'IRIS': 'EARTHSCOPE',  # IRIS已改名为EARTHSCOPE
            'GFZ': 'GFZ',
            'ISC': 'ISC'
        }

        client_id = obspy_client_map.get(network_id, 'USGS')

        # 创建ObsPy客户端
        client = Client(client_id, timeout=60)

        # 转换时间格式
        starttime = UTCDateTime(start_date)
        endtime = UTCDateTime(end_date)

        # 获取地震目录
        # 不同数据中心可能使用不同的参数名
        try:
            # 尝试使用maxradiuskm
            cat = client.get_events(
                starttime=starttime,
                endtime=endtime,
                minmagnitude=min_magnitude,
                latitude=target_lat,
                longitude=target_lon,
                maxradiuskm=radius,
                orderby="time-asc",
                limit=10000
            )
        except Exception as e:
            # 如果失败，尝试使用maxradius（度）
            self.log(f"[Debug] maxradiuskm失败，尝试使用maxradius: {str(e)}")
            # 将公里转换为度（约111.12公里/度）
            maxradius_deg = radius / 111.12
            cat = client.get_events(
                starttime=starttime,
                endtime=endtime,
                minmagnitude=min_magnitude,
                latitude=target_lat,
                longitude=target_lon,
                maxradius=maxradius_deg,
                orderby="time-asc",
                limit=10000
            )

        results = []
        for event in cat:
            origin = event.preferred_origin()
            magnitude = event.preferred_magnitude()

            if not origin or not magnitude:
                continue

            # 提取信息
            time = origin.time.strftime('%Y-%m-%d %H:%M:%S')
            lat = origin.latitude
            lon = origin.longitude
            mag = magnitude.mag
            # 处理震级类型可能不存在的情况
            mag_type = 'ML'
            try:
                mag_type = magnitude.mag_type if hasattr(magnitude, 'mag_type') else 'ML'
            except:
                mag_type = 'ML'
            depth = origin.depth / 1000.0 if origin.depth else ''  # 转换为公里

            # 提取位置信息
            place = ""
            if event.event_descriptions:
                place = event.event_descriptions[0].text

            # 转换震级为Mw震级
            mw_magnitude = mag_to_mw(mag, mag_type)

            results.append({
                '发震时间': time,
                '纬度': round(lat, 4),
                '经度': round(lon, 4),
                '震级': round(mw_magnitude, 2),
                '震级类型': 'Mw',
                '深度(km)': depth,
                '位置': place,
                '台网来源': network_id
            })

        self.log(f"[Info] ObsPy爬取完成，共获取 {len(results)} 条数据")
        return results

    def auto_select_network(self, lat: float, lon: float) -> str:
        """根据地理位置自动选择最佳台网（基于距离）"""
        # 台网总部坐标
        network_coords = {
            'USGS': (38.9542, -77.1993),  # 弗吉尼亚州雷斯顿
            'IRIS': (38.8985, -77.0285),  # 华盛顿特区
            'GFZ': (52.4083, 13.0531),  # 德国波茨坦
            'ISC': (55.9475, -3.1900)  # 英国爱丁堡
        }

        # 计算到每个台网的距离
        min_distance = float('inf')
        best_network = 'USGS'  # 默认值

        for network, (network_lat, network_lon) in network_coords.items():
            distance = self.haversine_distance(lat, lon, network_lat, network_lon)
            if distance < min_distance:
                min_distance = distance
                best_network = network

        self.log(f"[Debug] 自动选择台网: {best_network} (距离: {min_distance:.2f}km)")
        return best_network

    def generate_filename(self, lat: float, lon: float, zone_type: str, network: str, event_name: str = None,
                          event_type: str = None) -> str:
        """
        自动生成CSV文件名：事件名称+构造类型+经纬度+台网
        示例：Japan_2011_俯冲带_纬度38.32N_经度142.37E_USGS.csv
        """
        # 构造类型中文映射
        type_map = {
            'subduction_zone': '俯冲带',
            'strike_slip': '走滑断层',
            'intracontinental': '大陆内部',
            'all': '全部区域'
        }

        # 获取构造类型中文名
        if event_type and event_type in type_map:
            type_cn = type_map[event_type]
        else:
            type_cn = type_map.get(zone_type, '全部区域')

        # 格式化经纬度（保留2位小数）
        lat_str = f"纬度{abs(lat):.2f}" + ('N' if lat >= 0 else 'S')
        lon_str = f"经度{abs(lon):.2f}" + ('E' if lon >= 0 else 'W')

        # 生成文件名
        if event_name:
            filename = f"{event_name}_{type_cn}_{lat_str}_{lon_str}_{network}.csv"
        else:
            filename = f"ETAS_{type_cn}_{lat_str}_{lon_str}_{network}.csv"

        # 替换非法字符
        filename = filename.replace('/', '_').replace('\\', '_').replace(':', '_').replace(' ', '_')

        self.log(f"[Debug] 自动生成文件名: {filename}")
        return filename

    def save_to_csv(self, data: List[Dict], file_path: str) -> int:
        """保存为ETAS专用CSV（带Debug）"""
        if not data:
            raise Exception("无数据可保存")

        self.log(f"[Debug] 开始保存CSV到: {file_path}")
        fieldnames = ['发震时间', '纬度', '经度', '震级', '震级类型', '深度(km)', '位置', '台网来源']

        # 创建目录
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        self.log(f"[Debug] CSV保存完成，共写入 {len(data)} 行数据")
        return len(data)


# ======================== 爬取线程类 ========================
class CrawlThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str, int)

    def __init__(self, crawler, network_id, start_date, end_date, target_lat, target_lon,
                 output_dir, radius, min_magnitude, zone_type, event_name=None, event_type=None,
                 before_years=0):
        super().__init__()
        self.crawler = crawler
        self.network_id = network_id
        self.start_date = start_date
        self.end_date = end_date
        self.target_lat = target_lat
        self.target_lon = target_lon
        self.output_dir = output_dir
        self.radius = radius
        self.min_magnitude = min_magnitude
        self.zone_type = zone_type
        self.event_name = event_name
        self.event_type = event_type
        self.before_years = before_years

    def run(self):
        try:
            self.log_signal.emit(f"开始爬取 {self.network_id} 数据...")
            event_info = f"事件: {self.event_name}" if self.event_name else "自定义参数"
            self.log_signal.emit(f"参数：{event_info} | 半径{self.radius}km | 最小震级{self.min_magnitude}")

            # 初始化进度条，先慢慢挪动
            for i in range(1, 11):
                self.progress_signal.emit(i)
                import time
                time.sleep(0.1)

            before_data = []
            if self.before_years > 0:
                # 创建与output_dir平行的before目录
                before_dir = os.path.join(os.path.dirname(self.output_dir), "before")
                os.makedirs(before_dir, exist_ok=True)

                from datetime import datetime as dt
                start_dt = dt.strptime(self.start_date, "%Y-%m-%d")
                before_end_date = start_dt.strftime("%Y-%m-%d")
                before_start_date = (start_dt.replace(year=start_dt.year - self.before_years)).strftime("%Y-%m-%d")

                self.log_signal.emit(f"[Info] 开始爬取历史数据: {before_start_date} 至 {before_end_date}")

                # 历史数据爬取进度
                for i in range(11, 31):
                    self.progress_signal.emit(i)
                    import time
                    time.sleep(0.05)

                before_data = self.crawler.crawl_data(
                    self.network_id, before_start_date, before_end_date,
                    self.target_lat, self.target_lon, self.radius,
                    self.min_magnitude, self.zone_type
                )
                self.log_signal.emit(f"[Info] 历史数据获取完成，共 {len(before_data)} 条")

                if before_data:
                    before_filename = self.crawler.generate_filename(
                        self.target_lat, self.target_lon, self.zone_type, self.network_id,
                        self.event_name, self.event_type
                    )
                    before_filename = f"before_{self.before_years}y_{before_filename}"
                    before_output_file = os.path.join(before_dir, before_filename)
                    self.crawler.save_to_csv(before_data, before_output_file)
                    self.log_signal.emit(f"[Info] 历史数据已保存至: {before_output_file}")

            # 主数据爬取进度
            for i in range(31, 61):
                self.progress_signal.emit(i)
                import time
                time.sleep(0.05)

            data = self.crawler.crawl_data(
                self.network_id, self.start_date, self.end_date,
                self.target_lat, self.target_lon, self.radius,
                self.min_magnitude, self.zone_type
            )

            # 保存数据进度
            for i in range(61, 99):
                self.progress_signal.emit(i)
                import time
                time.sleep(0.03)

            self.log_signal.emit(f"成功获取 {len(data)} 条有效数据")

            if data:
                filename = self.crawler.generate_filename(
                    self.target_lat, self.target_lon, self.zone_type, self.network_id,
                    self.event_name, self.event_type
                )
                output_file = os.path.join(self.output_dir, filename)
                count = self.crawler.save_to_csv(data, output_file)

                # 完成进度
                self.progress_signal.emit(100)
                self.log_signal.emit(f"数据已保存至: {output_file}")
                total_count = count
                msg = f"爬取成功（历史{self.before_years}年: {len(before_data) if self.before_years > 0 else 0}条）"
                self.finished_signal.emit(True, msg, total_count)
            else:
                self.progress_signal.emit(100)
                self.log_signal.emit("未获取到符合条件的数据")
                self.finished_signal.emit(False, "未获取到数据", 0)

        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            self.log_signal.emit(f"[Error] 爬取失败: {str(e)}")
            self.log_signal.emit(f"[Debug] {error_msg}")
            # 确保进度条回到初始状态
            self.progress_signal.emit(0)
            self.finished_signal.emit(False, str(e), 0)


# ======================== GUI界面类 ========================
class EarthquakeCrawlerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.crawl_thread = None

        # 初始化界面（先创建debug_check等UI元素）
        self.init_ui()

        # 初始化爬虫（绑定日志回调）
        self.crawler = EarthquakeDataCrawler(log_callback=self.log_message)

        # 输出初始Debug信息
        self.log_message("[Info] 程序已启动，国内访问USGS失败请修改USE_PROXY=True")
        self.log_message(f"[Info] 当前代理配置: {'开启' if USE_PROXY else '关闭'}")

    def init_ui(self):
        # 基础窗口设置
        self.setWindowTitle("ETAS地震数据爬取工具")
        self.setGeometry(100, 100, 900, 900)

        # 设置整体样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
                color: #000000;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #000000;
            }
            QLabel {
                color: #000000;
                font-size: 12px;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                font-size: 12px;
                color: #000000;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 2px solid #409EFF;
            }
            QCheckBox {
                font-size: 12px;
                color: #000000;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QMessageBox {
                background-color: white;
            }
            QMessageBox QLabel {
                color: #000000;
                font-size: 13px;
            }
        """)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 标题
        title_label = QLabel("🌍 15d_earthquake地震数据爬取工具")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #000000; margin: 10px 0; font-weight: bold;")
        layout.addWidget(title_label)
        layout.addSpacing(15)

        # 1. 核心参数组
        core_group = QGroupBox("核心参数")
        core_layout = QGridLayout(core_group)

        # 预设地震事件选择
        core_layout.addWidget(QLabel("预设事件:"), 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("自定义参数")
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        core_layout.addWidget(self.preset_combo, 0, 1, 1, 3)

        # 坐标粘贴框（自动解析）
        core_layout.addWidget(QLabel("粘贴坐标:"), 1, 0)
        self.coord_paste = QLineEdit()
        self.coord_paste.setPlaceholderText("粘贴坐标 (经度,纬度) 例如: 101.78,1.00")
        self.coord_paste.textChanged.connect(self.auto_parse_coordinates)
        core_layout.addWidget(self.coord_paste, 1, 1, 1, 3)

        # 经纬度
        core_layout.addWidget(QLabel("主震经纬度:"), 2, 0)
        latlon_layout = QHBoxLayout()
        self.lat_input = QLineEdit("38.0")
        self.lat_input.setPlaceholderText("纬度（如：38.0）")
        latlon_layout.addWidget(self.lat_input)
        latlon_layout.addWidget(QLabel("    "))
        self.lon_input = QLineEdit("142.0")
        self.lon_input.setPlaceholderText("经度（如：142.0）")
        latlon_layout.addWidget(self.lon_input)
        core_layout.addLayout(latlon_layout, 2, 1, 1, 3)

        # 台网选择
        core_layout.addWidget(QLabel("数据源:"), 3, 0)
        self.network_combo = QComboBox()
        # 添加台网选项
        for network_id, config in networks_config.items():
            self.network_combo.addItem(f"{config['name']}（{config['region']}）", network_id)
        # 添加自动选择选项
        self.network_combo.insertItem(0, "自动选择（根据位置）", "auto")
        core_layout.addWidget(self.network_combo, 3, 1, 1, 3)

        # 时间范围
        core_layout.addWidget(QLabel("时间范围:"), 4, 0)
        date_layout = QHBoxLayout()
        self.start_date = QLineEdit("2015-01-01")
        self.start_date.setPlaceholderText("开始日期（YYYY-MM-DD）")
        date_layout.addWidget(self.start_date)
        date_layout.addWidget(QLabel(" 至 "))
        self.end_date = QLineEdit("2025-12-31")
        self.end_date.setPlaceholderText("结束日期（YYYY-MM-DD）")
        date_layout.addWidget(self.end_date)
        core_layout.addLayout(date_layout, 4, 1, 1, 3)

        # 历史数据倒推
        core_layout.addWidget(QLabel("历史数据:"), 5, 0)
        before_layout = QHBoxLayout()
        self.before_combo = QComboBox()
        self.before_combo.addItems(["无", "1年", "3年", "5年", "10年"])
        self.before_combo.setCurrentIndex(0)
        before_layout.addWidget(self.before_combo)
        before_layout.addWidget(QLabel("（从起始时间向前倒推）"))
        core_layout.addLayout(before_layout, 5, 1, 1, 3)

        # 半径
        core_layout.addWidget(QLabel("搜索半径(km):"), 6, 0)
        self.radius_input = QSpinBox()
        self.radius_input.setRange(10, 500)
        self.radius_input.setValue(100)
        core_layout.addWidget(self.radius_input, 6, 1)

        # Mc震级门槛
        core_layout.addWidget(QLabel("Mc震级门槛:"), 6, 2)
        self.mc_input = QDoubleSpinBox()
        self.mc_input.setRange(0.0, 5.0)
        self.mc_input.setValue(4.0)
        self.mc_input.setSingleStep(0.5)
        core_layout.addWidget(self.mc_input, 6, 3)

        layout.addWidget(core_group)
        layout.addSpacing(15)

        # 2. 文件保存组
        file_group = QGroupBox("文件设置")
        file_layout = QHBoxLayout(file_group)
        file_layout.addWidget(QLabel("保存目录:"))
        self.dir_input = QLineEdit(os.path.join(os.getcwd(), "15d_earthquake"))
        file_layout.addWidget(self.dir_input)
        self.browse_dir_btn = QPushButton("浏览目录")
        self.browse_dir_btn.clicked.connect(self.browse_dir)
        file_layout.addWidget(self.browse_dir_btn)
        layout.addWidget(file_group)
        layout.addSpacing(15)

        # 3. Debug开关（关键修复：QCheckBox）
        debug_layout = QHBoxLayout()
        self.debug_check = QCheckBox("显示Debug日志")
        self.debug_check.setChecked(True)
        debug_layout.addWidget(self.debug_check)
        layout.addLayout(debug_layout)
        layout.addSpacing(15)

        # 4. 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                text-align: center;
                background-color: #2d2d2d;
                color: #d4d4d4;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #409EFF;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(15)

        # 5. 按钮组
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("🚀 开始爬取")
        self.start_btn.clicked.connect(self.start_crawl)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #409EFF;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #66b1ff;
            }
            QPushButton:pressed {
                background-color: #3a8ee6;
            }
            QPushButton:disabled {
                background-color: #a0cfff;
            }
        """)
        btn_layout.addWidget(self.start_btn)

        self.clear_btn = QPushButton("🗑️ 清空日志")
        self.clear_btn.clicked.connect(self.clear_log)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #868e96;
            }
            QPushButton:pressed {
                background-color: #5a6268;
            }
        """)
        btn_layout.addWidget(self.clear_btn)

        self.export_log_btn = QPushButton("💾 导出日志")
        self.export_log_btn.clicked.connect(self.export_log)
        self.export_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #34ce57;
            }
            QPushButton:pressed {
                background-color: #218838;
            }
        """)
        btn_layout.addWidget(self.export_log_btn)
        layout.addLayout(btn_layout)
        layout.addSpacing(15)

        # 6. 日志区
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                line-height: 1.5;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #555;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #777;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)

        # 加载预设事件（在log_text创建之后）
        self.load_preset_events()

        # 绑定台网-Mc联动
        self.network_combo.currentIndexChanged.connect(self.update_mc_options)
        self.update_mc_options()

    def load_preset_events(self):
        """加载预设地震事件"""
        csv_path = os.path.join(os.path.dirname(__file__), 'earthquake_events.csv')
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                self.log_message(f"[Debug] CSV列: {list(df.columns)}")
                self.log_message(f"[Debug] 第一行数据: {df.iloc[0].to_dict()}")
                self.preset_data = df.to_dict('records')

                # 按类型分组添加
                type_names = {
                    'subduction_zone': '俯冲带',
                    'strike_slip': '走滑断层',
                    'intracontinental': '大陆内部'
                }

                current_type = None
                for _, row in df.iterrows():
                    event_type = row['type']
                    if event_type != current_type:
                        current_type = event_type
                        self.preset_combo.addItem(f"── {type_names.get(event_type, event_type)} ──")
                    event_name = f"{row['name']} (M{row['magnitude']})"
                    self.preset_combo.addItem(event_name)

                self.log_message(f"[Info] 已加载 {len(df)} 个预设地震事件")
            except Exception as e:
                self.log_message(f"[Warning] 加载预设事件失败: {str(e)}")
                self.preset_data = []
        else:
            self.preset_data = []
            self.log_message("[Warning] 未找到预设事件文件 earthquake_events.csv")

    def on_preset_changed(self, index):
        """预设事件选择变化"""
        if index == 0:  # 自定义参数
            return

        # 如果选择的是分隔符，跳过
        current_text = self.preset_combo.currentText()
        if current_text.startswith('──'):
            self.preset_combo.setCurrentIndex(0)  # 重置为自定义参数
            return

        # 重新计算实际索引：遍历所有选项，跳过分隔符
        actual_index = 0
        for i in range(1, index):
            text = self.preset_combo.itemText(i)
            if not text.startswith('──'):
                actual_index += 1

        self.log_message(f"[Debug] 选择索引: {index}, 实际数据索引: {actual_index}")

        # 检查索引是否有效
        if not hasattr(self, 'preset_data') or not self.preset_data:
            self.log_message("[Warning] 预设事件数据未加载")
            return

        self.log_message(f"[Debug] 预设数据长度: {len(self.preset_data)}")
        if 0 <= actual_index < len(self.preset_data):
            event = self.preset_data[actual_index]
            self.log_message(f"[Debug] 事件数据: {event}")
            self.lon_input.setText(str(event['lon']))
            self.lat_input.setText(str(event['lat']))

            # 自动填入时间范围
            if 'time' in event and pd.notna(event['time']):
                self.start_date.setText(str(event['time']))
                self.log_message(f"[Debug] 设置开始时间: {event['time']}")
            if 'end' in event and pd.notna(event['end']):
                self.end_date.setText(str(event['end']))
                self.log_message(f"[Debug] 设置结束时间: {event['end']}")

            # 根据震级自动设置搜索半径
            magnitude = event['magnitude']
            if magnitude >= 9.0:
                radius = 500
            elif magnitude >= 8.0:
                radius = 300
            elif magnitude >= 7.0:
                radius = 200
            else:
                radius = 150
            self.radius_input.setValue(radius)

            # 根据震级自动设置Mc
            if magnitude >= 8.0:
                mc = 4.5
            else:
                mc = 4.0
            self.mc_input.setValue(mc)

            self.log_message(f"[Info] 已选择预设事件: {event['name']} (类型: {event['type']}, M{event['magnitude']})")
        else:
            self.log_message(f"[Error] 索引越界: actual_index={actual_index}, 数据长度={len(self.preset_data)}")

    def update_mc_options(self):
        """根据台网自动调整Mc默认值"""
        self.mc_input.setValue(4.0)
        self.mc_input.setRange(4.0, 4.5)

    def auto_parse_coordinates(self):
        """自动解析粘贴的坐标 (经度,纬度)"""
        text = self.coord_paste.text().strip()
        if not text:
            return

        # 尝试解析各种格式
        parts = None
        for sep in [',', '，', ' ', '\t']:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                break

        if not parts or len(parts) != 2:
            return

        try:
            lon = float(parts[0])
            lat = float(parts[1])

            # 验证范围
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                self.lon_input.setText(str(lon))
                self.lat_input.setText(str(lat))
        except ValueError:
            pass

    def browse_dir(self):
        """选择保存目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择保存目录", self.dir_input.text())
        if dir_path:
            self.dir_input.setText(dir_path)

    def validate_inputs(self):
        """验证输入"""
        try:
            # 经纬度
            lat = float(self.lat_input.text())
            lon = float(self.lon_input.text())
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                raise ValueError("纬度范围[-90,90]，经度范围[-180,180]")

            # 日期
            datetime.strptime(self.start_date.text(), "%Y-%m-%d")
            datetime.strptime(self.end_date.text(), "%Y-%m-%d")

            # 半径和震级
            if self.radius_input.value() < 10:
                raise ValueError("半径不能小于10km")

            return True, lat, lon
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"参数验证失败：{str(e)}")
            return False, None, None

    def start_crawl(self):
        """开始爬取"""
        try:
            if self.crawl_thread and self.crawl_thread.isRunning():
                QMessageBox.warning(self, "提示", "正在爬取中，请等待！")
                return

            # 验证输入
            valid, lat, lon = self.validate_inputs()
            if not valid:
                return

            # 解析参数
            network_id = self.network_combo.currentData()

            # 处理自动选择台网
            if network_id == "auto":
                network_id = self.crawler.auto_select_network(lat, lon)
                self.log_message(f"[Info] 自动选择台网: {network_id}")

            start_date = self.start_date.text()
            end_date = self.end_date.text()
            radius = self.radius_input.value()
            min_mag = self.mc_input.value()
            zone_type = "all"  # 默认使用全部区域
            output_dir = self.dir_input.text()

            # 获取预设事件信息
            event_name = None
            event_type = None
            current_index = self.preset_combo.currentIndex()
            if current_index > 0 and hasattr(self, 'preset_data') and self.preset_data:
                # 检查是否是分隔符
                current_text = self.preset_combo.currentText()
                if not current_text.startswith('──'):
                    # 计算实际的数据索引
                    data_index = current_index - 1
                    separator_count = 0
                    for i in range(1, current_index):
                        if self.preset_combo.itemText(i).startswith('──'):
                            separator_count += 1

                    actual_index = data_index - separator_count
                    if 0 <= actual_index < len(self.preset_data):
                        event_name = self.preset_data[actual_index]['name']
                        event_type = self.preset_data[actual_index]['type']

            # 获取历史数据倒推选项
            before_years_map = {0: 0, 1: 1, 2: 3, 3: 5, 4: 10}
            before_years = before_years_map.get(self.before_combo.currentIndex(), 0)

            # 禁用按钮，重置进度
            self.start_btn.setEnabled(False)
            self.progress_bar.setValue(0)

            # 启动爬取线程
            self.crawl_thread = CrawlThread(
                self.crawler, network_id, start_date, end_date,
                lat, lon, output_dir, radius, min_mag, zone_type, event_name, event_type,
                before_years
            )
            self.crawl_thread.log_signal.connect(self.log_message)
            self.crawl_thread.progress_signal.connect(self.progress_bar.setValue)
            self.crawl_thread.finished_signal.connect(self.crawl_finished)
            self.crawl_thread.start()
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            self.log_message(f"[Error] 启动爬取失败: {str(e)}")
            self.log_message(f"[Debug] {error_msg}")
            QMessageBox.critical(self, "错误", f"启动爬取失败：{str(e)}")

    def crawl_finished(self, success, message, count):
        """爬取完成回调"""
        self.start_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "成功", f"{message}，共获取 {count} 条数据！")
        else:
            QMessageBox.warning(self, "失败", message)

    def log_message(self, msg):
        """添加日志（区分Debug和普通信息）"""
        if not self.debug_check.isChecked() and msg.startswith("[Debug]"):
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        # 日志级别颜色和图标
        if msg.startswith("[Error]"):
            color = "#ff6b6b"
            icon = "❌"
            level = "ERROR"
        elif msg.startswith("[Warning]"):
            color = "#ffa94d"
            icon = "⚠️"
            level = "WARN"
        elif msg.startswith("[Debug]"):
            color = "#74c0fc"
            icon = "🔍"
            level = "DEBUG"
        elif msg.startswith("[Info]"):
            color = "#69db7c"
            icon = "ℹ️"
            level = "INFO"
        elif "成功" in msg or "完成" in msg:
            color = "#69db7c"
            icon = "✅"
            level = "SUCCESS"
        else:
            color = "#d4d4d4"
            icon = "📝"
            level = "LOG"

        # 格式化日志消息
        formatted_msg = f'<span style="color: #6c757d;">[{timestamp}]</span> <span style="color: {color};">{icon} {msg}</span>'
        self.log_text.append(formatted_msg)

        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.log_message("[Info] 日志已清空，准备开始新的爬取任务")

    def export_log(self):
        """导出日志到文件"""
        log_content = self.log_text.toPlainText()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", f"ETAS爬取日志_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "文本文件 (*.txt)"
        )
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(log_content)
            QMessageBox.information(self, "成功", f"日志已导出到: {file_path}")


# ======================== 主函数 ========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EarthquakeCrawlerGUI()
    window.show()
    sys.exit(app.exec())