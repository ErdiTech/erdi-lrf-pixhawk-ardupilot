"""Protocol-level tests for the ERDI Lua draft.

The tests intentionally mirror the pure parser rules in erdi_lrf.lua and use
examples printed in the manufacturer manuals. They do not claim SITL or
real-hardware coverage.
"""

from __future__ import annotations

from dataclasses import dataclass


def b_checksum(payload: bytes) -> int:
    """ERDI B checksum: bitwise inverse of distance bytes, modulo 8 bits."""
    return (0xFF - (sum(payload) & 0xFF)) & 0xFF


def parse_b(frame: bytes, unit_m: float, oor_raw: int) -> float | None:
    """Return metres, None for invalid/OOR, and raise for malformed length."""
    if len(frame) not in (4, 5) or frame[0] != 0x5C:
        raise ValueError("not an ERDI B frame")
    if b_checksum(frame[1:-1]) != frame[-1]:
        raise ValueError("bad ERDI B checksum")
    raw = int.from_bytes(frame[1:-1], "little")
    if raw >= oor_raw:
        return None
    return raw * unit_m


def a_checksum(frame_without_checksum: bytes) -> int:
    """ERDI A reply checksum includes 55 AA and bytes 3..7."""
    return sum(frame_without_checksum) & 0xFF


def parse_a(frame: bytes) -> float | None:
    """Return metres for a successful 0x88 reply, None for STA != 1."""
    if len(frame) != 8 or frame[:2] != b"\x55\xAA":
        raise ValueError("not an ERDI A frame")
    if a_checksum(frame[:7]) != frame[7]:
        raise ValueError("bad ERDI A checksum")
    if frame[2] != 0x88 or frame[3] != 1:
        return None
    return int.from_bytes(frame[5:7], "big") / 10.0


@dataclass
class Checks:
    passed: int = 0

    def ok(self, condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)
        self.passed += 1


def main() -> None:
    c = Checks()

    # LRF50H/LRF100H/etc. sample from the ERDI 5C manuals:
    # 02 11 is 0x1102 = 4354 cm, and EC is the inverse checksum.
    b_sample = bytes.fromhex("5C 02 11 EC")
    c.ok(parse_b(b_sample, 0.01, 65535) == 43.54, "H-series centimetres")
    c.ok(parse_b(b_sample, 0.001, 20000) == 4.354, "VB-series millimetres")

    # H-family out-of-range marker is 0xFFFF; the Lua driver reports it as
    # above RNGFND1_MAX so ArduPilot can classify OutOfRangeHigh.
    b_oor = bytes.fromhex("5C FF FF 01")
    c.ok(parse_b(b_oor, 0.01, 65535) is None, "H OOR marker")

    # LRF1500H is a 5-byte, 24-bit little-endian frame. The source document's
    # shown EC checksum conflicts with its own formula; E9 is formula-correct.
    b_1500 = bytes.fromhex("5C 02 11 03 E9")
    c.ok(abs(parse_b(b_1500, 0.01, 0xFFFFFF) - 2009.62) < 1e-9, "1500H 24-bit frame")
    try:
        parse_b(bytes.fromhex("5C 02 11 03 EC"), 0.01, 0xFFFFFF)
    except ValueError:
        c.passed += 1
    else:
        raise AssertionError("contradictory 1500H sample must not pass checksum")

    # A-family single-ranging reply: STA=1, distance=0x00FA decimetres = 25m.
    a_reply = bytes.fromhex("55 AA 88 01 FF 00 FA 81")
    c.ok(parse_a(a_reply) == 25.0, "A-family success reply")

    # The documented request is retained as a fixture for checklist tooling.
    a_request = bytes.fromhex("55 AA 88 FF FF FF FF 84")
    c.ok(a_request[-1] == (sum(a_request[2:7]) & 0xFF), "A request checksum")

    # Failed measurement (STA=0) with a valid reply checksum is ignored.
    a_failed = bytearray(a_reply)
    a_failed[3] = 0
    a_failed[7] = a_checksum(bytes(a_failed[:7]))
    c.ok(parse_a(bytes(a_failed)) is None, "A-family failed measurement")

    # Corruption is rejected rather than silently converted to a distance.
    bad = bytearray(b_sample)
    bad[-1] ^= 0x01
    try:
        parse_b(bytes(bad), 0.01, 65535)
    except ValueError:
        c.passed += 1
    else:
        raise AssertionError("bad checksum accepted")

    print(f"PASS: {c.passed} ERDI protocol assertions")


if __name__ == "__main__":
    main()
