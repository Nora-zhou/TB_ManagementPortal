"""013-I01：检测采集专用账号（account-9001）的手动预登录。

背景：2026-10 起淘宝商品页强制登录（见 NOTES-item-page.md），匿名采集已不可行。
本工具打开**检测专用** profile 的可见浏览器窗口，由用户扫码完成淘宝登录；
登录态由 Chromium 持久化到 browser_data/account-9001，之后的采集任务复用。

流程：
    打开淘宝登录页 → 自动检测登录成功（cookie2 + 离开登录域名）→
    打开一个商品页验证详情数据链路 → 退出（登录态已落盘）

用法（在 backend/ 目录下）：
    python inspect_cli.py login
"""

from __future__ import annotations

import time

from rpa.browser import BrowserSession, NeedManualVerification, ScrapeError
from rpa.logging_utils import safe_print

from . import INSPECTION_ACCOUNT_ID

LOGIN_URL = "https://login.taobao.com/member/login.jhtml"
VALIDATE_ITEM_ID = "1052810876450"  # 本店在售商品，仅用于验证数据链路
VALIDATE_URL = f"https://item.taobao.com/item.htm?id={VALIDATE_ITEM_ID}"

POLL_INTERVAL = 2.0
LOGIN_TIMEOUT = 600.0  # 扫码 + 手机确认留足时间
VALIDATE_WAIT = 20.0


def _has_taobao_login_cookie(session: BrowserSession) -> bool:
    try:
        cookies = session.page.context.cookies()
    except Exception:  # noqa: BLE001 — 页面可能正在导航
        return False
    return any(c["name"] == "cookie2" and c["value"] for c in cookies)


def _wait_for_login(session: BrowserSession, timeout: float = LOGIN_TIMEOUT) -> None:
    safe_print("等待扫码 / 账号密码登录 …（最长 10 分钟，无需按回车）")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _has_taobao_login_cookie(session) and "login.taobao.com" not in session.page.url:
            safe_print(f"检测到登录成功：{session.page.url}")
            return
        time.sleep(POLL_INTERVAL)
    raise ScrapeError("登录等待超时（10 分钟）")


def _validate(session: BrowserSession) -> bool:
    """登录后打开商品页，验证详情数据请求是否恢复。"""
    hits: list[str] = []

    def on_response(resp) -> None:
        try:
            if resp.request.resource_type in ("xhr", "fetch") and any(
                key in resp.url for key in ("detail", "pcdetail", "mtop")
            ):
                hits.append(resp.url)
        except Exception:  # noqa: BLE001
            pass

    page = session.page
    page.on("response", on_response)

    try:
        session.goto(VALIDATE_URL)
    except NeedManualVerification:
        safe_print("验证：商品页出现滑块（正常风控），采集时会暂停等待人工处理")
        return True

    deadline = time.time() + VALIDATE_WAIT
    while time.time() < deadline and not hits:
        time.sleep(0.5)

    if hits:
        safe_print(f"验证通过：商品页抓到 {len(hits)} 个数据请求")
        return True
    safe_print("验证未通过：商品页没有数据请求，登录态可能未生效（可重试 login）")
    return False


def login() -> int:
    safe_print(f"打开检测专用浏览器 profile：account-{INSPECTION_ACCOUNT_ID}")
    safe_print("请在弹出的浏览器窗口中完成淘宝登录（推荐扫码）。")
    safe_print("登录成功会自动继续，无需回到本窗口操作。")

    with BrowserSession(
        INSPECTION_ACCOUNT_ID,
        label="inspection-login",
        mode="isolated",
        headless=False,
    ) as session:
        try:
            session.goto(LOGIN_URL)
        except NeedManualVerification:
            # 登录页本身含滑块组件（密码登录形态），不算异常
            safe_print("登录页出现验证组件，请直接在浏览器窗口完成登录")

        try:
            _wait_for_login(session)
        except (ScrapeError, KeyboardInterrupt) as exc:
            safe_print(f"登录未完成：{exc}")
            return 2

        time.sleep(2.0)  # 等登录态稳定
        ok = _validate(session)
        safe_print(f"登录态已保存到：{session.profile_dir}")
        safe_print("之后 collect 会自动复用，无需再登录。")
        return 0 if ok else 3
