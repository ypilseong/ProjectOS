# Phase 2a — Continuous File Watcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 백그라운드에서 `projects/<id>/files/`의 신규·수정 파일을 해시 폴링으로 감지해 재파싱 → incremental 그래프 빌드를 자동 트리거한다.

**Architecture:** FastAPI `lifespan`에서 시작되는 단일 asyncio 백그라운드 태스크(`WatcherService`)가 주기적으로 각 빌드완료 프로젝트의 `files/`를 폴링한다. 직전 빌드 해시(`hashes.json`)와 비교해 변경 파일을 찾고, 직전 폴링 대비 해시가 안정된 파일만 처리한다. 변경 파일은 재파싱해 `chunks.json`에서 교체한 뒤 기존 `_run_graph(incremental=True)`를 호출한다. 기존 인프라(DocumentHashStore, ParserAgent, task_manager, Phase 1 trace/budget) 재사용.

**Tech Stack:** Python 3, FastAPI, asyncio, pytest. 신규 외부 의존성 없음.

---

## File Structure

| 파일 | 역할 | 신규/수정 |
|------|------|-----------|
| `src/backend/app/services/watcher.py` | WatcherService + 순수 헬퍼(compute_stable_changes), reparse_and_replace_chunks, run_auto_update | 신규 |
| `src/backend/app/services/task_manager.py` | `has_active_build(project_id)` 추가 | 수정 |
| `src/backend/app/api/graph.py` | `_run_graph`에 `trigger` 파라미터 추가 + trace에 기록 | 수정 |
| `src/backend/app/config.py` | `WATCHER_ENABLED`, `WATCHER_POLL_SECONDS` 추가 | 수정 |
| `src/backend/app/main.py` | lifespan으로 WatcherService 시작/정지 | 수정 |
| `src/backend/tests/test_services/test_task_manager_active_build.py` | has_active_build 테스트 | 신규 |
| `src/backend/tests/test_services/test_watcher.py` | 감지/디바운스/청크교체/오케스트레이션 테스트 | 신규 |
| `src/backend/tests/test_agents/test_graph_build_trigger.py` | trigger trace 테스트 | 신규 |

**참고**: 모든 명령은 `src/backend/`에서 실행. 테스트는 `python3 -m pytest`.

---

### Task 1: TaskManager.has_active_build

프로젝트별로 진행 중인 그래프 빌드 task가 있는지 조회한다. Watcher가 빌드 중복을 막는 데 사용.

**Files:**
- Modify: `src/backend/app/services/task_manager.py`
- Test: `src/backend/tests/test_services/test_task_manager_active_build.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_services/test_task_manager_active_build.py` 생성:

```python
from app.services.task_manager import TaskManager
from app.models.project import TaskStatus


def test_has_active_build_true_when_graph_task_running(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.task_manager.config.PROJECTS_DIR", str(tmp_path))
    tm = TaskManager()
    task = tm.create("p1", "graph")
    tm.update(task.task_id, status=TaskStatus.RUNNING)
    assert tm.has_active_build("p1") is True


def test_has_active_build_false_when_completed(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.task_manager.config.PROJECTS_DIR", str(tmp_path))
    tm = TaskManager()
    task = tm.create("p1", "graph_incremental")
    tm.update(task.task_id, status=TaskStatus.COMPLETED)
    assert tm.has_active_build("p1") is False


def test_has_active_build_ignores_other_projects_and_types(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.task_manager.config.PROJECTS_DIR", str(tmp_path))
    tm = TaskManager()
    t1 = tm.create("p2", "graph")
    tm.update(t1.task_id, status=TaskStatus.RUNNING)
    t2 = tm.create("p1", "parse")
    tm.update(t2.task_id, status=TaskStatus.RUNNING)
    assert tm.has_active_build("p1") is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_services/test_task_manager_active_build.py -v`
Expected: FAIL — `AttributeError: 'TaskManager' object has no attribute 'has_active_build'`

- [ ] **Step 3: 구현 추가**

`src/backend/app/services/task_manager.py`의 `get` 메서드 다음에 추가 (클래스 내부, 4-space 들여쓰기):

```python
    def has_active_build(self, project_id: str) -> bool:
        build_types = {"graph", "graph_incremental", "graph_watcher"}
        for task in self._tasks.values():
            if (
                task.project_id == project_id
                and task.task_type in build_types
                and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
            ):
                return True
        return False
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_services/test_task_manager_active_build.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/services/task_manager.py tests/test_services/test_task_manager_active_build.py
git commit -m "feat: add TaskManager.has_active_build for watcher dedup"
```

---

### Task 2: compute_stable_changes (순수 감지 함수)

직전 빌드 해시·직전 폴링 해시·현재 해시를 받아 "처리할 안정적 변경 파일" 집합을 반환하는 순수 함수. IO 없음 → 단위 테스트 쉬움.

**Files:**
- Create: `src/backend/app/services/watcher.py`
- Test: `src/backend/tests/test_services/test_watcher.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_services/test_watcher.py` 생성:

```python
from app.services.watcher import compute_stable_changes


def test_new_file_stable_after_two_identical_polls():
    # 신규 파일: last_built에 없음. 직전 폴링과 현재 해시 동일 → 안정 → 포함
    current = {"a.txt": "h1"}
    last_built = {}
    prev_poll = {"a.txt": "h1"}
    assert compute_stable_changes(current, last_built, prev_poll) == {"a.txt"}


def test_modified_file_included_when_stable():
    current = {"a.txt": "h2"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h2"}
    assert compute_stable_changes(current, last_built, prev_poll) == {"a.txt"}


def test_unchanged_file_excluded():
    current = {"a.txt": "h1"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h1"}
    assert compute_stable_changes(current, last_built, prev_poll) == set()


def test_unstable_file_excluded_until_settled():
    # 직전 폴링과 현재 해시가 다름 → 아직 쓰기/동기화 중 → 제외
    current = {"a.txt": "h2"}
    last_built = {"a.txt": "h1"}
    prev_poll = {"a.txt": "h1_partial"}
    assert compute_stable_changes(current, last_built, prev_poll) == set()


def test_new_file_excluded_on_first_sighting():
    # 직전 폴링에 없던 신규 파일은 첫 발견 시 불안정 → 제외
    current = {"a.txt": "h1"}
    last_built = {}
    prev_poll = {}
    assert compute_stable_changes(current, last_built, prev_poll) == set()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_services/test_watcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.watcher'`

- [ ] **Step 3: 구현 작성**

`src/backend/app/services/watcher.py` 생성:

```python
def compute_stable_changes(
    current: dict[str, str],
    last_built: dict[str, str],
    prev_poll: dict[str, str],
) -> set[str]:
    """변경(신규/수정)되었고 직전 폴링 대비 안정된 파일명 집합을 반환.

    - 변경: last_built에 해시가 없거나(신규) 다름(수정).
    - 안정: prev_poll의 해시가 current와 동일(쓰기/동기화 완료).
    """
    stable: set[str] = set()
    for fname, h in current.items():
        changed = last_built.get(fname) != h
        settled = prev_poll.get(fname) == h
        if changed and settled:
            stable.add(fname)
    return stable
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_services/test_watcher.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/services/watcher.py tests/test_services/test_watcher.py
git commit -m "feat: add compute_stable_changes detection helper"
```

---

### Task 3: reparse_and_replace_chunks

변경 파일을 재파싱하고 `chunks.json`에서 해당 `source_file`의 기존 청크를 제거한 뒤 새 청크로 교체한다. 수정 파일에서 중복 청크가 생기지 않도록 한다. 기존 파일의 `file_type`은 보존하고, 신규 파일은 `"note"`를 사용한다.

**Files:**
- Modify: `src/backend/app/services/watcher.py`
- Test: `src/backend/tests/test_services/test_watcher.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_services/test_watcher.py`에 추가 (파일 상단 import에 합치기):

```python
import json
from pathlib import Path

from app.models.graph import TextChunk
from app.services.watcher import reparse_and_replace_chunks


def _write_chunks(proj_dir: Path, chunks: list[dict]) -> None:
    (proj_dir / "chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False), encoding="utf-8"
    )


def test_replace_chunks_no_duplicates_for_modified_file(monkeypatch, tmp_path):
    proj_dir = tmp_path / "p1"
    (proj_dir / "files").mkdir(parents=True)
    # 기존 chunks.json: a.txt 청크 1개(옛 내용) + b.txt 청크 1개(무관)
    _write_chunks(proj_dir, [
        {"chunk_id": "old", "text": "old", "source_file": "a.txt",
         "file_type": "resume", "page_num": 1, "char_offset": 0},
        {"chunk_id": "keep", "text": "keep", "source_file": "b.txt",
         "file_type": "note", "page_num": 1, "char_offset": 0},
    ])
    monkeypatch.setattr("app.services.watcher.config.PROJECTS_DIR", str(tmp_path))

    # ParserAgent.run을 가짜로: a.txt에 대해 새 청크 1개 반환
    def fake_run(self, file_paths, file_type="note", progress_callback=None):
        return [TextChunk(chunk_id="new", text="new", source_file="a.txt",
                          file_type=file_type, page_num=1, char_offset=0)]
    monkeypatch.setattr("app.agents.parser_agent.ParserAgent.run", fake_run)

    reparse_and_replace_chunks("p1", {"a.txt"})

    result = json.loads((proj_dir / "chunks.json").read_text(encoding="utf-8"))
    a_chunks = [c for c in result if c["source_file"] == "a.txt"]
    b_chunks = [c for c in result if c["source_file"] == "b.txt"]
    assert len(a_chunks) == 1
    assert a_chunks[0]["text"] == "new"
    assert a_chunks[0]["file_type"] == "resume"  # 기존 file_type 보존
    assert len(b_chunks) == 1  # 무관 파일 청크는 유지
    assert b_chunks[0]["chunk_id"] == "keep"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_services/test_watcher.py::test_replace_chunks_no_duplicates_for_modified_file -v`
Expected: FAIL — `ImportError: cannot import name 'reparse_and_replace_chunks'`

- [ ] **Step 3: 구현 추가**

`src/backend/app/services/watcher.py` 상단에 import 추가하고 함수 추가:

```python
import dataclasses
import json
from pathlib import Path

from app.config import config


def reparse_and_replace_chunks(project_id: str, changed_files: set[str]) -> None:
    """changed_files를 재파싱해 chunks.json에서 해당 source_file 청크를 교체한다."""
    from app.agents.parser_agent import ParserAgent

    proj_dir = Path(config.PROJECTS_DIR) / project_id
    files_dir = proj_dir / "files"
    chunks_path = proj_dir / "chunks.json"

    existing = json.loads(chunks_path.read_text(encoding="utf-8")) if chunks_path.exists() else []

    # source_file → file_type 매핑(기존 청크에서 보존)
    file_type_by_source = {c["source_file"]: c.get("file_type", "note") for c in existing}

    # 변경 파일의 기존 청크 제거
    kept = [c for c in existing if c["source_file"] not in changed_files]

    agent = ParserAgent()
    new_chunks: list[dict] = []
    for fname in sorted(changed_files):
        fpath = files_dir / fname
        if not fpath.exists():
            continue
        file_type = file_type_by_source.get(fname, "note")
        parsed = agent.run([str(fpath)], file_type=file_type)
        new_chunks.extend(dataclasses.asdict(c) for c in parsed)

    combined = kept + new_chunks
    chunks_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_services/test_watcher.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add app/services/watcher.py tests/test_services/test_watcher.py
git commit -m "feat: add reparse_and_replace_chunks for in-place file edits"
```

---

### Task 4: _run_graph에 trigger 파라미터 + trace 기록

자동 빌드와 수동 빌드를 trace에서 구분할 수 있게 `_run_graph`에 `trigger` 파라미터를 추가하고 graph_build trace에 포함한다.

**Files:**
- Modify: `src/backend/app/api/graph.py`
- Test: `src/backend/tests/test_agents/test_graph_build_trigger.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_agents/test_graph_build_trigger.py` 생성:

```python
import inspect

from app.api.graph import _run_graph


def test_run_graph_accepts_trigger_param():
    sig = inspect.signature(_run_graph)
    assert "trigger" in sig.parameters
    assert sig.parameters["trigger"].default == "manual"


def test_run_graph_source_records_trigger_in_trace():
    # _run_graph 본문이 record_trace 호출에 trigger=trigger를 전달하는지 정적 확인
    src = inspect.getsource(_run_graph)
    assert "trigger=trigger" in src
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_agents/test_graph_build_trigger.py -v`
Expected: FAIL — `trigger`가 시그니처에 없음 / `trigger=trigger` 미존재

- [ ] **Step 3: 구현 수정**

`src/backend/app/api/graph.py`에서 `_run_graph` 시그니처를 변경:

변경 전:
```python
async def _run_graph(task_id: str, project_id: str, incremental: bool):
```
변경 후:
```python
async def _run_graph(task_id: str, project_id: str, incremental: bool, trigger: str = "manual"):
```

같은 함수의 trace 기록 블록(Phase 1에서 추가됨, `record_trace(` 호출)에서 `cost_usd=round(cost_delta, 6),` 다음 줄에 `trigger=trigger,`를 추가. 최종 형태:

```python
        try:
            cost_delta = get_llm_usage().get("total_cost_usd", 0.0) - usage_before
            record_trace(
                project_id,
                "graph_build",
                backend=route(Role.CHUNK_EXTRACTION),
                incremental=incremental,
                nodes=stats.total_nodes,
                edges=stats.total_edges,
                cost_usd=round(cost_delta, 6),
                trigger=trigger,
            )
        except Exception:
            pass  # trace is best-effort; never fail a successful build on logging
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_agents/test_graph_build_trigger.py -v`
Expected: PASS (2 passed)

전체 회귀:
Run: `python3 -m pytest tests/ -q`
Expected: 실패 0

- [ ] **Step 5: 커밋**

```bash
git add app/api/graph.py tests/test_agents/test_graph_build_trigger.py
git commit -m "feat: add trigger field to graph build trace"
```

---

### Task 5: WatcherService (감지 IO + 오케스트레이션)

`files/` 열거·해시 계산·직전 폴링 상태 보관(IO)과, 자동 업데이트 오케스트레이션을 담당한다. 폴링 루프와 시작/정지도 포함.

**Files:**
- Modify: `src/backend/app/services/watcher.py`
- Modify: `src/backend/app/config.py`
- Test: `src/backend/tests/test_services/test_watcher.py`

- [ ] **Step 1: config 설정 추가**

`src/backend/app/config.py`에서 `GRAPH_BUILD_WORKERS: int = 2` 다음 줄에 추가:

```python
    WATCHER_ENABLED: bool = False
    WATCHER_POLL_SECONDS: int = 15
```

- [ ] **Step 2: 실패하는 테스트 작성**

`src/backend/tests/test_services/test_watcher.py`에 추가:

```python
import asyncio
import hashlib

import pytest

from app.services.watcher import WatcherService


def _make_project(tmp_path, pid, files: dict[str, str], built_hashes: dict[str, str]):
    proj_dir = tmp_path / pid
    files_dir = proj_dir / "files"
    files_dir.mkdir(parents=True)
    for name, content in files.items():
        (files_dir / name).write_text(content, encoding="utf-8")
    # 빌드완료 표시 파일들
    (proj_dir / "chunks.json").write_text("[]", encoding="utf-8")
    (proj_dir / "ontology.json").write_text("{}", encoding="utf-8")
    (proj_dir / "graph.json").write_text("{}", encoding="utf-8")
    (proj_dir / "hashes.json").write_text(
        json.dumps(built_hashes), encoding="utf-8"
    )
    return proj_dir


def test_eligible_projects_only_built(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watcher.config.PROJECTS_DIR", str(tmp_path))
    _make_project(tmp_path, "built", {"a.txt": "x"}, {})
    # 미빌드 프로젝트: graph.json 없음
    unbuilt = tmp_path / "unbuilt" / "files"
    unbuilt.mkdir(parents=True)
    (tmp_path / "unbuilt" / "chunks.json").write_text("[]", encoding="utf-8")

    svc = WatcherService()
    assert svc.eligible_projects() == ["built"]


def test_poll_once_triggers_update_for_stable_change(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watcher.config.PROJECTS_DIR", str(tmp_path))
    content = "hello"
    h = hashlib.md5(content.encode()).hexdigest()
    _make_project(tmp_path, "p1", {"a.txt": content}, {})  # last_built 비어있음 → 신규

    svc = WatcherService()
    # 직전 폴링 상태를 현재와 동일하게 미리 채워 "안정" 상태로 만듦
    svc._prev_hashes["p1"] = {"a.txt": h}

    calls = []

    async def fake_update(project_id, files):
        calls.append((project_id, set(files)))

    monkeypatch.setattr(svc, "run_auto_update", fake_update)
    monkeypatch.setattr(
        "app.services.watcher.task_manager.has_active_build", lambda pid: False
    )

    asyncio.run(svc.poll_once())
    assert calls == [("p1", {"a.txt"})]


def test_poll_once_skips_when_build_active(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watcher.config.PROJECTS_DIR", str(tmp_path))
    content = "hello"
    h = hashlib.md5(content.encode()).hexdigest()
    _make_project(tmp_path, "p1", {"a.txt": content}, {})

    svc = WatcherService()
    svc._prev_hashes["p1"] = {"a.txt": h}

    calls = []

    async def fake_update(project_id, files):
        calls.append(project_id)

    monkeypatch.setattr(svc, "run_auto_update", fake_update)
    monkeypatch.setattr(
        "app.services.watcher.task_manager.has_active_build", lambda pid: True
    )

    asyncio.run(svc.poll_once())
    assert calls == []


def test_start_noop_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watcher.config.WATCHER_ENABLED", False)
    svc = WatcherService()
    svc.start()
    assert svc._task is None
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_services/test_watcher.py -v`
Expected: FAIL — `ImportError: cannot import name 'WatcherService'`

- [ ] **Step 4: 구현 추가**

`src/backend/app/services/watcher.py`에 import와 클래스를 추가. 파일 상단 import 블록을 다음으로 확장(기존 `import dataclasses`/`import json`/`from pathlib import Path`/`from app.config import config`에 추가):

```python
import asyncio
import hashlib

from app.services.task_manager import task_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)
```

파일 끝에 클래스 추가:

```python
class WatcherService:
    def __init__(self):
        self._prev_hashes: dict[str, dict[str, str]] = {}
        self._task: asyncio.Task | None = None
        self._stop = False

    def eligible_projects(self) -> list[str]:
        root = Path(config.PROJECTS_DIR)
        if not root.exists():
            return []
        result = []
        for proj in sorted(root.iterdir()):
            if not proj.is_dir():
                continue
            if (
                (proj / "chunks.json").exists()
                and (proj / "ontology.json").exists()
                and (proj / "graph.json").exists()
            ):
                result.append(proj.name)
        return result

    def _current_hashes(self, project_id: str) -> dict[str, str]:
        files_dir = Path(config.PROJECTS_DIR) / project_id / "files"
        if not files_dir.exists():
            return {}
        out: dict[str, str] = {}
        for f in files_dir.iterdir():
            if f.is_file():
                out[f.name] = hashlib.md5(f.read_bytes()).hexdigest()
        return out

    def _last_built_hashes(self, project_id: str) -> dict[str, str]:
        path = Path(config.PROJECTS_DIR) / project_id / "hashes.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {k: v for k, v in data.items() if k != "__ontology__"}

    def detect_changes(self, project_id: str) -> set[str]:
        current = self._current_hashes(project_id)
        last_built = self._last_built_hashes(project_id)
        prev_poll = self._prev_hashes.get(project_id, {})
        stable = compute_stable_changes(current, last_built, prev_poll)
        self._prev_hashes[project_id] = current
        return stable

    async def run_auto_update(self, project_id: str, changed_files: set[str]) -> None:
        from app.api.graph import _run_graph

        reparse_and_replace_chunks(project_id, changed_files)
        task = task_manager.create(project_id, "graph_watcher")
        await _run_graph(task.task_id, project_id, incremental=True, trigger="watcher")

    async def poll_once(self) -> None:
        for project_id in self.eligible_projects():
            try:
                if task_manager.has_active_build(project_id):
                    self._prev_hashes[project_id] = self._current_hashes(project_id)
                    continue
                changed = self.detect_changes(project_id)
                if changed:
                    logger.info(f"Watcher: {project_id} 변경 감지 {sorted(changed)} → 자동 빌드")
                    await self.run_auto_update(project_id, changed)
            except Exception as e:
                logger.error(f"Watcher: {project_id} 처리 실패: {e}")

    async def _loop(self) -> None:
        while not self._stop:
            try:
                await self.poll_once()
            except Exception as e:
                logger.error(f"Watcher 폴링 사이클 실패: {e}")
            await asyncio.sleep(config.WATCHER_POLL_SECONDS)

    def start(self) -> None:
        if not config.WATCHER_ENABLED:
            return
        self._stop = False
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Watcher 시작 (간격 {config.WATCHER_POLL_SECONDS}s)")

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_services/test_watcher.py -v`
Expected: PASS (10 passed)

전체 회귀:
Run: `python3 -m pytest tests/ -q`
Expected: 실패 0

- [ ] **Step 6: 커밋**

```bash
git add app/services/watcher.py app/config.py tests/test_services/test_watcher.py
git commit -m "feat: add WatcherService polling loop and orchestration"
```

---

### Task 6: main.py lifespan 통합

WatcherService를 앱 시작 시 시작하고 종료 시 정지한다.

**Files:**
- Modify: `src/backend/app/main.py`
- Test: `src/backend/tests/test_services/test_watcher.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/backend/tests/test_services/test_watcher.py`에 추가:

```python
def test_app_has_lifespan_and_watcher_imported():
    import app.main as main_mod

    # lifespan이 FastAPI 앱에 연결되어 있어야 함
    assert main_mod.app.router.lifespan_context is not None
    # WatcherService가 main에서 import되어 있어야 함
    assert hasattr(main_mod, "WatcherService") or "WatcherService" in dir(main_mod)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_services/test_watcher.py::test_app_has_lifespan_and_watcher_imported -v`
Expected: FAIL — main에 WatcherService 미존재 (현재 lifespan 미설정)

- [ ] **Step 3: main.py 수정**

`src/backend/app/main.py`를 수정. import 블록과 앱 생성 부분을 다음으로 변경.

변경 전:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, graph, chat, tasks, user, settings, skills
from app.utils.logger import configure_logging

configure_logging()

app = FastAPI(title="ProjectOS", version="0.1.0")
```

변경 후:
```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import projects, graph, chat, tasks, user, settings, skills
from app.services.watcher import WatcherService
from app.utils.logger import configure_logging

configure_logging()

_watcher = WatcherService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _watcher.start()
    try:
        yield
    finally:
        await _watcher.stop()


app = FastAPI(title="ProjectOS", version="0.1.0", lifespan=lifespan)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_services/test_watcher.py::test_app_has_lifespan_and_watcher_imported -v`
Expected: PASS (1 passed)

import 정상 확인:
Run: `python3 -c "import app.main"`
Expected: exit 0

전체 회귀:
Run: `python3 -m pytest tests/ -q`
Expected: 실패 0 (기본 `WATCHER_ENABLED=False`라 테스트 중 watcher 미동작)

- [ ] **Step 5: 커밋**

```bash
git add app/main.py tests/test_services/test_watcher.py
git commit -m "feat: start file watcher in app lifespan"
```

---

## 실행 후 확인 (수동, 선택)

`.env`에 `WATCHER_ENABLED=true` 설정 후 서버 실행, 빌드 완료된 프로젝트의 `files/`에 파일을 추가/수정하고 ~30초(2 폴링 사이클) 대기 → task 로그에 `graph_watcher` 빌드가 생기고 `traces.jsonl`에 `"trigger": "watcher"` 레코드가 남는지 확인. 끝나면 `WATCHER_ENABLED`를 다시 끄거나 유지.

---

## 문서 갱신 (마지막 태스크 후)

CLAUDE.md 규칙: 작업 완료 후 `docs/claude-code-handoff.md`를 갱신할 것 — 변경 내역, 검증 결과(전체 테스트 통과 수), 다음 작업 후보(Phase 2b Digest Agent) 포함.
