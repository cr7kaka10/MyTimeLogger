import sqlite3
import json
from sync_client import SyncClient
from datetime import datetime
import os

def migrate():
    # Load config or setup minimal config
    config = {
        "api_config": {
            "enabled": True,
            "base_url": os.environ.get("SYNC_BASE_URL"),
            "ws_url": os.environ.get("SYNC_WS_URL"),
            "username": os.environ.get("SYNC_USERNAME"),
            "password": os.environ.get("SYNC_PASSWORD")
        }
    }

    client = SyncClient(config)

    # Register and Login to get the token
    client.register()
    if not client.login():
        print("Failed to authenticate. Exiting.")
        return
    db_path = "study_log.db"

    if not os.path.exists(db_path):
        print("No local database found. Skipping migration.")
        return

    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Migrate Categories
        cursor.execute("SELECT * FROM categories")
        categories = cursor.fetchall()
        print(f"Found {len(categories)} categories to migrate.")

        for cat in categories:
            cat_data = dict(cat)
            try:
                res = client._post("categories/", cat_data)
                print(f"Migrated category: {cat_data['name']}")
            except Exception as e:
                print(f"Failed to migrate category {cat_data['name']}: {e}")

        # Migrate Sessions
        cursor.execute("SELECT * FROM study_sessions")
        sessions = cursor.fetchall()
        print(f"Found {len(sessions)} sessions to migrate.")

        for session in sessions:
            sess_data = dict(session)
            # SQLite stores dates as strings, convert format if needed, but dict() should be fine if it matches schema
            # Ensure proper keys match schema SessionCreate
            # id is usually skipped or we can map it
            sess_payload = {
                "start_time": sess_data["start_time"],
                "end_time": sess_data["end_time"],
                "net_duration_minutes": sess_data["net_duration_minutes"],
                "date": sess_data["date"],
                "day_of_week": sess_data.get("day_of_week"),
                "pause_count": sess_data.get("pause_count", 0),
                "pause_reasons": sess_data.get("pause_reasons"),
                "session_summary": sess_data.get("session_summary"),
                "category_id": sess_data.get("category_id")
            }
            try:
                res = client.sync_session(sess_payload)
                print(f"Migrated session on {sess_data['date']}")
            except Exception as e:
                print(f"Failed to migrate session {sess_data['id']}: {e}")

    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting migration to server API...")
    migrate()
    print("Migration finished.")
