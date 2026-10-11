"""Load dotenv before engine imports and validate this process's admission settings."""

import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()  # Shell configuration wins; admission settings stay fixed until restart.
MODE: Final = os.getenv("MIRAGE_MODE", "live")
if MODE not in ("live", "replay"):
    raise ValueError("MIRAGE_MODE must be 'live' or 'replay'")

GATE_CONTEXT: Final = os.getenv("MIRAGE_GATE_CONTEXT", "0") == "1"  # layer 2 sees recent tool results

try:
    GATE_REVIEW: Final = float(os.getenv("MIRAGE_GATE_REVIEW", "0.4"))
    GATE_THRESHOLD: Final = float(os.getenv("MIRAGE_GATE_THRESHOLD", "0.7"))
    if not 0 <= GATE_REVIEW <= GATE_THRESHOLD <= 1:
        raise ValueError
except ValueError:
    raise ValueError("Gate thresholds must be finite numbers with "
                     "0 <= MIRAGE_GATE_REVIEW <= MIRAGE_GATE_THRESHOLD <= 1") from None
