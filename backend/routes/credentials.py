from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from database import get_session
from models import PLATFORMS, PLATFORM_DATASETS, PlatformAccount
from rpa.crypto import CryptoError, decrypt, encrypt, mask
from schemas import (
    AccountCreate,
    AccountListResponse,
    AccountRead,
    AccountUpdate,
    DatasetOption,
    PlatformMeta,
    TestLoginResponse,
)

router = APIRouter(prefix="/credentials", tags=["credentials"])

_PLATFORM_LABELS = {
    "qianniu": "千牛工作台",
    "alimama": "阿里妈妈投放后台",
}


@router.get("/platforms", response_model=list[PlatformMeta])
def list_platforms() -> list[PlatformMeta]:
    """平台与可抓取数据集选项（前端「选择拉取哪个数据」的来源）。"""
    return [
        PlatformMeta(
            platform=platform,
            label=_PLATFORM_LABELS.get(platform, platform),
            datasets=[
                DatasetOption(key=d["key"], label=d["label"], category=d["category"])
                for d in datasets
            ],
        )
        for platform, datasets in PLATFORM_DATASETS.items()
    ]


@router.get("", response_model=AccountListResponse)
def list_accounts(
    platform: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> AccountListResponse:
    stmt = select(PlatformAccount)
    if platform:
        stmt = stmt.where(PlatformAccount.platform == platform)
    stmt = stmt.order_by(PlatformAccount.id)
    rows = session.exec(stmt).all()
    return AccountListResponse(
        total=len(rows),
        items=[_to_read(a) for a in rows],
    )


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, session: Session = Depends(get_session)) -> AccountRead:
    if payload.platform not in PLATFORMS:
        raise HTTPException(status_code=422, detail=f"platform 必须是 {PLATFORMS} 之一")
    try:
        password_enc = encrypt(payload.password)
    except CryptoError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    account = PlatformAccount(
        platform=payload.platform,
        account_label=payload.account_label,
        username=payload.username,
        password_enc=password_enc or "",
        store=payload.store,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return _to_read(account)


@router.put("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    session: Session = Depends(get_session),
) -> AccountRead:
    account = session.get(PlatformAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    if payload.account_label is not None:
        account.account_label = payload.account_label
    if payload.username is not None:
        account.username = payload.username
    if payload.store is not None:
        account.store = payload.store
    if payload.password:
        try:
            account.password_enc = encrypt(payload.password) or ""
        except CryptoError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    session.add(account)
    session.commit()
    session.refresh(account)
    return _to_read(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, session: Session = Depends(get_session)) -> None:
    account = session.get(PlatformAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    session.delete(account)
    session.commit()


@router.post("/{account_id}/test-login", response_model=TestLoginResponse)
def test_login(account_id: int, session: Session = Depends(get_session)) -> TestLoginResponse:
    """仅验证登录是否成功，不抓取任何数据。"""
    account = session.get(PlatformAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    from rpa.browser import BrowserSession, LoginFailed, NeedManualVerification
    from rpa.selectors import ALIMAMA, QIANNIU

    home = QIANNIU["home"] if account.platform == "qianniu" else ALIMAMA["home"]
    password = decrypt(account.password_enc) or ""

    try:
        with BrowserSession(account.id, account.account_label) as browser:
            if browser.is_logged_in(home):
                message = "已保存的登录态仍然有效，无需重新登录"
                result_status = "ok"
            else:
                try:
                    browser.login(account.username, password, home)
                    message = "登录成功"
                    result_status = "ok"
                except NeedManualVerification as exc:
                    message = str(exc)
                    result_status = "need_verify"
    except LoginFailed as exc:
        message, result_status = str(exc), "fail"
    except Exception as exc:  # noqa: BLE001
        message, result_status = f"{type(exc).__name__}: {exc}", "fail"

    account.last_login_status = result_status
    account.last_login_at = datetime.now(timezone.utc)
    session.add(account)
    session.commit()
    return TestLoginResponse(ok=result_status == "ok", status=result_status, message=message)


def _to_read(account: PlatformAccount) -> AccountRead:
    try:
        masked = mask(decrypt(account.password_enc))
    except CryptoError:
        masked = "⚠️ 密钥不匹配"
    return AccountRead(
        id=account.id or 0,
        platform=account.platform,
        account_label=account.account_label,
        username=account.username,
        store=account.store,
        password_masked=masked,
        last_login_at=account.last_login_at,
        last_login_status=account.last_login_status,
        created_at=account.created_at,
    )
