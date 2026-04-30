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

class SuccessOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(parent.size())
        self._opacity = 0.0
        
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(0.0)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 胜利文本
        self.label = QLabel("SUCCESS")
        self.label.setStyleSheet("""
            color: #FFD700;
            font-family: 'Microsoft YaHei', 'Segoe UI';
            font-size: 48px;
            font-weight: 900;
            background: transparent;
        """)
        # 添加发光阴影效果
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(255, 215, 0, 200))
        shadow.setOffset(0, 0)
        self.label.setGraphicsEffect(shadow)
        
        layout.addWidget(self.label)
        
        self.sub_label = QLabel("奖励已入账")
        self.sub_label.setStyleSheet("color: white; font-size: 18px; background: transparent;")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sub_label)

    def paintEvent(self, event):
        painter = QPainter(self)
        # 顶部到底部的金色渐变背景
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(255, 215, 0, 0))
        gradient.setColorAt(0.5, QColor(255, 215, 0, 40))
        gradient.setColorAt(1, QColor(255, 215, 0, 0))
        painter.fillRect(self.rect(), QBrush(gradient))

    def start_anim(self):
        self.show()
        # 整体淡入淡出
        fade_in = QPropertyAnimation(self.effect, b"opacity")
        fade_in.setDuration(500)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # 文本缩放效果 (通过字体大小模拟)
        self.label_anim = QPropertyAnimation(self, b"geometry") # 只是占位，实际用定时器
        
        # 停留
        pause = QTimer()
        pause.setSingleShot(True)
        
        fade_out = QPropertyAnimation(self.effect, b"opacity")
        fade_out.setDuration(800)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        
        group = QSequentialAnimationGroup(self)
        group.addAnimation(fade_in)
        group.addPause(1500)
        group.addAnimation(fade_out)
        group.finished.connect(self.deleteLater)
        group.start()
        
        # 额外触发金币雨
        QTimer.singleShot(200, self.spawn_coin_rain)

    def spawn_coin_rain(self):
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
            # 保持引用防回收
            if not hasattr(self, '_coin_anims'): self._coin_anims = []
            self._coin_anims.append(anim)

class FailureOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(parent.size())
        
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(0.0)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label = QLabel("FAILURE")
        self.label.setStyleSheet("""
            color: #CF6679;
            font-family: 'Microsoft YaHei', 'Segoe UI';
            font-size: 48px;
            font-weight: 900;
            background: transparent;
        """)
        layout.addWidget(self.label)
        
        self.sub_label = QLabel("再接再厉...")
        self.sub_label.setStyleSheet("color: #E5E9F0; font-size: 16px; background: transparent;")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sub_label)

    def paintEvent(self, event):
        painter = QPainter(self)
        # 暗色滤镜背景
        painter.fillRect(self.rect(), QColor(20, 20, 30, 160))

    def start_anim(self):
        self.show()
        fade_in = QPropertyAnimation(self.effect, b"opacity")
        fade_in.setDuration(400)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        
        fade_out = QPropertyAnimation(self.effect, b"opacity")
        fade_out.setDuration(1000)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        
        group = QSequentialAnimationGroup(self)
        group.addAnimation(fade_in)
        group.addPause(1200)
        group.addAnimation(fade_out)
        group.finished.connect(self.deleteLater)
        group.start()

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