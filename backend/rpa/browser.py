"""Playwright 浏览器会话管理。

设计要点：
- 每个平台账号使用**独立的 user_data_dir**，登录态（Cookie）由 Chromium
  持久化到磁盘，无需自行管理 Cookie 加密；同一账号重复抓取可免登录。
- 使用 **sync API**，必须在独立线程中运行（FastAPI 主线程是 asyncio 事件循环）。
- 出现滑块 / 短信验证时，任务会进入 `need_verify` 状态并等待用户在本机浏览器
  中手动完成（因为 headless=false 时浏览器窗口对用户可见）。
"""

from __future__ import annotations

import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PWTimeout,
    sync_playwright,
)

from rpa.config import rpa_config
from rpa.logging_utils import safe_print
from rpa.selectors import (
    ALIMAMA,
    CAPTCHA_CSS,
    LOGGED_OUT_MARKER_CSS,
    LOGIN_INPUTS,
    LOGIN_SUBMIT,
    LOGIN_URL_KEYWORDS,
    POPUP_CLOSE_CSS,
    QIANNIU,
    SSO_AUTHORIZE_BUTTONS,
)


class NeedManualVerification(Exception):
    """需要人工完成滑块 / 短信验证。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class LoginFailed(Exception):
    """登录失败（账号密码错误或页面结构变化）。"""


class ScrapeError(Exception):
    """抓取失败（页面改版、找不到目标元素等）。"""


class BrowserSession:
    """单个平台账号的一次抓取会话（同一账号复用同一浏览器 profile）。"""

    def __init__(self, account_id: int, label: str = ""):
        self.account_id = account_id
        self.label = label
        self._pw = None
        self._context: BrowserContext | None = None
        self._browser: Browser | None = None
        # CDP 模式下浏览器是用户的，不能整体关闭，只关自己开的标签页
        self._owns_context = True
        # 本次会话打开/接管的标签页。CDP / 系统 profile 模式下不能操作用户
        # 自己的标签页，因此只跟踪「我们的」页面。
        self._our_pages: list[Page] = []
        self.profile_dir: Path | None = (
            rpa_config.browser_profile_dir(account_id)
            if rpa_config.browser_mode == "isolated"
            else None
        )
        self.screenshots: list[str] = []
        self.logs: list[str] = []

    # ── 生命周期 ─────────────────────────────────────────────────
    def __enter__(self) -> "BrowserSession":
        self._pw = sync_playwright().start()
        mode = rpa_config.browser_mode

        if mode == "cdp":
            # 连接一个已经打开的浏览器，直接复用其登录态
            return self._connect_cdp()

        launch_kwargs: dict[str, Any] = {
            "headless": rpa_config.headless,
            "viewport": {"width": 1440, "height": 900},
            "accept_downloads": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        }
        if mode == "system":
            # 直接用系统浏览器（Edge/Chrome）的真实 profile：复用日常登录态，
            # 不再每次重新登录。要求该浏览器已完全关闭（profile 不能同时被占用）。
            if not rpa_config.system_profile_dir:
                raise ScrapeError(
                    "RPA_BROWSER_MODE=system，但未探测到系统浏览器 profile，"
                    "请在 .env 中配置 RPA_SYSTEM_PROFILE_DIR"
                )
            if rpa_config.browser_channel:
                launch_kwargs["channel"] = rpa_config.browser_channel
            launch_kwargs["user_data_dir"] = str(rpa_config.system_profile_dir)
            self.log(
                f"使用系统浏览器 profile：{rpa_config.system_profile_dir}"
                f"（channel={rpa_config.browser_channel}）"
                "——请先完全关闭该浏览器，否则会因 profile 被占用而启动失败"
            )
        else:
            launch_kwargs["user_data_dir"] = str(self.profile_dir)
            if rpa_config.chromium_path:
                launch_kwargs["executable_path"] = rpa_config.chromium_path

        try:
            self._context = self._pw.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:  # noqa: BLE001
            if mode == "system":
                raise ScrapeError(
                    f"启动系统浏览器失败：{exc}。常见原因是该浏览器正在运行、"
                    "profile 被占用——请先完全关闭 Edge/Chrome 后重试；"
                    "或者改用 RPA_BROWSER_MODE=cdp 连接已经打开的浏览器。"
                ) from exc
            raise
        self._context.set_default_timeout(30_000)
        self._adopt_context(self._context, adopt_existing=True)
        return self

    def _connect_cdp(self) -> "BrowserSession":
        """通过 CDP 连接已打开的浏览器，复用其全部登录态。"""
        endpoint = rpa_config.cdp_endpoint
        self.log(f"连接已经打开的浏览器（CDP {endpoint}）…")
        try:
            self._browser = self._pw.chromium.connect_over_cdp(endpoint)
        except Exception as exc:  # noqa: BLE001
            raise ScrapeError(
                f"无法连接 {endpoint}：{exc}。\n"
                "请先完全关闭浏览器，然后运行项目根目录的 "
                "start-browser-debug.bat 启动带调试端口的浏览器，再重试。"
            ) from exc
        contexts = self._browser.contexts
        self._context = contexts[0] if contexts else self._browser.new_context()
        self._owns_context = False
        self._context.set_default_timeout(30_000)
        self._adopt_context(self._context, adopt_existing=False)
        self.log("CDP 已连接：只操作本任务新开的标签页，不会动你已经打开的标签页")
        return self

    def _adopt_context(self, context: BrowserContext, adopt_existing: bool) -> None:
        """监听新标签页（登录弹窗等会开新标签），并准备工作标签页。

        adopt_existing=True 用于自己启动的浏览器（复用初始空白页）；
        CDP 模式下用户已打开的标签页不能动，必须新开一个。
        """
        context.on("page", self._track_page)
        if adopt_existing and context.pages:
            self._track_page(context.pages[-1])
        else:
            self._track_page(context.new_page())

    def _track_page(self, page: Page) -> None:
        if not any(p is page for p in self._our_pages):
            self._our_pages.append(page)

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._owns_context:
                if self._context is not None:
                    self._context.close()
            else:
                # CDP 连接：只关闭自己开的标签页，绝不去关闭用户的浏览器
                for page in list(self._our_pages):
                    try:
                        if not page.is_closed():
                            page.close()
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            if self._pw is not None:
                self._pw.stop()

    # ── 页面操作 ─────────────────────────────────────────────────
    @property
    def page(self) -> Page:
        """当前工作标签页。

        优先返回本次会话中最新打开、且未关闭的标签页（登录弹窗等会开新标签），
        不会去操作用户自己的标签页。
        """
        if self._context is None:
            raise ScrapeError("浏览器会话未启动")
        for candidate in reversed(self._our_pages):
            try:
                if not candidate.is_closed():
                    return candidate
            except Exception:  # noqa: BLE001
                continue
        # 自己的标签页都不在了：开一个新的
        new_page = self._context.new_page()
        self._track_page(new_page)
        return new_page

    def log(self, message: str) -> None:
        line = f"[{datetime.now(timezone.utc).astimezone().strftime('%H:%M:%S')}] {message}"
        self.logs.append(line)
        safe_print(line)

    def human_delay(self, low: float | None = None, high: float | None = None) -> None:
        low = low if low is not None else rpa_config.delay_min
        high = high if high is not None else rpa_config.delay_max
        time.sleep(random.uniform(max(0.0, low), max(low, high)))

    def goto(self, url: str, wait_until: str = "domcontentloaded") -> Page:
        page = self.page
        self.log(f"打开页面：{url}")
        try:
            page.goto(url, wait_until=wait_until, timeout=45_000)
        except PWTimeout:
            self.log(f"页面加载超时（继续尝试）：{url}")
        # SPA 页面 domcontentloaded 后仍在拉数据/渲染：尽量等 load 事件
        # （部分页面 load 事件可能很久不触发，超时后不阻塞流程）
        try:
            page.wait_for_load_state("load", timeout=10_000)
        except Exception:  # noqa: BLE001 — 等不到 load 也继续
            pass
        self.human_delay(1.0, 2.0)
        self._raise_if_manual_verify_needed(page)
        return page

    def screenshot(self, name: str) -> str:
        path = rpa_config.screenshot_dir / (
            f"{self.account_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{name}.png"
        )
        try:
            self.page.screenshot(path=str(path), full_page=True)
            self.screenshots.append(str(path))
            self.log(f"已保存截图：{path.name}")
        except Exception as exc:  # noqa: BLE001
            self.log(f"截图失败：{exc}")
        return str(path)

    # ── 登录态判定 / 登录 ────────────────────────────────────────
    @staticmethod
    def _is_login_url(url: str) -> bool:
        return any(k in url for k in LOGIN_URL_KEYWORDS)

    def _raise_if_manual_verify_needed(self, page: Page) -> None:
        """检测滑块 / 短信验证，命中则抛 NeedManualVerification。"""
        # 所有验证特征合并为一个选择器，命中任一即返回，避免逐个等待超时
        scopes = [page, *[f for f in page.frames if f != page.main_frame][:8]]
        for scope in scopes:
            try:
                if scope.locator(CAPTCHA_CSS).first.is_visible(timeout=800):
                    self.screenshot("captcha-detected")
                    raise NeedManualVerification(
                        f"检测到滑块/短信验证（{CAPTCHA_CSS}），"
                        "请在弹出的浏览器窗口中手动完成"
                    )
            except PWTimeout:
                continue
            except NeedManualVerification:
                raise
            except Exception:  # noqa: BLE001
                continue

    def is_logged_in(self, target_url: str, attempts: int = 3) -> bool:
        page = self.page
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
        except PWTimeout:
            self.log(f"页面加载超时：{target_url}")
        # SPA 门户（work.taobao.com 等）登录态渲染慢：domcontentloaded 之后
        # 页面可能还没 hydrate，此时按 DOM 判定会把「加载中」误判为未登录。
        # 因此先等待页面稳定，未登录特征命中后再复核几次才下结论。
        self.human_delay(2.0, 3.5)
        for attempt in range(1, attempts + 1):
            url = page.url
            if self._is_login_url(url):
                self.log(f"需要登录（当前位于 {url}）")
                return False
            if self._looks_logged_out(page):
                if attempt < attempts:
                    self.log(
                        f"页面暂未显示登录状态，等待渲染后重试（{attempt}/{attempts}）"
                    )
                    self.human_delay(2.5, 4.0)
                    continue
                self.log(f"需要登录（页面显示未登录状态）：{url}")
                return False
            self.log(f"已登录（{url}）")
            return True
        return False

    def ensure_logged_in(self, target_url: str, attempts: int = 3) -> bool:
        """确保已登录目标门户：导航 + 完成 SSO 授权链 + 复核。

        淘宝系在 login.taobao.com 登录成功后，跳回工作台（work.taobao.com 等）
        还要走完 SSO 授权跳转链（登录页 → 授权确认页 → 门户）。链上任何一环
        没走完都会退回到登录页，表现为「登录成功后又回到登录页面」。
        这里反复导航到目标门户，并在授权/确认页点击授权按钮。
        """
        for attempt in range(1, attempts + 1):
            page = self.page
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
            except PWTimeout:
                self.log(f"页面加载超时：{target_url}")
            self.human_delay(2.0, 3.5)
            # 停在登录/授权页时，点击「授权并登录」等按钮把 SSO 链走完
            if self._is_login_url(self.page.url) or self._looks_logged_out(self.page):
                self._click_sso_authorize()
            url = self.page.url
            if not self._is_login_url(url) and not self._looks_logged_out(self.page):
                self.log(f"已进入目标门户（{url}）")
                return True
            self.log(
                f"尚未进入目标门户（当前 {url}），等待后重试（{attempt}/{attempts}）"
            )
            self.human_delay(3.0, 5.0)
        return False

    def _click_sso_authorize(self) -> bool:
        """在 SSO 授权/确认页点击授权按钮（如「授权并登录」）。"""
        clicked = False
        try:
            elements = self.page.locator(", ".join(SSO_AUTHORIZE_BUTTONS)).all()
        except Exception:  # noqa: BLE001
            return False
        for el in elements[:3]:
            try:
                if el.is_visible(timeout=600):
                    el.click()
                    clicked = True
                    self.log("已点击 SSO 授权按钮")
                    self.human_delay(2.0, 3.5)
            except Exception:  # noqa: BLE001
                continue
        return clicked

    def login(self, username: str, password: str, login_url: str) -> None:
        """账号密码登录。出现验证码时抛 NeedManualVerification。"""
        page = self.goto(login_url)
        self.log("开始登录…")

        # 部分门户（如 work.taobao.com）不会自动跳转登录页，需先点「登录」入口
        if not self._is_login_url(page.url):
            self._click_login_entry(page)
        # 「登录」入口可能打开新标签页/弹窗，重新取当前页
        page = self.page

        user_input, pwd_input = self._find_login_form(page)
        if user_input is None or pwd_input is None:
            self.screenshot("login-form-not-found")
            # 浏览器窗口对用户可见：登录页改版导致自动填写不可用时，
            # 转为等待用户在窗口中手动完成登录，而不是直接让任务失败。
            self.log("未找到账号/密码输入框，转为等待人工登录")
            self.wait_for_manual_verification(
                "未找到账号/密码输入框（登录页结构可能已改版），"
                "请在弹出的浏览器窗口中手动完成登录"
            )
            return

        user_input.click()
        self.human_delay(0.3, 0.8)
        user_input.fill(username)
        self.human_delay(0.3, 0.8)
        pwd_input.click()
        self.human_delay(0.3, 0.8)
        pwd_input.fill(password)
        self.human_delay(0.5, 1.2)

        submit = self._first_visible_any_frame(self.page, LOGIN_SUBMIT)
        if submit is None:
            self.screenshot("login-submit-not-found")
            raise LoginFailed("未找到登录提交按钮")
        submit.click()
        self.human_delay(2.0, 4.0)

        self._raise_if_manual_verify_needed(self.page)

        # 提交后轮询判定：SSO 跳转链走完、到达门户且不再显示未登录特征 → 登录成功。
        # 跳转链中途的页面既不是登录页、也没有未登录特征，连续两次判定一致
        # 才认定成功，防止把「正在跳转」的中间页误判为已登录。
        stable = 0
        for _ in range(15):
            page = self.page
            self._raise_if_manual_verify_needed(page)
            self.human_delay(1.5, 2.5)
            if not self._is_login_url(page.url) and not self._looks_logged_out(page):
                stable += 1
                if stable >= 2:
                    self.log("登录成功")
                    return
            else:
                stable = 0

        # 轮询超时：常见原因是 SSO 授权链未走完，尝试直接导航到目标门户完成授权
        self.log("登录后未到达目标门户，尝试完成 SSO 授权…")
        if self.ensure_logged_in(login_url):
            self.log("登录成功（SSO 授权已完成）")
            return
        self.screenshot("login-failed")
        raise LoginFailed(
            "登录失败：账号密码错误、被风控拦截或 SSO 授权未完成"
        )

    def _find_login_form(self, page: Page):
        """在主页与各 iframe 中查找账号/密码输入框。

        淘宝登录页是 SPA：渲染慢、默认展示二维码登录、表单可能嵌在 iframe 或
        新开的弹窗标签页里。因此轮询重试，并尝试切换到「账号密码登录」。
        返回 (user_input, pwd_input)；都找不到时返回 (None, None)。
        """
        for attempt in range(3):
            page = self.page  # 登录弹窗可能开在新标签页，每次重新取当前页
            user_input = self._first_visible_any_frame(
                page, LOGIN_INPUTS["username"], timeout=2000
            )
            pwd_input = self._first_visible_any_frame(
                page, LOGIN_INPUTS["password"], timeout=2000
            )
            if user_input is not None and pwd_input is not None:
                return user_input, pwd_input
            if attempt == 0:
                # 默认可能是二维码登录页，尝试切换到账号密码登录
                self._switch_to_password_login(page)
                user_input = self._first_visible_any_frame(
                    self.page, LOGIN_INPUTS["username"], timeout=2000
                )
                pwd_input = self._first_visible_any_frame(
                    self.page, LOGIN_INPUTS["password"], timeout=2000
                )
                if user_input is not None and pwd_input is not None:
                    return user_input, pwd_input
            self.log(f"第 {attempt + 1} 次未找到登录表单，等待页面渲染后重试…")
            self.human_delay(2.0, 3.5)
        return None, None

    def _switch_to_password_login(self, page: Page) -> bool:
        scopes = [page, *[f for f in page.frames if f != page.main_frame]]
        for scope in scopes:
            for selector in (
                "text=账号密码登录",
                "text=密码登录",
                "text=账户登录",
                "text=账号登录",
                "a:has-text('密码')",
                "button:has-text('密码')",
                ".login-switch",
                "[class*='login-switch']",
                "[class*='switch-login']",
            ):
                try:
                    el = scope.locator(selector).first
                    if el.is_visible(timeout=1200):
                        el.click()
                        self.human_delay(0.8, 1.5)
                        return True
                except PWTimeout:
                    continue
                except Exception:  # noqa: BLE001
                    continue
        return False

    def _click_login_entry(self, page: Page) -> None:
        """在门户页点击「登录」入口，跳转到登录页（已在登录页时不要调用）。"""
        for round_index in range(2):
            if self._click_login_entry_once(page):
                return
            if round_index == 0:
                self.log("未找到登录入口按钮，等待页面渲染后重试…")
                self.human_delay(2.0, 3.5)
        self.log("未找到登录入口按钮，继续尝试直接定位登录表单")

    def _click_login_entry_once(self, page: Page) -> bool:
        for selector in (
            "a:has-text('登录')",
            "button:has-text('登录')",
            "[class*='login'] a",
            "text=登录",
            "[class*='login-btn']",
            ".login-btn",
        ):
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1500):
                    el.click()
                    self.human_delay(2.0, 3.5)
                    self.log(f"已点击登录入口（{selector}），当前位于 {self.page.url}")
                    return True
            except PWTimeout:
                continue
        return False

    def open_workbench_page(
        self,
        direct_url: str,
        menu_texts: tuple[str, ...],
        page_name: str,
        page_label: str | None = None,
    ) -> Page:
        """打开千牛工作台内的功能页。

        SPA 工作台的子页面 URL 不固定：优先使用配置的直链；
        否则回到工作台首页，按菜单文本点击左侧导航进入。
        page_name 用于截图文件名（英文slug），page_label 是展示给用户的中文名称。
        """
        label = page_label or page_name

        def _ensure_logged_in() -> None:
            # SPA 渲染慢：未登录特征命中后等待一次再复核，避免误判
            for attempt in range(2):
                if not self._looks_logged_out(self.page):
                    return
                if attempt == 0:
                    self.log(f"「{label}」页面暂未显示登录状态，等待渲染后重试…")
                    self.human_delay(2.5, 4.0)
            self.screenshot(f"qianniu-{page_name}-not-logged-in")
            raise ScrapeError(
                f"尚未登录千牛工作台，无法进入「{label}」页面。"
                "请检查账号密码是否正确，或先在浏览器中手动登录后重试。"
            )

        if direct_url:
            page = self.goto(direct_url)
            _ensure_logged_in()
            return page

        self.goto(QIANNIU["home"])
        self.close_popups()
        self.human_delay(1.5, 2.5)
        _ensure_logged_in()

        # 左侧导航菜单可能渲染较慢：多轮查找，每轮之间等待
        for round_index in range(3):
            for text in menu_texts:
                for selector in (
                    f"nav a:has-text('{text}')",
                    f"[role='menu'] >> text={text}",
                    f"a:has-text('{text}')",
                    f"text={text}",
                ):
                    try:
                        el = self.page.locator(selector).first
                        if el.is_visible(timeout=2000):
                            el.click()
                            self.human_delay(2.0, 3.5)
                            self.close_popups()
                            self.log(f"已通过工作台菜单进入「{text}」")
                            return self.page
                    except PWTimeout:
                        continue
            if round_index < 2:
                self.log(
                    f"第 {round_index + 1} 轮未找到「{label}」菜单，"
                    "等待工作台导航渲染后重试…"
                )
                self.close_popups()
                self.human_delay(2.0, 3.5)

        self.screenshot(f"qianniu-{page_name}-menu-not-found")
        raise ScrapeError(
            f"未能在千牛工作台找到「{label}」入口。请手动登录工作台，"
            "从地址栏复制该页面 URL 并配置到 .env"
            "（财务：RPA_QIANNIU_FINANCE_URL；交易：RPA_QIANNIU_TRADE_URL）"
        )

    @staticmethod
    def _first_visible(page, selectors: list[str], timeout: int = 1000):
        # 合并为单个选择器：命中任一即返回，避免逐个等待超时
        combined = ", ".join(selectors)
        try:
            el = page.locator(combined).first
            if el.is_visible(timeout=timeout):
                return el
        except PWTimeout:
            pass
        except Exception:  # noqa: BLE001 — 合并选择器个别不被支持时退回逐个尝试
            for selector in selectors:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=timeout):
                        return el
                except PWTimeout:
                    continue
                except Exception:  # noqa: BLE001
                    continue
        return None

    @classmethod
    def _first_visible_any_frame(
        cls, page: Page, selectors: list[str], timeout: int = 1000
    ):
        """先查主页面，再逐个 iframe 查（淘宝登录弹窗常把表单嵌在 iframe 里）。"""
        el = cls._first_visible(page, selectors, timeout)
        if el is not None:
            return el
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                el = cls._first_visible(frame, selectors, timeout)
            except Exception:  # noqa: BLE001 — 单个 frame 异常不影响其它 frame
                continue
            if el is not None:
                return el
        return None

    @classmethod
    def _looks_logged_out(cls, page: Page) -> bool:
        """按 DOM 特征判断是否处于未登录状态（SPA 门户不跳转登录页时的补充判定）。

        所有特征合并为一个逗号分隔选择器：命中任一即算未登录，
        避免 10+ 个特征逐个等待超时（那会让每次判定慢 10 秒左右）。
        """
        scopes = [page, *[f for f in page.frames if f != page.main_frame][:8]]
        for scope in scopes:
            try:
                if scope.locator(LOGGED_OUT_MARKER_CSS).first.is_visible(timeout=600):
                    return True
            except PWTimeout:
                continue
            except Exception:  # noqa: BLE001
                continue
        return False

    def wait_for_manual_verification(self, reason: str, timeout: int | None = None) -> None:
        """阻塞等待用户在可见浏览器中完成人工验证。"""
        timeout = timeout or rpa_config.verify_timeout
        self.log(f"等待人工处理：{reason}（最长 {timeout}s）")
        self.screenshot("waiting-manual-verify")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._is_login_url(self.page.url) and not self._looks_logged_out(self.page):
                self.log("人工验证已完成，继续执行")
                return
            time.sleep(3)
        self.screenshot("manual-verify-timeout")
        raise NeedManualVerification(f"等待人工验证超时（{timeout}s）：{reason}")

    # ── 数据提取辅助 ─────────────────────────────────────────────
    @staticmethod
    def parse_amount(text: str | None) -> float | None:
        """从文本中提取金额数字，支持千分位与负数。"""
        if not text:
            return None
        cleaned = text.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "")
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    def extract_page_amount(self, hint_text: str | None = None) -> float | None:
        """通用金额提取：优先按提示文本定位，再退回通用金额节点。

        报表页是 SPA，金额常延迟渲染：每轮取不到值就等待后重试。
        """
        from rpa.selectors import AMOUNT_NODES

        for attempt in range(3):
            page = self.page
            if hint_text:
                for selector in (
                    f"text={hint_text}",
                    f"//*[contains(text(), '{hint_text}')]",
                ):
                    try:
                        el = page.locator(selector).first
                        if el.is_visible(timeout=2000):
                            # 取元素自身及父级文本
                            for scope in (el, el.locator("xpath=..")):
                                amount = self.parse_amount(scope.inner_text(timeout=2000))
                                if amount is not None:
                                    return amount
                    except PWTimeout:
                        continue

            for selector in AMOUNT_NODES:
                try:
                    texts = page.locator(selector).all_inner_texts()
                except PWTimeout:
                    continue
                for t in texts:
                    amount = self.parse_amount(t)
                    if amount is not None:
                        return amount

            if attempt < 2:
                self.log(f"第 {attempt + 1} 次未提取到金额，等待页面渲染后重试…")
                self.human_delay(2.0, 3.5)
        return None

    def close_popups(self) -> None:
        """关闭常见弹窗（新功能引导、公告等），避免遮挡。

        弹窗常延迟出现：先扫一轮，短暂等待后再扫一轮。
        """
        self._close_popups_once()
        self.human_delay(0.8, 1.5)
        self._close_popups_once()

    def _close_popups_once(self) -> None:
        """扫描一轮并关闭可见弹窗（all() 不等待，只有真正命中才检查可见性）。"""
        try:
            elements = self.page.locator(POPUP_CLOSE_CSS).all()
        except Exception:  # noqa: BLE001
            return
        for el in elements[:3]:  # 一次最多关 3 个，避免连环误触
            try:
                if el.is_visible(timeout=500):
                    el.click()
                    self.human_delay(0.3, 0.8)
            except Exception:  # noqa: BLE001
                continue
