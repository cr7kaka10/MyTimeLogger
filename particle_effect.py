import random
import math
import os
try:
    import pygame
except ImportError:
    pygame = None

from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtProperty
from PyQt6.QtGui import QFont
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