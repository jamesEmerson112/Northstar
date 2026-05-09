from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_drone_and_telemetry_persist(session_maker):
    from app.models import Drone, TelemetryRecord

    SessionLocal = session_maker
    async with SessionLocal() as s:
        d = Drone(system_id=1, component_id=1, name="d1")
        s.add(d)
        await s.commit()
        await s.refresh(d)
        s.add(TelemetryRecord(
            drone_id=d.id, ts=datetime.now(timezone.utc),
            lat=37.7, lon=-122.4, alt_m=10.0, rel_alt_m=10.0,
            armed=True, mode="AUTO",
        ))
        await s.commit()

    async with SessionLocal() as s:
        from sqlalchemy import select
        rows = (await s.execute(select(TelemetryRecord))).scalars().all()
        assert len(rows) == 1
        assert rows[0].mode == "AUTO" and rows[0].armed is True
