import os
import sys
import json
import shutil
import hashlib
import wave
import urllib.parse
import requests
from bs4 import BeautifulSoup
import numpy as np

try:
    import yt_dlp
    YTDLP_READY = True
except Exception:
    YTDLP_READY = False

try:
    import pygame
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.mixer.init()
    PYGAME_READY = True
except Exception:
    PYGAME_READY = False

try:
    import soundfile as sf
    SF_READY = True
except Exception:
    SF_READY = False

from PyQt6.QtCore import (
    Qt, QUrl, QPoint, QRect, QTimer, QMimeData, QModelIndex,
    QThread, pyqtSignal
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QDrag,
    QKeyEvent, QFont, QFontMetrics, QStandardItemModel, QStandardItem,
    QIcon, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTreeView, QFileDialog, QStyledItemDelegate,
    QLineEdit
)

LOGO_FILENAME = "DUCTAM24VN_TOOLS_GROUP_128x128.png"
AUDIO_EXTENSIONS = ('.wav', '.mp3', '.ogg', '.flac', '.aiff', '.m4a')
CONFIG_FILE = "sfx_factory_config.json"
FAVORITE_DIR_NAME = "Favorite FX"
DOWNLOAD_DIR_NAME = "Sound FX Download"
CACHE_DIR_NAME = ".trimmed_cache"

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 2
IS_LOADED_ROLE = Qt.ItemDataRole.UserRole + 3
IS_ONLINE_ROLE = Qt.ItemDataRole.UserRole + 4
ONLINE_DOWNLOAD_URL_ROLE = Qt.ItemDataRole.UserRole + 5

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.myinstants.com/"
}


def read_audio_data_safe(file_path):
    if SF_READY:
        try:
            data, sr = sf.read(file_path, always_2d=True)
            mono = np.mean(data, axis=1)
            duration = len(mono) / float(sr)
            return mono, duration, sr
        except Exception:
            pass

    if file_path.lower().endswith('.wav'):
        try:
            with wave.open(file_path, 'rb') as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                channels = wf.getnchannels()
                frames = wf.readframes(n_frames)
                audio_array = np.frombuffer(frames, dtype=np.int16)
                if channels > 1:
                    audio_array = audio_array.reshape(-1, channels).mean(axis=1)
                mono = audio_array / 32768.0
                duration = len(mono) / float(sr)
                return mono, duration, sr
        except Exception:
            pass

    dummy_mono = np.sin(np.linspace(0, 40, 300)) * 0.4
    return dummy_mono, 1.5, 44100


def trim_leading_silence_file(file_path):
    if not SF_READY or not os.path.exists(file_path):
        return
    try:
        data, sr = sf.read(file_path, always_2d=True)
        mono = np.mean(data, axis=1) if data.ndim > 1 else data
        indices = np.where(np.abs(mono) > 0.01)[0]
        if len(indices) > 0:
            start_idx = max(0, indices[0] - int(sr * 0.003))
            if start_idx > 0:
                trimmed_data = data[start_idx:]
                sf.write(file_path, trimmed_data, sr)
    except Exception:
        pass


class SmartMemeSearchWorker(QThread):
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        combined_results = []
        try:
            encoded_query = urllib.parse.quote(self.query)
            url = f"https://www.myinstants.com/en/search/?name={encoded_query}"
            res = requests.get(url, headers=BROWSER_HEADERS, timeout=6)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                buttons = soup.find_all("div", class_="instant")
                for b in buttons[:10]:
                    link_tag = b.find("a", class_="instant-link")
                    play_btn = b.find("button", class_="small-button")
                    if link_tag and play_btn:
                        name = link_tag.text.strip()
                        onclick = play_btn.get("onclick", "")
                        if "play('" in onclick:
                            mp3_path = onclick.split("play('")[1].split("'")[0]
                            mp3_url = urllib.parse.urljoin("https://www.myinstants.com", mp3_path)
                            combined_results.append({
                                "name": f"⭐ [Clean] {name}",
                                "url": mp3_url,
                                "score": 95
                            })
        except Exception:
            pass

        if YTDLP_READY:
            try:
                search_term = f"ytsearch8:{self.query} meme sound effect"
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': 'in_playlist',
                    'skip_download': True
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(search_term, download=False)
                    entries = info.get('entries', [])
                    for e in entries:
                        duration = e.get('duration', 0)
                        if 1 <= duration <= 35:
                            title = e.get('title', '')
                            video_id = e.get('id', '')
                            combined_results.append({
                                "name": f"🎬 {title} ({duration}s)",
                                "url": f"https://www.youtube.com/watch?v={video_id}",
                                "score": max(50, 90 - duration)
                            })
            except Exception:
                pass

        combined_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        self.results_ready.emit(combined_results)


class StreamPreviewWorker(QThread):
    preview_ready = pyqtSignal(str, object)
    preview_failed = pyqtSignal(str)

    def __init__(self, url, temp_path, index):
        super().__init__()
        self.url = url
        self.temp_path = temp_path
        self.index = index

    def run(self):
        if "youtube.com" in self.url:
            if not YTDLP_READY:
                self.preview_failed.emit("Cần cài đặt: pip install yt-dlp")
                return
            try:
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': self.temp_path.replace('.mp3', '') + '.%(ext)s',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([self.url])
                
                final_file = self.temp_path
                if not os.path.exists(final_file):
                    base = self.temp_path.replace('.mp3', '')
                    for ext in ['.mp3', '.m4a', '.webm', '.opus']:
                        if os.path.exists(base + ext):
                            final_file = base + ext
                            break

                if os.path.exists(final_file) and os.path.getsize(final_file) > 1024:
                    self.preview_ready.emit(final_file, self.index)
                    return
            except Exception as e:
                self.preview_failed.emit(f"Lỗi YouTube: {e}")
                return

        try:
            r = requests.get(self.url, headers=BROWSER_HEADERS, stream=True, timeout=8)
            if r.status_code == 200:
                with open(self.temp_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                if os.path.exists(self.temp_path) and os.path.getsize(self.temp_path) > 1024:
                    self.preview_ready.emit(self.temp_path, self.index)
                    return
            self.preview_failed.emit("Không thể stream audio này!")
        except Exception as e:
            self.preview_failed.emit(f"Lỗi kết nối: {e}")


class DownloadAudioWorker(QThread):
    download_finished = pyqtSignal(str, str)

    def __init__(self, download_url, save_path, sound_name):
        super().__init__()
        self.download_url = download_url
        self.save_path = save_path
        self.sound_name = sound_name

    def run(self):
        if "youtube.com" in self.download_url:
            try:
                base_path = os.path.splitext(self.save_path)[0]
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': base_path + '.%(ext)s',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([self.download_url])

                final_path = base_path + ".mp3"
                if os.path.exists(final_path):
                    trim_leading_silence_file(final_path)
                    self.download_finished.emit(final_path, self.sound_name)
                    return
            except Exception:
                pass
            self.download_finished.emit("", self.sound_name)
            return

        try:
            r = requests.get(self.download_url, headers=BROWSER_HEADERS, stream=True, timeout=12)
            if r.status_code == 200:
                with open(self.save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                if os.path.getsize(self.save_path) > 1024:
                    trim_leading_silence_file(self.save_path)
                    self.download_finished.emit(self.save_path, self.sound_name)
                    return
            self.download_finished.emit("", self.sound_name)
        except Exception:
            self.download_finished.emit("", self.sound_name)


class FLStudioDelegate(QStyledItemDelegate):
    def __init__(self, parent_tree):
        super().__init__(parent_tree)
        self.tree = parent_tree

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return size.__class__(size.width(), 26)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        file_path = index.data(PATH_ROLE)
        is_dir = index.data(IS_DIR_ROLE)
        is_online = index.data(IS_ONLINE_ROLE)
        item_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        is_active = (index == self.tree.active_index and self.tree.current_samples is not None)

        if is_active:
            painter.fillRect(rect, QColor("#14241B"))
            painter.setPen(QPen(QColor("#00E676"), 1))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
        elif option.state & option.state.State_Selected:
            painter.fillRect(rect, QColor("#282D32"))

        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        fm = QFontMetrics(font)
        indent = rect.left() + 4

        if is_dir:
            is_expanded = self.tree.isExpanded(index)
            arrow_icon = "▼ " if is_expanded else "▶ "
            folder_icon = "📁 "
            display_str = f"{arrow_icon}{folder_icon}{item_text}"
            painter.setPen(QColor("#D69A55"))
            painter.drawText(QRect(indent, rect.top(), max(10, rect.width() - indent - 4), rect.height()),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, display_str)
            painter.restore()
            return

        action_btn_w = 22
        btn_rect = QRect(rect.right() - action_btn_w - 4, rect.top() + 2, action_btn_w, rect.height() - 4)

        if is_online:
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.setPen(QColor("#00E676"))
            painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "⬇")
        else:
            is_fav = self.tree.parent_window.is_favorite(file_path) if file_path else False
            painter.setFont(QFont("Segoe UI", 11))
            if is_fav:
                painter.setPen(QColor("#00E676"))
                painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "★")
            else:
                painter.setPen(QColor("#404040"))
                painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "☆")

        painter.setFont(font)
        prefix = "▶ " if is_active else ""
        display_name = f"{prefix}{item_text}"

        if not is_active:
            name_w = rect.width() - indent - action_btn_w - 10
            text_rect = QRect(indent, rect.top(), max(10, name_w), rect.height())
            if "⭐" in item_text:
                painter.setPen(QColor("#FFD54F"))
            else:
                painter.setPen(QColor("#A0E8AF" if is_online else "#C5C5C5"))
            elided = fm.elidedText(display_name, Qt.TextElideMode.ElideRight, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
            painter.restore()
            return

        mins, secs = divmod(int(self.tree.audio_duration), 60)
        ms = int((self.tree.audio_duration - int(self.tree.audio_duration)) * 10)
        time_str = f"{mins:02d}:{secs:02d}.{ms}"
        time_width = fm.horizontalAdvance(time_str) + 8

        name_width = min(fm.horizontalAdvance(display_name) + 8, int(rect.width() * 0.35))
        text_rect = QRect(indent, rect.top(), max(10, name_width), rect.height())
        time_rect = QRect(btn_rect.left() - time_width - 4, rect.top(), time_width, rect.height())

        painter.setPen(QColor("#00E676"))
        elided = fm.elidedText(display_name, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        painter.setPen(QColor("#69F0AE"))
        painter.drawText(time_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, time_str)

        wave_left = text_rect.right() + 6
        wave_right = time_rect.left() - 6
        wave_width = max(10, wave_right - wave_left)
        wave_rect = QRect(wave_left, rect.top() + 4, wave_width, rect.height() - 8)

        painter.fillRect(wave_rect, QColor("#0D1410"))
        mid_y = wave_rect.top() + (wave_rect.height() / 2.0)
        painter.setPen(QPen(QColor("#1A2B20"), 1))
        painter.drawLine(wave_rect.left(), int(mid_y), wave_rect.right(), int(mid_y))

        samples = self.tree.current_samples
        num_points = wave_rect.width()
        chunk_size = max(1, len(samples) // num_points)

        grad = QLinearGradient(0, wave_rect.top(), 0, wave_rect.bottom())
        grad.setColorAt(0.0, QColor("#B9F6CA"))
        grad.setColorAt(0.5, QColor("#00E676"))
        grad.setColorAt(1.0, QColor("#00C853"))
        painter.setPen(QPen(QBrush(grad), 1.0))

        half_h = (wave_rect.height() / 2.0) - 1.0
        for i in range(num_points):
            start = i * chunk_size
            chunk = samples[start:start + chunk_size]
            if len(chunk) == 0:
                continue
            y_top = mid_y - (np.max(chunk) * half_h)
            y_bottom = mid_y - (np.min(chunk) * half_h)
            if abs(y_bottom - y_top) < 1.0:
                y_bottom = y_top + 1.0
            painter.drawLine(wave_rect.left() + i, int(y_top), wave_rect.left() + i, int(y_bottom))

        if self.tree.playhead_progress > 0.0:
            playhead_x = wave_rect.left() + int(self.tree.playhead_progress * wave_rect.width())
            painter.setPen(QPen(QColor("#FFFFFF"), 1.2))
            painter.drawLine(playhead_x, wave_rect.top(), playhead_x, wave_rect.bottom())

        painter.restore()


class DraggableFileTreeView(QTreeView):
    def __init__(self, parent_window=None):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.active_index = QModelIndex()
        self.current_samples = None
        self.audio_duration = 0.0
        self.playhead_progress = 0.0
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setHeaderHidden(True)
        self.drag_start_pos = QPoint()
        self.setItemDelegate(FLStudioDelegate(self))

    def set_active_audio(self, index, samples, duration):
        old_index = self.active_index
        self.active_index = index
        self.current_samples = samples
        self.audio_duration = duration
        self.playhead_progress = 0.0
        if old_index.isValid():
            self.update(old_index)
        if self.active_index.isValid():
            self.update(self.active_index)

    def set_playhead(self, progress):
        self.playhead_progress = max(0.0, min(1.0, progress))
        if self.active_index.isValid():
            self.update(self.active_index)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            index = self.indexAt(event.pos())
            if index.isValid():
                rect = self.visualRect(index)
                if event.pos().x() >= rect.right() - 28:
                    is_online = index.data(IS_ONLINE_ROLE)
                    if is_online:
                        self.parent_window.download_online_sound(index)
                    else:
                        file_path = index.data(PATH_ROLE)
                        if file_path and not index.data(IS_DIR_ROLE):
                            self.parent_window.toggle_favorite(file_path)
                            self.update(index)
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        index = self.indexAt(self.drag_start_pos)
        if not index.isValid():
            return
        file_path = self.parent_window.get_ready_filepath(index)
        if file_path and os.path.isfile(file_path):
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setUrls([QUrl.fromLocalFile(file_path)])
            drag.setMimeData(mime_data)
            drag.exec(Qt.DropAction.CopyAction)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Space:
            if self.parent_window:
                self.parent_window.toggle_play_pause()
            event.accept()
            return
        super().keyPressEvent(event)
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            curr_idx = self.currentIndex()
            if curr_idx.isValid() and self.parent_window:
                self.parent_window.play_from_index(curr_idx)


class SoundFXFactory(QMainWindow):
    def __init__(self):
        super().__init__()
        # Title thương hiệu DUCTAM24VN TOOLS
        self.setWindowTitle("Sound FX Factory - DUCTAM24VN TOOLS")
        self.resize(410, 750)

        # Tích hợp Logo vào App Icon & Taskbar
        if os.path.exists(LOGO_FILENAME):
            self.setWindowIcon(QIcon(LOGO_FILENAME))

        self.favorite_dir = os.path.abspath(FAVORITE_DIR_NAME)
        self.download_dir = os.path.abspath(DOWNLOAD_DIR_NAME)
        self.cache_dir = os.path.abspath(CACHE_DIR_NAME)
        self.preview_cache_dir = os.path.abspath(".preview_stream")

        os.makedirs(self.favorite_dir, exist_ok=True)
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.preview_cache_dir, exist_ok=True)

        self.current_playing_file = None
        self.is_paused = False
        self.audio_duration = 0.0
        self.current_view_mode = "ALL"

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.update_playhead)

        self.folders = self.load_saved_folders()
        self.search_worker = None
        self.stream_worker = None
        self.download_worker = None

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 4)
        main_layout.setSpacing(5)

        # --- BRAND HEADER: LOGO + DUCTAM24VN TOOLS ---
        brand_header = QHBoxLayout()
        brand_header.setSpacing(8)

        # Logo Image
        self.lbl_logo = QLabel()
        if os.path.exists(LOGO_FILENAME):
            pix = QPixmap(LOGO_FILENAME).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.lbl_logo.setPixmap(pix)
        else:
            self.lbl_logo.setText("💠")
            self.lbl_logo.setStyleSheet("font-size: 16px;")
        brand_header.addWidget(self.lbl_logo)

        # Brand Text
        brand_title_box = QVBoxLayout()
        brand_title_box.setSpacing(0)
        lbl_title = QLabel("SOUND FX FACTORY")
        lbl_title.setStyleSheet("font-weight: 900; font-size: 13px; color: #00E676; letter-spacing: 1px;")
        lbl_author = QLabel("DUCTAM24VN TOOLS")
        lbl_author.setStyleSheet("font-weight: bold; font-size: 10px; color: #00B0FF; letter-spacing: 0.5px;")
        brand_title_box.addWidget(lbl_title)
        brand_title_box.addWidget(lbl_author)
        brand_header.addLayout(brand_title_box)
        brand_header.addStretch()

        main_layout.addLayout(brand_header)

        # Tab bar
        tab_bar = QHBoxLayout()
        tab_bar.setSpacing(4)

        self.btn_tab_all = QPushButton("📂 All")
        self.btn_tab_all.clicked.connect(self.switch_to_all)

        self.btn_tab_down = QPushButton("📥 Download")
        self.btn_tab_down.clicked.connect(self.switch_to_download)

        self.btn_tab_fav = QPushButton("★ Fav")
        self.btn_tab_fav.clicked.connect(self.switch_to_fav)

        self.btn_add = QPushButton("+ Add")
        self.btn_add.clicked.connect(self.add_folder_dialog)

        tab_bar.addWidget(self.btn_tab_all)
        tab_bar.addWidget(self.btn_tab_down)
        tab_bar.addWidget(self.btn_tab_fav)
        tab_bar.addWidget(self.btn_add)
        main_layout.addLayout(tab_bar)

        # Search Bar
        search_box = QHBoxLayout()
        search_box.setSpacing(3)
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Tìm meme (VD: sợ quá sợ quá độ mixi, cười, punch)...")
        self.txt_search.returnPressed.connect(self.start_smart_search)
        self.txt_search.setStyleSheet("""
            QLineEdit {
                background-color: #22252A;
                border: 1px solid #3B4048;
                border-radius: 3px;
                color: #FFF;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #00E676;
            }
        """)

        btn_search = QPushButton("Tìm")
        btn_search.clicked.connect(self.start_smart_search)
        btn_search.setFixedWidth(45)

        search_box.addWidget(self.txt_search)
        search_box.addWidget(btn_search)
        main_layout.addLayout(search_box)

        self.status_lbl = QLabel("Sẵn sàng")
        self.status_lbl.setStyleSheet("color: #777; font-size: 10px; margin-left: 2px;")
        main_layout.addWidget(self.status_lbl)

        # Tree View
        self.tree_model = QStandardItemModel()
        self.tree = DraggableFileTreeView(self)
        self.tree.setModel(self.tree_model)
        self.tree.clicked.connect(self.on_item_clicked)
        self.tree.expanded.connect(self.on_item_expanded)
        main_layout.addWidget(self.tree)

        # Footer bản quyền
        footer_lbl = QLabel("© DUCTAM24VN TOOLS - High Quality Sound FX Manager")
        footer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_lbl.setStyleSheet("color: #444; font-size: 9px; padding-top: 2px;")
        main_layout.addWidget(footer_lbl)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #16181A;
                color: #C0C0C0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QTreeView {
                background-color: #1C1E22;
                border: 1px solid #2B2E33;
                border-radius: 3px;
                padding: 2px;
                outline: 0;
            }
            QPushButton {
                background-color: #262A30;
                color: #DCDCDC;
                border: 1px solid #383E48;
                padding: 4px 10px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #313740;
                color: #00E676;
                border-color: #00E676;
            }
        """)

        self.switch_to_all()

    def start_smart_search(self):
        query = self.txt_search.text().strip()
        if not query:
            return

        self.status_lbl.setText(f"Đang quét tìm âm thanh sạch nhất: '{query}'...")
        self.status_lbl.setStyleSheet("color: #00E676; font-size: 10px;")

        self.search_worker = SmartMemeSearchWorker(query)
        self.search_worker.results_ready.connect(self.on_search_results)
        self.search_worker.error_occurred.connect(lambda e: self.status_lbl.setText(e))
        self.search_worker.start()

    def on_search_results(self, results):
        self.current_view_mode = "ONLINE"
        self.btn_tab_all.setStyleSheet("")
        self.btn_tab_down.setStyleSheet("")
        self.btn_tab_fav.setStyleSheet("")
        self.tree_model.clear()
        self.tree.active_index = QModelIndex()
        self.tree.current_samples = None

        if not results:
            self.status_lbl.setText("Không tìm thấy âm thanh phù hợp.")
            return

        self.status_lbl.setText(f"Đã đề xuất {len(results)} kết quả âm thanh sạch nhất! Bấm nghe thử.")
        for item_data in results:
            name = item_data["name"]
            url = item_data["url"]

            item = QStandardItem(name)
            item.setData(False, IS_DIR_ROLE)
            item.setData(True, IS_ONLINE_ROLE)
            item.setData(url, ONLINE_DOWNLOAD_URL_ROLE)
            self.tree_model.appendRow(item)

    def download_online_sound(self, index):
        download_url = index.data(ONLINE_DOWNLOAD_URL_ROLE)
        sound_name = index.data(Qt.ItemDataRole.DisplayRole)
        if not download_url:
            return

        clean_name = "".join(c for c in sound_name if c.isalnum() or c in (' ', '_', '-')).strip()
        clean_name = clean_name.replace("Clean", "").strip()
        save_file = os.path.join(self.download_dir, f"{clean_name}.mp3")

        self.status_lbl.setText(f"Đang lưu vào Sound FX Download: {clean_name}...")
        self.status_lbl.setStyleSheet("color: #00E676; font-size: 10px;")

        self.download_worker = DownloadAudioWorker(download_url, save_file, clean_name)
        self.download_worker.download_finished.connect(self.on_download_complete)
        self.download_worker.start()

    def on_download_complete(self, save_path, sound_name):
        if save_path:
            self.status_lbl.setText(f"✔ Đã tải '{sound_name}' vào 'Sound FX Download'!")
            if self.current_view_mode == "DOWNLOAD":
                self.switch_to_download()
        else:
            self.status_lbl.setText(f"Lỗi khi tải sound: {sound_name}")

    def switch_to_all(self):
        self.current_view_mode = "ALL"
        self.btn_tab_all.setStyleSheet("background-color: #1B382B; color: #00E676; border-color: #00E676;")
        self.btn_tab_down.setStyleSheet("")
        self.btn_tab_fav.setStyleSheet("")
        self.tree_model.clear()
        self.tree.active_index = QModelIndex()
        self.tree.current_samples = None

        valid_folders = [f for f in self.folders if os.path.exists(f)]
        if not valid_folders:
            self.status_lbl.setText("Chưa có folder! Bấm '+ Add' để thêm thư mục.")
            return

        self.status_lbl.setText(f"Đã nạp {len(valid_folders)} thư mục.")
        for folder_path in valid_folders:
            folder_item = QStandardItem(os.path.basename(folder_path) or folder_path)
            folder_item.setData(folder_path, PATH_ROLE)
            folder_item.setData(True, IS_DIR_ROLE)
            folder_item.setData(False, IS_LOADED_ROLE)
            folder_item.appendRow(QStandardItem("Đang nạp..."))
            self.tree_model.appendRow(folder_item)

    def switch_to_download(self):
        self.current_view_mode = "DOWNLOAD"
        self.btn_tab_down.setStyleSheet("background-color: #1B382B; color: #00E676; border-color: #00E676;")
        self.btn_tab_all.setStyleSheet("")
        self.btn_tab_fav.setStyleSheet("")
        self.tree_model.clear()
        self.tree.active_index = QModelIndex()
        self.tree.current_samples = None

        down_item = QStandardItem("📥 Sound FX Download")
        down_item.setData(self.download_dir, PATH_ROLE)
        down_item.setData(True, IS_DIR_ROLE)
        down_item.setData(False, IS_LOADED_ROLE)
        self.tree_model.appendRow(down_item)

        self.populate_children(down_item, self.download_dir)
        self.tree.expand(down_item.index())
        self.status_lbl.setText("Thư mục Sound FX Download")

    def switch_to_fav(self):
        self.current_view_mode = "FAV"
        self.btn_tab_fav.setStyleSheet("background-color: #1B382B; color: #00E676; border-color: #00E676;")
        self.btn_tab_all.setStyleSheet("")
        self.btn_tab_down.setStyleSheet("")
        self.tree_model.clear()
        self.tree.active_index = QModelIndex()
        self.tree.current_samples = None

        fav_item = QStandardItem("★ Favorite FX")
        fav_item.setData(self.favorite_dir, PATH_ROLE)
        fav_item.setData(True, IS_DIR_ROLE)
        fav_item.setData(False, IS_LOADED_ROLE)
        self.tree_model.appendRow(fav_item)

        self.populate_children(fav_item, self.favorite_dir)
        self.tree.expand(fav_item.index())
        self.status_lbl.setText("Thư mục Favorite FX")

    def on_item_expanded(self, index):
        item = self.tree_model.itemFromIndex(index)
        if item and item.data(IS_DIR_ROLE) and not item.data(IS_LOADED_ROLE):
            folder_path = item.data(PATH_ROLE)
            item.removeRows(0, item.rowCount())
            if folder_path and os.path.exists(folder_path):
                self.populate_children(item, folder_path)
            item.setData(True, IS_LOADED_ROLE)

    def populate_children(self, parent_item, folder_path):
        try:
            entries = sorted(os.listdir(folder_path), key=lambda s: s.lower())
        except Exception:
            return

        for name in entries:
            full_p = os.path.join(folder_path, name)
            if os.path.isdir(full_p):
                sub_item = QStandardItem(name)
                sub_item.setData(full_p, PATH_ROLE)
                sub_item.setData(True, IS_DIR_ROLE)
                sub_item.setData(False, IS_LOADED_ROLE)
                sub_item.appendRow(QStandardItem("Đang nạp..."))
                parent_item.appendRow(sub_item)

        for name in entries:
            full_p = os.path.join(folder_path, name)
            if os.path.isfile(full_p) and name.lower().endswith(AUDIO_EXTENSIONS):
                file_item = QStandardItem(name)
                file_item.setData(full_p, PATH_ROLE)
                file_item.setData(False, IS_DIR_ROLE)
                parent_item.appendRow(file_item)

    def on_item_clicked(self, index):
        if index.data(IS_DIR_ROLE):
            if self.tree.isExpanded(index):
                self.tree.collapse(index)
            else:
                self.tree.expand(index)
            return
        self.play_from_index(index)

    def play_from_index(self, index):
        is_online = index.data(IS_ONLINE_ROLE)
        if is_online:
            preview_url = index.data(ONLINE_DOWNLOAD_URL_ROLE)
            if not preview_url:
                return

            h = hashlib.md5(preview_url.encode('utf-8')).hexdigest()[:10]
            temp_path = os.path.join(self.preview_cache_dir, f"preview_{h}.mp3")

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1024:
                self.play_file(temp_path, index)
                return

            self.status_lbl.setText("Đang trích xuất audio nghe thử...")
            self.status_lbl.setStyleSheet("color: #00E676; font-size: 10px;")

            self.stream_worker = StreamPreviewWorker(preview_url, temp_path, index)
            self.stream_worker.preview_ready.connect(self.on_preview_stream_ready)
            self.stream_worker.preview_failed.connect(lambda msg: self.status_lbl.setText(msg))
            self.stream_worker.start()
            return

        path = index.data(PATH_ROLE)
        if path and not index.data(IS_DIR_ROLE) and os.path.isfile(path) and path.lower().endswith(AUDIO_EXTENSIONS):
            self.play_file(path, index)

    def on_preview_stream_ready(self, temp_path, index):
        self.status_lbl.setText("Đang phát nghe thử [Ấn ⬇ để tải về máy]")
        self.play_file(temp_path, index)

    def play_file(self, path, index):
        try:
            self.timer.stop()
            if PYGAME_READY:
                pygame.mixer.music.stop()

            mono_data, duration, sr = read_audio_data_safe(path)
            self.audio_duration = duration
            self.current_playing_file = path
            self.is_paused = False

            self.tree.set_active_audio(index, mono_data, duration)

            if PYGAME_READY:
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                self.timer.start()
        except Exception as err:
            self.status_lbl.setText(f"Lỗi đọc file: {err}")

    def toggle_play_pause(self):
        if not PYGAME_READY or not self.current_playing_file:
            return

        if pygame.mixer.music.get_busy() and not self.is_paused:
            pygame.mixer.music.pause()
            self.is_paused = True
            self.timer.stop()
        elif self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.timer.start()
        else:
            curr_idx = self.tree.currentIndex()
            if curr_idx.isValid():
                self.play_from_index(curr_idx)

    def update_playhead(self):
        if not PYGAME_READY:
            return
        if not pygame.mixer.music.get_busy() and not self.is_paused:
            self.timer.stop()
            self.tree.set_playhead(1.0)
            return
        pos_ms = pygame.mixer.music.get_pos()
        if pos_ms >= 0 and self.audio_duration > 0:
            self.tree.set_playhead((pos_ms / 1000.0) / self.audio_duration)

    def get_ready_filepath(self, index):
        return index.data(PATH_ROLE)

    def add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục Audio / SFX")
        if folder:
            norm_folder = os.path.normpath(folder)
            if norm_folder not in self.folders:
                self.folders.append(norm_folder)
                self.save_folders()
            self.switch_to_all()

    def is_favorite(self, file_path):
        if not file_path:
            return False
        fav_path = os.path.join(self.favorite_dir, os.path.basename(file_path))
        return os.path.exists(fav_path)

    def toggle_favorite(self, file_path):
        base_name = os.path.basename(file_path)
        fav_path = os.path.join(self.favorite_dir, base_name)
        if os.path.exists(fav_path):
            try:
                os.remove(fav_path)
            except Exception:
                pass
        else:
            try:
                shutil.copy2(file_path, fav_path)
            except Exception:
                pass
        if self.current_view_mode == "FAV":
            self.switch_to_fav()

    def load_saved_folders(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return [os.path.normpath(p) for p in data if isinstance(p, str) and os.path.exists(p)]
            except Exception:
                return []
        return []

    def save_folders(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.folders, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SoundFXFactory()
    window.show()
    sys.exit(app.exec())