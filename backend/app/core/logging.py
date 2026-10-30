import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    """
    Configures root logger with a standardized console handler and log format.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


# Application-level logger
logger = logging.getLogger("scout")
