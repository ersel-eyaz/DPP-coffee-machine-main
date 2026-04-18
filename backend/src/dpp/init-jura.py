# src/dpp/run_seed_jura.py
from __future__ import annotations

import asyncio
import logging
import sys
import time

logger = logging.getLogger(__name__)

try:
    from dpp.data.seed_jura import init as seed_init
except Exception as exc:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logging.getLogger(__name__).exception("Failed to import dpp.data.seed_jura.init: %s", exc)
    raise


async def _run_async() -> None:
    """Await the async Jura seeding function."""
    await seed_init()


def main() -> int:
    """
    Entry point for creating initial Jura demo data.

    Returns:
        int: process exit code (0 on success).
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    start = time.perf_counter()
    try:
        if asyncio.iscoroutinefunction(seed_init):
            asyncio.run(_run_async())
        else:
            seed_init()  # type: ignore[call-arg]
        elapsed = time.perf_counter() - start
        logger.info("Jura data seeding finished in %.2fs", elapsed)
        return 0
    except KeyboardInterrupt:
        logger.warning("Jura data seeding cancelled by user.")
        return 130  # SIGINT
    except Exception as exc:
        logger.exception("Jura data seeding failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
