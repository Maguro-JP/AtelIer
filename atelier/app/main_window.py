"""AtelIer のウィンドウ。チャットで頼むと絵を描いて並べる。

  python atelier/app/main_window.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from atelier.files.paths import HOME as DATA  # noqa: E402


def attach_streams():
    """pythonw.exe で起動すると標準の出力が None になり、模型を取るときの進み表示（tqdm）が書き込めずに落ちた。
    出力が無いときは記録のファイル（DATA/atelier.log）へ向ける"""
    for stream in (sys.stdout, sys.stderr):
        # Windows の窓（コンソール）の文字コードは cp1252 などで、日本語を書くと UnicodeEncodeError で落ちた。
        # 書けない文字は置き換えて書き続ける
        enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if stream is not None and hasattr(stream, "reconfigure") and enc != "utf8":
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        log = open(DATA / "atelier.log", "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        import os
        log = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


attach_streams()


def isolate():
    """前の版やほかのアプリが残した環境の設定に引っ張られないようにする。
    Hugging Face の置き場や「取らない」の設定が残っていると、選んだ置き場と違う所を見たり、模型を取れなかったりした"""
    import os
    from atelier.files.paths import HUB
    for k in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE",
              "HF_DATASETS_OFFLINE", "DIFFUSERS_CACHE"):
        os.environ.pop(k, None)
    os.environ["HF_HUB_CACHE"] = str(HUB)
    # 利用者の Python に入っている物（site-packages）を読まない。版の違う部品が混ざって起動しなかった
    import site
    user = getattr(site, "USER_SITE", None)
    if user:
        import os.path
        mine = os.path.normcase(user)   # Windows は道の大文字小文字を区別しないので、そろえてから比べる
        sys.path[:] = [p for p in sys.path if not os.path.normcase(p).startswith(mine)]


isolate()

# 部品はデータの置き場に入れる（入れたアプリ本体の場所は書き換えない）
for lib in (DATA / "simple" / "lib", DATA / "gen" / "lib", DATA / "llm" / "lib"):
    if lib.exists() and str(lib) not in sys.path:
        sys.path.insert(0, str(lib))

try:
    __import__("PySide6")   # 入っているかだけを確かめる
except ImportError:
    # 初めての起動だけ、ウィンドウの部品（PySide6）を入れる。6.12.0 は Python 3.11 で None の参照数を減らしすぎ、
    # 線を数百本引くと落ちた。落ちないことを確かめた 6.9.3 に固定する
    import subprocess
    lib = DATA / "simple" / "lib"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--target", str(lib), "PySide6-Essentials==6.9.3"], check=True,
                   stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    sys.path.insert(0, str(lib))


from PySide6.QtCore import QSettings, QSize, Qt, QThread  # noqa: E402
from PySide6.QtGui import QAction, QActionGroup  # noqa: E402
from PySide6.QtWidgets import (QTabWidget, QApplication, QDockWidget, QFileDialog,  # noqa: E402
                               QHBoxLayout, QListWidget, QMainWindow,
                               QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QSlider, QSpinBox, QToolBar, QVBoxLayout, QWidget)


from atelier.panels.activity_panel import ActivityPanel, show_ops  # noqa: E402
from atelier.paint.canvas import Canvas  # noqa: E402
from atelier.panels.color_panel import ColorPanel  # noqa: E402
from atelier.ui.icons import icon  # noqa: E402
from atelier.ai.engine import Studio  # noqa: E402
from atelier.app.settings import Settings  # noqa: E402

from atelier.app.window.constants import MARK_OK, PANEL, PANEL_ORDER, REDPEN_SHAPES, SHAPE_TIPS, TOOLS  # noqa: E402
from atelier.app.window.image_convert import fit_size, gray_to_pil, qimage_from_pil, qimage_to_pil, qimage_to_pil_rgba  # noqa: E402
from atelier.app.window.jobs import Bridge, Job, PAUSED_HEAD, PhaseAsk, Task, fresh_stop, guarded  # noqa: E402
from atelier.app.window.process_check import crashed_before, pid_alive  # noqa: E402
from atelier.app.window.widgets import Navigator, NoteEdit, PanelTitle, Reference, _BIG_ICON_STYLE, _big_icon_style, exec_once  # noqa: E402
from atelier.app.window.ai_drawing import AiDrawingMixin  # noqa: E402
from atelier.app.window.ai_results import AiResultsMixin  # noqa: E402
from atelier.app.window.canvas_menu import CanvasMenuMixin  # noqa: E402
from atelier.app.window.chat import ChatMixin  # noqa: E402
from atelier.app.window.files import FilesMixin  # noqa: E402
from atelier.app.window.history import HistoryMixin  # noqa: E402
from atelier.app.window.image_editing import ImageEditingMixin  # noqa: E402
from atelier.app.window.layers_and_selection import LayersAndSelectionMixin  # noqa: E402
from atelier.app.window.layout import LayoutMixin  # noqa: E402
from atelier.app.window.models import ModelsMixin  # noqa: E402
from atelier.app.window.modes_and_logos import ModesAndLogosMixin  # noqa: E402
from atelier.app.window.prompts import PromptsMixin  # noqa: E402
from atelier.app.window.redpen import RedpenMixin  # noqa: E402
from atelier.app.window.results_and_progress import ResultsAndProgressMixin  # noqa: E402
from atelier.app.window.settings_and_debug import SettingsAndDebugMixin  # noqa: E402
from atelier.app.window.tour import TourMixin  # noqa: E402

# 前からこのモジュールの名前で読まれている物（試験、道具、拡張）を、置き場を移したあとも同じ名前で出す
__all__ = ['Bridge', 'Job', 'MARK_OK', 'Navigator', 'NoteEdit', 'PANEL', 'PANEL_ORDER', 'PAUSED_HEAD', 'PanelTitle', 'PhaseAsk', 'REDPEN_SHAPES', 'Reference', 'SHAPE_TIPS', 'TOOLS', 'Task', '_BIG_ICON_STYLE', '_big_icon_style', 'crashed_before', 'exec_once', 'fit_size', 'fresh_stop', 'gray_to_pil', 'guarded', 'pid_alive', 'qimage_from_pil', 'qimage_to_pil', 'qimage_to_pil_rgba', 'QFileDialog', 'Window', 'dark', 'main', 'THEME', 'DATA', 'ROOT']


class Window(FilesMixin, AiDrawingMixin, AiResultsMixin, ChatMixin, PromptsMixin, RedpenMixin, CanvasMenuMixin, LayersAndSelectionMixin, ImageEditingMixin, ModelsMixin, HistoryMixin, ModesAndLogosMixin, SettingsAndDebugMixin, ResultsAndProgressMixin, LayoutMixin, TourMixin, QMainWindow):
    """作画ソフトの並び: 左に頼みの欄、真ん中に絵、右に描いた絵の一覧、下に進み"""

    def __init__(self, studio: Studio | None = None):
        super().__init__()
        from atelier.ui import wheel_guard as wheelguard
        wheelguard.install()   # 欄のスクロールで種や強さが変わらないようにする
        from atelier.ui import type_guard as typeguard
        typeguard.install()    # 打っている欄のキーをショートカットに取られないようにする
        self.settings = Settings()
        from atelier.ai import memory_budget as membudget
        membudget.set_mode(self.settings.get("mem_mode"))   # メモリの使い方（設定で選ぶ。既定は自動）
        self.layout_store = QSettings("AtelIer", "atelier")   # 配置・テーマ・AI プリセット・ツアーの済み
        self.last_text = ""
        self._own_studio = studio is None
        # 拡張（atelier/extensions.py）が足す口。描く仕組みを作るより先に用意する（_studio_from_settings が studio_hooks を呼ぶ）
        self.studio_hooks: list = []          # 描く仕組みを作り直すたびに呼ぶ関数（引数は Studio）
        self.expression_sources: list = []    # 表情差分の絵を返す関数。返すのは (書き出すときの名前, 絵の道の並び)
        self.studio = studio or self._studio_from_settings()
        self.setWindowTitle("AtelIer")
        self.resize(1400, 900)
        self.images: list[str] = []
        self.thread: QThread | None = None
        self.bg_pending = 0   # 裏の糸で回している、画面に答えを返す前の処理の数

        self.canvas = Canvas()
        self.canvas.set_cursor_style(self.settings.get("cursor"))
        self.canvas.new_canvas()
        self.setCentralWidget(self.canvas)
        self.canvas.menu_wanted.connect(self.canvas_menu)
        self.canvas.hide_cursor_after = 1500 if self.settings.get("cursor_hide") == "止まったら隠す" else 0

        # 左: 頼み（チャット）
        # チャットは相談と操作の場、描く内容は AI の欄に書く（1 行の欄に描く頼み・操作・質問が混ざり、会話として読めなかった）
        from atelier.panels.chat_panel import ChatPanel, EnterEdit
        self.chat = ChatPanel()
        self.chat.sent.connect(self.chat_send)
        self.chat.open_image = self.open_chat_image
        self.entry = EnterEdit("描きたい絵を書く（例: 赤いマフラーの女の子 全身）", lines=3)
        self.entry.setToolTip("描いてほしい絵を日本語か英語で書き、Enter か「描く」で描きます（Shift+Enter で改行）")
        self.entry.returnPressed.connect(self.send)
        self.button = QPushButton(icon("ai", "#ffffff"), " 描く")
        self.button.setToolTip("AI で描く（Enter）")
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.send)
        self.stop_button = QPushButton("■")
        self.stop_button.setToolTip("止める")
        self.stop_button.setFixedWidth(40)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        self.entry.setMinimumWidth(120)
        row = QHBoxLayout()
        row.addWidget(self.button, 1)
        row.addWidget(self.stop_button)
        # 描き方: 新しく描くか、キャンバスの絵（下描き・ラフ）を元に描き直すか
        self.mode = QComboBox()
        self.mode.addItems(["新規", "ラフから", "直す"])
        self.mode.setToolTip("新規: 白紙から描く\nラフから: キャンバスの線の形に沿って描く")
        self.size_pick = QComboBox()
        self.size_pick.setToolTip("描く絵の大きさ")
        for label, wh in (("縦 832×1216", (832, 1216)), ("横 1216×832", (1216, 832)), ("正方形 1024", (1024, 1024))):
            self.size_pick.addItem(label, wh)
        self.strength = QSlider(Qt.Horizontal)
        self.strength.setRange(30, 100)
        self.strength.setValue(int(self.settings.get("rough_follow") * 100))
        self.strength_label = QLabel(f"{self.strength.value()}%")
        self.strength.setToolTip("ラフに沿う強さ。大きいほどラフの線の形どおりに描く")
        self.strength.valueChanged.connect(lambda v: self.strength_label.setText(f"{v}%"))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed(0)
        for hidden in (self.mode, self.size_pick):   # 選ぶのは AI の欄のボタン。こちらは値の入れ物
            hidden.setParent(self)
            hidden.hide()
        follow = QHBoxLayout()
        follow.addWidget(self.strength, 1)
        follow.addWidget(self.strength_label)
        # AI の欄は描き方の設定（描き方・大きさ・ラフに沿う強さ・絵の模型）だけ。頼みを書くのはチャットの欄
        from atelier.panels.ai_panel import AiPanel
        ask = QVBoxLayout()
        ask.setContentsMargins(0, 0, 0, 0)
        self.ai_panel = AiPanel(self)
        ask.addWidget(self.ai_panel)
        follow.setContentsMargins(0, 0, 0, 0)
        self.ai_panel.sections["詳しい設定"].body.addWidget(QLabel("ラフに沿う強さ"))
        self.ai_panel.sections["詳しい設定"].body.addLayout(follow)
        self.model_label = QPushButton()
        self.model_label.setObjectName("modelButton")
        self.model_label.setToolTip("絵の模型。押すと切り替えられます")
        self.model_label.clicked.connect(lambda: self.ai_menu.exec(self.model_label.mapToGlobal(self.model_label.rect().bottomLeft())))
        ask_page = QWidget()
        ask_page.setLayout(ask)
        # 外の入れ物（描き方）は ai_pages。ai_tabs は AI の欄のタブを出し入れする TabDocks が使う
        self.ai_pages = QTabWidget()
        # 中身の縦の流れは AI の欄のタブごとに持つ（描くボタンをタブの外に出し、流しても隠れないようにする）
        ask_scroll = ask_page
        self.ai_pages.addTab(ask_scroll, "描き方")
        self.ai_pages.setTabBarAutoHide(True)   # タブが 1 つのときは見出しだけで足りる
        dock = QDockWidget("AI", self)
        dock.setWidget(self.ai_pages)
        dock.setObjectName("chat")
        dock.setFeatures(PANEL)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        # AI の欄の「描く内容」: 頼みを書く欄、模型に渡る言葉の目安、禁止ワード、「描く」と止める、直近の言葉
        tl = self.ai_panel.sections["描く内容"].body
        neg_head = QLabel("禁止ワード")
        neg_head.setObjectName("sectionHead")
        neg_head.setToolTip(self.ai_panel.negative.toolTip())
        self.ai_panel.negative.textChanged.connect(lambda _t: self._apply_avoid())
        self.entry.textChanged.connect(self.ai_panel.preview_timer.start)
        # 模型に渡る言葉の目安は欄に常に出さず、書く欄にカーソルを合わせたときだけ出す。
        # 目安の札（aipanel の preview）は隠した入れ物に入れ、出し入れされても画面には出ない
        self._preview_hold = QWidget(self)
        self._preview_hold.hide()
        self.ai_panel.preview.setParent(self._preview_hold)
        self.last_model_prompt = ""
        self.ai_panel.preview_timer.timeout.connect(self._entry_tip)
        self.ai_panel.update_preview()
        self._entry_tip()
        for w in self._tip_watch():
            if w is not self.entry:
                w.installEventFilter(self)   # 欄（と中の表示面）にカーソルを合わせたら、言葉を作り直して出す
        line = self.ai_panel.draw_bar   # 描くボタンはタブの外。どのタブからも押せる
        # 作成枚数は描くボタンのすぐ左に置く（前は指示のタブの中の模型の下にあり、見つからなかった）。
        # 詳しい設定の 1・2・4 枚のボタンと同じ値
        self.ai_panel.count_spin.setToolTip("作成枚数。一度に描く枚数です（直すときは 1 枚）")
        self.ai_panel.count_spin.setAccessibleName("作成枚数")
        count_label = QLabel("枚数")   # 欄だけだと何の数か分からず、見つからなかった
        count_label.setBuddy(self.ai_panel.count_spin)
        count_label.setToolTip(self.ai_panel.count_spin.toolTip())
        self.count_label = count_label
        # 描き方のモード（AI モード / 精度優先）。設定の奥に入れると切り替えられず、どちらで描いたか分からなかった
        from atelier.app.settings import AI_MODE, PRECISE
        self.way_pick = QComboBox()
        self.way_pick.addItem("AI モード", AI_MODE)
        self.way_pick.addItem("精度優先", PRECISE)
        self.way_pick.setItemData(0, AI_MODE, Qt.ToolTipRole)
        self.way_pick.setItemData(1, PRECISE + "。構図 → 体型と姿勢 → 線画 → 塗り → 仕上げの順に、工程ごとに検品して描く", Qt.ToolTipRole)
        self.way_pick.setToolTip("描き方。AI モード: 今までの描き方で速く描く。精度優先: 工程に分けて描き、工程ごとに検品する")
        self.way_pick.setAccessibleName("描き方")
        self.way_pick.setCurrentIndex(1 if self.settings.get("draw_way") == PRECISE else 0)
        self.way_pick.currentIndexChanged.connect(self._pick_way)
        # 描くボタンの帯に並べると、狭い欄で描くボタンが幅 0 に潰れたので、帯のすぐ上の 1 行に置く
        way_row = QHBoxLayout()
        way_row.setSpacing(4)
        way_label = QLabel("描き方")
        way_label.setBuddy(self.way_pick)
        way_label.setToolTip(self.way_pick.toolTip())
        way_row.addWidget(way_label)
        way_row.addWidget(self.way_pick, 1)
        outer = self.ai_panel.layout()
        outer.insertLayout(max(0, outer.indexOf(line)), way_row)
        line.addWidget(count_label)
        # 描くボタンが横に伸びると、数の欄が幅 0 に潰れて見えなくなった。数が読めて打てる幅を必ず取る
        self.ai_panel.count_spin.setMinimumWidth(self.ai_panel.count_spin.fontMetrics().horizontalAdvance("9999") + 40)
        line.addWidget(self.ai_panel.count_spin)
        line.addWidget(self.button, 1)
        line.addWidget(self.stop_button)
        # 書く欄の下のボタン。登録した言葉（★）を先に、そのあとに直近に頼んだ言葉を新しい順に並べる。
        # 押すと書く欄に入り、ダブルクリックでそのまま描く。右クリックで登録・外す・消す。書く欄で ↑↓ でも呼び出せる
        # 音声入力。押して話すと、話した言葉を描くワードの欄に入れる（atelier/agent/voice.py。手元の模型 faster-whisper を先に使う）。
        # 使えない環境でもボタンは出し、何を入れれば使えるかをツールチップと押したときの知らせに出す
        from atelier.agent import voice
        self.mic_button = voice.mic_button(self.entry, parent=self)
        line.addWidget(self.mic_button)
        self.fav_button = QPushButton("☆")
        self.fav_button.setToolTip("書く欄の言葉を描くワードに登録する（もう一度押すと外す）")
        self.fav_button.setFixedWidth(40)
        self.fav_button.clicked.connect(self._toggle_fav)
        self.entry.textChanged.connect(lambda: self.fav_button.setText(
            "★" if (t := self.entry.text().strip()) and t in self.favorite_prompts() else "☆"))
        line.addWidget(self.fav_button)
        from atelier.ui.flow_layout import FlowLayout
        from PySide6.QtWidgets import QSizePolicy
        # 登録・履歴のボタンは欄の横幅で折り返して並べる（横 1 行だと欄からはみ出し、奥のボタンが見えなかった）
        self.tips = FlowLayout()
        tips_box = QWidget()
        tips_box.setLayout(self.tips)
        tips_box.setObjectName("scrollInner")
        self.tips_scroll = tips_box
        self.entry.installEventFilter(self)
        self._load_prompts()
        # 単語のお気に入りの段（描くワードの登録の中、文のまとまりの下）と、読めなかった語の段（atelier/panels/word_panel.py）
        from atelier.panels import word_panel as wordpanel
        self.word_row = wordpanel.WordRow(self.entry, on_change=self._words_changed)
        self.lost_row = wordpanel.LostRow(self.entry, on_change=self._words_changed)
        self.entry.setContextMenuPolicy(Qt.CustomContextMenu)
        self.entry.customContextMenuRequested.connect(
            lambda pos: wordpanel.entry_menu(self.entry, self._words_changed).exec(self.entry.mapToGlobal(pos)))
        # 禁止ワードの登録。描くワードの登録と同じく、押すと禁止ワードの欄に入る。設定に残すので更新でも消えない
        self.neg_fav_button = QPushButton("☆")
        self.neg_fav_button.setFixedWidth(40)
        self.neg_fav_button.setToolTip("禁止ワードの欄の言葉を登録する（もう一度押すと外す）")
        self.neg_fav_button.clicked.connect(self._toggle_neg_fav)
        self.ai_panel.negative.textChanged.connect(lambda _t: self.neg_fav_button.setText(
            "★" if (t := self.ai_panel.negative.text().strip()) and t in self.negative_presets() else "☆"))
        self.neg_tips = FlowLayout()
        neg_box = QWidget()
        neg_box.setLayout(self.neg_tips)
        neg_box.setObjectName("scrollInner")
        self.neg_tips_box = neg_box
        self._load_negatives()
        # 指示のタブの並び: 模型、描くワード、描くワードの登録、禁止ワード、禁止ワードの登録
        model_head = QLabel("絵の模型")   # 見出しは 1 つだけ（前は見出し「模型」とボタンの「絵の模型: 」が重なっていた）
        model_head.setObjectName("sectionHead")
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.addWidget(self.model_label)
        word_head = QLabel("描くワード")
        word_head.setObjectName("sectionHead")
        word_head.setToolTip("描きたい絵を言葉で書きます。下のボタンは登録した言葉と、前に頼んだ言葉です")
        neg_row = QHBoxLayout()
        neg_row.setContentsMargins(0, 0, 0, 0)
        neg_row.addWidget(self.ai_panel.negative, 1)
        neg_row.addWidget(self.neg_fav_button)
        for wdg in (model_head, word_head, neg_head, self.ai_panel.negative):
            wdg.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        tl.addWidget(model_head)
        tl.addLayout(model_row)
        self._lora_row()
        tl.addWidget(word_head)
        tl.addWidget(self.entry)
        tl.addWidget(self.lost_row)
        tl.addWidget(tips_box)
        tl.addWidget(self.word_row)
        tl.addWidget(neg_head)
        tl.addLayout(neg_row)
        tl.addWidget(neg_box)
        # 真ん中の下: チャット。吹き出しの会話と、複数行の書く欄
        talk = QDockWidget("チャット", self)
        talk.setWidget(self.chat)
        talk.setObjectName("talk")
        talk.setFeatures(PANEL)
        self.addDockWidget(Qt.BottomDockWidgetArea, talk)

        # 右: 描いた絵。AI の今の工程・進み・時間と、描いた絵の履歴
        self.activity = ActivityPanel()
        self.history = self.activity.list
        # ダブルクリックは今の絵に重ねる（今の絵を閉じない）。右クリックで開く・同じ設定で描き直す
        # 押すとその絵をキャンバスに出す（元に戻すで戻せる）。ダブルクリックは今の絵に重ねる
        self.history.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.show_history_image(it.data(Qt.UserRole)))
        # ダブルクリックはその絵を見せるだけ（レイヤーに足すと勝手に増えた）。重ねるのは右クリックの「今の絵に重ねる」
        self.history.itemDoubleClicked.connect(lambda it: it.data(Qt.UserRole) and self.show_history_image(it.data(Qt.UserRole)))
        self.history.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self._history_menu)
        # 履歴で選んだ絵を Delete キーで消す（確かめてからごみ箱へ）。キャンバスの Delete（選んだ所を消す）とぶつからないよう履歴の中だけで効かせる
        hist_del = QAction("消す（ごみ箱へ）", self.history, shortcut="Delete", shortcutContext=Qt.WidgetWithChildrenShortcut)
        hist_del.triggered.connect(lambda: self.delete_images([it.data(Qt.UserRole) for it in self.history.selectedItems()]))
        self.history.addAction(hist_del)
        hist = QDockWidget("履歴", self)
        hist.setWidget(self.activity)
        hist.setObjectName("history")
        hist.setFeatures(PANEL)
        self.addDockWidget(Qt.RightDockWidgetArea, hist)
        # 真ん中の上: 進み（工程・帯・時間）
        prog = QDockWidget("進み", self)
        prog.setWidget(self.activity.progress_view)
        self.activity.changed.connect(self.show_progress)
        prog.setObjectName("progress")
        prog.setFeatures(PANEL)
        self.addDockWidget(Qt.TopDockWidgetArea, prog)
        # 緊急停止。いつでも見える所（上の帯と進みの欄）に置き、押したら必ず止める。帯は閉じられない（隠すと止められなくなる）
        self.emergency_stop = QAction("■ 緊急停止", self)
        self.emergency_stop.setObjectName("emergencyStop")
        self.emergency_stop.setShortcut("Shift+Esc")
        self.emergency_stop.setShortcutContext(Qt.ApplicationShortcut)
        self.emergency_stop.setToolTip("動いている AI の処理を今すぐ止めます（Shift+Esc）。キャンバスは元のままです")
        self.emergency_stop.triggered.connect(self.stop)
        sbar = QToolBar("緊急停止", self)
        sbar.setObjectName("stopbar")
        sbar.addAction(self.emergency_stop)
        sbar.toggleViewAction().setEnabled(False)
        self.addToolBar(Qt.TopToolBarArea, sbar)
        self.stop_bar = sbar
        self.activity.stop_tool.setDefaultAction(self.emergency_stop)

        # 下: 進み
        self.progress = self.activity.bar   # 進みは描いた絵の欄に出す


        # 上: メニュー。メニュー・リボン・帯・欄の右クリックで同じ働きの物は、同じ QAction を使う
        # （別々に作ると、片方だけキーや働きが変わり、名前が同じで違う動きになった。リボンの「保存」は PNG の書き出しだった）
        self.build_shared_actions()
        S = self.shared
        file = self.menuBar().addMenu("ファイル")
        self.file_menu = file
        file.setToolTipsVisible(True)
        # 一括生成は描く仕事なので、絵の模型の一覧ではなくファイルのメニューに置く（模型の一覧に並ぶと、模型の名前と紛れた）
        self.batch_action = file.addAction("一括生成…", lambda: self.batch_draw())
        self.batch_action.setToolTip("頼みの一覧（1 行 1 つ、または CSV）から、枚数と種を付けて順に描き、全部をライブラリーに入れます。止めるは「止める」")
        file.addAction(S["new"])
        file.addAction(S["open"])
        edit_open = QAction("画像を開いて直す…", self, triggered=self.open_to_edit)
        edit_open.setToolTip("手元の絵を開き、赤ペンで囲んだ所だけを AI に直させます。囲みの外は変えません")
        file.addAction(edit_open)
        file.addAction(S["save"])
        file.addAction(QAction("名前を付けて保存…", self, shortcut="Ctrl+Shift+S", triggered=lambda: self.save_project(ask=True)))
        # 保存と書き出しの間。拡張はこの区切りの前に、自分のファイルの種類の項目を足す
        self.file_extension_anchor = file.addSeparator()
        out = file.addMenu("書き出す")
        out.addAction(QAction("PNG（重ねた 1 枚）…", self, shortcut="Ctrl+E", triggered=self.save_as))
        out.addAction(QAction("PSD（レイヤーごと）…", self, triggered=self.export_psd))
        # タイムラプスは表示のメニューの奥にしか書き出しが無く、見つからなかった。ファイルの「書き出す」からも出せるようにする
        out.addAction(QAction("タイムラプスを GIF に…", self, triggered=lambda: self.export_timelapse(False)))
        out.addAction(QAction("タイムラプスを動画（MP4）に…", self, triggered=lambda: self.export_timelapse(True)))
        # 置き場はボタンを並べず、1 つの下の段にまとめる（開くたびに作り直し、保存先を変えたらすぐ合うようにする）
        from atelier.files import folders
        self.folder_menu = file.addMenu("ディレクトリを開く")
        self.folder_menu.aboutToShow.connect(lambda: folders.fill_menu(self.folder_menu, self.settings, self))
        folders.fill_menu(self.folder_menu, self.settings, self)
        file.addSeparator()
        file.addAction(S["trash"])
        file.addSeparator()
        file.addAction(QAction("終了", self, shortcut="Ctrl+Q", triggered=self.close))
        edit = self.menuBar().addMenu("編集")
        edit.setToolTipsVisible(True)
        edit.addAction(S["undo"])
        edit.addAction(S["redo"])
        edit.addAction(S["redpen_clear"])
        edit.addAction(S["inspect"])
        edit.addSeparator()
        edit.addAction(S["cut"])
        edit.addAction(S["copy"])
        edit.addAction(S["copy_merged"])
        edit.addAction(S["paste"])
        edit.addAction(S["paste_in_place"])
        edit.addSeparator()
        edit.addAction(S["layer_cut"])
        edit.addAction(S["layer_copy"])
        edit.addAction(S["layer_paste"])

        # 左端: 道具
        tools = QToolBar("道具", self)
        tools.setObjectName("tools")
        tools.setIconSize(QSize(22, 22))
        tools.setMovable(True)
        self.addToolBar(Qt.LeftToolBarArea, tools)
        group = QActionGroup(self)
        self.tool_actions = {}
        # 作画ソフトでよく使う並びと同じキー（V 移動、M 選択、B ペン、E 消しゴム、G 塗り、I スポイト、H 手のひら、Z 拡大）
        for key, label, short in TOOLS:
            if key is None:
                tools.addSeparator()
                continue
            act = QAction(icon(key), label, self, checkable=True, shortcut=short,
                          triggered=lambda _=False, k=key: self.canvas.set_tool(k))
            act.setToolTip(f"{label}（{short}）")
            group.addAction(act)
            tools.addAction(act)
            self.tool_actions[key] = act
        self.tool_actions["pen"].setChecked(True)
        for k, tip in SHAPE_TIPS.items():
            self.tool_actions[k].setToolTip(tip)
        # 絵の上の R は、押して離すとぼかし、押したままドラッグすると表示を回す（canvas.on_r_tap）
        self.canvas.on_r_tap = self.tool_actions["blur"].trigger
        self.tool_actions["blur"].setToolTip("ぼかし（R）。絵の上で R を押したままドラッグすると表示を回します")
        self.extra_key_actions = []
        for text, short, fn in (("描く色と背景の色を入れ替える", "X", self.canvas.swap_colors),
                                ("色を黒と白に戻す", "D", self.canvas.reset_colors)):
            act = QAction(text, self, shortcut=short, triggered=fn)
            self.addAction(act)
            self.extra_key_actions.append(act)

        # 上: 選んだ道具の設定（太さ・濃さ・形の塗り）。作画ソフトと同じく、絵のすぐ上に置いて手元で変える
        bar = QToolBar("道具の設定", self)
        bar.setObjectName("options")
        bar.setMovable(True)
        self.addToolBar(Qt.TopToolBarArea, bar)
        self.options = bar
        self.tool_name = QLabel("ペン")
        self.tool_name.setObjectName("toolName")
        bar.addWidget(self.tool_name)
        bar.addSeparator()
        bar.addWidget(QLabel(" 太さ "))
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(1, 300)
        self.size_slider.setFixedWidth(160)
        self.size_slider.setValue(self.canvas.size)
        bar.addWidget(self.size_slider)
        self.size_box = QSpinBox()
        self.size_box.setRange(1, 300)
        self.size_box.setValue(self.canvas.size)
        self.size_box.setSuffix(" px")
        bar.addWidget(self.size_box)
        self.size_box.valueChanged.connect(lambda v: (setattr(self.canvas, "size", v), self.size_slider.setValue(v)))
        self.size_slider.valueChanged.connect(self.size_box.setValue)
        bar.addSeparator()
        bar.addWidget(QLabel(" 濃さ "))
        self.flow = QSlider(Qt.Horizontal)
        self.flow.setRange(1, 100)
        self.flow.setValue(100)
        self.flow.setFixedWidth(120)
        self.flow_label = QLabel("100%")
        self.flow.valueChanged.connect(lambda v: (setattr(self.canvas, "brush_opacity", v / 100), self.flow_label.setText(f"{v}%")))
        bar.addWidget(self.flow)
        bar.addWidget(self.flow_label)
        bar.addSeparator()
        self.fill_shapes = QCheckBox("塗り")
        self.fill_shapes.setToolTip("四角・楕円・多角形・正多角形を、線だけでなく中まで塗る")
        self.fill_shapes.toggled.connect(lambda on: setattr(self.canvas, "fill_shapes", on))
        # 帯に置いた部品は、部品ではなく帯の項目を隠さないと消えない（前は「塗り」がペンでも出たままだった）
        self.fill_shapes_act = bar.addWidget(self.fill_shapes)
        self.poly_sides = QSpinBox()
        self.poly_sides.setRange(3, 24)
        self.poly_sides.setValue(self.canvas.poly_sides)
        self.poly_sides.setSuffix(" 角")
        self.poly_sides.setToolTip("正多角形の角（辺）の数")
        self.poly_sides.valueChanged.connect(lambda v: setattr(self.canvas, "poly_sides", v))
        self.poly_sides_act = bar.addWidget(self.poly_sides)
        # 赤ペンの印の取り方。赤ペンを選んだときだけ出す（帯と右クリックにも同じ操作を置く）
        from PySide6 import QtWidgets as _qw   # 名前で読むと、この関数の後ろで読む同じ名前とぶつかる
        S = self.shared
        shape_group = QActionGroup(self)
        for key, label, tip in REDPEN_SHAPES:
            a = QAction(f"赤ペン: {label}", self, checkable=True, triggered=lambda _=False, k=key: self.set_redpen_shape(k))
            a.setToolTip(tip)
            a.setIconText(label)
            shape_group.addAction(a)
            S[f"redpen_shape:{key}"] = a
        S["redpen_shape:free"].setChecked(True)
        S["redpen_all"] = QAction("赤ペン: 全体", self, triggered=self.redpen_all,
                                  toolTip="絵の全体を赤ペンの印 1 つにします（全体を直す指示を書けます）")
        S["redpen_all"].setIconText("全体")
        box = _qw.QWidget()
        lay = _qw.QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(QLabel(" 囲み方 "))
        for k in [f"redpen_shape:{key}" for key, _l, _t in REDPEN_SHAPES] + ["redpen_all"]:
            b = _qw.QToolButton()
            b.setDefaultAction(S[k])
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            lay.addWidget(b)
        self.redpen_shape_bar = bar.addWidget(box)
        self.redpen_shape_bar.setVisible(False)
        for key, _label, _s in TOOLS:
            if key:
                self.tool_actions[key].triggered.connect(lambda _=False, k=key: self._tool_changed(k))
                self.tool_actions[key].triggered.connect(lambda _=False, k=key: self.feature_tour(k))
        self._tool_changed("pen")

        # 左上: 色（色相・彩度と明度・16 進・描く色と背景色・見本・最近使った色）
        self.color_panel = ColorPanel(self.canvas)
        self.canvas.used_color.connect(self.color_panel.remember)
        self.color_panel.eyedropper_wanted.connect(lambda: self.tool_actions["eyedropper"].trigger())
        self.canvas.text_wanted.connect(self.ask_text)
        odock = QDockWidget("カラー", self)
        odock.setObjectName("color")
        odock.setWidget(self.color_panel)
        odock.setFeatures(PANEL)
        self.addDockWidget(Qt.LeftDockWidgetArea, odock)

        # 左上: ブラシ。種類を選び、硬さ・流量・間隔・筆圧の効き方を変える
        self.brush_list = QListWidget()
        for b in self.canvas.brushes.values():
            self.brush_list.addItem(b.name)
        self.brush_list.currentTextChanged.connect(self._brush_selected)
        self.hardness = QSlider(Qt.Horizontal)
        self.hardness.setRange(0, 100)
        self.flow_s = QSlider(Qt.Horizontal)
        self.flow_s.setRange(1, 100)
        self.spacing = QSlider(Qt.Horizontal)
        self.spacing.setRange(2, 100)
        self.size_pressure = QCheckBox("筆圧→太さ")
        self.opacity_pressure = QCheckBox("筆圧→濃さ")
        self.size_pressure.setToolTip("ペンタブレットの筆圧で線の太さを変える")
        self.opacity_pressure.setToolTip("ペンタブレットの筆圧で線の濃さを変える")
        self.hardness.valueChanged.connect(lambda v: setattr(self.canvas.brush, "hardness", v / 100))
        self.flow_s.valueChanged.connect(lambda v: setattr(self.canvas.brush, "flow", v / 100))
        self.spacing.valueChanged.connect(lambda v: setattr(self.canvas.brush, "spacing", v / 100))
        self.size_pressure.toggled.connect(lambda on: setattr(self.canvas.brush, "size_pressure", on))
        self.opacity_pressure.toggled.connect(lambda on: setattr(self.canvas.brush, "opacity_pressure", on))
        bform = QFormLayout()
        self.hardness.setToolTip("縁のくっきりさ")
        self.flow_s.setToolTip("1 回に置く絵の具の量")
        self.spacing.setToolTip("筆の跡の間隔")
        bform.addRow("硬さ", self.hardness)
        bform.addRow("流量", self.flow_s)
        bform.addRow("間隔", self.spacing)
        bform.addRow(self.size_pressure)
        bform.addRow(self.opacity_pressure)
        # 手ぶれ補正と左右対称は、ペン・消しゴム・ぼかし・スプレー・指先のなぞる道具すべてに効く
        self.stabilizer = QSpinBox()
        from atelier.paint.canvas import STABILIZER_MAX
        self.stabilizer.setRange(0, STABILIZER_MAX)
        self.stabilizer.setSingleStep(5)
        self.stabilizer.setToolTip(f"手ぶれ補正の強さ（0〜{STABILIZER_MAX}）。大きいほど線がカーソルに遅れてついてきて、なめらかになる（0 で切る）")
        self.stabilizer.valueChanged.connect(lambda v: setattr(self.canvas, "stabilizer", v))
        bform.addRow("手ぶれ補正", self.stabilizer)
        # 対称: 線対称（左右・上下・上下左右）と点対称。表示のメニューの「対称定規」と同じ設定
        from atelier.paint.canvas import SYMMETRY
        self.symmetry = QComboBox()
        self.symmetry.addItem("なし", "")
        for key, label in SYMMETRY.items():
            self.symmetry.addItem(label, key)
        self.symmetry.setToolTip("描いた線と図形を、軸の反対側にも同時に描きます。軸の丸をドラッグすると軸を動かせます")
        self.symmetry.currentIndexChanged.connect(lambda _i: self.canvas.set_symmetry(self.symmetry.currentData()))
        bform.addRow("対称", self.symmetry)
        # 定規: なぞる線と直線を、平行線・同心円・放射・パースの向きに沿わせる。表示のメニューの「定規」と同じ設定
        from atelier.paint.drawing_assist import RULERS
        self.ruler = QComboBox()
        self.ruler.addItem("なし", "")
        for key, label in RULERS.items():
            self.ruler.addItem(label, key)
        self.ruler.setToolTip("なぞる線と直線を定規に沿わせます。緑の丸をドラッグすると、中心・消失点・平行線の向きを動かせます")
        self.ruler.currentIndexChanged.connect(lambda _i: self.canvas.set_ruler(self.ruler.currentData()))
        bform.addRow("定規", self.ruler)
        self.quickshape = QCheckBox("描いて止めると形を整える")
        self.quickshape.setToolTip("ペンで描き終えて少し止めると、直線・円・楕円・四角・三角に整えます。元に戻すで整える前の線に戻ります")
        self.quickshape.toggled.connect(lambda on: setattr(self.canvas, "quickshape", on))
        bform.addRow(self.quickshape)
        bbox = QWidget()
        bbox.setLayout(bform)
        # タブで「ブラシ」（種類を選ぶ）と「設定」（硬さ・流量・間隔・筆圧）を切り替える
        self.brush_tabs = QTabWidget()
        self.brush_tabs.addTab(self.brush_list, "ブラシ")
        self.brush_tabs.addTab(bbox, "設定")
        # 見本の線。ブラシ・太さ・色・濃さ・硬さ・間隔・筆圧・色の出方を変えるたびに描き直す
        from atelier.panels.brush_preview import BrushPreview
        self.brush_preview = BrushPreview(self.canvas)
        for sig in (self.size_box.valueChanged, self.flow.valueChanged, self.hardness.valueChanged, self.flow_s.valueChanged,
                    self.spacing.valueChanged, self.size_pressure.toggled, self.opacity_pressure.toggled,
                    self.color_panel.color_changed, self.canvas.color_picked, self.brush_list.currentTextChanged,
                    self.canvas.brush_changed, self.color_panel.mode_changed):
            sig.connect(lambda *_a: self.brush_preview.update())
        bwrap = QWidget()
        bl = QVBoxLayout(bwrap)
        bl.setContentsMargins(6, 4, 6, 4)
        bl.setSpacing(4)
        bl.addWidget(self.brush_preview)
        bl.addWidget(self.brush_tabs, 1)
        bdock = QDockWidget("ブラシ", self)
        bdock.setObjectName("brushes")
        bdock.setWidget(bwrap)
        bdock.setFeatures(PANEL)
        self.addDockWidget(Qt.LeftDockWidgetArea, bdock)
        self.brush_list.setCurrentRow(0)
        self.canvas.brush_changed.connect(self.size_box.setValue)
        self.build_status()

        # 右下: レイヤー（縮小図・表示・ロック・名前・並べ替え。atelier/panels/layer_panel.py）
        from atelier.panels.layer_panel import LayerPanel
        self.layer_panel = LayerPanel(self.canvas)
        self.layer_panel.shared = self.shared   # 右クリックにメニューと同じ操作（同じキー）を出す
        self.layer_list, self.layer_opacity = self.layer_panel.list, self.layer_panel.opacity
        self.canvas.refused.connect(lambda why: self.statusBar().showMessage(why, 6000))
        lbox = self.layer_panel
        self.navigator = Navigator(self.canvas)
        self.layer_tabs = QTabWidget()
        self.layer_tabs.addTab(lbox, "レイヤー")
        self.layer_tabs.setTabBarAutoHide(True)
        # 右の上: 表示（全体の縮小図と参考画像）
        self.reference = Reference()
        self.view_tabs = QTabWidget()
        self.view_tabs.addTab(self.navigator, "全体")
        self.view_tabs.addTab(self.reference, "参考画像")
        vdock = QDockWidget("表示", self)
        vdock.setWidget(self.view_tabs)
        vdock.setObjectName("view")
        vdock.setFeatures(PANEL)
        self.addDockWidget(Qt.RightDockWidgetArea, vdock)
        self.view_dock = vdock
        ldock = QDockWidget("レイヤー", self)
        ldock.setWidget(self.layer_tabs)
        ldock.setObjectName("layers")
        ldock.setFeatures(PANEL)
        self.addDockWidget(Qt.RightDockWidgetArea, ldock)
        self.canvas.marked.connect(lambda: self.mode.setCurrentIndex(2))
        self.canvas.redpen.on_change = self._redpen_changed   # 赤ペンで囲んだら、AI の欄を「直す」にする
        self.canvas.note_wanted.connect(self.edit_note)
        self.canvas.autosel_wanted.connect(self.run_autosel)
        self.canvas.layer_deleted.connect(self.trash_layer_file)
        # 自動保存: 変わってから 2 分ごとに書く
        self.dirty = False
        self.canvas.history_changed.connect(lambda: setattr(self, "dirty", True))
        from PySide6.QtCore import QTimer
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(120_000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()
        # 裏の糸が動いている間は、Python の後片付け（gc）を画面の糸だけで回す（gc_guard）
        self.gc_timer = QTimer(self)
        self.gc_timer.setInterval(500)
        self.gc_timer.timeout.connect(self.gc_guard)
        self.gc_timer.start()
        # 操作の履歴（履歴の欄の「操作」のタブ）
        self.canvas.history_changed.connect(lambda: show_ops(self.activity.ops, self.canvas))
        self.activity.ops.currentRowChanged.connect(lambda r: r >= 0 and self.canvas.go_to(r))
        show_ops(self.activity.ops, self.canvas)

        view = self.menuBar().addMenu("表示")
        view.setToolTipsVisible(True)
        for k in ("fit", "actual", "zoom_in", "zoom_out", "zoom_ask", None, "rotate_left", "rotate_right", "rotate_dial",
                  "rotate_reset", "flip_view", "view_reset", None, "grid", "op_history"):
            view.addAction(S[k]) if k else view.addSeparator()
        self.build_symmetry_menu(view.addMenu("対称定規"))
        self.build_ruler_menu(view.addMenu("定規"))
        # 図形の道具。おすすめの配置の道具の帯には出さない（初めはシンプルにする）ので、メニューからも選べるようにする
        shapes = view.addMenu("図形")
        shapes.setToolTipsVisible(True)
        for k in ("line", "rect", "ellipse", "polyshape", "regpoly"):
            shapes.addAction(self.tool_actions[k])
        view.addSeparator()
        from atelier.paint.timelapse import Recorder
        self.recorder = Recorder()
        self.recorder.enabled = self.settings.get("timelapse") == "記録する"
        self.canvas.stroke_done.connect(self._record)
        self.tl_action = QAction("タイムラプスを記録する", self, checkable=True, checked=self.recorder.enabled)
        self.tl_action.setToolTip("線を引くたび、AI が描く工程ごとに写しを撮り、描いた過程を残します")
        self.tl_action.toggled.connect(self._set_timelapse)
        # タイムラプスの 4 つは 1 つの小さなメニューにまとめる（表示のメニューが長く、絵の見え方の項目が埋もれた）
        tl = view.addMenu("タイムラプス")
        tl.setToolTipsVisible(True)
        tl.addAction(self.tl_action)
        tl.addAction(QAction("タイムラプスを見る…", self, shortcut="Ctrl+Shift+T", triggered=self.open_timelapse))
        tl.addAction(QAction("タイムラプスを消す", self, triggered=self.recorder.clear))
        tl.addAction(QAction("GIF・動画を開く…", self, triggered=self.open_player))
        view.addSeparator()
        self.pin_action = QAction("表示する絵を固定する", self, checkable=True)
        self.pin_action.setToolTip("固定すると、AI が新しく描いた絵はキャンバスに出さず履歴に入れます。外すと最新の絵を出します")
        self.pin_action.toggled.connect(self._set_pinned)
        view.addAction(self.pin_action)
        from atelier.ui import themes
        self.theme_menu = view.addMenu("テーマ")
        self.theme_menu.aboutToShow.connect(self._fill_theme_menu)
        # モード（atelier/app/modes.py）。起動したときに選び、ここからいつでも替える。替えても絵とレイヤーはそのまま
        from atelier.app import modes as _modes
        self.mode_menu = view.addMenu("モード")
        self.mode_menu.setToolTipsVisible(True)
        self.mode_actions = {}
        self.mode_menu_end = self.mode_menu.addSeparator()   # モードの並びの終わり。モードはこの前に足す
        for key in _modes.MODES:
            self.add_mode(key)
        self.mode_menu.addAction("このモードのツアー", lambda: _modes.show_tour(self, getattr(self, "app_mode", _modes.DEFAULT), force=True)
                                 ).setToolTip("今のモードの使い方を 3 枚で案内します")
        self.mode_ask_action = self.mode_menu.addAction("起動したときにモードを聞く")
        self.mode_ask_action.setCheckable(True)
        self.mode_ask_action.setChecked(not _modes.stored(self.layout_store)[1])
        self.mode_ask_action.setToolTip("外すと、次の起動から窓を出さずに今のモードで開きます")
        self.mode_ask_action.toggled.connect(lambda on: self.layout_store.setValue("mode/ask", int(on)))
        from PySide6.QtWidgets import QMenu
        self.ai_menu = QMenu("AI", self)   # 窓を親にして作る（文字だけで足すと、作り直しの知らせの前に消えていた）
        self.menuBar().addMenu(self.ai_menu)
        # 開くたびに手元の模型を数え直してから作る。開いている間に変わった分は、閉じたあとに作り直す
        self.ai_menu.aboutToShow.connect(self._open_ai_menu)
        self.ai_menu.aboutToHide.connect(self._ai_menu_hidden)
        self._have_images: set[str] | None = None   # 手元にある絵の模型。裏の糸で数え、メニューを開くたびには数えない
        self._fill_ai_menu()
        self.rescan_models()
        self.logo_menu = QMenu("ロゴ・スタンプ", self)   # ロゴ・マーク、スタンプを作る。atelier/ai/logo_maker.py
        self.menuBar().addMenu(self.logo_menu)
        self.logo_menu.aboutToShow.connect(self._fill_logo_menu)
        self._fill_logo_menu()
        # 加工（綺麗にする・ディテール・拡大・画風など）。右クリックと同じ項目を、メニューバーからも選べるようにする。
        # 右クリックは隠した物・よく使う物で並びが変わるが、ここは全部を処理の種類ごとに出す（探せば必ずある所）
        self.finish_menu = QMenu("加工", self)
        self.menuBar().addMenu(self.finish_menu)
        self.finish_menu.aboutToShow.connect(self._fill_finish_menu)
        self._fill_finish_menu()
        from atelier.models import ratings
        ratings.on_change(self._models_changed)
        setting_menu = self.menuBar().addMenu("設定")
        setting_menu.addAction(QAction("設定…", self, shortcut="Ctrl+,", triggered=self.open_settings))
        setting_menu.addAction(QAction("キーの設定…", self, triggered=self.open_keys))
        setting_menu.addAction(QAction("作風の登録…", self, triggered=self.open_favorites,
                                       toolTip="好きな作家・作品の言葉を名前で残し、描くときに足します"))
        setting_menu.addAction(QAction("参考画像を探す…", self, triggered=self.ask_reference_search))
        setting_menu.addAction(QAction("単語辞書…", self, triggered=self.open_word_dict,
                                       toolTip="頼みの語がどのタグになったか、描いて使えた語と訳、学びの様子を見ます"))
        setting_menu.addAction(QAction("予約の一覧", self, triggered=lambda: self.say(self.scheduler.summary())))
        setting_menu.addAction(QAction("確かめの窓をまた出す", self, triggered=self.reset_confirms,
                                       toolTip="「次から聞かない」を選んだ確かめの窓を、また出すようにします"))
        setting_menu.addAction(QAction("予約を全部消す", self, triggered=lambda: (self.scheduler.clear(), self.say("予約を全部消しました"))))
        sel = self.menuBar().addMenu("選択範囲")
        sel.addAction(S["select_all"])
        sel.addAction(S["deselect"])
        sel.addSeparator()
        sel.addAction(self.tool_actions["select"])
        sel.addAction(self.tool_actions["lasso"])
        sel.addAction(self.tool_actions["polygon"])
        sel.addAction(self.tool_actions["autosel"])
        sel.addSeparator()
        sel.addAction(S["sel_clear"])
        sel.addAction(S["sel_fill"])
        sel.addAction(S["copy"])
        sel.addAction(S["cut"])
        sel.addAction(QAction("選択範囲を AI で直す", self, triggered=self.fix_marked,
                              toolTip="選択範囲の中だけを、指示の欄の言葉で AI が直します"))
        layer_menu = self.menuBar().addMenu("レイヤー")
        layer_menu.setToolTipsVisible(True)
        layer_menu.addAction(S["add_layer"])
        layer_menu.addAction(S["dup_layer"])
        layer_menu.addAction(S["delete_layer"])
        layer_menu.addAction(S["clear_layer"])
        layer_menu.addSeparator()
        for k in ("layer_cut", "layer_copy", "layer_paste", "via_copy", "via_cut"):
            layer_menu.addAction(S[k])
        layer_menu.addSeparator()
        layer_menu.addAction(S["flip_layer_h"])
        layer_menu.addAction(S["flip_layer_v"])
        layer_menu.addSeparator()
        layer_menu.addAction(QAction("画像をレイヤーとして読み込む…", self, triggered=self.import_layer))
        layer_menu.addAction(QAction("レイヤーを PNG で保存…", self, triggered=self.save_layer_png))
        layer_menu.addAction(QAction("全部のレイヤーを PNG で書き出す…", self, triggered=self.export_layers_png))
        layer_menu.addSeparator()
        layer_menu.addAction(S["merge_down"])
        layer_menu.addAction(QAction("見えているレイヤーを結合", self, shortcut="Ctrl+Shift+E", triggered=self.canvas.merge_visible))
        layer_menu.addAction(QAction("結合して元の画像に上書き保存…", self, triggered=self.merge_and_overwrite))

        # ウィンドウ: 欄ごとの表示と、並べ方（整列・別ウィンドウ・自由配置）
        # ライブラリー: 作品・資料・好み。試験（描く仕組みを渡したとき）は、その出力の置き場の中に作って本物を汚さない
        from atelier.files.library import Library
        from atelier.panels.library_panel import LibraryPanel
        self.library = Library(None if studio is None else Path(self.studio.out) / ".library")
        from atelier.files.paths import HOME
        from atelier.files.trash import Trash
        self.trash = Trash(HOME / "trash" if studio is None else Path(self.studio.out) / ".trash")
        # 0.5.19 までの版が書いた赤ペンの直しだけの絵を、履歴・ライブラリーから外してごみ箱へ移す（開いたあと裏で 1 度だけ）
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self, self.sweep_old_redpen)   # 窓に結ぶ（先に閉じて消えた窓では呼ばない）
        self.library_panel = LibraryPanel(self)
        self.thread_main = QThread.currentThread()
        self._learn_runner()
        # チャットの会話は閉じても残す（ライブラリーと同じく、試験では出力の置き場の中に作る）
        self.chat.decorate = self.offer_prompt
        self.chat.set_store((DATA if studio is None else Path(self.studio.out)) / "chat.json")
        libdock = QDockWidget("ライブラリー", self)
        libdock.setWidget(self.library_panel)
        libdock.setObjectName("library")
        libdock.setFeatures(PANEL)
        self.addDockWidget(Qt.RightDockWidgetArea, libdock)
        self.panels = {"color": (odock, Qt.LeftDockWidgetArea), "brushes": (bdock, Qt.LeftDockWidgetArea),
                       "library": (libdock, Qt.RightDockWidgetArea),
                       "chat": (dock, Qt.RightDockWidgetArea),
                       "history": (hist, Qt.RightDockWidgetArea), "layers": (ldock, Qt.LeftDockWidgetArea),
                       "view": (self.view_dock, Qt.RightDockWidgetArea), "talk": (talk, Qt.BottomDockWidgetArea),
                       "progress": (prog, Qt.TopDockWidgetArea)}
        from PySide6.QtWidgets import QScrollArea
        for key in self.panels:
            # 中身が欄より大きいときは欄の中で流す。中身の大きさで欄が縮まず、ウィンドウが画面（ノートの高さ 720 など）からはみ出した
            d = self.panels[key][0]
            inner = d.widget()
            box = QScrollArea()
            box.setWidget(inner)
            box.setWidgetResizable(True)
            box.setFrameShape(QScrollArea.NoFrame)
            # 縦も横も、収まらないときだけ流す棒を出す
            box.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            box.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            box.setMinimumSize(0, 0)
            inner.setObjectName(inner.objectName() or "scrollInner")
            d.setWidget(box)
        for key, (d, _area) in self.panels.items():
            d.setTitleBarWidget(PanelTitle(d))
            # 欄の中で、自分のメニューを持たない所を右クリックしても、使えるメニューを出す（押しても何も出ない所を作らない）
            d.setContextMenuPolicy(Qt.CustomContextMenu)
            d.customContextMenuRequested.connect(lambda pos, d=d, k=key: exec_once(self.area_menu(k), d.mapToGlobal(pos)))
            # 欄の境目をドラッグして上下左右に広げ縮めできる。狭めすぎて中身が潰れない大きさだけ決める
            d.setMinimumSize(160, 80)
            d.topLevelChanged.connect(lambda floating, d=d: self._as_window(d, floating))
            d.dockLocationChanged.connect(lambda _area, d=d: d.titleBarWidget().expand())
            d.visibilityChanged.connect(lambda on, d=d: self._appear(d, on))
        self.tools = tools
        self.setDockNestingEnabled(True)
        # GroupedDragging: タブにまとめた欄を、まとめたまま動かせる（1 枚ずつはタブを引いて外へ出す）
        self.setDockOptions(QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks | QMainWindow.AnimatedDocks
                            | QMainWindow.GroupedDragging)
        # 欄どうしを重ねるとタブになる（欄の見出しを別の欄の上へドラッグ）。タブは上に出す
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)
        self.tabifiedDockWidgetActivated.connect(lambda d: isinstance(d.titleBarWidget(), PanelTitle) and d.titleBarWidget().expand())
        # 欄の帯: 欄ごとのアイコン。押すと欄を出す・隠す。初めは右の端に置き、上下左右のどこへでも動かせる
        bar = QToolBar("欄の帯", self)
        bar.setObjectName("panelbar")
        bar.setIconSize(QSize(22, 22))
        self.addToolBar(Qt.RightToolBarArea, bar)
        self.panel_bar = bar
        from atelier.ui.popup import ProgressPopup
        self.progress_popup = ProgressPopup(self)   # 進みは右下のポップアップに出す（上の欄は「ウィンドウ」から出せる）
        win = self.menuBar().addMenu("ウィンドウ")
        keys = {"brushes": "F3", "color": "F5", "chat": "F6", "history": "F7", "layers": "F8", "view": "F9", "talk": "F10",
                "progress": "F11", "library": "F12"}
        icons = {"color": "palette", "brushes": "brush", "chat": "ai", "history": "history", "layers": "layers", "view": "view",
                 "talk": "chat", "progress": "progress", "library": "library"}
        self.panel_actions = {}
        for k in PANEL_ORDER:
            d = self.panels[k][0]
            # Qt の toggleViewAction は、タブの裏に隠れた欄も「出ている」と数え、押すと隠した。
            # ライブラリーは履歴・表示とタブで重なっているので、F12 や欄の帯で押しても前に出ず、開けなくなっていた。
            # 裏に隠れている欄は前に出し、前に出ている欄だけを隠す
            act = QAction(d.windowTitle(), self, checkable=True)   # チェックが付いていれば表示中
            act.setChecked(not d.isHidden())
            act.setShortcut(keys[k])
            act.setIcon(icon(icons[k]))
            act.setToolTip(f"{d.windowTitle()}（{keys[k]}）")
            act.triggered.connect(lambda _on, k=k: self.toggle_panel(k))
            d.visibilityChanged.connect(lambda _on, d=d, act=act: act.setChecked(not d.isHidden()))
            self.panel_actions[k] = act
            win.addAction(act)
            bar.addAction(act)
        tact = tools.toggleViewAction()
        tact.setShortcut("F4")
        win.addAction(tact)
        win.addAction(bar.toggleViewAction())
        win.addAction(self.options.toggleViewAction())
        self._bars_menu = win
        self._ribbon_toggle = win
        # 帯は上下左右のどこにでも置ける（帯の端をドラッグしても動く）
        panel_where = win.addMenu("欄の位置")
        for k in PANEL_ORDER:
            d = self.panels[k][0]
            sub = panel_where.addMenu(d.windowTitle())
            for label, area in (("左", Qt.LeftDockWidgetArea), ("右", Qt.RightDockWidgetArea), ("下", Qt.BottomDockWidgetArea),
                                ("上", Qt.TopDockWidgetArea)):
                sub.addAction(QAction(label, self, triggered=lambda _=False, d=d, area=area: self.move_panel(d, area)))
        where = win.addMenu("帯の位置")
        self._where = where
        for name, tb in (("道具の帯", tools), ("欄の帯", bar)):
            sub = where.addMenu(name)
            for label, area in (("左", Qt.LeftToolBarArea), ("右", Qt.RightToolBarArea), ("上", Qt.TopToolBarArea),
                                ("下", Qt.BottomToolBarArea)):
                sub.addAction(QAction(label, self, triggered=lambda _=False, tb=tb, area=area: self.place_bar(tb, area)))
        win.addSeparator()
        win.addAction(QAction("すべての欄を畳む", self, triggered=lambda: self._collapse_all(True)))
        win.addAction(QAction("すべての欄を広げる", self, triggered=lambda: self._collapse_all(False)))
        win.addAction(QAction("メインウィンドウを最小化", self, shortcut="Ctrl+M", triggered=self.showMinimized))
        win.addSeparator()
        win.addAction(QAction("すべての欄を表示", self, triggered=lambda: self._show_all(True)))
        # Tab は出す・隠すを入れ替える。隠すだけだと、もう一度押しても戻らず、帯も消えて操作できなくなった
        win.addAction(QAction("欄を隠す・出す（絵だけを見る）", self, shortcut="Tab", triggered=self.toggle_all))
        win.addSeparator()
        # 初めの並びに戻すのはここの 1 か所（前は「設定」にも同じ働きの項目があった）
        win.addAction(QAction("並びを初めの形に戻す", self, triggered=self.reset_layout))
        win.addAction(QAction("リボンの並びを変える…", self, triggered=self.edit_ribbon_order))
        win.addAction(QAction("すべて別ウィンドウにする", self, triggered=self.float_all))
        win.addAction(QAction("自由配置（欄をドラッグして好きな所に置く）", self, triggered=self.free_layout))
        self.build_ribbon()
        self.build_bottom()
        self.build_quick_bar()
        win.addAction(self.quick_bar.toggleViewAction())
        win.addSeparator()
        self.edit_menus_action = QAction("メニューを編集…", self, triggered=lambda: self.edit_menus().exec())
        self.edit_menus_action.setToolTip("メニューの項目を隠す・出す・並べ替える")
        self.edit_bars_action = QAction("帯を編集…", self, triggered=lambda: self.edit_bars().exec())
        self.edit_bars_action.setToolTip("帯に操作を足す・外す、区切りを入れる、並べ替える")
        self.lock_bars_action = QAction("帯を固定する", self, checkable=True)
        self.lock_bars_action.setToolTip("帯とリボンのタブをドラッグで動かせなくします")
        self.lock_bars_action.toggled.connect(lambda on: self.bars_editor.set_locked(on))
        for a in (self.edit_menus_action, self.edit_bars_action, self.lock_bars_action):
            win.addAction(a)
        self.build_layout_menu()
        from atelier.ui.look import Look
        themes.load_custom(self.layout_store)
        self.look = Look(self)
        self._look(themes.current)
        self._show_model()
        help_menu = self.menuBar().addMenu("ヘルプ")
        help_menu.addAction(S["tour"])
        help_menu.addAction(QAction("操作方法", self, triggered=lambda: self.open_help("manual")))
        help_menu.addAction(QAction("落ちた記録を開く", self, triggered=self.open_crashlog))
        help_menu.addAction(QAction("手順書（入れ方・模型の置き方・困ったとき）", self, triggered=lambda: self.open_help("install")))
        help_menu.addAction(QAction("記録の置き場を開く", self, triggered=self.open_logs))
        stats = QAction("あなたの統計…", self, triggered=self.open_userstats)
        stats.setToolTip("良い・悪いと判定した絵、よく使う言葉・模型・画風・大きさ、頼み直しの回数を見ます。記録はここで消せます")
        help_menu.addAction(stats)
        help_menu.addAction(QAction("更新を確かめる", self, triggered=lambda: self.check_update(manual=True)))
        from atelier.ui import tours
        self.new_tours_menu = help_menu.addMenu("新しいツアー")   # まだ見ていない新しい案内。数を名前に出す
        help_menu.aboutToShow.connect(self._fill_new_tours)   # 開くたびに数を合わせる
        self._fill_new_tours()
        each = help_menu.addMenu("機能ごとの案内")
        for key, (name, _steps) in tours.catalog(self).items():
            each.addAction(QAction(name, self, triggered=lambda _=False, k=key: tours.show(self, k, force=True)))
        each.addSeparator()   # 案内の出し方も「機能ごとの案内」の中にまとめる
        auto = QAction("機能を初めて使うときに案内を出す", self, checkable=True)
        auto.setChecked(tours.enabled(self))
        auto.toggled.connect(lambda on: self.layout_store.setValue("feature_tours", int(on)))
        each.addAction(auto)
        each.addAction(QAction("機能の案内をもう一度出す", self, triggered=lambda: (tours.reset(self),
                                                                                       self.notify("次に使うときに、また案内します", "ok"))))
        from atelier.ui import i18n
        # 拡張を付ける。メニューと欄を全部作り終えたあとで、メニューの言葉の引き換え・欄の並びを戻す・キーの割り当て・
        # メニューの編集（どれも今ある項目を見て当てる）より前に呼ぶ。あとに呼ぶと、拡張の項目だけが訳されず、覚えた並びにも入らない
        from atelier import extensions
        extensions.attach_all(self)
        self._fill_logo_menu()   # 拡張が表情差分の出どころ（expression_sources）を足すと項目が増えるので、付けたあとに作り直す
        lang = self.settings.get("language")
        i18n.translate_menus(self.menuBar(), lang)   # 英語を選んだときだけ換える（表に無い言葉は日本語のまま）
        # ボタン・欄・ツールチップ・ダイアログ・右クリックのメニューは、出すたびに引き換える（前はメニューだけが英語になった）
        from PySide6.QtWidgets import QApplication
        i18n.install(QApplication.instance(), lang)
        from atelier.agent.scheduler import Scheduler
        self.scheduler = Scheduler(self.settings.store, self)   # チャットの「10 分後に」「毎晩」の予約。開いている間だけ動く
        self.scheduler.fire.connect(self._scheduled)
        QTimer.singleShot(5000, self.scheduler.tick)   # 閉じていた間に過ぎた予約は、開いて落ち着いてから 1 回だけ行う
        self._ribbon_toggle.addAction(self.ribbon_bar.toggleViewAction())
        self._bars_menu.addAction(self.bottom_bar.toggleViewAction())
        for name, tb in (("下の帯", self.bottom_bar), ("道具の設定の帯", self.options)):
            sub = self._where.addMenu(name)
            for label, area in (("上", Qt.TopToolBarArea), ("下", Qt.BottomToolBarArea)):
                sub.addAction(QAction(label, self, triggered=lambda _=False, tb=tb, area=area: self.place_bar(tb, area)))
        # AI の欄のタブの順と、外へ出したタブの欄。欄の位置を戻す（restoreState）より先に欄を作る
        from atelier.ui.tab_dock import TabDocks
        self.ai_tabs = TabDocks(self, self.ai_panel, self.layout_store)
        self.ai_tabs.restore()
        state = self.layout_store.value("state9")   # 欄の並びを変えたら名前を変え、古い並びを読まない
        if state is not None:
            self.restoreGeometry(self.layout_store.value("geometry9"))
            if not self.restoreState(state):
                self.arrange()
            for d, _area in self.panels.values():
                if d.isFloating():
                    self._as_window(d, True)   # 戻した並びで外に出ている欄も、ふつうの窓の枠にする
        else:
            self.arrange()
        for old in ("state8", "geometry"):   # 前の版の並び。読むと欄が画面の外や縦長のまま戻った
            self.layout_store.remove(old)
        from atelier.app import key_bindings as keys
        keys.apply(self, self.layout_store)
        self.setup_customizing()
        # 起動したときの道具。初めは手（絵を動かして見る）。描くときにペンを選ぶ。設定でペンにもできる
        self.select_tool("pen" if self.settings.get("first_tool") == "ペン" else "hand")
        self.apply_debug_mode()   # デバッグモード（既定はオフ。オンなら下に「記録」の欄を出す）



from atelier.ui.themes import qss as _qss
THEME = _qss()   # 既定のテーマ（atelier/ui/themes.py）



def dark(app: QApplication, name: str | None = None):
    """テーマの色を当てる。name が無ければ前に選んだテーマ（初めはナイト: 暗い灰色の地に赤とオレンジの差し色）"""
    from atelier.ui import themes
    store = QSettings("AtelIer", "atelier")
    themes.load_custom(store)
    if name is None:
        name = store.value("theme", themes.DEFAULT)
    return themes.apply(app, name)


def main():
    from atelier.app import crash_log as crashlog
    from atelier.files.paths import adopt_stray
    crashlog.install()
    try:
        from atelier.app.migrate import import_once
        if import_once(DATA, QSettings):   # CharacterDesigner の部品・設定・記録を、初めての起動で引き継ぐ
            for lib in (DATA / "simple" / "lib", DATA / "gen" / "lib", DATA / "llm" / "lib"):
                if lib.exists() and str(lib) not in sys.path:
                    sys.path.insert(0, str(lib))
    except OSError:
        pass
    try:
        adopt_stray()   # 前の版がずれた置き場（cd）に書いた ★・非表示などを、本来の置き場へ合わせる
    except OSError:
        pass
    app = QApplication(sys.argv)
    dark(app)
    from atelier.ui import window_fit as fit
    fit.install(app)
    from atelier.ai import logo_maker as logo
    if logo.icon_png() is not None:   # 選ばれたアイコンがあるときだけ替える。無い間は今のまま
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(logo.icon_png())))
    from atelier import extensions
    extensions.load_bundled()        # 同梱の拡張
    extensions.load_entry_points()   # 別のパッケージで入れた拡張。窓を作る前に登録する（窓が作り終わりに付ける）
    w = Window()
    w.show()
    w.ask_models()
    w.ask_words_once()
    w.upgrade_models()
    w.check_ai()
    opened = sys.argv[sys.argv.index("--open") + 1] if "--open" in sys.argv[:-1] else None
    if opened:
        w.open_path(opened)   # AI の結果を別ファイルで開くとき。自動保存から戻すかは聞かない
    else:
        w.offer_restore()
        w.offer_paused()   # 前に一時停止した処理があれば「続きから」を出す
    # closeEvent を通らずに終わる道（更新を入れて閉じるなど）でも、正しく閉じた印を残す
    app.aboutToQuit.connect(lambda: (w.layout_store.setValue("running", 0), w.layout_store.sync()))
    # 前の回が落ちていたら、記録の場所を知らせる（次に直すときの手がかりにする）
    try:
        prev = int(w.layout_store.value("crashlog_size", 0) or 0)
    except (TypeError, ValueError):
        prev = 0
    if crashlog.last_crash(prev):
        w.notify("前に落ちたときの記録があります", "error", f"記録: {crashlog.path()}（ヘルプの「落ちた記録を開く」で開けます）")
    try:
        w.layout_store.setValue("crashlog_size", crashlog.path().stat().st_size)
    except OSError:
        pass
    w.start_mode()   # 起動したときにモードを選ぶ（覚えたモードで「次から聞かない」なら窓を出さない）
    if getattr(w, "mode_tour", None) is None:   # モードのツアーを出した回は、はじめのツアーを重ねない
        w.maybe_tour()
    from PySide6.QtCore import QTimer
    QTimer.singleShot(5000, w.check_update)   # 起動の邪魔をしないよう、少し待ってから確かめる
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
