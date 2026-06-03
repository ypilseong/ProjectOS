import asyncio
import json
from datetime import date, datetime
from pathlib import Path

import networkx as nx

from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def should_run(now: datetime, last_run_date: date | None, hour: int) -> bool:
    """True iff no digest has run today and the local hour has reached `hour`."""
    if last_run_date == now.date():
        return False
    return now.hour >= hour
