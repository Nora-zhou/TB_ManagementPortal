"""013-I01·T0 探针：打开商品页，记录全部 XHR/fetch，回答 6 个探路问题。

与 T3（fetch_item）使用同一引擎（Playwright Chromium + account-9001 profile），
保证探路结论可直接复用。探针本身也是一个最小采集骨架。

用法：
    cd backend
    python -m inspection.collect.probe --item 1052810876450
    python -m inspection.collect.probe --item 1052810876450 --headed

产出：data/probe/<item_id>/page.html、shot.png、xhr/*.json
stdout：JSON 摘要（最终 URL / 是否登录墙 / XHR 清单及可解析性 / 下架特征）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rpa.browser import BrowserSession, NeedManualVerification

from . import INSPECTION_ACCOUNT_ID

PROBE_DIR = Path(__file__).resolve().parents[3] / "data" / "probe"

LOGIN_WALL_MARKERS = ("login.taobao.com", "亲，请登录", "请登录后查看")
GONE_MARKERS = ("宝贝不存在", "该商品已经下架", "商品已下架", "页面不见了")


def _looks_like_json(body: bytes) -> tuple[bool, list[str]]:
    """回答探路问题 6：mtop 系接口的包壳 / 加密情况。"""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return False, []
    if isinstance(data, dict):
        return True, list(data.keys())[:12]
    return True, [type(data).__name__]


PC_URL = "https://item.taobao.com/item.htm?id={item_id}"
H5_URL = "https://main.m.taobao.com/security-h5-detail/home?id={item_id}"


def probe(item_id: str, *, headed: bool = False, kind: str = "pc", url: str | None = None) -> int:
    url = url or (PC_URL if kind == "pc" else H5_URL).format(item_id=item_id)
    if url and kind not in url:
        # --url 自定义地址：用 host 末段避免目录互相覆盖
        from urllib.parse import urlparse

        slug = urlparse(url).netloc.split(".")[-2]
        kind = f"url-{slug}"
    out_dir = PROBE_DIR / f"{item_id}-{kind}"
    (out_dir / "xhr").mkdir(parents=True, exist_ok=True)

    captured: list[tuple[str, int, bytes]] = []

    with BrowserSession(
        INSPECTION_ACCOUNT_ID, label="probe", mode="isolated", headless=not headed
    ) as session:
        page = session.page

        def on_response(resp) -> None:
            try:
                if resp.request.resource_type in ("xhr", "fetch"):
                    captured.append((resp.url, resp.status, resp.body()))
            except Exception:  # noqa: BLE001 — 个别响应（如重定向）无 body
                pass

        page.on("response", on_response)

        console_lines: list[str] = []

        def on_console(msg) -> None:
            console_lines.append(f"[{msg.type}] {msg.text[:300]}")

        page.on("console", on_console)
        page.on("pageerror", lambda err: console_lines.append(f"[pageerror] {err}"))

        try:
            session.goto(url)
        except NeedManualVerification as exc:
            print(json.dumps({"need_verify": True, "reason": exc.reason}, ensure_ascii=False))
            return 2

        final_url = page.url
        title = page.title()

        # 滚动触发懒加载（详情图 / desc 模块）
        for _ in range(4):
            try:
                page.evaluate("window.scrollBy(0, 1500)")
            except Exception:  # noqa: BLE001
                break
            session.human_delay(0.8, 1.2)

        # 多等几秒：H5 SPA 的数据请求可能比渲染晚
        session.human_delay(3.0, 4.0)
        console_lines.append(f"[info] final_url={page.url}")
        (out_dir / "console.log").write_text(
            "\n".join(console_lines), encoding="utf-8"
        )

        html = page.content()
        (out_dir / "page.html").write_text(html, encoding="utf-8")
        try:
            page.screenshot(path=str(out_dir / "shot.png"), full_page=False)
        except Exception:  # noqa: BLE001
            pass

    login_wall = any(m in final_url for m in LOGIN_WALL_MARKERS) or any(
        m in html for m in LOGIN_WALL_MARKERS[:1]
    )
    gone = any(m in html for m in GONE_MARKERS)

    xhr_summary = []
    for idx, (req_url, status, body) in enumerate(captured, start=1):
        json_ok, keys = _looks_like_json(body)
        name = f"{idx:03d}.json"
        (out_dir / "xhr" / name).write_bytes(body)
        xhr_summary.append(
            {
                "file": name,
                "status": status,
                "bytes": len(body),
                "url": req_url[:160],
                "json_ok": json_ok,
                "keys": keys,
            }
        )

    report = {
        "item_id": item_id,
        "kind": kind,
        "requested_url": url,
        "final_url": final_url,
        "title": title,
        "login_wall": login_wall,
        "gone": gone,
        "xhr_count": len(captured),
        "xhr": xhr_summary,
        "out_dir": str(out_dir),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="013-I01 商品页探针")
    parser.add_argument("--item", required=True, help="商品 ID")
    parser.add_argument("--page", choices=("pc", "h5"), default="pc")
    parser.add_argument("--url", default=None, help="完整 URL（覆盖 --page 模板）")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口（默认 headless）")
    args = parser.parse_args(argv)
    return probe(args.item, headed=args.headed, kind=args.page, url=args.url)


if __name__ == "__main__":
    sys.exit(main())
