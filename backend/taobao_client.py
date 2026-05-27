"""
Taobao Open Platform (TOP) REST API client.

Implements HMAC-MD5 request signing per the TOP specification and provides
two async helper functions:
  - fetch_store_items: retrieve all on-sale items in the seller's store
  - fetch_item_price:  retrieve the current price for a single item

TOP API base URL: https://eco.taobao.com/router/rest
Signing spec: https://open.taobao.com/doc.htm?docId=101617&docType=1
"""

import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

TOP_API_URL = "https://eco.taobao.com/router/rest"
_DEFAULT_TIMEOUT = 10.0  # seconds


def _sign(params: dict, app_secret: str) -> str:
    """Compute HMAC-MD5 signature for the given parameter dict."""
    sorted_params = sorted(params.items())
    query = "".join(f"{k}{v}" for k, v in sorted_params)
    return hmac.new(
        app_secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.md5,
    ).hexdigest().upper()


def _base_params(method: str, app_key: str, session_key: str) -> dict:
    return {
        "method": method,
        "app_key": app_key,
        "session": session_key,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "2.0",
        "sign_method": "hmac",
    }


def _build_signed_params(method: str, app_key: str, app_secret: str,
                          session_key: str, extra: dict) -> dict:
    params = _base_params(method, app_key, session_key)
    params.update(extra)
    params["sign"] = _sign(params, app_secret)
    return params


async def fetch_store_items(
    session_key: str,
    app_key: str,
    app_secret: str,
    page_size: int = 100,
) -> list[dict]:
    """
    Fetch all on-sale items from the seller's Taobao store.

    Returns a list of dicts with keys: item_id, title, price.
    Raises httpx.HTTPStatusError on HTTP errors, ValueError on API errors.
    """
    results: list[dict] = []
    page_no = 1

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        while True:
            params = _build_signed_params(
                method="taobao.items.onsale.get",
                app_key=app_key,
                app_secret=app_secret,
                session_key=session_key,
                extra={
                    "fields": "num_iid,title,price",
                    "page_no": str(page_no),
                    "page_size": str(page_size),
                },
            )
            resp = await client.post(TOP_API_URL, data=params)
            resp.raise_for_status()
            data = resp.json()

            if "error_response" in data:
                err = data["error_response"]
                raise ValueError(f"Taobao API error {err.get('code')}: {err.get('zh_desc', err.get('msg'))}")

            items_data = data.get("items_onsale_get_response", {})
            items = items_data.get("items", {}).get("item", [])
            for item in items:
                results.append({
                    "item_id": str(item["num_iid"]),
                    "title": item.get("title", ""),
                    "price": float(item.get("price", 0)),
                })

            total = int(items_data.get("total_results", 0))
            if page_no * page_size >= total or not items:
                break
            page_no += 1
            if page_no > 100:  # L2 — safety guard against infinite loop
                break

    return results


async def fetch_item_price(
    item_id: str,
    session_key: str,
    app_key: str,
    app_secret: str,
) -> Optional[float]:
    """
    Fetch the current price for a single Taobao item.

    Returns the price as a float, or None if the item has no price data.
    Raises httpx.HTTPStatusError on HTTP errors, ValueError on API errors.
    """
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        params = _build_signed_params(
            method="taobao.item.get",
            app_key=app_key,
            app_secret=app_secret,
            session_key=session_key,
            extra={
                "num_iid": item_id,
                "fields": "num_iid,price",
            },
        )
        resp = await client.post(TOP_API_URL, data=params)
        resp.raise_for_status()
        data = resp.json()

        if "error_response" in data:
            err = data["error_response"]
            raise ValueError(f"Taobao API error {err.get('code')}: {err.get('zh_desc', err.get('msg'))}")

        item = data.get("item_get_response", {}).get("item", {})
        price_str = item.get("price")
        return float(price_str) if price_str else None
