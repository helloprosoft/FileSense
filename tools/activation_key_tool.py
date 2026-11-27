"""Issue an offline FileSense activation key for one device."""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from filesense.license_manager import PRODUCT_ID, _emsa_pkcs1_v1_5, validate_activation_key


def encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def read_tlv(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    tag = data[offset]
    offset += 1
    first_length = data[offset]
    offset += 1
    if first_length & 0x80:
        count = first_length & 0x7F
        if not count or count > 4:
            raise ValueError("Unsupported DER length")
        length = int.from_bytes(data[offset:offset + count], "big")
        offset += count
    else:
        length = first_length
    end = offset + length
    if end > len(data):
        raise ValueError("Truncated DER data")
    return tag, data[offset:end], end


def parse_sequence(data: bytes) -> list[tuple[int, bytes]]:
    tag, content, end = read_tlv(data)
    if tag != 0x30 or end != len(data):
        raise ValueError("Invalid RSA private key structure")
    fields = []
    offset = 0
    while offset < len(content):
        tag, value, offset = read_tlv(content, offset)
        fields.append((tag, value))
    return fields


def load_rsa_private_numbers(path: Path) -> tuple[int, int, int]:
    pem = path.read_text(encoding="ascii")
    if "ENCRYPTED" in pem:
        raise ValueError("The private PEM must not be password-encrypted for this tool.")
    body = "".join(line for line in pem.splitlines() if not line.startswith("---"))
    der = base64.b64decode(body, validate=True)
    fields = parse_sequence(der)
    if len(fields) >= 3 and fields[1][0] == 0x30 and fields[2][0] == 0x04:
        # PKCS#8 wraps the PKCS#1 RSA private key in an OCTET STRING.
        fields = parse_sequence(fields[2][1])
    if len(fields) < 4 or any(fields[index][0] != 0x02 for index in range(4)):
        raise ValueError("The PEM does not contain an RSA private key.")
    n, e, d = (int.from_bytes(fields[index][1], "big") for index in (1, 2, 3))
    return n, e, d


def generate_activation_key(machine_code: str, private_path: Path) -> str:
    machine_code = machine_code.strip().upper()
    if not re.fullmatch(r"FS1-[A-Z2-7]{16}", machine_code):
        raise ValueError("Enter a complete FileSense device code in the format FS1-…")
    modulus, exponent, private_exponent = load_rsa_private_numbers(private_path)
    if modulus.bit_length() < 2048 or exponent != 65537:
        raise ValueError("Use the FileSense RSA-2048 (or stronger) key with exponent 65537.")

    payload = json.dumps({
        "product": PRODUCT_ID,
        "machine": machine_code,
        "license": "perpetual",
        "issued": datetime.now(timezone.utc).date().isoformat(),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature_length = (modulus.bit_length() + 7) // 8
    encoded_message = _emsa_pkcs1_v1_5(payload, signature_length)
    signature = pow(int.from_bytes(encoded_message, "big"), private_exponent, modulus).to_bytes(signature_length, "big")
    key = "FS1." + encode(payload) + "." + encode(signature)
    valid, message = validate_activation_key(key, expected_machine=machine_code)
    if not valid:
        raise ValueError(f"The private key does not match FileSense's public key: {message}")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an offline FileSense activation key.")
    parser.add_argument("--machine-code", required=True, help="Device code shown by FileSense")
    parser.add_argument(
        "--private-key", default=str(PROJECT_ROOT / "developer_keys" / "FileSense_activation_private.pem"),
        help="Path to the private signing key (never distribute this file)",
    )
    args = parser.parse_args()

    try:
        key = generate_activation_key(args.machine_code, Path(args.private_key))
    except (OSError, ValueError, TypeError) as error:
        parser.error(f"Cannot load private signing key: {error}")
    print("Activation key (send this key to the user):\n")
    print(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
