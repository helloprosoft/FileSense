"""Offline machine-bound trial and license validation using Python's stdlib."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


PRODUCT_ID = "FileSense"
TRIAL_DAYS = 30
RSA_PUBLIC_EXPONENT = 65537
RSA_PUBLIC_MODULUS = int(
    "A125D69DC645F0B7BEB596E76EAD554B21F72311371FDE70A172BDC4D60FD02E"
    "96142DF40A24FC4936665558B34968D67E4E8FEF71C9A06A0E2DC1A82C50A49"
    "D90F6FB9B1265FDD776F1773D98F996C0B53EB163E5145550085D66F028D54B"
    "C3905572C33F6F050CE38ADF3A75FDA3810DCB7F650F440D90D8B4AE6FFA2C4"
    "73F0D31241DC602AB3829370855EB72E14B9FEE8DEBAF46D19EFEB8D64C19F4"
    "FDE908EF8C7E0DB021E7B0620EFECFEBE3515B3854A5EA64187A4ECBD7CD135"
    "15445348B0BF1503201208169B8793AF0EFAAAF4CFFB00547882A57430AA0E783"
    "CCBB78008D838F3EAF4820B24BB4C734CC73F66BFD9C52017285A14042E4C027B3C1",
    16,
)
SHA256_DER_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _emsa_pkcs1_v1_5(message: bytes, length: int) -> bytes:
    digest_info = SHA256_DER_PREFIX + hashlib.sha256(message).digest()
    padding_length = length - len(digest_info) - 3
    if padding_length < 8:
        raise ValueError("RSA key is too short")
    return b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info


def verify_signature(message: bytes, signature: bytes) -> bool:
    length = (RSA_PUBLIC_MODULUS.bit_length() + 7) // 8
    if len(signature) != length:
        return False
    signature_number = int.from_bytes(signature, "big")
    if signature_number >= RSA_PUBLIC_MODULUS:
        return False
    decoded = pow(signature_number, RSA_PUBLIC_EXPONENT, RSA_PUBLIC_MODULUS).to_bytes(length, "big")
    try:
        expected = _emsa_pkcs1_v1_5(message, length)
    except ValueError:
        return False
    return hmac.compare_digest(decoded, expected)


def machine_fingerprint() -> str:
    """Return an install-level Windows machine identifier without user data."""
    source = ""
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                source = str(winreg.QueryValueEx(key, "MachineGuid")[0]).strip().casefold()
        except (OSError, ImportError):
            source = ""
    if not source:
        source = f"{platform.node().casefold()}|{uuid.getnode():012x}"
    digest = hashlib.sha256(f"{PRODUCT_ID}|{source}".encode("utf-8")).digest()
    return "FS1-" + base64.b32encode(digest[:10]).decode("ascii").rstrip("=")


def validate_activation_key(key: str, expected_machine: str | None = None) -> tuple[bool, str]:
    try:
        prefix, encoded_payload, encoded_signature = key.strip().split(".", 2)
        if prefix != "FS1":
            return False, "This activation key format is not supported."
        payload_bytes = _b64url_decode(encoded_payload)
        signature = _b64url_decode(encoded_signature)
        if not verify_signature(payload_bytes, signature):
            return False, "The activation key is invalid or has been altered."
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return False, "The activation key is incomplete or malformed."
    if not isinstance(payload, dict):
        return False, "The activation key payload is malformed."
    if payload.get("product") != PRODUCT_ID or payload.get("license") != "perpetual":
        return False, "This key is not a FileSense license."
    if payload.get("machine") != (expected_machine or machine_fingerprint()):
        return False, "This activation key was issued for a different machine."
    return True, "Activated."


def _trial_file() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "ProSoft" / "FileSense" / "trial.json"


def _read_trial_records(settings) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    try:
        registry_record = settings.value("license_trial_state", "")
        if registry_record:
            parsed = json.loads(str(registry_record))
            if isinstance(parsed, dict):
                records.append(parsed)
    except (TypeError, ValueError, json.JSONDecodeError):
        records.append({"invalid": "1"})
    try:
        path = _trial_file()
        if path.exists():
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                records.append(parsed)
            else:
                records.append({"invalid": "1"})
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        records.append({"invalid": "1"})
    return records


def _write_trial_state(settings, state: dict[str, str]) -> None:
    serialized = json.dumps(state, separators=(",", ":"))
    settings.setValue("license_trial_state", serialized)
    path = _trial_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")


def _trial_status(settings) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    machine = machine_fingerprint()
    records = _read_trial_records(settings)
    if not records:
        start = now
        last_seen = now
        expired = False
    else:
        try:
            if any(record.get("machine") != machine for record in records):
                raise ValueError("machine mismatch")
            starts = [datetime.fromisoformat(record["started"]).astimezone(timezone.utc) for record in records]
            seen = [datetime.fromisoformat(record["last_seen"]).astimezone(timezone.utc) for record in records]
            start, last_seen = min(starts), max(seen)
            expired = any(record.get("expired") == "1" for record in records)
            if now < last_seen - timedelta(minutes=5):
                expired = True
        except (KeyError, TypeError, ValueError):
            start = now - timedelta(days=TRIAL_DAYS)
            last_seen = now
            expired = True

    expired = expired or now >= start + timedelta(days=TRIAL_DAYS)
    if not expired:
        last_seen = max(last_seen, now)
    state = {
        "machine": machine,
        "started": start.isoformat(),
        "last_seen": last_seen.isoformat(),
        "expired": "1" if expired else "0",
    }
    try:
        _write_trial_state(settings, state)
    except OSError:
        settings.setValue("license_trial_state", json.dumps(state, separators=(",", ":")))
    remaining = max(0, (start + timedelta(days=TRIAL_DAYS) - now).days)
    if not expired and start + timedelta(days=TRIAL_DAYS) - now > timedelta(days=remaining):
        remaining += 1
    return {"state": "expired" if expired else "trial", "days_remaining": remaining}


def license_status(settings) -> dict[str, object]:
    key = str(settings.value("license_activation_key", "") or "")
    if key:
        valid, _message = validate_activation_key(key)
        if valid:
            return {"state": "activated", "days_remaining": None}
    return _trial_status(settings)


def activate(settings, key: str) -> tuple[bool, str]:
    valid, message = validate_activation_key(key)
    if not valid:
        return False, message
    settings.setValue("license_activation_key", key.strip())
    settings.sync()
    return True, message
