# -*- coding: utf-8 -*-
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sleep_analyzer import SleepAnalyzer, clean_num, to_min


def main():
    assert to_min("1小时20分") == 80
    assert to_min("80min") == 80
    assert clean_num("85分") == 85

    data = {
        "sleep_score": "88分",
        "total_sleep_min": "7小时30分",
        "deep_sleep_min": "100分",
        "light_sleep_min": "260分",
        "rem_sleep_min": "90分",
        "deep_sleep_ratio": "22%",
        "sleep_start": "23:30",
        "sleep_end": "07:10",
    }
    normalized = SleepAnalyzer.normalize_data(data)
    ok, reason = SleepAnalyzer.validate_data(normalized)
    assert ok, reason
    assert normalized["total_sleep_min"] == 450
    assert normalized["sleep_score"] == 88

    extracted = SleepAnalyzer.extract_json("""```json\n{"a": 1}\n```""")
    assert extracted == {"a": 1}

    print("sleep_analyzer_core ok")


if __name__ == "__main__":
    main()
