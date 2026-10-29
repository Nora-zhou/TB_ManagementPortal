"""手动预登录工具。

work.taobao.com 等 SPA 门户未登录时不跳转登录页，自动登录对页面结构较敏感；
本工具打开指定账号的持久化浏览器 profile，由用户手动完成登录（账号密码 / 扫码），
会话保存在 ``browser_data/account-<id>/``，之后所有 RPA 任务自动复用登录态。

用法（在 backend/ 目录下执行）::

    python -m rpa.manual_login                        # 默认账号 1，千牛工作台
    python -m rpa.manual_login --account-id 2         # 指定账号
    python -m rpa.manual_login --platform alimama     # 阿里妈妈后台

流程：弹出浏览器窗口 → 手动登录 → 看到工作台首页后回到本窗口按回车 → 保存退出。
"""

from __future__ import annotations

import argparse

from rpa.browser import BrowserSession
from rpa.selectors import ALIMAMA, QIANNIU


def main() -> int:
    parser = argparse.ArgumentParser(
        description="手动预登录：打开持久化浏览器，登录完成后回车保存退出"
    )
    parser.add_argument("--account-id", type=int, default=1, help="平台账号 ID（默认 1）")
    parser.add_argument(
        "--platform",
        choices=("qianniu", "alimama"),
        default="qianniu",
        help="平台（默认 qianniu）",
    )
    args = parser.parse_args()

    url = QIANNIU["home"] if args.platform == "qianniu" else ALIMAMA["home"]

    print(f"正在打开浏览器 profile：account-{args.account_id}")
    print(f"目标地址：{url}")
    print("请在打开的浏览器窗口中完成登录（账号密码或扫码），")
    print("确认已进入工作台首页后，回到本窗口按回车键保存并退出。")

    with BrowserSession(args.account_id, f"manual-login-{args.platform}") as session:
        session.goto(url)
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        print(f"登录态已保存到：{session.profile_dir}")
    print("完成。之后创建 RPA 抓取任务时会自动复用该登录态。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
