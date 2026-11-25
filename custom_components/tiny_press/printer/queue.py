"""Single job queue so two prints never interleave on the printer."""

from __future__ import annotations

import asyncio
import logging

from .escpos import PrinterStatus
from .transport import PrinterConnectError, PrinterTransport

_LOGGER = logging.getLogger(__name__)

RETRY_DELAY = 1.0


class PrintQueue:
    """Serializes jobs and status polls behind one ``asyncio.Lock``."""

    def __init__(self, transport: PrinterTransport) -> None:
        """Wrap a transport."""
        self.transport = transport
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        """Return True while a job (or status poll) holds the printer."""
        return self._lock.locked()

    async def print_job(self, data: bytes) -> None:
        """Send one job, waiting for any earlier job to finish.

        A connection that fails before any byte is written is retried once.
        A job that was partly sent is never resent.
        """
        async with self._lock:
            try:
                await self.transport.send(data)
            except PrinterConnectError as err:
                _LOGGER.debug("Connect failed, retrying once: %s", err)
                await asyncio.sleep(RETRY_DELAY)
                await self.transport.send(data)

    async def poll_status(self) -> PrinterStatus | None:
        """Read the status, or return None if a job is printing right now."""
        if self._lock.locked():
            return None
        async with self._lock:
            return await self.transport.read_status()
