import asyncio
import base64
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import config
from app.models.project import Project
from app.services.project_store import project_store
from app.utils.logger import get_logger

logger = get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
DRIVE_API = "https://www.googleapis.com/drive/v3"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

GOOGLE_EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
}


@dataclass
class SyncedFile:
    filename: str
    source: str
    external_id: str
    file_type: str


class GoogleApiClient:
    def get_json(self, url: str, headers: dict[str, str] | None = None) -> dict:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def post_form(self, url: str, data: dict[str, str]) -> dict:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(url, data=encoded, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))


class GoogleConnector:
    def __init__(self, client: GoogleApiClient | None = None):
        self._client = client or GoogleApiClient()

    def auth_url(self, state: str = "projectos") -> str:
        if not config.GOOGLE_CLIENT_ID:
            raise ValueError("GOOGLE_CLIENT_ID is not configured")
        params = {
            "client_id": config.GOOGLE_CLIENT_ID,
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required")
        token = self._client.post_form(
            GOOGLE_TOKEN_URL,
            {
                "code": code,
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": config.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        self._save_token(token)
        return token

    def status(self) -> dict:
        token_path = Path(config.GOOGLE_TOKEN_PATH)
        state_path = Path(config.GOOGLE_STATE_PATH)
        return {
            "connected": token_path.exists(),
            "token_path": str(token_path),
            "state_path": str(state_path),
            "scopes": GOOGLE_SCOPES,
            "sync_enabled": config.GOOGLE_SYNC_ENABLED,
            "sync_project_id": config.GOOGLE_SYNC_PROJECT_ID,
        }

    def sync_project(
        self,
        project_id: str,
        include_gmail: bool = True,
        include_drive: bool = True,
        gmail_query: str | None = None,
        drive_query: str | None = None,
        max_results: int | None = None,
    ) -> dict:
        project = project_store.get(project_id)
        if not project:
            raise ValueError("Project not found")

        max_results = max(1, int(max_results or config.GOOGLE_SYNC_MAX_RESULTS))
        state = self._load_state()
        project_state = state.setdefault(project_id, {"gmail_ids": [], "drive_files": {}})
        synced: list[SyncedFile] = []

        if include_gmail:
            synced.extend(
                self._sync_gmail(
                    project,
                    project_state,
                    gmail_query or config.GOOGLE_GMAIL_QUERY,
                    max_results,
                )
            )
        if include_drive:
            synced.extend(
                self._sync_drive(
                    project,
                    project_state,
                    drive_query or config.GOOGLE_DRIVE_QUERY,
                    max_results,
                )
            )

        self._save_state(state)
        if synced:
            project.files = sorted(set(project.files) | {item.filename for item in synced})
            project_store.save(project)

        return {
            "project_id": project_id,
            "synced_count": len(synced),
            "files": [item.__dict__ for item in synced],
        }

    def _sync_gmail(
        self,
        project: Project,
        project_state: dict[str, Any],
        query: str,
        max_results: int,
    ) -> list[SyncedFile]:
        known_ids = set(project_state.setdefault("gmail_ids", []))
        params = urllib.parse.urlencode({"q": query, "maxResults": max_results})
        listing = self._get_json(f"{GMAIL_API}/users/me/messages?{params}")
        synced: list[SyncedFile] = []
        for item in listing.get("messages", []) or []:
            msg_id = str(item.get("id") or "")
            if not msg_id or msg_id in known_ids:
                continue
            message = self._get_json(f"{GMAIL_API}/users/me/messages/{msg_id}?format=full")
            markdown = self._render_gmail_message(message)
            filename = f"google_gmail_{msg_id}.md"
            self._write_project_file(project.project_id, filename, markdown.encode("utf-8"))
            known_ids.add(msg_id)
            synced.append(SyncedFile(filename, "gmail", msg_id, "email"))
        project_state["gmail_ids"] = sorted(known_ids)
        return synced

    def _sync_drive(
        self,
        project: Project,
        project_state: dict[str, Any],
        query: str,
        max_results: int,
    ) -> list[SyncedFile]:
        drive_files = project_state.setdefault("drive_files", {})
        fields = "files(id,name,mimeType,modifiedTime,webViewLink)"
        params = urllib.parse.urlencode({"q": query, "pageSize": max_results, "fields": fields})
        listing = self._get_json(f"{DRIVE_API}/files?{params}")
        synced: list[SyncedFile] = []
        for item in listing.get("files", []) or []:
            file_id = str(item.get("id") or "")
            modified = str(item.get("modifiedTime") or "")
            if not file_id or drive_files.get(file_id) == modified:
                continue
            content, filename = self._download_drive_file(item)
            if not content:
                continue
            self._write_project_file(project.project_id, filename, content)
            drive_files[file_id] = modified
            synced.append(SyncedFile(filename, "drive", file_id, self._drive_file_type(item)))
        return synced

    def _download_drive_file(self, item: dict[str, Any]) -> tuple[bytes, str]:
        file_id = str(item.get("id") or "")
        name = _safe_filename(str(item.get("name") or file_id))
        mime_type = str(item.get("mimeType") or "")
        if mime_type in GOOGLE_EXPORT_MIME_TYPES:
            export_mime, suffix = GOOGLE_EXPORT_MIME_TYPES[mime_type]
            params = urllib.parse.urlencode({"mimeType": export_mime})
            content = self._get_bytes(f"{DRIVE_API}/files/{file_id}/export?{params}")
            return content, _ensure_suffix(f"google_drive_{file_id}_{name}", suffix)
        params = urllib.parse.urlencode({"alt": "media"})
        content = self._get_bytes(f"{DRIVE_API}/files/{file_id}?{params}")
        return content, f"google_drive_{file_id}_{name}"

    def _drive_file_type(self, item: dict[str, Any]) -> str:
        mime_type = str(item.get("mimeType") or "")
        name = str(item.get("name") or "").lower()
        if "presentation" in mime_type or "spreadsheet" in mime_type:
            return "report"
        if "pdf" in mime_type or name.endswith(".pdf"):
            return "paper"
        return "note"

    def _render_gmail_message(self, message: dict[str, Any]) -> str:
        payload = message.get("payload", {}) or {}
        headers = {
            str(item.get("name", "")).lower(): str(item.get("value", ""))
            for item in payload.get("headers", []) or []
        }
        body = _message_body(payload).strip()
        lines = [
            "---",
            "type: email",
            f"gmail_id: {message.get('id', '')}",
            f"thread_id: {message.get('threadId', '')}",
            "---",
            "",
            f"# {headers.get('subject') or '(no subject)'}",
            "",
            f"- From: {headers.get('from', '')}",
            f"- To: {headers.get('to', '')}",
            f"- Date: {headers.get('date', '')}",
            "",
            "## Body",
            body or str(message.get("snippet") or ""),
            "",
        ]
        return "\n".join(lines)

    def _headers(self) -> dict[str, str]:
        token = self._valid_token()
        return {"Authorization": f"Bearer {token['access_token']}"}

    def _get_json(self, url: str) -> dict:
        return self._client.get_json(url, headers=self._headers())

    def _get_bytes(self, url: str) -> bytes:
        return self._client.get_bytes(url, headers=self._headers())

    def _valid_token(self) -> dict:
        token = self._load_token()
        expires_at = float(token.get("expires_at") or 0)
        if expires_at - 60 > time.time():
            return token
        refresh_token = token.get("refresh_token")
        if not refresh_token:
            return token
        refreshed = self._client.post_form(
            GOOGLE_TOKEN_URL,
            {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "refresh_token": str(refresh_token),
                "grant_type": "refresh_token",
            },
        )
        if refresh_token and "refresh_token" not in refreshed:
            refreshed["refresh_token"] = refresh_token
        self._save_token(refreshed)
        return refreshed

    def _load_token(self) -> dict:
        path = Path(config.GOOGLE_TOKEN_PATH)
        if not path.exists():
            raise ValueError("Google is not connected — run OAuth first")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_token(self, token: dict) -> None:
        expires_in = int(token.get("expires_in") or 3600)
        token["expires_at"] = time.time() + expires_in
        path = Path(config.GOOGLE_TOKEN_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(token, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_state(self) -> dict:
        path = Path(config.GOOGLE_STATE_PATH)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_state(self, state: dict) -> None:
        path = Path(config.GOOGLE_STATE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_project_file(self, project_id: str, filename: str, content: bytes) -> None:
        files_dir = Path(config.PROJECTS_DIR) / project_id / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        (files_dir / filename).write_bytes(content)


class GoogleSyncService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = False

    def start(self) -> None:
        if not config.GOOGLE_SYNC_ENABLED or not config.GOOGLE_SYNC_PROJECT_ID:
            return
        self._stop = False
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Google sync started "
            f"(project={config.GOOGLE_SYNC_PROJECT_ID}, interval={config.GOOGLE_SYNC_POLL_SECONDS}s)"
        )

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop:
            try:
                from app.api.google import run_google_sync_pipeline

                await run_google_sync_pipeline(config.GOOGLE_SYNC_PROJECT_ID, trigger="scheduled")
            except Exception as exc:
                logger.error(f"Google sync failed: {exc}")
            await asyncio.sleep(config.GOOGLE_SYNC_POLL_SECONDS)


def _message_body(payload: dict[str, Any]) -> str:
    mime_type = str(payload.get("mimeType") or "")
    body_data = (payload.get("body") or {}).get("data")
    if body_data and (mime_type.startswith("text/plain") or mime_type.startswith("text/html")):
        return _decode_base64url(str(body_data))

    parts = payload.get("parts", []) or []
    plain_parts = [
        _message_body(part)
        for part in parts
        if str(part.get("mimeType") or "").startswith("text/plain")
    ]
    if plain_parts:
        return "\n\n".join(part for part in plain_parts if part)
    return "\n\n".join(_message_body(part) for part in parts if _message_body(part))


def _decode_base64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")


def _safe_filename(name: str) -> str:
    cleaned = "".join("_" if ch in '<>:"/\\|?*\x00' else ch for ch in name).strip()
    return cleaned or "untitled"


def _ensure_suffix(name: str, suffix: str) -> str:
    return name if name.lower().endswith(suffix.lower()) else f"{name}{suffix}"
