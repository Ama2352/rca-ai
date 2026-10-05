"""Frozen validator vocabulary shared by the pipeline and API result."""

from enum import Enum


class Decision(str, Enum):
    """Whether a generated candidate is retained, qualified, or rejected."""

    KEEP = "KEEP"
    KEEP_QUALIFIED = "KEEP_QUALIFIED"
    REJECT = "REJECT"


class SupportLevel(str, Enum):
    """Independent assessment of support for a candidate explanation."""

    STRONG = "STRONG"
    PLAUSIBLE = "PLAUSIBLE"
    WEAK = "WEAK"
    CONTRADICTED = "CONTRADICTED"
