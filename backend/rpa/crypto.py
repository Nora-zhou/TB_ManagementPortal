from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from rpa.config import rpa_config


class CryptoError(RuntimeError):
    """加解密失败（密钥缺失或不匹配）。"""


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = rpa_config.master_key
        if not key:
            raise CryptoError(
                "未配置 RPA_MASTER_KEY。请在项目根目录 .env 中设置，"
                '生成方式：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        try:
            _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as exc:  # noqa: BLE001
            raise CryptoError(f"RPA_MASTER_KEY 格式无效：{exc}") from exc
    return _fernet


def encrypt(plaintext: str | None) -> str | None:
    """加密明文，返回 base64 密文。None/空串原样返回。"""
    if plaintext is None or plaintext == "":
        return plaintext
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str | None) -> str | None:
    """解密密文，返回明文。None/空串原样返回。"""
    if ciphertext is None or ciphertext == "":
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError(
            "解密失败：RPA_MASTER_KEY 与保存数据时使用的不一致，"
            "或密文已损坏。请检查 .env 中的 RPA_MASTER_KEY。"
        ) from exc


def mask(text: str | None, keep: int = 2) -> str:
    """脱敏展示：保留前 keep 位，其余替换为 *。"""
    if not text:
        return ""
    if len(text) <= keep:
        return "*" * len(text)
    return text[:keep] + "*" * min(len(text) - keep, 12)
