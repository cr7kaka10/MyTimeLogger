import logging
import threading
import json
import urllib.request
import urllib.error
from urllib.parse import urljoin
from websockets.sync.client import connect as ws_connect
from websockets.exceptions import WebSocketException

class SyncClient:
    """Client for synchronizing PC local data to the remote server via REST API and WebSocket."""

    def __init__(self, config: dict):
        self.config = config
        import os

        # Load API URL from config, default to localhost if not set
        api_config = self.config.get("api_config", {})
        self.base_url = api_config.get("base_url", os.environ.get("SYNC_BASE_URL", "http://127.0.0.1:8080/api/"))
        self.ws_url = api_config.get("ws_url", os.environ.get("SYNC_WS_URL", "ws://127.0.0.1:8080/ws/sync"))
        self.token = api_config.get("token", os.environ.get("SYNC_TOKEN"))
        self.username = api_config.get("username", os.environ.get("SYNC_USERNAME", "admin"))
        self.password = api_config.get("password", os.environ.get("SYNC_PASSWORD", "adminpass"))

    def login(self):
        """Authenticate with the server to get an access token."""
        url = urljoin(self.base_url, "auth/login")
        import urllib.parse
        data = urllib.parse.urlencode({"username": self.username, "password": self.password}).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                self.token = result.get("access_token")
                return True
        except urllib.error.URLError as e:
            logging.error(f"[SyncClient] Login failed: {e}")
            return False

    def register(self):
        """Register a new user."""
        url = urljoin(self.base_url, "auth/register")
        data = json.dumps({"username": self.username, "password": self.password}).encode('utf-8')
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return True
        except urllib.error.URLError as e:
            logging.error(f"[SyncClient] Registration failed: {e}")
            return False

    def _get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _post(self, endpoint: str, data: dict):
        url = urljoin(self.base_url, endpoint)
        headers = self._get_headers()
        req = urllib.request.Request(
            url,
            data=json.dumps(data, default=str).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.URLError as e:
            logging.error(f"[SyncClient] POST {url} failed: {e}")
            raise

    def sync_session(self, session_data: dict):
        """Send a session object to the server."""
        try:
            return self._post("sessions/start", session_data)
        except Exception as e:
            logging.error(f"Failed to sync session to server: {e}")
            return None

    def broadcast_sync_event(self, event_data: dict):
        """Send a sync event over WebSocket to notify other clients."""
        try:
            with ws_connect(self.ws_url) as websocket:
                websocket.send(json.dumps(event_data, default=str))
        except Exception as e:
            logging.error(f"[SyncClient] WebSocket broadcast failed: {e}")
