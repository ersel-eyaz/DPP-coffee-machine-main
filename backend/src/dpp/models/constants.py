# src/dpp/models/constants.py
"""
Identifier utilities for the DPP prototype.
"""

from __future__ import annotations

import random
import re
from datetime import datetime
from typing import Callable, Set

# ──────────────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────────────

# URN UUID style
UUID_URN_REGEX = re.compile(
    r"^urn:uuid:[0-9a-fA-F]{8}-" r"[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{12}$"
)


def is_urn_uuid(value: str) -> bool:
    """Return True if `value` is a valid 'urn:uuid:<UUID>' string, else False."""
    return bool(UUID_URN_REGEX.fullmatch(value))


async def validate_urn_uuid(value: str) -> bool:
    return is_urn_uuid(value)


_DIGITS = "0123456789"

# In-memory registries for issued identifiers
_issued_glns: Set[str] = set()
_issued_eoris: Set[str] = set()
_issued_lucids: Set[str] = set()
_issued_gtins: Set[str] = set()
_issued_sgtins: Set[str] = set()
_issued_transport_numbers: Set[str] = set()


def _random_digits(length: int) -> str:
    """Return a string of `length` random decimal digits."""
    return "".join(random.choices(_DIGITS, k=length))


def _generate_unique(make_candidate: Callable[[], str], registry: Set[str]) -> str:
    """
    Generate a string candidate
    """
    while True:
        candidate = make_candidate()
        if candidate not in registry:
            registry.add(candidate)
            return candidate


def _gs1_check_digit(number_without_check: str) -> str:
    """
    Compute GS1 (EAN/GTIN/GLN) check digit for a numeric string.
    """
    total = 0
    for idx, ch in enumerate(reversed(number_without_check), start=1):
        d = ord(ch) - 48
        total += d * (3 if idx % 2 == 1 else 1)
    return str((10 - (total % 10)) % 10)


def _make_gs1_number(total_length: int) -> str:
    """Generate a numeric string with a valid GS1 check digit as the last digit."""
    if total_length < 2:
        raise ValueError("total_length must be at least 2")
    body = _random_digits(total_length - 1)
    return body + _gs1_check_digit(body)


# ──────────────────────────────────────────────────────────────────────────────
# Public ID generators
# ──────────────────────────────────────────────────────────────────────────────


def generate_gln_number() -> str:
    """Generate a unique GLN (13 digits)."""
    return _generate_unique(lambda: _make_gs1_number(13), _issued_glns)


def generate_eori_number() -> str:
    """Generate a unique German EORI number: 'DE' + 10 digits."""
    return _generate_unique(lambda: "DE" + _random_digits(10), _issued_eoris)


def generate_lucid_number() -> str:
    """Generate a unique German LUCID number: 'DE' + 20 digits."""
    return _generate_unique(lambda: "DE" + _random_digits(20), _issued_lucids)


def generate_gtin_14_number() -> str:
    """Generate a unique GTIN-14 (14 digits)."""
    return _generate_unique(lambda: _make_gs1_number(14), _issued_gtins)


def generate_sgtin_96_number() -> str:
    """Generate a unique SGTIN-96 (34 digits)."""
    return _generate_unique(lambda: _random_digits(34), _issued_sgtins)


def generate_transport_authority_number() -> str:
    """
    Generate an example German transport authority number:
    'DE-BAG-<YYYY>-<6 digits>'
    """

    def make() -> str:
        year = datetime.now().year
        seq = _random_digits(6)
        return f"DE-BAG-{year}-{seq}"

    return _generate_unique(make, _issued_transport_numbers)


# ──────────────────────────────────────────────────────────────────────────────
# Additional validation helpers (GS1)
# ──────────────────────────────────────────────────────────────────────────────

_GS1_NUMERIC_RE = re.compile(r"^\d+$")


def is_valid_gln(value: str) -> bool:
    """Validate GLN."""
    if not (isinstance(value, str) and len(value) == 13 and _GS1_NUMERIC_RE.fullmatch(value)):
        return False
    return value[-1] == _gs1_check_digit(value[:-1])


def is_valid_gtin14(value: str) -> bool:
    """Validate GTIN-14."""
    if not (isinstance(value, str) and len(value) == 14 and _GS1_NUMERIC_RE.fullmatch(value)):
        return False
    return value[-1] == _gs1_check_digit(value[:-1])


__all__ = [
    "UUID_URN_REGEX",
    "is_urn_uuid",
    "validate_urn_uuid",
    "generate_gln_number",
    "generate_eori_number",
    "generate_lucid_number",
    "generate_gtin_14_number",
    "generate_sgtin_96_number",
    "generate_transport_authority_number",
    "is_valid_gln",
    "is_valid_gtin14",
]
