"""013-I01·T3：取数层。驱动浏览器抓一个商品页，返回 run 目录。

要点（都来自探路实测）：
- 必须用检测专用 profile（account-9001）+ 登录态（先跑 inspect_cli.py login）。
- 数据在 SSR HTML 里，等待 window.__ICE_APP_CONTEXT__ 出现即可，不用等 XHR。
- headless 模式易触发滑块：默认 headed，--headless 显式开启（I05 批量再评估）。
- 详情图数量需要二次请求 item.pcADescUrl（页面本身不含详情长图）。
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from rpa.browser import BrowserSession, NeedManualVerification
from rpa.selectors import TAOBAO_ITEM, item_url

from . import INSPECTION_ACCOUNT_ID, raw_store


class CollectError(RuntimeError):
    """采集失败。kind: need_login / need_verify / item_gone / no_data / unexpected"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def _save_detail_xhr(run_dir: Path, state: dict) -> None:
    def on_response(resp) -> None:
        try:
            if resp.request.resource_type in ("xhr", "fetch") and any(
                key in resp.url for key in ("detail", "pcdetail", "mtop")
            ):
                state["count"] += 1
                raw_store.save_xhr(run_dir, state["count"], resp.url, resp.body())
        except Exception:  # noqa: BLE001 — 无 body 的响应（重定向等）跳过
            pass

    return on_response


def _fetch_desc(session, run_dir: Path, html: str) -> bool:
    """打开详情描述页（SPA，JS 渲染），等图片渲染后落盘。

    pcADescUrl 返回的只是 JS 壳（实测 1.7KB，无内容），必须让浏览器执行 JS。
    失败不阻断主流程，只影响 detail_image_count。
    """
    match = re.search(r'"pcADescUrl"\s*:\s*"([^"]+)"', html)
    if not match:
        return False
    desc_url = match.group(1)
    if desc_url.startswith("//"):
        desc_url = "https:" + desc_url

    page = session.page
    try:
        session.goto(desc_url)
    except Exception:  # noqa: BLE001 — 滑块 / 超时：desc 尽力而为
        return False

    # 滚动 + 轮询，等懒加载的详情图渲染出来
    deadline = time.time() + 12.0
    image_count = 0
    while time.time() < deadline:
        try:
            image_count = page.evaluate(
                "document.querySelectorAll('#root img').length"
            )
        except Exception:  # noqa: BLE001
            image_count = 0
        if image_count > 0:
            break
        try:
            page.evaluate("window.scrollBy(0, 1200)")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)

    try:
        content = page.content()
        raw_store.save_desc(run_dir, desc_url, content.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return image_count > 0


def fetch_item(
    item_id: str,
    *,
    headed: bool = True,
    wait_timeout: float = 20.0,
    raw_root: Path | None = None,
) -> Path:
    """抓一个商品页。成功返回 run 目录；失败抛 CollectError（run 目录仍保留）。"""
    url = item_url(item_id)
    run_dir = raw_store.new_run(item_id, url, raw_root=raw_root)
    xhr_state = {"count": 0}
    source = "none"

    try:
        with BrowserSession(
            INSPECTION_ACCOUNT_ID,
            label=f"collect-{item_id}",
            mode="isolated",
            headless=not headed,
        ) as session:
            page = session.page
            page.on("response", _save_detail_xhr(run_dir, xhr_state))

            try:
                session.goto(url)
            except NeedManualVerification as exc:
                raw_store.finish(
                    run_dir, ok=False, error=f"need_verify: {exc.reason}",
                    xhr_count=xhr_state["count"], source=source,
                )
                raise CollectError("need_verify", exc.reason) from exc

            # 未登录：跳登录墙
            if TAOBAO_ITEM["login_url_keyword"] in page.url:
                raw_store.finish(
                    run_dir, ok=False, error="redirected_to_login",
                    xhr_count=xhr_state["count"], source=source,
                )
                raise CollectError(
                    "need_login",
                    "页面跳转到登录墙：请先运行 python inspect_cli.py login 完成扫码登录",
                )

            html = page.content()

            # 商品不存在 / 已下架
            if any(marker in html for marker in TAOBAO_ITEM["gone_markers"]):
                raw_store.save_html(run_dir, html)
                raw_store.save_shot(page, run_dir)
                raw_store.finish(
                    run_dir, ok=False, error="item_gone",
                    xhr_count=xhr_state["count"], source=source,
                )
                raise CollectError("item_gone", "商品不存在或已下架")

            # 等 SSR 数据就绪（轮询，命中即走，不空等满超时）
            deadline = time.time() + wait_timeout
            ready = False
            while time.time() < deadline:
                try:
                    if page.evaluate(TAOBAO_ITEM["ssr_ready_js"]):
                        ready = True
                        break
                except Exception:  # noqa: BLE001 — 页面导航中
                    pass
                time.sleep(0.3)
            source = "page_dom" if ready else "none"

            session.human_delay(0.5, 1.0)
            html = page.content()
            raw_store.save_html(run_dir, html)
            raw_store.save_shot(page, run_dir)
            desc_fetched = _fetch_desc(session, run_dir, html)

            raw_store.finish(
                run_dir, ok=ready,
                error=None if ready else "ssr_data_not_found",
                xhr_count=xhr_state["count"], source=source,
                desc_fetched=desc_fetched,
            )
            if not ready:
                raise CollectError(
                    "no_data",
                    "页面未出现 __ICE_APP_CONTEXT__ 数据（可能登录态失效或页面改版）",
                )

    except CollectError:
        raise
    except Exception as exc:  # noqa: BLE001 — 兜底：保留 run 目录供排查
        raw_store.finish(
            run_dir, ok=False, error=f"{type(exc).__name__}: {exc}",
            xhr_count=xhr_state["count"], source=source,
        )
        raise CollectError("unexpected", str(exc)) from exc

    return run_dir
