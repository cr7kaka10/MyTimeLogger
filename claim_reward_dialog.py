"""
领取外部奖励弹窗 - 金币爆炸动画版
类似游戏打怪爆奖品的体验
"""
import random
import math
from PyQt6.QtWidgets import (
    QDialog, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QScrollArea, QFrame
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, QRect, pyqtProperty, QObject
)
from PyQt6.QtGui import QFont, QColor


# ──────────────────────────────────────────────
# 单个金币粒子
# ──────────────────────────────────────────────
class CoinParticle(QLabel):
    def __init__(self, parent):
        super().__init__("🪙", parent)
        self.setFont(QFont("Segoe UI Emoji", 18))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(36, 36)
        self._opacity = 1.0

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, v):
        self._opacity = v
        self.setStyleSheet(f"opacity: {v}; background: transparent; border: none;")

    opacity = pyqtProperty(float, get_opacity, set_opacity)


# ──────────────────────────────────────────────
# 奖励列表中的单行 Widget
# ──────────────────────────────────────────────
class RewardItemRow(QWidget):
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        type_icon = "✅" if item['item_type'] == 'habit' else "📋"
        name_lbl = QLabel(f"{type_icon}  {item['item_name']}")
        name_lbl.setStyleSheet("color: #2E3440; font-size: 13px; background: transparent;")
        name_lbl.setFont(QFont("Microsoft YaHei", 10))

        coin_lbl = QLabel(f"🪙 {item['coins']:g}")
        coin_lbl.setStyleSheet("color: #D08770; font-weight: bold; font-size: 13px; background: transparent;")
        coin_lbl.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        coin_lbl.setFixedWidth(60)
        coin_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(name_lbl, 1)
        layout.addWidget(coin_lbl)

        self.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.8);
                border-radius: 8px;
                margin: 2px 0;
            }
        """)


# ──────────────────────────────────────────────
# 主弹窗
# ──────────────────────────────────────────────
class ClaimRewardDialog(QDialog):
    def __init__(self, unclaimed: list, parent=None):
        super().__init__(parent)
        self.unclaimed = unclaimed
        self.total_coins = sum(i['coins'] for i in unclaimed)
        self._particles = []
        self._claimed = False

        self.setWindowTitle("🎁 奖励领取")
        self.setModal(True)
        self.setFixedSize(380, 520)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E2030, stop:1 #2A2D3E
                );
                border-radius: 16px;
            }
        """)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部标题区 ──────────────────────────────
        header = QWidget()
        header.setFixedHeight(90)
        header.setStyleSheet("background: transparent;")
        h_layout = QVBoxLayout(header)
        h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("🎊 你有新奖励！")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #EBCB8B; background: transparent; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        count_lbl = QLabel(f"共 {len(self.unclaimed)} 项  ·  合计 🪙{self.total_coins:g}")
        count_lbl.setFont(QFont("Microsoft YaHei", 10))
        count_lbl.setStyleSheet("color: #A3BE8C; background: transparent; border: none;")
        count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        h_layout.addWidget(title)
        h_layout.addWidget(count_lbl)
        root.addWidget(header)

        # ── 列表区 ──────────────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 4px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #4C566A; border-radius: 2px;
            }
        """)

        list_widget = QWidget()
        list_widget.setStyleSheet("background: transparent;")
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(16, 4, 16, 4)
        list_layout.setSpacing(4)

        for item in self.unclaimed:
            row = RewardItemRow(item)
            list_layout.addWidget(row)

        list_layout.addStretch()
        scroll_area.setWidget(list_widget)

        # 外框
        list_frame = QFrame()
        list_frame.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 12px;
                margin: 0 16px;
            }
        """)
        frame_layout = QVBoxLayout(list_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(scroll_area)

        root.addWidget(list_frame, 1)

        # ── 底部按钮区 ──────────────────────────────
        btn_area = QWidget()
        btn_area.setFixedHeight(90)
        btn_area.setStyleSheet("background: transparent;")
        btn_layout = QVBoxLayout(btn_area)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.setContentsMargins(24, 12, 24, 12)

        self.claim_btn = QPushButton(f"✨  一键收取全部  🪙{self.total_coins:g}")
        self.claim_btn.setFixedHeight(48)
        self.claim_btn.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.claim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.claim_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #EBCB8B, stop:1 #D08770
                );
                color: #2E3440;
                border: none;
                border-radius: 12px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #F0D49C, stop:1 #DCA080
                );
            }
            QPushButton:pressed {
                background: #C07850;
            }
            QPushButton:disabled {
                background: #4C566A;
                color: #7A8093;
            }
        """)
        self.claim_btn.clicked.connect(self._on_claim)
        btn_layout.addWidget(self.claim_btn)
        root.addWidget(btn_area)

    # ── 点击领取 ────────────────────────────────
    def _on_claim(self):
        if self._claimed:
            return
        self._claimed = True
        self.claim_btn.setEnabled(False)
        self.claim_btn.setText("✅  已收取！")
        self._start_coin_explosion()
        # 动画结束后 1.2s 关闭
        QTimer.singleShot(1800, self.accept)

    def _start_coin_explosion(self):
        """爆金币：多枚硬币从按钮中心飞出"""
        btn_center = self.claim_btn.mapTo(self, self.claim_btn.rect().center())
        num_coins = min(30, max(10, len(self.unclaimed) * 3))

        for i in range(num_coins):
            coin = CoinParticle(self)
            start_x = btn_center.x() - 18
            start_y = btn_center.y() - 18
            coin.move(start_x, start_y)
            coin.show()
            coin.raise_()
            self._particles.append(coin)

            # 随机飞行方向（360° 全方向）
            angle = random.uniform(0, 2 * math.pi)
            # 随机飞行距离（内圈密集 + 外圈稀疏）
            dist = random.uniform(60, 200)
            end_x = int(start_x + math.cos(angle) * dist)
            end_y = int(start_y + math.sin(angle) * dist)

            delay = random.randint(0, 200)
            QTimer.singleShot(delay, lambda c=coin, ex=end_x, ey=end_y: self._animate_coin(c, ex, ey))

    def _animate_coin(self, coin: CoinParticle, end_x: int, end_y: int):
        """单枚金币飞行动画"""
        anim = QPropertyAnimation(coin, b"pos", self)
        anim.setDuration(random.randint(500, 900))
        anim.setStartValue(coin.pos())
        anim.setEndValue(QPoint(end_x, end_y))
        anim.setEasingCurve(QEasingCurve.Type.OutQuart)
        anim.start()

        # 淡出
        fade_delay = random.randint(400, 700)
        QTimer.singleShot(fade_delay, lambda c=coin: self._fade_out_coin(c))

    def _fade_out_coin(self, coin: CoinParticle):
        steps = 8
        step = 0

        def tick():
            nonlocal step
            step += 1
            alpha = max(0, 1.0 - step / steps)
            coin.setWindowOpacity(alpha)
            if step >= steps:
                coin.hide()

        timer = QTimer(self)
        timer.setInterval(40)
        timer.timeout.connect(tick)
        timer.start()
