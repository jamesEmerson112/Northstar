import pytest


@pytest.mark.asyncio
async def test_list_and_telemetry_endpoints(session_maker):
    from datetime import datetime, timezone
    from httpx import ASGITransport, AsyncClient
    from app.main import create_app
    from app.models import Drone, TelemetryRecord

    SessionLocal = session_maker
    async with SessionLocal() as s:
        d = Drone(system_id=7, component_id=1, name="d7")
        s.add(d)
        await s.commit()
        await s.refresh(d)
        s.add(TelemetryRecord(
            drone_id=d.id, ts=datetime.now(timezone.utc),
            lat=37.7, lon=-122.4, alt_m=10, rel_alt_m=10, mode="AUTO", armed=True,
        ))
        await s.commit()

    # Build app without invoking lifespan (no MAVLink in unit tests).
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/drones")
        assert r.status_code == 200
        data = r.json()
        assert any(x["system_id"] == 7 for x in data)

        drone_id = next(x["id"] for x in data if x["system_id"] == 7)
        r2 = await ac.get(f"/api/drones/{drone_id}/telemetry/latest")
        assert r2.status_code == 200
        assert r2.json()["mode"] == "AUTO"


@pytest.mark.asyncio
async def test_command_endpoint_returns_503_without_mavlink(session_maker):
    from httpx import ASGITransport, AsyncClient
    from app.main import create_app
    from app.models import Drone

    SessionLocal = session_maker
    async with SessionLocal() as s:
        d = Drone(system_id=9, component_id=1, name="d9")
        s.add(d)
        await s.commit()
        await s.refresh(d)
        drone_id = d.id

    # Reset cmd_service so endpoint sees the uninitialised state.
    from app import command_service as cs_mod
    cs_mod.cmd_service = None

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(f"/api/drones/{drone_id}/commands/arm")
        assert r.status_code == 503
