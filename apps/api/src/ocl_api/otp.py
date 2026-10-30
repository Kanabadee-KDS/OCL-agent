"""One-time sign-in codes for invited outside evaluators (FS-8a · US-U-02 · mock login-ext).

Only an account the university invited (kind external), still usable on the Thai calendar
day, may ask for a code. A code is six digits, sent through the outbox, kept as a keyed hash,
good once and for CODE_MINUTES [สมมติ: 10 นาที]; a new request voids the older codes, five
wrong tries void the code, and an address may ask PER_HOUR times an hour [สมมติ C12: 5 ครั้ง].
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from ocl_api.db import connect
from ocl_api.mail import Outbox
from ocl_api.users import UserStore

CODE_MINUTES = 10
MAX_ATTEMPTS = 5
PER_HOUR = 5


class OtpError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class OtpStore:
    def __init__(self, url: str, schema: str | None, secret: str):
        self.url, self.schema, self.secret = url, schema, secret.encode()

    def _conn(self):
        return connect(self.url, self.schema)

    def _hash(self, email: str, code: str) -> str:
        return hmac.new(self.secret, f"{email}|{code}".encode(), hashlib.sha256).hexdigest()

    def request(self, email: str) -> dict[str, Any]:
        email = email.strip().lower()
        u = UserStore(self.url, self.schema).get(email)
        if u is None or u.get("kind") != "external" or not u["usable"]:
            raise OtpError("อีเมลนี้ไม่ได้รับเชิญ หรือหมดสิทธิ์เข้าใช้แล้ว", 404)
        code = f"{secrets.randbelow(10**6):06d}"
        with self._conn() as conn, conn.transaction():
            n = conn.execute(
                "SELECT count(*) AS n FROM login_codes WHERE lower(email) = %s "
                "AND created_at > now() - interval '1 hour'",
                (email,),
            ).fetchone()["n"]
            if n >= PER_HOUR:
                raise OtpError(f"ขอรหัสได้ไม่เกิน {PER_HOUR} ครั้งต่อชั่วโมง ลองใหม่ภายหลัง", 429)
            conn.execute(
                "UPDATE login_codes SET used_at = now() "
                "WHERE lower(email) = %s AND used_at IS NULL",
                (email,),
            )
            conn.execute(
                "INSERT INTO login_codes (email, code_hash, expires_at) "
                f"VALUES (%s, %s, now() + interval '{CODE_MINUTES} minutes')",
                (email, self._hash(email, code)),
            )
        Outbox(self.url, self.schema).send(
            [email],
            "รหัสเข้าสู่ระบบ · ระบบบริหารจัดการหลักสูตร มศว",
            f"รหัสเข้าสู่ระบบของท่านคือ {code}\nใช้ได้ครั้งเดียว ภายใน {CODE_MINUTES} นาที",
            kind="otp",
            by="system",
        )
        return {"sent": True, "minutes": CODE_MINUTES}

    def verify(self, email: str, code: str) -> dict[str, Any]:
        email = email.strip().lower()
        wrong: str | None = None
        with self._conn() as conn, conn.transaction():
            r = conn.execute(
                "SELECT * FROM login_codes WHERE lower(email) = %s AND used_at IS NULL "
                "AND expires_at > now() ORDER BY id DESC LIMIT 1 FOR UPDATE",
                (email,),
            ).fetchone()
            if r is None:
                wrong = "รหัสหมดอายุหรือถูกใช้แล้ว ขอรหัสใหม่"
            elif not hmac.compare_digest(r["code_hash"], self._hash(email, code.strip())):
                done = r["attempts"] + 1 >= MAX_ATTEMPTS
                conn.execute(
                    "UPDATE login_codes SET attempts = attempts + 1, "
                    "used_at = CASE WHEN %s THEN now() END WHERE id = %s",
                    (done, r["id"]),
                )
                wrong = "รหัสไม่ถูกต้อง" + (" ขอรหัสใหม่" if done else "")
            else:
                conn.execute("UPDATE login_codes SET used_at = now() WHERE id = %s", (r["id"],))
        if wrong:  # raised after the commit, so a wrong try stays counted
            raise OtpError(wrong, 401)
        u = UserStore(self.url, self.schema).get(email)
        if u is None or not u["usable"]:
            raise OtpError("บัญชีนี้ถูกระงับหรือหมดสิทธิ์แล้ว", 401)
        return u
