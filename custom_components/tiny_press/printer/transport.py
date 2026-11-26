"""Raw TCP (port 9100) transport to an ESC/POS printer.

The printer is driven with plain ESC/POS over a socket, with no drivers and no
ePOS-Print HTTP. Port 9100 already covers every command Tiny Press uses,
including the real-time status replies (``DLE EOT``), so the HTTP endpoint
would only add an XML layer and a second code path.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from .escpos import (
    STATUS_OFFLINE,
    STATUS_PAPER,
    STATUS_PRINTER,
    PrinterStatus,
    status_request,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0
STATUS_TIMEOUT = 3.0
CHUNK = 4096
BYTES_PER_SECOND_FLOOR = 4096  # used to size the send timeout for big jobs


class PrinterError(Exception):
    """Base error talking to the printer."""


class PrinterConnectError(PrinterError):
    """The connection failed before any job bytes were written."""


class PrinterSendError(PrinterError):
    """The connection dropped after some job bytes were written."""

    def __init__(self, message: str, sent: int) -> None:
        """Record how many bytes went out before the failure."""
        super().__init__(message)
        self.sent = sent


class PrinterTransport:
    """Opens a fresh connection per job or status query."""

    def __init__(self, host: str, port: int) -> None:
        """Store the address."""
        self.host = host
        self.port = port

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                return await asyncio.open_connection(self.host, self.port)
        except (OSError, TimeoutError) as err:
            raise PrinterConnectError(
                f"cannot connect to {self.host}:{self.port}: {err}"
            ) from err

    @staticmethod
    async def _close(writer: asyncio.StreamWriter) -> None:
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()

    async def send(self, data: bytes) -> None:
        """Write a whole job.

        Raises ``PrinterConnectError`` when nothing was written (safe to retry)
        and ``PrinterSendError`` once any byte was handed to the socket (never
        retry: the printer may already have printed part of the job).
        """
        _reader, writer = await self._open()
        sent = 0
        timeout = 10.0 + len(data) / BYTES_PER_SECOND_FLOOR
        try:
            async with asyncio.timeout(timeout):
                for start in range(0, len(data), CHUNK):
                    chunk = data[start : start + CHUNK]
                    writer.write(chunk)
                    sent += len(chunk)
                    await writer.drain()
        except (OSError, TimeoutError) as err:
            raise PrinterSendError(
                f"connection lost after {sent} of {len(data)} bytes: {err}", sent
            ) from err
        finally:
            await self._close(writer)

    async def read_status(self) -> PrinterStatus:
        """Query DLE EOT 1, 2 and 4 on one connection."""
        reader, writer = await self._open()
        try:
            async with asyncio.timeout(STATUS_TIMEOUT):
                replies: list[int] = []
                for n in (STATUS_PRINTER, STATUS_OFFLINE, STATUS_PAPER):
                    writer.write(status_request(n))
                    await writer.drain()
                    replies.append((await reader.readexactly(1))[0])
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
            raise PrinterError(f"no status reply: {err}") from err
        finally:
            await self._close(writer)
        try:
            return PrinterStatus.parse(*replies)
        except ValueError as err:
            raise PrinterError(str(err)) from err
