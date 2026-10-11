"""Load dotenv before engine imports and keep one validated mode for this process."""

import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()  # Shell configuration wins; later dotenv loads cannot change mode authority.
MODE: Final = os.getenv("MIRAGE_MODE", "live")
if MODE not in ("live", "replay"):
    raise ValueError("MIRAGE_MODE must be 'live' or 'replay'")
