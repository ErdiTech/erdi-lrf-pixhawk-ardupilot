#!/usr/bin/env python3
"""ArduPilot SITL harness for scripts/erdi_lrf.lua (run inside WSL, venv with pymavlink).

Phase 1 (prime): boot SITL so the Lua script registers its ERDI_* parameter table, set the
ERDI_* values over MAVLink, stop SITL (values persist in eeprom.bin).
Phase 2 (run): boot SITL again with serial2 on a TCP socket, feed it ERDI frames, record
DISTANCE_SENSOR, STATUSTEXT, process CPU and RSS, and write summary.json.

Usage: erdi_sitl_case.py --case vb --instance 1 --duration 90 --out /tmp/erdi-w3a/vb
"""
import argparse, json, os, shutil, socket, subprocess, sys, threading, time, collections
from pymavlink import mavutil

LATENCY = [0.05]
AP = os.path.expanduser("~/ap/ardupilot")
SITL = f"{AP}/build/sitl/bin/arducopter"
LUA = os.environ.get("ERDI_LUA") or "/mnt/d/AgentWork/ERDI/upgrade-r4-20261113/W3a-repos/work/erdi-lrf-pixhawk-ardupilot/scripts/erdi_lrf.lua"

CASES = {
    # name: (erdi params, RNGFND1_MIN, RNGFND1_MAX)
    "vb":    ({"ERDI_MODE": 0, "ERDI_BR": 460800, "ERDI_UNIT": 0.001, "ERDI_LEN": 4, "ERDI_OOR": 20000}, 0.05, 20),
    "h1500": ({"ERDI_MODE": 0, "ERDI_BR": 460800, "ERDI_UNIT": 0.01, "ERDI_LEN": 5, "ERDI_OOR": 16777215}, 0.05, 1500),
    "a":     ({"ERDI_MODE": 1, "ERDI_BR": 115200, "ERDI_POLL_MS": 200}, 1, 3000),
}


def b_frame(raw, n):
    body = [(raw >> (8 * i)) & 0xFF for i in range(n - 2)]
    return bytes([0x5C] + body + [(~sum(body)) & 0xFF])


def a_reply(dm, sta=1):
    f = [0x55, 0xAA, 0x88, sta, 0x00, (dm >> 8) & 0xFF, dm & 0xFF]
    return bytes(f + [sum(f) & 0xFF])


class Feeder(threading.Thread):
    """Phases are defined as (seconds, kind, value)."""
    def __init__(self, port, case, rate_hz, stop):
        super().__init__(daemon=True)
        self.port, self.case, self.rate, self.stop = port, case, rate_hz, stop
        self.sent = 0
        self.polls = 0
        self.rx = bytearray()
        self.crash = None
        self.expected = []   # (t_rel, metres or 'oor' or 'none')
        self.t0 = None

    def connect(self):
        for _ in range(120):
            try:
                return socket.create_connection(("127.0.0.1", self.port), timeout=2)
            except OSError:
                time.sleep(0.5)
        raise SystemExit("feeder: cannot connect")

    def schedule(self, t):
        """Return (kind, metres) for relative time t; cycles every 60 s so long runs repeat."""
        c = t % 60
        if self.case == "vb":
            if c < 20: return "val", 5.000 + 0.5 * (c / 20)          # slow ramp 5.0..5.5 m
            if c < 30: return "oor", None
            if c < 50: return "val", 7.321
            return "val", 0.5
        if self.case == "h1500":
            if c < 20: return "val", 1234.56
            if c < 30: return "oor", None
            if c < 50: return "val", 800.00 + 10 * (c - 30) / 20
            return "val", 3.25
        if self.case == "a":
            if c < 20: return "val", 1234.5
            if c < 30: return "none", None      # module silent (no echo)
            if c < 40: return "invalid", None   # STA=0 reply
            if c < 55: return "val", 2999.9
            return "val", 12.3
        raise SystemExit("bad case")

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.crash = repr(e); raise

    def _run(self):
        s = self.connect()
        s.settimeout(0.005)
        self.t0 = time.time()
        period = 1.0 / self.rate
        nxt = time.time()
        buf = b""
        while not self.stop.is_set():
            t = time.time() - self.t0
            kind, val = self.schedule(t)
            try:
                if self.case in ("vb", "h1500"):
                    n = 4 if self.case == "vb" else 5
                    if kind == "oor":
                        raw = 20000 if self.case == "vb" else 16777215
                    else:
                        raw = int(round(val * (1000 if self.case == "vb" else 100)))
                    s.sendall(b_frame(raw, n)); self.sent += 1
                    nxt += period
                    d = nxt - time.time()
                    if d > 0: time.sleep(d)
                    else: nxt = time.time()
                else:
                    try:
                        chunk = s.recv(64)
                        if len(self.rx) < 64: self.rx += chunk
                        buf += chunk
                    except socket.timeout:
                        pass
                    while len(buf) >= 8:
                        i = buf.find(b"\x55\xAA")
                        if i < 0: buf = buf[-1:]; break
                        if len(buf) - i < 8: buf = buf[i:]; break
                        pkt, buf = buf[i:i + 8], buf[i + 8:]
                        if pkt == bytes([0x55, 0xAA, 0x88, 0xFF, 0xFF, 0xFF, 0xFF, 0x84]):
                            self.polls += 1
                            if kind == "val":
                                time.sleep(LATENCY[0])
                                s.sendall(a_reply(int(round(val * 10)))); self.sent += 1
                            elif kind == "invalid":
                                s.sendall(a_reply(0, sta=0)); self.sent += 1
            except OSError:
                break


def proc_stats(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            p = f.read().rsplit(")", 1)[1].split()
        ticks = int(p[11]) + int(p[12])
        rss = 0
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS"):
                    rss = int(line.split()[1])
        return ticks, rss
    except Exception:
        return None


def start_sitl(workdir, inst, serial2_port, log):
    cmd = [SITL, "--model", "quad", "--speedup", "1", "-I", str(inst),
           "--defaults", f"{AP}/Tools/autotest/default_params/copter.parm,erdi.parm"]
    if serial2_port:
        cmd.append(f"--serial2=tcp:{serial2_port}")
    return subprocess.Popen(cmd, cwd=workdir, stdout=open(log, "ab"), stderr=subprocess.STDOUT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, choices=CASES)
    ap.add_argument("--instance", type=int, required=True)
    ap.add_argument("--duration", type=int, default=90)
    ap.add_argument("--rate", type=float, default=None)
    ap.add_argument("--latency", type=float, default=0.05)
    ap.add_argument("--poll-ms", type=int, default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    params, rmin, rmax = CASES[a.case]
    params = dict(params)
    if a.poll_ms and a.case == 'a': params['ERDI_POLL_MS'] = a.poll_ms
    LATENCY[0] = a.latency
    inst = a.instance
    mav_port = 5760 + 10 * inst
    s2 = 6000 + inst
    W = a.out
    shutil.rmtree(W, ignore_errors=True)
    os.makedirs(f"{W}/scripts")
    shutil.copy(LUA, f"{W}/scripts/erdi_lrf.lua")
    with open(f"{W}/erdi.parm", "w") as f:
        f.write(f"SCR_ENABLE 1\nSCR_HEAP_SIZE 200000\nSCR_DEBUG_OPTS 2\nSERIAL2_PROTOCOL 28\nRNGFND1_TYPE 36\n"
                f"RNGFND1_MIN {rmin}\nRNGFND1_MAX {rmax}\nRNGFND1_ORIENT 25\n")
    sitl_log = f"{W}/sitl.log"

    # ---- phase 1: prime parameters
    p = start_sitl(W, inst, None, sitl_log)
    m = None
    for _ in range(60):
        try:
            m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{mav_port}", source_system=250)
            m.wait_heartbeat(timeout=5); break
        except Exception:
            time.sleep(1)
    got = False
    t0 = time.time()
    while time.time() - t0 < 90 and not got:
        m.mav.param_request_read_send(m.target_system, m.target_component, b"ERDI_MODE", -1)
        r = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=2)
        got = bool(r and r.param_id.startswith("ERDI_MODE"))
    if not got:
        p.terminate(); sys.exit("prime: ERDI_MODE never appeared (Lua script did not load)")
    for k, v in params.items():
        ok = False
        for _ in range(6):
            m.mav.param_set_send(m.target_system, m.target_component, k.encode(), float(v), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
            t1 = time.time()
            while time.time() - t1 < 2:
                r = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
                if r and r.param_id.rstrip("\x00") == k and abs(r.param_value - float(v)) < 1e-6 * max(1, abs(v)):
                    ok = True; break
            if ok: break
        if not ok: sys.exit(f"prime: could not set {k}")
    time.sleep(2)
    p.terminate(); p.wait(timeout=15); m.close()
    time.sleep(2)

    # ---- phase 2: run
    stop = threading.Event()
    rate = a.rate or {"vb": 100, "h1500": 20, "a": 1}[a.case]
    feeder = Feeder(s2, a.case, rate, stop)
    p = start_sitl(W, inst, s2, sitl_log)
    feeder.start()
    m = None
    for _ in range(60):
        try:
            m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{mav_port}", source_system=250)
            m.wait_heartbeat(timeout=5); break
        except Exception:
            time.sleep(1)
    m.mav.request_data_stream_send(m.target_system, m.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
    for mid in (173, 132):   # RANGEFINDER (float metres), DISTANCE_SENSOR (uint16 cm, saturates at 655.35 m)
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, mid, 100000, 0, 0, 0, 0, 0)
    # read back params to prove they stuck
    verify = {}
    for k in params:
        for _ in range(5):
            m.mav.param_request_read_send(m.target_system, m.target_component, k.encode(), -1)
            t1 = time.time(); hit = None
            while time.time() - t1 < 2 and hit is None:
                r = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
                if r and r.param_id.rstrip("\x00") == k: hit = r
            if hit is not None:
                verify[k] = hit.param_value; break

    ticks_hz = os.sysconf("SC_CLK_TCK")
    start = time.time()
    last_stat = (start, *(proc_stats(p.pid) or (0, 0)))
    cpu, rss = [], []
    ds = []            # (t, cm)
    rf = []            # (t, metres) from RANGEFINDER
    texts = []
    while time.time() - start < a.duration:
        msg = m.recv_match(blocking=True, timeout=1)
        now = time.time()
        if now - last_stat[0] >= 10:
            st = proc_stats(p.pid)
            if st:
                cpu.append(100.0 * (st[0] - last_stat[1]) / ticks_hz / (now - last_stat[0]))
                rss.append(st[1])
                last_stat = (now, st[0], st[1])
        if not msg: continue
        t = msg.get_type()
        if t == "DISTANCE_SENSOR":
            ds.append((round(now - start, 2), msg.current_distance))
        elif t == "RANGEFINDER":
            rf.append((round(now - start, 2), round(msg.distance, 3)))
        elif t == "STATUSTEXT":
            texts.append((round(now - start, 1), msg.severity, msg.text))
    stop.set()
    p.terminate()
    try: p.wait(timeout=15)
    except Exception: p.kill()

    import re
    lua_t = [int(mm.group(1)) for x in texts for mm in [re.match(r"Lua: Time: (\d+) Mem: (\d+) \+ (\d+)", x[2])] if mm]
    lua_m = [int(mm.group(2)) + int(mm.group(3)) for x in texts for mm in [re.match(r"Lua: Time: (\d+) Mem: (\d+) \+ (\d+)", x[2])] if mm]
    rvals = collections.Counter(v for _, v in rf)
    rchanges = []; prev = None
    for t, v in rf:
        if v != prev: rchanges.append((t, v)); prev = v
    vals = collections.Counter(v for _, v in ds)
    changes = []
    prev = None
    for t, v in ds:
        if v != prev:
            changes.append((t, v)); prev = v
    lua_err = [x for x in texts if ("ERDI:" in x[2] and x[1] <= 4) or "Lua" in x[2] and ("error" in x[2].lower() or "bad" in x[2].lower())
               or "Script" in x[2] and "error" in x[2].lower()]
    runtime = [x for x in texts if "Runtime" in x[2] or "Time:" in x[2] or "Mem:" in x[2]]
    summary = {
        "case": a.case, "responder_latency_s": a.latency, "poll_ms": params.get("ERDI_POLL_MS"), "duration_s": a.duration, "params_readback": verify, "rate_hz": rate,
        "frames_sent_or_replies": feeder.sent, "polls_seen": feeder.polls, "first_rx_bytes_hex": feeder.rx.hex(), "feeder_crash": feeder.crash,
        "rangefinder_msgs": len(rf), "rangefinder_distinct_m_top": rvals.most_common(12),
        "rangefinder_value_changes_first_60": rchanges[:60],
        "lua_runtime_us_max": max(lua_t) if lua_t else None, "lua_runtime_us_mean": round(sum(lua_t) / len(lua_t), 1) if lua_t else None,
        "lua_runtime_samples": len(lua_t), "lua_mem_total_bytes_max": max(lua_m) if lua_m else None,
        "lua_mem_total_bytes_last": lua_m[-1] if lua_m else None,
        "distance_sensor_msgs": len(ds), "distinct_values_cm_top": vals.most_common(12),
        "value_changes_first_40": changes[:40],
        "cpu_pct_avg": round(sum(cpu) / len(cpu), 1) if cpu else None,
        "cpu_pct_max": round(max(cpu), 1) if cpu else None,
        "rss_kb_first": rss[0] if rss else None, "rss_kb_last": rss[-1] if rss else None,
        "rss_kb_max": max(rss) if rss else None,
        "lua_error_statustext": lua_err[:20],
        "runtime_statustext_samples": runtime[:3] + runtime[-3:],
        "all_erdi_or_prearm_statustext_unique": sorted({x[2] for x in texts if "ERDI" in x[2] or "Rangefinder" in x[2] or "Lua" in x[2] or "Script" in x[2]})[:30],
    }
    json.dump(summary, open(f"{W}/summary.json", "w"), indent=1)
    with open(f"{W}/statustext.log", "w") as f:
        for x in texts: f.write(f"{x[0]}\t{x[1]}\t{x[2]}\n")
    with open(f"{W}/rangefinder.csv", "w") as f:
        f.write("t_s,distance_m"+chr(10))
        for t, v in rf: f.write(f"{t},{v}"+chr(10))
    with open(f"{W}/distance_sensor.csv", "w") as f:
        f.write("t_s,current_distance_cm\n")
        for t, v in ds: f.write(f"{t},{v}\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
