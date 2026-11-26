"""A fake ESC/POS printer on localhost: records jobs, answers DLE EOT."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

DLE_EOT = b"\x10\x04"


@dataclass
class FakePrinter:
    """Accepts connections like a TM printer on port 9100."""

    status: dict[int, int] = field(
        default_factory=lambda: {1: 0x16, 2: 0x12, 3: 0x12, 4: 0x12}
    )
    jobs: list[bytes] = field(default_factory=list)
    connections: int = 0
    answer_status: bool = True
    drop_after: int | None = None  # close the socket after this many bytes
    hold: asyncio.Event | None = None  # block reading until set
    server: asyncio.Server | None = None
    port: int = 0
    received: asyncio.Event = field(default_factory=asyncio.Event)

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.connections += 1
        data = bytearray()
        try:
            if self.hold is not None:
                await self.hold.wait()
            while chunk := await reader.read(65536):
                data += chunk
                # A status query arrives alone and waits for its reply.
                if len(data) == 3 and data[:2] == DLE_EOT:
                    if self.answer_status:
                        writer.write(bytes([self.status[data[2]]]))
                        await writer.drain()
                    data.clear()
                if self.drop_after is not None and len(data) >= self.drop_after:
                    break
        except ConnectionError:
            pass
        finally:
            if data:
                self.jobs.append(bytes(data))
                self.received.set()
            writer.close()
