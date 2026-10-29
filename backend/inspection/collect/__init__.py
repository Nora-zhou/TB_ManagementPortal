"""013-I01：商品内容采集。

分层：
- raw_store.py  文件存档（run 目录 / manifest / XHR / HTML / 截图）
- item.py       取数（BrowserSession 驱动，返回 run 目录）
- parser.py     解析（纯函数，只读 run 目录，不联网）

检测专用浏览器 profile：account_id=9001 → browser_data/account-9001，
与千牛（account-1 等）物理隔离，绝不共用登录态。
"""

INSPECTION_ACCOUNT_ID = 9001
