"""安全模块：配置密码（PBKDF2）、会话（内存 + HTTP-only Cookie）、API token、
AI 配置中 API Key 的存储加密（演示级：XOR + base64 封装，防明文落盘，无 HMAC 完整性校验）。

RBAC（R101）落地时，本模块升级为用户/角色/权限点鉴权。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from typing import Optional

from . import config, store as store_mod

_PBKDF2_ITERATIONS = 100_000
_SESSION_TTL = 24 * 3600  # 会话有效期 24h
_FAIL_LIMIT = 5
_FAIL_WINDOW = 60  # 连续失败锁定秒数

# 会话表：{token: 过期时间戳}（单机单用户，内存即可）
_sessions: dict[str, float] = {}
_sessions_lock = threading.Lock()
# 密码尝试记录：{key: [次数, 首次失败时间]}
_fails: dict[str, list] = {}


# ---------------------------------------------------------------- 配置密码
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except Exception:
        return False


def check_rate_limit(key: str = "default") -> bool:
    """连续失败 _FAIL_LIMIT 次后锁定 _FAIL_WINDOW 秒。返回 False 表示被锁定。"""
    with _sessions_lock:
        rec = _fails.get(key)
        now = time.time()
        if rec and rec[0] >= _FAIL_LIMIT:
            if now - rec[1] < _FAIL_WINDOW:
                return False
            _fails.pop(key, None)
        return True


def register_failure(key: str = "default") -> None:
    with _sessions_lock:
        rec = _fails.get(key)
        if rec and now_within(rec[1]):
            rec[0] += 1
        else:
            _fails[key] = [1, time.time()]


def now_within(ts: float) -> bool:
    return time.time() - ts < _FAIL_WINDOW


def reset_failures(key: str = "default") -> None:
    with _sessions_lock:
        _fails.pop(key, None)


# ---------------------------------------------------------------- 会话
def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[token] = time.time() + _SESSION_TTL
    return token


def validate_session(token: Optional[str]) -> bool:
    if not token:
        return False
    with _sessions_lock:
        exp = _sessions.get(token)
        if exp is None:
            return False
        if time.time() > exp:
            _sessions.pop(token, None)
            return False
        return True


def clear_sessions() -> None:
    with _sessions_lock:
        _sessions.clear()


# ---------------------------------------------------------------- API token
def generate_api_token() -> str:
    return "lt-" + secrets.token_urlsafe(32)


# ---------------------------------------------------------------- API Key 存储加密
def _xor_key() -> bytes:
    secret = _session_secret()
    return hashlib.sha256(("ai-key:" + secret).encode("utf-8")).digest()


def _session_secret() -> str:
    raw = store_mod.Store().get_setting("session_secret")
    if raw:
        return raw
    val = secrets.token_hex(32)
    store_mod.Store().set_setting("session_secret", val)
    return val


def encrypt_api_key(plain: str) -> str:
    if not plain:
        return ""
    key = _xor_key()
    data = plain.encode("utf-8")
    enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return "x1:" + base64.b64encode(enc).decode("ascii")


def decrypt_api_key(stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith("x1:"):
        return stored  # 兼容明文旧数据
    try:
        enc = base64.b64decode(stored[3:])
        key = _xor_key()
        data = bytes(b ^ key[i % len(key)] for i, b in enumerate(enc))
        return data.decode("utf-8")
    except Exception:
        return ""


def mask_api_key(key: str) -> str:
    if not key:
        return ""
    return "****" + key[-4:]
