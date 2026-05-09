from __future__ import annotations

import argparse
import os
import signal
import threading
import time

from pymavlink import mavutil

from .mav_io import MockMavIO
from .sim import DroneSim, Mode


def parse_args():
    p = argparse.ArgumentParser(description="MAVLink mock drone")
    p.add_argument("--target", default="127.0.0.1:14550",
                   help="host:port to send telemetry to (the service)")
    p.add_argument("--listen", default="0.0.0.0:14551",
                   help="host:port to listen for commands on")
    p.add_argument("--system-id", type=int, default=1)
    p.add_argument("--component-id", type=int, default=1)
    p.add_argument("--home", default="37.77927,-122.41924", help="home lat,lon")
    return p.parse_args()


def split_addr(s: str) -> tuple[str, int]:
    host, port = s.rsplit(":", 1)
    return host, int(port)


def handle_command(io: MockMavIO, sim: DroneSim, msg) -> None:
    t = msg.get_type()
    if t == "COMMAND_LONG":
        cmd = msg.command
        if cmd == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
            ok, status = sim.cmd_arm(armed=msg.param1 > 0.5)
        elif cmd == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF:
            ok, status = sim.cmd_takeoff(alt_m=float(msg.param7))
        elif cmd == mavutil.mavlink.MAV_CMD_NAV_LAND:
            ok, status = sim.cmd_land()
        elif cmd == mavutil.mavlink.MAV_CMD_DO_SET_MODE:
            try:
                mode = Mode(int(msg.param2))
            except ValueError:
                ok, status = False, "DENIED"
            else:
                ok, status = sim.cmd_set_mode(mode)
        else:
            ok, status = False, "UNSUPPORTED"
        result = {
            "ACCEPTED": mavutil.mavlink.MAV_RESULT_ACCEPTED,
            "DENIED": mavutil.mavlink.MAV_RESULT_DENIED,
            "UNSUPPORTED": mavutil.mavlink.MAV_RESULT_UNSUPPORTED,
        }.get(status, mavutil.mavlink.MAV_RESULT_FAILED)
        io.send_command_ack(cmd, result)
        print(f"[mock] COMMAND_LONG {cmd} → {status}")
    elif t == "SET_POSITION_TARGET_GLOBAL_INT":
        sim.cmd_goto(lat=msg.lat_int / 1e7, lon=msg.lon_int / 1e7, alt_m=float(msg.alt))
        print(f"[mock] goto ({msg.lat_int/1e7:.5f}, {msg.lon_int/1e7:.5f}, {msg.alt:.1f})")


def reader_loop(io: MockMavIO, sim: DroneSim, stop: threading.Event):
    while not stop.is_set():
        try:
            msg = io.recv(timeout=0.5)
        except Exception as e:
            print(f"[mock] recv err: {e}")
            continue
        if msg is None or msg.get_type() == "BAD_DATA":
            continue
        try:
            handle_command(io, sim, msg)
        except Exception as e:
            print(f"[mock] handler err: {e}")


def main() -> None:
    os.environ.setdefault("MAVLINK20", "1")
    os.environ.setdefault("MAVLINK_DIALECT", "ardupilotmega")

    args = parse_args()
    target_host, target_port = split_addr(args.target)
    listen_host, listen_port = split_addr(args.listen)
    home_lat, home_lon = (float(x) for x in args.home.split(","))

    io = MockMavIO(
        target_host=target_host, target_port=target_port,
        listen_host=listen_host, listen_port=listen_port,
        system_id=args.system_id, component_id=args.component_id,
    )
    io.open()
    sim = DroneSim(home_lat=home_lat, home_lon=home_lon)

    stop = threading.Event()
    rt = threading.Thread(target=reader_loop, args=(io, sim, stop), name="mock-reader", daemon=True)
    rt.start()

    def _sig(_signum, _frame):
        stop.set()
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    print(f"[mock] sending → {target_host}:{target_port}; listening on {listen_host}:{listen_port}")
    boot_t0 = time.monotonic()
    last_hb = 0.0
    last_pos = 0.0
    last_attitude = 0.0
    last_sys = 0.0
    last_gps = 0.0
    last_tick = time.monotonic()

    try:
        while not stop.is_set():
            now = time.monotonic()
            sim.tick(now - last_tick)
            last_tick = now
            time_boot_ms = int((now - boot_t0) * 1000)

            base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            if sim.armed:
                base_mode |= mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED

            if now - last_hb >= 1.0:
                io.send_state(base_mode=base_mode, custom_mode=int(sim.mode))
                last_hb = now
            if now - last_pos >= 0.2:
                io.send_global_position(
                    time_boot_ms=time_boot_ms,
                    lat=sim.lat, lon=sim.lon,
                    alt_m=sim.alt_m, rel_alt_m=sim.rel_alt_m,
                    hdg_deg=sim.yaw_deg,
                )
                last_pos = now
            if now - last_attitude >= 0.1:
                io.send_attitude(
                    time_boot_ms=time_boot_ms,
                    roll=0.0, pitch=0.0,
                    yaw=sim.yaw_deg * 3.14159265 / 180.0,
                )
                last_attitude = now
            if now - last_sys >= 1.0:
                io.send_sys_status(voltage_v=sim.battery_v, battery_pct=sim.battery_pct)
                last_sys = now
            if now - last_gps >= 1.0:
                io.send_gps_raw_int(
                    time_usec=int(now * 1e6),
                    lat=sim.lat, lon=sim.lon, alt_m=sim.alt_m,
                )
                last_gps = now

            time.sleep(0.05)
    finally:
        stop.set()
        rt.join(timeout=1.0)
        io.close()


if __name__ == "__main__":
    main()
