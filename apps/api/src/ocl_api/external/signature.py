"""Digital signature of issued documents (Skill Transcript, BRD 03 US-M3-08).

The signer comes from SUPREME (`ext_signers`); the signing service is not chosen yet, so
FS-5 codes against `DigitalSigner` and uses `SampleSigner` until it is.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Protocol


class DigitalSigner(Protocol):
    name: str

    def sign(self, document: bytes, signer_id: str) -> dict[str, Any]: ...


class SampleSigner:
    """Records who would sign and a fingerprint of the document; carries no legal weight."""

    name = "sample"

    def sign(self, document: bytes, signer_id: str) -> dict[str, Any]:
        return {
            "signer_id": signer_id,
            "sha256": hashlib.sha256(document).hexdigest(),
            "signed_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "method": self.name,
            "sample": True,
            "note": "ข้อมูลตัวอย่าง ยังไม่ใช่ลายมือชื่อดิจิทัลจริง",
        }
