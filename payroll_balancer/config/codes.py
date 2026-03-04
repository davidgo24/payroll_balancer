"""
Domain config — single source of truth for pay code mappings.
Used by backend; frontend never duplicates code sets.
"""

# 6.1 Skip employees (finance handled)
SKIP_CODES = {"ADMIN LEAVE PAY"}

# 6.2 Leave bank mappings — which codes draw from which banks
BANK_DRAWS = {
    "SICK": {
        "AL SICK PAY",
        "FMLA SICK",
        "SICK PAY",
        "HEALTHY SICK PAY",
        "HEALTHY SICK PT",
        "HEALTHY LMTD PT",
        "HEALTHY SICK LMTD",
    },
    "VAC": {"FMLA VAC", "VAC PAY"},
    "AL": {
        "AL PAY",
        "AL PT PAY",
        "FMLA AL",
        "AL SAL PAY",
        "ADMIN SAL PAY",
        "ADMIN DIS",
        "BEREAVEMENT",
    },
    "COMP": {"CT PAY 1.0", "CT PAY 1J", "FMLA CT PAY", "CT SAL PAY", "CT SAL PAY 1.0"},
}

# 6.3 Bank fallback order (when exhausted)
BANK_FALLBACK_ORDER = {
    "SICK": ["VAC", "COMP", "AL", "LWOP"],
    "VAC": ["SICK", "COMP", "AL", "LWOP"],
    "AL": ["SICK", "VAC", "COMP", "LWOP"],
    "COMP": ["SICK", "VAC", "AL", "LWOP"],
}

# 6.4 Bank → default New World code for reallocation suggestion
BANK_TO_DEFAULT_CODE = {
    "SICK": "SICK PAY",
    "VAC": "VAC PAY",
    "AL": "AL PAY",
    "COMP": "CT PAY 1.0",
}

# 6.5 Totals code sets
# REG-like / Paid codes (count as paid straight-time)
REG_LIKE_CODES = {
    "REG FT",
    "REG PT",
    "REG SAL",
    "REG PT LMTD",
    "REG PT OTHER",
    "GUARANTEE",
    "NON PROD LUNCH",
    "RECOVERY 1.5",
    "HOL PAY",
    "HOL PAYOUT",
    "HOL UTU",
    "HOL UTU SAL",
    "SICK PAY",
    "FMLA SICK",
    "AL SICK PAY",
    "HEALTHY SICK PAY",
    "HEALTHY SICK PT",
    "HEALTHY LMTD PT",
    "VAC PAY",
    "FMLA VAC",
    "AL PAY",
    "AL PT PAY",
    "FMLA AL",
    "BEREAVEMENT",
    "AL SAL PAY",
    "ADMIN SAL PAY",
    "ADMIN DIS",
    "CT PAY 1.0",
    "CT PAY 1J",
    "FMLA CT PAY",
    "CT SAL PAY",
    "CT SAL PAY 1.0",
}

# Premium codes (OT/premium bucket)
PREMIUM_CODES = {
    "OT 1.5",
    "OT 1.0",
    "OT 1.5 PT BUS",
    "OT PT",
    "OT PT-LMTD",
    "CT EARN 1.5",
    "CT EARN 1.0",
    "HOL 1.5",
    "HOL 1.0",
    "HOL 1.0 CTE",
}

# LWOP code
LWOP_CODE = "LWOP"

# Special constants
GUARANTEE_CODE = "GUARANTEE"
REG_CODE = "REG FT"
OT_15_CODE = "OT 1.5"
OT_10_CODE = "OT 1.0"
CT_EARN_15_CODE = "CT EARN 1.5"
CT_EARN_10_CODE = "CT EARN 1.0"

# Premium 1.5x codes and their 1.0x equivalents (OT and CT EARN treated same for sick/LWOP rules)
PREMIUM_15_TO_10 = [
    ("OT 1.5", "OT 1.0"),
    ("CT EARN 1.5", "CT EARN 1.0"),
]
PREMIUM_OT_LIKE_CODES = ["OT 1.5", "OT 1.0", "CT EARN 1.5", "CT EARN 1.0"]


# Helpers
def code_draws_from_bank(code: str) -> str | None:
    """Return bank name if code draws from a bank, else None."""
    for bank, codes in BANK_DRAWS.items():
        if code in codes:
            return bank
    return None


def is_reg_like(code: str) -> bool:
    return code in REG_LIKE_CODES


def is_premium(code: str) -> bool:
    return code in PREMIUM_CODES


def is_lwop(code: str) -> bool:
    return code == LWOP_CODE
