import asyncio
import json
from dataclasses import dataclass

import pytest


@dataclass
class FakeLink:
    sent: list = None
    def __post_init__(self): self.sent = []
    async def send(self, fn):
        # Capture the lambda's intent via a stub mav object.
        class StubMav:
            def __init__(self, sink): self.sink = sink
            def command_long_send(self, *a, **k): self.sink.append(("command_long", a, k))
            def set_position_target_global_int_send(self, *a, **k): self.sink.append(("setpos", a, k))
        fn(StubMav(self.sent))


@pytest.mark.asyncio
async def test_arm_records_pending_then_accepted(session_maker):
    from app.command_service import CommandService
    from app.models import Drone, Command
    from sqlalchemy import select

    SessionLocal = session_maker
    async with SessionLocal() as s:
        d = Drone(system_id=1, component_id=1, name="d1")
        s.add(d)
        await s.commit()
        await s.refresh(d)
        drone_id = d.id

    link = FakeLink()
    svc = CommandService(link=link, ack_timeout_s=0.5)

    # Inject a synthetic ACK shortly after sending.
    async def deliver_ack():
        await asyncio.sleep(0.05)
        from app.mavlink_link import ParsedMessage
        from pymavlink import mavutil
        svc.handle_message(ParsedMessage(
            msg_type="COMMAND_ACK", sender_system=1, sender_component=1,
            payload={"command": mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, "result": 0},
        ))

    asyncio.create_task(deliver_ack())
    cid, status = await svc.arm(drone_id, 1, 1, armed=True)
    assert status == "ACCEPTED"
    assert link.sent and link.sent[0][0] == "command_long"

    async with SessionLocal() as s:
        row = (await s.execute(select(Command).where(Command.id == cid))).scalar_one()
        assert row.kind == "arm"
        assert row.ack_status == "ACCEPTED"
        assert json.loads(row.params_json) == {}


@pytest.mark.asyncio
async def test_arm_times_out_when_no_ack(session_maker):
    from app.command_service import CommandService
    from app.models import Drone, Command
    from sqlalchemy import select

    SessionLocal = session_maker
    async with SessionLocal() as s:
        d = Drone(system_id=2, component_id=1, name="d2")
        s.add(d)
        await s.commit()
        await s.refresh(d)
        drone_id = d.id

    svc = CommandService(link=FakeLink(), ack_timeout_s=0.1)
    cid, status = await svc.arm(drone_id, 2, 1, armed=True)
    assert status == "TIMEOUT"

    async with SessionLocal() as s:
        row = (await s.execute(select(Command).where(Command.id == cid))).scalar_one()
        assert row.ack_status == "TIMEOUT"


@pytest.mark.asyncio
async def test_goto_treated_as_accepted(session_maker):
    from app.command_service import CommandService
    from app.models import Drone

    SessionLocal = session_maker
    async with SessionLocal() as s:
        d = Drone(system_id=3, component_id=1, name="d3")
        s.add(d)
        await s.commit()
        await s.refresh(d)
        drone_id = d.id

    link = FakeLink()
    svc = CommandService(link=link, ack_timeout_s=0.1)
    cid, status = await svc.goto(drone_id, 3, 1, lat=37.78, lon=-122.42, alt_m=20.0)
    assert status == "ACCEPTED"
    assert link.sent and link.sent[0][0] == "setpos"
