"""Job queue: no interleaving, one retry before sending, no resend after."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.tiny_press.printer.queue import PrintQueue
from custom_components.tiny_press.printer.transport import (
    PrinterConnectError,
    PrinterError,
    PrinterSendError,
    PrinterTransport,
)

from .fake_printer import FakePrinter


async def test_jobs_never_interleave(printer: FakePrinter) -> None:
    queue = PrintQueue(PrinterTransport("127.0.0.1", printer.port))
    jobs = [bytes([i]) * 200_000 for i in range(1, 4)]
    await asyncio.gather(*(queue.print_job(j) for j in jobs))
    for _ in range(50):
        if len(printer.jobs) == 3:
            break
        await asyncio.sleep(0.01)
    assert sorted(printer.jobs) == sorted(jobs)
    assert all(len(set(j)) == 1 for j in printer.jobs)


async def test_second_job_waits_for_first() -> None:
    order: list[str] = []
    gate = asyncio.Event()

    async def send(data: bytes) -> None:
        order.append(f"start {data.decode()}")
        if data == b"a":
            await gate.wait()
        order.append(f"end {data.decode()}")

    transport = AsyncMock(spec=PrinterTransport)
    transport.send.side_effect = send
    queue = PrintQueue(transport)
    first = asyncio.create_task(queue.print_job(b"a"))
    await asyncio.sleep(0)
    second = asyncio.create_task(queue.print_job(b"b"))
    await asyncio.sleep(0)
    assert queue.busy
    assert await queue.poll_status() is None  # never polls mid-job
    gate.set()
    await asyncio.gather(first, second)
    assert order == ["start a", "end a", "start b", "end b"]


async def test_retries_once_when_nothing_was_sent() -> None:
    transport = AsyncMock(spec=PrinterTransport)
    transport.send.side_effect = [PrinterConnectError("refused"), None]
    await PrintQueue(transport).print_job(b"job")
    assert transport.send.await_count == 2


async def test_gives_up_after_second_connect_failure() -> None:
    transport = AsyncMock(spec=PrinterTransport)
    transport.send.side_effect = PrinterConnectError("refused")
    with pytest.raises(PrinterConnectError):
        await PrintQueue(transport).print_job(b"job")
    assert transport.send.await_count == 2


async def test_never_resends_partial_job() -> None:
    transport = AsyncMock(spec=PrinterTransport)
    transport.send.side_effect = PrinterSendError("reset", sent=4096)
    with pytest.raises(PrinterSendError):
        await PrintQueue(transport).print_job(b"x" * 10000)
    assert transport.send.await_count == 1


async def test_connect_refused_is_connect_error(socket_enabled: None) -> None:
    fake = FakePrinter()
    await fake.start()
    port = fake.port
    await fake.stop()
    with pytest.raises(PrinterConnectError):
        await PrinterTransport("127.0.0.1", port).send(b"x")


async def test_status_round_trip(printer: FakePrinter) -> None:
    printer.status[4] = 0x1E  # near end
    status = await PrinterTransport("127.0.0.1", printer.port).read_status()
    assert status.online and status.paper_near_end
    assert printer.jobs == []


async def test_status_without_reply(
    printer: FakePrinter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "custom_components.tiny_press.printer.transport.STATUS_TIMEOUT", 0.2
    )
    printer.answer_status = False
    with pytest.raises(PrinterError):
        await PrinterTransport("127.0.0.1", printer.port).read_status()
