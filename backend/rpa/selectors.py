"""各平台页面选择器集中管理。

淘宝系后台（千牛 / 阿里妈妈）会不定期改版，当抓取失败时优先修改本文件中的
选择器，无需改动抓取逻辑代码。每个选择器按「优先级从高到低」排列，运行时
依次尝试，第一个命中的即被采用。
"""

from __future__ import annotations

# ── 通用 ──────────────────────────────────────────────────────────
# 登录成功判定：页面 URL 包含以下任一特征
LOGIN_URL_KEYWORDS = ("login.taobao.com", "login.aliyun.com", "qrlogin", "login.tmall.com")

# 未登录特征（DOM 判定）。
# work.taobao.com 等 SPA 门户未登录时不会跳转登录页，仅靠 URL 会误判为已登录，
# 因此按页面元素补充判定：右上角登录入口 / 扫码登录文案等。
LOGGED_OUT_MARKERS = (
    "text=扫码登录",
    "text=二维码登录",
    "text=请登录",
    "text=立即登录",
    "text=登录千牛",
    "header a:has-text('登录')",
    "header button:has-text('登录')",
    "a[href*='login']:has-text('登录')",
    "[class*='login-dialog']",
    "[class*='loginDialog']",
    "[class*='login-modal']",
)

# 合并为单个逗号分隔选择器：命中任一特征即算未登录，避免逐个等待超时
LOGGED_OUT_MARKER_CSS = ", ".join(LOGGED_OUT_MARKERS)

# SSO 授权 / 二次确认按钮（淘宝系登录成功后跳回门户前的授权页）
SSO_AUTHORIZE_BUTTONS = (
    "button:has-text('授权并登录')",
    "button:has-text('授权登录')",
    "button:has-text('确认授权')",
    "button:has-text('同意授权')",
    "button:has-text('授权')",
    "a:has-text('授权并登录')",
    "button:has-text('继续登录')",
    "button:has-text('确认')",
    "button:has-text('同意')",
)

# 弹窗关闭按钮
POPUP_CLOSE_CSS = ", ".join(
    (
        "[class*='dialog'] [class*='close']",
        "[class*='modal'] [class*='close']",
        "button[aria-label='Close']",
        "button[aria-label='关闭']",
    )
)

# 滑块 / 短信验证（合并选择器）
CAPTCHA_CSS = ", ".join(
    (
        ".nc_wrapper",
        "#nc_1_wrapper",
        ".slidetounlock",
        "iframe[src*='captcha']",
        ".baxia-dialog",
        "[class*='slider-verify']",
    )
)

# 登录页用户名 / 密码输入框
LOGIN_INPUTS = {
    "username": [
        "#fm-login-id",
        "input[name='fm-login-id']",
        "input[placeholder*='手机号']",
        "input[placeholder*='会员名']",
        "input[placeholder*='账号']",
        "input[placeholder*='用户名']",
        "input[placeholder*='账户']",
        "#loginName",
        "input[type='text'][name*='login']",
        "input[name*='account']",
    ],
    "password": [
        "#fm-login-password",
        "input[name='fm-login-password']",
        "input[type='password']",
        "input[name='password']",
        "input[placeholder*='密码']",
        "#password",
    ],
}

# 登录提交按钮
LOGIN_SUBMIT = [
    "button[type='submit']",
    ".fm-button.fm-submit",
    "#login-form button",
    "button:has-text('登录')",
]

# 滑块验证（出现时需人工处理）
CAPTCHA_SLIDER = [
    ".nc_wrapper",
    "#nc_1_wrapper",
    ".slidetounlock",
    "iframe[src*='captcha']",
    ".baxia-dialog",
    "[class*='slider-verify']",
]

# 短信验证码
CAPTCHA_SMS = [
    "input[placeholder*='验证码']",
    ".sms-code-input",
    "#container-code",
]

# ── 千牛工作台（网页版） ───────────────────────────────────────────
# 登录入口：千牛网页版统一入口为 work.taobao.com
# （旧 qianniu.taobao.com 已跳转到开发者平台，其 /finance、/trade 子路径均已失效）
QIANNIU = {
    "home": "https://work.taobao.com/",
    # 工作台是登录后渲染的 SPA，财务 / 交易页没有稳定的公开 URL：
    # - 优先使用 .env 配置的 RPA_QIANNIU_FINANCE_URL / RPA_QIANNIU_TRADE_URL 直链；
    # - 未配置时进入工作台首页，按下列文本尝试点击左侧导航菜单进入。
    "finance_menu_texts": ("财务", "账房", "账单中心", "账单"),
    "trade_menu_texts": ("交易", "交易管理", "订单管理", "订单"),
}

# ── 阿里妈妈投放后台 ──────────────────────────────────────────────
ALIMAMA = {
    "home": "https://www.alimama.com/index.htm",
    # 直通车
    "zhitongche": "https://subway.simba.taobao.com/",
    # 引力魔方
    "mofang": "https://one.taobao.com/marketing/index.htm",
    # 万相台
    "wanxiangtai": "https://ff.one.taobao.com/",
    # 统一报表入口
    "report": "https://subway.simba.taobao.com/report",
}

# ── 金额提取 ──────────────────────────────────────────────────────
# 在页面中定位「金额」文本的通用候选（命中后取其文本中的数字）
AMOUNT_NODES = [
    "[class*='amount']",
    "[class*='fee']",
    "[class*='cost']",
    "[class*='money']",
    "[class*='consume']",
    "[class*='spend']",
    ".num",
    ".value",
]

# 月份切换 / 日期选择器
DATE_PICKERS = [
    "input[placeholder*='开始']",
    "input[placeholder*='月份']",
    "[class*='date-picker'] input",
    "[class*='rangepicker'] input",
    ".ant-calendar-picker-input",
]

# 导出 / 下载按钮（优先尝试「导出 Excel」拿到结构化数据）
EXPORT_BUTTONS = [
    "button:has-text('导出')",
    "button:has-text('下载')",
    "a:has-text('导出')",
    "[class*='export']",
    "[class*='download']",
]
