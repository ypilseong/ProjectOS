import base64
import json
import time
import urllib.parse

from app.services.project_store import project_store


class FakeGoogleClient:
    def __init__(self):
        self.posts = []

    def post_form(self, url, data):
        self.posts.append((url, data))
        return {
            "access_token": "new-token",
            "refresh_token": data.get("refresh_token", "refresh-token"),
            "expires_in": 3600,
        }

    def get_json(self, url, headers=None):
        if "gmail/v1/users/me/messages?" in url:
            return {"messages": [{"id": "m1"}]}
        if "gmail/v1/users/me/messages/m1" in url:
            body = base64.urlsafe_b64encode("메일 본문".encode("utf-8")).decode("ascii").rstrip("=")
            return {
                "id": "m1",
                "threadId": "t1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "ProjectOS 회의"},
                        {"name": "From", "value": "a@example.com"},
                        {"name": "To", "value": "b@example.com"},
                        {"name": "Date", "value": "Thu, 04 Jun 2026 09:00:00 +0900"},
                    ],
                    "mimeType": "text/plain",
                    "body": {"data": body},
                },
            }
        if "drive/v3/files?" in url:
            return {
                "files": [
                    {
                        "id": "d1",
                        "name": "Research Memo",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2026-06-04T00:00:00Z",
                    }
                ]
            }
        raise AssertionError(f"unexpected json url: {url}")

    def get_bytes(self, url, headers=None):
        if "drive/v3/files/d1/export" in url:
            return b"drive document text"
        raise AssertionError(f"unexpected bytes url: {url}")


def _configure_google(monkeypatch, tmp_path):
    from app.config import config

    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(config, "GOOGLE_TOKEN_PATH", str(tmp_path / "google_token.json"))
    monkeypatch.setattr(config, "GOOGLE_STATE_PATH", str(tmp_path / "google_state.json"))
    monkeypatch.setattr(config, "GOOGLE_GMAIL_QUERY", "newer_than:7d")
    monkeypatch.setattr(config, "GOOGLE_DRIVE_QUERY", "trashed = false")


def test_google_auth_url_contains_gmail_and_drive_scopes(monkeypatch, tmp_path):
    from app.services.google_connector import GoogleConnector

    _configure_google(monkeypatch, tmp_path)

    url = GoogleConnector(FakeGoogleClient()).auth_url(state="p1")
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    assert query["client_id"] == ["client-id"]
    assert query["state"] == ["p1"]
    assert "gmail.readonly" in query["scope"][0]
    assert "drive.readonly" in query["scope"][0]


def test_google_sync_writes_gmail_and_drive_files(monkeypatch, tmp_path):
    from app.config import config
    from app.services.google_connector import GoogleConnector

    _configure_google(monkeypatch, tmp_path)
    token = {
        "access_token": "token",
        "refresh_token": "refresh-token",
        "expires_at": time.time() + 3600,
    }
    (tmp_path / "google_token.json").write_text(json.dumps(token), encoding="utf-8")
    project = project_store.create(name="Google Sync", description="")

    result = GoogleConnector(FakeGoogleClient()).sync_project(project.project_id)

    assert result["synced_count"] == 2
    files_dir = tmp_path / "projects" / project.project_id / "files"
    gmail_file = files_dir / "google_gmail_m1.md"
    drive_file = files_dir / "google_drive_d1_Research Memo.txt"
    assert "ProjectOS 회의" in gmail_file.read_text(encoding="utf-8")
    assert "메일 본문" in gmail_file.read_text(encoding="utf-8")
    assert drive_file.read_text(encoding="utf-8") == "drive document text"

    state = json.loads((tmp_path / "google_state.json").read_text(encoding="utf-8"))
    assert state[project.project_id]["gmail_ids"] == ["m1"]
    assert state[project.project_id]["drive_files"]["d1"] == "2026-06-04T00:00:00Z"
    assert "google_gmail_m1.md" in project_store.get(project.project_id).files
    assert config.PROJECTS_DIR.endswith("projects")


def test_google_sync_skips_already_synced_items(monkeypatch, tmp_path):
    from app.services.google_connector import GoogleConnector

    _configure_google(monkeypatch, tmp_path)
    (tmp_path / "google_token.json").write_text(
        json.dumps({"access_token": "token", "expires_at": time.time() + 3600}),
        encoding="utf-8",
    )
    project = project_store.create(name="Google Sync Skip", description="")
    (tmp_path / "google_state.json").write_text(
        json.dumps({
            project.project_id: {
                "gmail_ids": ["m1"],
                "drive_files": {"d1": "2026-06-04T00:00:00Z"},
            }
        }),
        encoding="utf-8",
    )

    result = GoogleConnector(FakeGoogleClient()).sync_project(project.project_id)

    assert result["synced_count"] == 0
