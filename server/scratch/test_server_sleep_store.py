# -*- coding: utf-8 -*-
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server_sleep_store import serverSleepStore


def main():
    db_path = os.path.join(tempfile.gettempdir(), "mytimelogger_server_sleep_store_test.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    store = serverSleepStore(db_path)
    store.create_job("req-1", "image.jpg")
    assert store.get_job("req-1")["status"] == "queued"

    store.mark_running("req-1")
    assert store.get_job("req-1")["status"] == "running"

    sleep_data = {"sleep_score": 88, "sleep_reflection": ""}
    store.mark_done("req-1", "2026-05-13", sleep_data, "report")
    rows = store.list_done_since("")
    assert len(rows) == 1
    assert rows[0]["sleep_data"]["sleep_score"] == 88

    assert store.ack_sync(["req-1"]) == 1
    assert store.ack_sync(["req-1"]) == 1

    assert store.save_reflection("2026-05-13", "good")
    job = store.get_job("req-1")
    assert job["sleep_data"]["sleep_reflection"] == "good"

    print("server_sleep_store ok")


if __name__ == "__main__":
    main()
