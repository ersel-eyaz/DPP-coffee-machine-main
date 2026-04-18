# src/dpp/seed.py
from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import Callable, Awaitable

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("dpp.seed")
from dpp.data.seed_jura import init as seed_jura
from dpp.data.seed_dpp_multilevel import init as seed_multilevel
from dpp.data.clear_db import clear_db as seed_clear


async def _run(fn: Callable[[], Awaitable[int] | Awaitable[None]] | Callable[[], int | None]) -> None:
    """Run a callable that may be sync or async, and raise if non-zero code is returned."""
    if asyncio.iscoroutinefunction(fn):
        rv = await fn()  # type: ignore[misc]
        if isinstance(rv, int) and rv != 0:
            raise SystemExit(rv)
        return
    rv = fn()  # type: ignore[misc]
    if isinstance(rv, int) and rv != 0:
        raise SystemExit(rv)


async def _init_both() -> None:
    """Single public seed: run both datasets in sequence."""
    t0 = time.perf_counter()
    log.info(">> Seeding dataset 1/2: jura")
    await _run(seed_jura)
    log.info(">> Seeding dataset 1/2: jura ok")

    log.info(">> Seeding dataset 2/2: multilevel")
    await _run(seed_multilevel)
    log.info(">> Seeding dataset 2/2: multilevel ok")
    log.info("All datasets finished in %.2fs", time.perf_counter() - t0)


def main(argv: list[str]) -> int:
    """
    Usage:
      python -m dpp.seed init   # run both seeders (single name)
      python -m dpp.seed clear  # clear DB via existing clear routine
    """
    if len(argv) < 2:
        print("Usage: python -m dpp.seed <init|clear>")
        return 2

    cmd = argv[1].strip().lower()
    try:
        if cmd == "init":
            asyncio.run(_init_both())
            return 0
        if cmd == "clear":
            if asyncio.iscoroutinefunction(seed_clear):
                asyncio.run(seed_clear())
            else:
                seed_clear()  # type: ignore[misc]
            return 0

        print("Usage: python -m dpp.seed <init|clear>")
        return 2

    except KeyboardInterrupt:
        log.warning("Cancelled by user.")
        return 130
    except SystemExit as e:
        code = int(e.code) if isinstance(e.code, int) else 1
        log.error("Aborted with exit code %s", code)
        return code
    except Exception as exc:
        log.exception("Seed failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
