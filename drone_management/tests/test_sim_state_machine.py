import math

from mock_drone.sim import DroneSim, Mode


def test_arm_and_takeoff_climbs_to_target():
    sim = DroneSim()
    ok, status = sim.cmd_arm(armed=True)
    assert ok and status == "ACCEPTED"
    sim.cmd_takeoff(alt_m=10.0)

    for _ in range(60):
        sim.tick(0.1)

    assert sim.armed is True
    assert math.isclose(sim.rel_alt_m, 10.0, abs_tol=0.5)
    assert sim.mode == Mode.AUTO


def test_disarm_in_air_denied():
    sim = DroneSim()
    sim.cmd_arm(armed=True)
    sim.cmd_takeoff(alt_m=10.0)
    for _ in range(60):
        sim.tick(0.1)
    ok, status = sim.cmd_arm(armed=False)
    assert not ok and status == "DENIED"
    assert sim.armed is True


def test_land_disarms_on_touchdown():
    sim = DroneSim()
    sim.cmd_arm(armed=True)
    sim.cmd_takeoff(alt_m=5.0)
    for _ in range(40):
        sim.tick(0.1)
    sim.cmd_land()
    for _ in range(60):
        sim.tick(0.1)
    assert sim.rel_alt_m == 0.0
    assert sim.armed is False


def test_goto_moves_horizontally():
    sim = DroneSim(home_lat=37.0, home_lon=-122.0)
    sim.cmd_arm(armed=True)
    sim.cmd_takeoff(alt_m=10.0)
    for _ in range(60):
        sim.tick(0.1)
    sim.cmd_goto(lat=37.0005, lon=-122.0005, alt_m=10.0)

    for _ in range(200):
        sim.tick(0.1)

    assert math.isclose(sim.lat, 37.0005, abs_tol=1e-4)
    assert math.isclose(sim.lon, -122.0005, abs_tol=1e-4)


def test_set_mode_rtl_targets_home():
    sim = DroneSim(home_lat=37.0, home_lon=-122.0)
    sim.cmd_arm(armed=True)
    sim.cmd_takeoff(alt_m=10.0)
    for _ in range(60):
        sim.tick(0.1)
    sim.cmd_goto(lat=37.001, lon=-122.001, alt_m=10.0)
    for _ in range(50):
        sim.tick(0.1)

    sim.cmd_set_mode(Mode.RTL)
    for _ in range(800):
        sim.tick(0.1)

    assert math.isclose(sim.lat, sim.home_lat, abs_tol=1e-4)
    assert math.isclose(sim.lon, sim.home_lon, abs_tol=1e-4)
    assert sim.rel_alt_m == 0.0
