import sys
from unittest.mock import MagicMock

# Mock pygame before it's imported in logic
mock_pygame = MagicMock()
sys.modules["pygame"] = mock_pygame

# Mock PyQt6
mock_pyqt6 = MagicMock()
class DummyQObject:
    def __init__(self, *args, **kwargs):
        pass
    def moveToThread(self, *args, **kwargs):
        pass

# Mock pyqtSignal to return a mock that has a 'connect' method
def mock_pyqtSignal(*args, **kwargs):
    signal = MagicMock()
    signal.connect = MagicMock()
    return signal

mock_pyqt6.QtCore.QObject = DummyQObject
mock_pyqt6.QtCore.pyqtSignal = mock_pyqtSignal
mock_pyqt6.QtCore.QTimer = MagicMock
mock_pyqt6.QtCore.QThread = MagicMock

sys.modules["PyQt6"] = mock_pyqt6
sys.modules["PyQt6.QtCore"] = mock_pyqt6.QtCore
sys.modules["PyQt6.QtWidgets"] = mock_pyqt6.QtWidgets

# Mock pynput
sys.modules["pynput"] = MagicMock()
sys.modules["pynput.keyboard"] = MagicMock()

import pytest
from unittest.mock import patch
from datetime import datetime, timedelta
import logic

@pytest.fixture
def mock_config():
    return {
        "study_time_min": 25 * 60,
        "study_time_max": 25 * 60,
        "short_break_duration": 5 * 60,
        "long_break_threshold": 90 * 60,
        "long_break_duration": 15 * 60,
        "music_folder": "study_music",
        "sound_files": {
            "start_short_break": "start_short_break.mp3",
            "start_long_break": "start_long_break.mp3",
            "end_long_break": "end_long_break.mp3",
            "victory": "victory.mp3",
            "start_study": "start_study.mp3"
        },
        "total_study_time": 0
    }

@pytest.fixture
def logic_instance(mock_config):
    with patch('logic.StudyLogger'), \
         patch('logic.DatabaseWorker'), \
         patch('logic.QThread'), \
         patch('logic.QTimer') as mock_qtimer:

        # Setup the timer mock
        mock_timer_instance = MagicMock()
        mock_qtimer.return_value = mock_timer_instance

        instance = logic.MyTimeLoggerLogic(mock_config)

        # Replace the timer instance with the mock to ensure we're using the same one
        instance.timer = mock_timer_instance

        # Re-mock signals to ensure they are MagicMocks we can track
        instance.state_changed = MagicMock()
        instance.input_reason_requested = MagicMock()
        instance.time_updated = MagicMock()
        instance.notification_requested = MagicMock()
        instance._sync_trigger = MagicMock()
        instance._async_log_trigger = MagicMock()

        # Reset mocks to clear calls made during initialization (e.g., reset_cycle)
        instance.timer.reset_mock()
        instance.state_changed.reset_mock()

        return instance

def test_init(logic_instance):
    assert logic_instance.is_paused is False
    assert logic_instance.current_state == "stopped"

def test_toggle_pause_from_studying(logic_instance):
    # Setup: starting a study cycle
    logic_instance.current_state = "studying"
    logic_instance.timer.isActive.return_value = True
    logic_instance.timer.remainingTime.return_value = 10000  # 10 seconds left

    # Action: Pause
    with patch('logic.datetime') as mock_datetime:
        now = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = now
        logic_instance.toggle_pause()

    # Assertions
    assert logic_instance.is_paused is True
    assert logic_instance.time_remaining_on_pause == 10000
    assert logic_instance.current_pause_start_time == now
    logic_instance.timer.stop.assert_called_once()
    logic_instance.state_changed.emit.assert_called_with("⏸️ 已暂停", "studying")
    logic_instance.input_reason_requested.emit.assert_called_once()

def test_toggle_pause_resume_studying(logic_instance):
    # Setup: paused during studying
    logic_instance.current_state = "studying"
    logic_instance.is_paused = True
    logic_instance.time_remaining_on_pause = 10000
    pause_start = datetime(2023, 1, 1, 12, 0, 0)
    logic_instance.current_pause_start_time = pause_start
    logic_instance.pending_pause_reason = "Drinking water"
    logic_instance.cycle_count = 1

    # Action: Resume
    resume_time = pause_start + timedelta(seconds=45)
    with patch('logic.datetime') as mock_datetime:
        mock_datetime.now.return_value = resume_time
        logic_instance.toggle_pause()

    # Assertions
    assert logic_instance.is_paused is False
    assert logic_instance.current_pause_start_time is None
    assert logic_instance.pending_pause_reason == "无"
    assert logic_instance.large_session_pause_count == 1
    assert "Drinking water (45秒)" in logic_instance.large_session_pause_reasons

    logic_instance.timer.start.assert_called_with(10000)
    logic_instance.state_changed.emit.assert_called_with("📚 学习中...\n(第 1 轮)", "studying")

def test_format_pause_duration():
    from logic import MyTimeLoggerLogic
    assert MyTimeLoggerLogic._format_pause_duration(30) == "30秒"
    assert MyTimeLoggerLogic._format_pause_duration(60) == "1分"
    assert MyTimeLoggerLogic._format_pause_duration(65) == "1分5秒"
    assert MyTimeLoggerLogic._format_pause_duration(3600) == "1时"
    assert MyTimeLoggerLogic._format_pause_duration(3660) == "1时1分"
    assert MyTimeLoggerLogic._format_pause_duration(3665) == "1时1分5秒"

def test_toggle_pause_countup_studying(logic_instance):
    logic_instance.current_state = "countup_studying"
    logic_instance.timer.isActive.return_value = True

    # Pause
    logic_instance.toggle_pause()
    assert logic_instance.is_paused is True

    # Resume
    logic_instance.timer.start.reset_mock()
    logic_instance.toggle_pause()
    assert logic_instance.is_paused is False
    # For countup, it starts with a large value
    logic_instance.timer.start.assert_called_with(24 * 3600 * 1000)
    logic_instance.state_changed.emit.assert_called_with("⏳ 正计时中...", "countup_studying")

def test_toggle_pause_short_breaking(logic_instance):
    logic_instance.current_state = "short_breaking"
    logic_instance.timer.isActive.return_value = True
    logic_instance.timer.remainingTime.return_value = 5000

    # Pause
    logic_instance.toggle_pause()
    assert logic_instance.is_paused is True

    # Resume
    logic_instance.toggle_pause()
    assert logic_instance.is_paused is False
    logic_instance.timer.start.assert_called_with(5000)
    logic_instance.state_changed.emit.assert_called_with("☕ 短暂休息中...", "short_breaking")

def test_toggle_pause_long_breaking(logic_instance):
    logic_instance.current_state = "long_breaking"
    logic_instance.timer.isActive.return_value = True
    logic_instance.timer.remainingTime.return_value = 15000

    # Pause
    logic_instance.toggle_pause()
    assert logic_instance.is_paused is True

    # Resume
    logic_instance.toggle_pause()
    assert logic_instance.is_paused is False
    logic_instance.timer.start.assert_called_with(15000)
    logic_instance.state_changed.emit.assert_called_with("🧘 长时间休息...", "long_breaking")
