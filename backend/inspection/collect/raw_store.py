"""013-I01：采集原始响应存档（data/raw/<run_id>/）。

原则：
- **不截断任何响应**。raw 是页面改版后排查的证据，截断等于销毁证据。
- manifest.json 是目录索引：谁、什么时候、从哪采、采到什么、结论如何。
- `source` 字段只由采集层（item.py）判定：抓到 ≥1 个详情 XHR → page_xhr，
  否则 none。解析层（parser.py）沿用，不重新解释。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAW_ROOT = Path(__file__).resolve().parents[3] / "data" / "raw"


class RawStoreError(RuntimeError):
    """存档写入失败（磁盘 / 权限问题）。"""


def make_run_id(item_id: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{item_id}"


def _write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def update_manifest(run_dir: Path, **patch: Any) -> dict[str, Any]:
    manifest = read_manifest(run_dir)
    manifest.update(patch)
    _write_manifest(run_dir, manifest)
    return manifest


def new_run(item_id: str, url: str, *, raw_root: Path | None = None) -> Path:
    root = raw_root or RAW_ROOT
    run_id = make_run_id(item_id)
    run_dir = root / run_id
    (run_dir / "xhr").mkdir(parents=True, exist_ok=True)
    _write_manifest(
        run_dir,
        {
            "run_id": run_id,
            "item_id": item_id,
            "url": url,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "finished_at": None,
            "ok": None,
            "error": None,
            "xhr_count": 0,
            "source": "none",
            "desc_fetched": False,
        },
    )
    return run_dir


def _short_name(url: str) -> str:
    """从 URL 提取可读文件名：mtop 接口取方法名，其余取末段路径。"""
    match = re.search(r"mtop\.([A-Za-z0-9_.-]+)", url)
    if match:
        return match.group(1)
    segment = url.split("?")[0].rstrip("/").split("/")[-1]
    segment = re.sub(r"[^\w.-]", "_", segment)
    return segment[:60] or "response"


def save_xhr(run_dir: Path, idx: int, url: str, body: bytes) -> Path:
    path = run_dir / "xhr" / f"{idx:03d}-{_short_name(url)}.json"
    path.write_bytes(body)
    return path


def save_desc(run_dir: Path, url: str, body: bytes) -> Path:
    """详情描述（desc）内容：单独落盘，便于 parser 直接统计详情图。"""
    (run_dir / "desc.url.txt").write_text(url, encoding="utf-8")
    path = run_dir / "desc.html"
    path.write_bytes(body)
    return path


def save_html(run_dir: Path, html: str) -> Path:
    path = run_dir / "page.html"
    path.write_text(html, encoding="utf-8")
    return path


def save_shot(page, run_dir: Path, name: str = "shot") -> Path | None:
    try:
        path = run_dir / f"{name}.png"
        page.screenshot(path=str(path), full_page=False)
        return path
    except Exception:  # noqa: BLE001 — 截图失败不阻断主流程
        return None


def finish(
    run_dir: Path,
    *,
    ok: bool,
    error: str | None = None,
    xhr_count: int,
    source: str,
    desc_fetched: bool = False,
) -> dict[str, Any]:
    return update_manifest(
        run_dir,
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ok=ok,
        error=error,
        xhr_count=xhr_count,
        source=source,
        desc_fetched=desc_fetched,
    )
