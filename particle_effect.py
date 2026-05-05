import random
import math
import os
try:
    import pygame
except ImportError:
    pygame = None

from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtProperty, QRect, QSequentialAnimationGroup, QParallelAnimationGroup
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QLinearGradient
from utils import resource_path

class CoinParticle(QLabel):
    def __init__(self, parent):
        super().__init__("🪙", parent)
        self.setFont(QFont("Segoe UI Emoji", 18))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(36, 36)
        self._opacity = 1.0

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, v):
        self._opacity = v
        self.effect.setOpacity(v)

    opacity = pyqtProperty(float, get_opacity, set_opacity)

def play_reward_sound():
    if pygame and pygame.mixer and pygame.mixer.get_init():
        sound_path = resource_path(os.path.join("study_music", "victory.mp3"))
        if os.path.exists(sound_path):
            try:
                sound = pygame.mixer.Sound(sound_path)
                sound.set_volume(0.6)
                sound.play()
            except Exception as e:
                print(f"Error playing sound: {e}")

def start_coin_explosion(parent_widget, source_widget, num_items=1):
    """
    在 parent_widget 上，以 source_widget 为中心，产生金币爆炸动画。
    同时播放领奖音效。
    """
    play_reward_sound()
    
    btn_center = source_widget.mapTo(parent_widget, source_widget.rect().center())
    num_coins = min(40, max(10, num_items * 4))
    
    if not hasattr(parent_widget, '_particles'):
        parent_widget._particles = []
        
    for i in range(num_coins):
        coin = CoinParticle(parent_widget)
        start_x = btn_center.x() - 18
        start_y = btn_center.y() - 18
        coin.move(start_x, start_y)
        coin.show()
        coin.raise_()
        parent_widget._particles.append(coin)

        # 向上方 180 度扇形喷射
        angle = random.uniform(math.pi + 0.2, 2 * math.pi - 0.2)
        dist = random.uniform(80, 220)
        end_x = int(start_x + math.cos(angle) * dist)
        end_y = int(start_y + math.sin(angle) * dist)

        delay = random.randint(0, 150)
        QTimer.singleShot(delay, lambda c=coin, ex=end_x, ey=end_y: _animate_coin(parent_widget, c, ex, ey))

def _animate_coin(parent_widget, coin, end_x, end_y):
    anim = QPropertyAnimation(coin, b"pos", parent_widget)
    anim.setDuration(random.randint(600, 1000))
    anim.setStartValue(coin.pos())
    anim.setEndValue(QPoint(end_x, end_y))
    anim.setEasingCurve(QEasingCurve.Type.OutQuart)
    
    if not hasattr(parent_widget, '_anims'):
        parent_widget._anims = []
    parent_widget._anims.append(anim)
    
    anim.start()

    # 淡出
    fade_delay = random.randint(400, 700)
    QTimer.singleShot(fade_delay, lambda c=coin: _fade_out_coin(parent_widget, c))

def _fade_out_coin(parent_widget, coin):
    anim = QPropertyAnimation(coin, b"opacity", parent_widget)
    anim.setDuration(300)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.finished.connect(lambda: _cleanup_coin(parent_widget, coin, anim))
    parent_widget._anims.append(anim)
    anim.start()

def _cleanup_coin(parent_widget, coin, anim):
    coin.deleteLater()
    if hasattr(parent_widget, '_particles') and coin in parent_widget._particles:
        parent_widget._particles.remove(coin)
    if hasattr(parent_widget, '_anims') and anim in parent_widget._anims:
        parent_widget._anims.remove(anim)

# ==================== Onmyoji Style Overlays ====================
# 纯自绘方案: 彻底废弃 QGraphicsOpacityEffect / QGraphicsDropShadowEffect,
# 所有视觉效果在 paintEvent 中用 QPainter 直接绘制,
# 从根源消除 QWidgetEffectSourcePrivate 管线冲突导致的 "Painter not active" 报错。

class SuccessOverlay(QWidget):
    """成功覆盖层 — 纯自绘, 无 QGraphicsEffect"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(parent.size())
        self._opacity = 0.0
        self._destroying = False

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, v):
        self._opacity = v
        self.update()

    overlay_opacity = pyqtProperty(float, get_opacity, set_opacity)

    def paintEvent(self, event):
        if self._destroying:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setOpacity(self._opacity)

        # 金色渐变背景
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(255, 215, 0, 0))
        gradient.setColorAt(0.3, QColor(255, 215, 0, 50))
        gradient.setColorAt(0.5, QColor(255, 215, 0, 60))
        gradient.setColorAt(0.7, QColor(255, 215, 0, 50))
        gradient.setColorAt(1, QColor(255, 215, 0, 0))
        painter.fillRect(self.rect(), QBrush(gradient))

        # 绘制 SUCCESS 文本 (自绘替代 QLabel + QGraphicsDropShadowEffect)
        cy = self.height() / 2 - 20

        # 发光层 (模拟 DropShadow)
        glow_font = QFont("Microsoft YaHei", 48, QFont.Weight.Black)
        painter.setFont(glow_font)
        for r in (3, 2):
            glow_alpha = int(50 * self._opacity / r)
            painter.setPen(QColor(255, 215, 0, min(255, glow_alpha)))
            for dx in (-r, 0, r):
                for dy in (-r, 0, r):
                    painter.drawText(
                        QRect(dx, int(cy - 30 + dy), self.width(), 60),
                        Qt.AlignmentFlag.AlignCenter, "SUCCESS"
                    )

        # 主文字层
        painter.setPen(QColor(255, 215, 0, int(255 * self._opacity)))
        painter.drawText(
            QRect(0, int(cy - 30), self.width(), 60),
            Qt.AlignmentFlag.AlignCenter, "SUCCESS"
        )

        # 副标题
        sub_font = QFont("Microsoft YaHei", 14)
        painter.setFont(sub_font)
        painter.setPen(QColor(255, 255, 255, int(220 * self._opacity)))
        painter.drawText(
            QRect(0, int(cy + 40), self.width(), 30),
            Qt.AlignmentFlag.AlignCenter, "奖励已入账"
        )

        painter.end()

    def start_anim(self):
        self.show()
        self.raise_()

        fade_in = QPropertyAnimation(self, b"overlay_opacity")
        fade_in.setDuration(500)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        fade_out = QPropertyAnimation(self, b"overlay_opacity")
        fade_out.setDuration(800)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)

        self._anim_group = QSequentialAnimationGroup(self)
        self._anim_group.addAnimation(fade_in)
        self._anim_group.addPause(1500)
        self._anim_group.addAnimation(fade_out)
        self._anim_group.finished.connect(self._safe_cleanup)
        self._anim_group.start()

        # 金币雨
        QTimer.singleShot(200, self._spawn_coin_rain)

    def _spawn_coin_rain(self):
        if self._destroying:
            return
        self._coin_anims = []
        for _ in range(15):
            coin = CoinParticle(self)
            start_x = random.randint(20, self.width() - 40)
            coin.move(start_x, -40)
            coin.show()

            anim = QPropertyAnimation(coin, b"pos")
            anim.setDuration(random.randint(1200, 2000))
            anim.setStartValue(coin.pos())
            anim.setEndValue(QPoint(start_x + random.randint(-50, 50), self.height() + 40))
            anim.setEasingCurve(QEasingCurve.Type.Linear)
            anim.start()
            self._coin_anims.append(anim)

    def _safe_cleanup(self):
        self._destroying = True
        if hasattr(self, '_anim_group'):
            self._anim_group.stop()
        if hasattr(self, '_coin_anims'):
            for a in self._coin_anims:
                a.stop()
        self.hide()
        self.deleteLater()


class FailureOverlay(QWidget):
    """失败覆盖层 — 纯自绘, 无 QGraphicsEffect"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(parent.size())
        self._opacity = 0.0
        self._destroying = False

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, v):
        self._opacity = v
        self.update()

    overlay_opacity = pyqtProperty(float, get_opacity, set_opacity)

    def paintEvent(self, event):
        if self._destroying:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setOpacity(self._opacity)

        # 暗色滤镜背景
        painter.fillRect(self.rect(), QColor(20, 20, 30, 160))

        # FAILURE 文本
        cy = self.height() / 2 - 20
        font = QFont("Microsoft YaHei", 48, QFont.Weight.Black)
        painter.setFont(font)
        painter.setPen(QColor(207, 102, 121, int(255 * self._opacity)))
        painter.drawText(
            QRect(0, int(cy - 30), self.width(), 60),
            Qt.AlignmentFlag.AlignCenter, "FAILURE"
        )

        # 副标题
        sub_font = QFont("Microsoft YaHei", 14)
        painter.setFont(sub_font)
        painter.setPen(QColor(229, 233, 240, int(200 * self._opacity)))
        painter.drawText(
            QRect(0, int(cy + 40), self.width(), 30),
            Qt.AlignmentFlag.AlignCenter, "再接再厉..."
        )

        painter.end()

    def start_anim(self):
        self.show()
        self.raise_()

        fade_in = QPropertyAnimation(self, b"overlay_opacity")
        fade_in.setDuration(400)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)

        fade_out = QPropertyAnimation(self, b"overlay_opacity")
        fade_out.setDuration(1000)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)

        self._anim_group = QSequentialAnimationGroup(self)
        self._anim_group.addAnimation(fade_in)
        self._anim_group.addPause(1200)
        self._anim_group.addAnimation(fade_out)
        self._anim_group.finished.connect(self._safe_cleanup)
        self._anim_group.start()

    def _safe_cleanup(self):
        self._destroying = True
        if hasattr(self, '_anim_group'):
            self._anim_group.stop()
        self.hide()
        self.deleteLater()


def show_success_effect(parent):
    if not parent: return
    overlay = SuccessOverlay(parent)
    overlay.start_anim()
    play_reward_sound()

def show_failure_effect(parent):
    if not parent: return
    overlay = FailureOverlay(parent)
    overlay.start_anim()
    # 播放失败音效（如果有的话，暂用普通提示音或不播）