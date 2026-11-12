# SITL evidence, 2026-11-13

Method and results for `scripts/erdi_lrf.lua` in ArduPilot SITL. No flight controller and no real module were used: a Python harness (`erdi_sitl_case.py`, run with `run_cases.sh`) plays the module on a TCP socket attached to `SERIAL2` (`SERIAL2_PROTOCOL=28`, `RNGFND1_TYPE=36`) and records MAVLink `RANGEFINDER` (float metres), `DISTANCE_SENSOR`, `STATUSTEXT` and the SITL process CPU and memory.

- Firmware: ArduCopter V4.8.0-dev, SITL build of ArduPilot master 802db19de plus the ERDI driver PR branch (commit 8ce00e7). The native driver is not used; only the Lua backend is.
- Parameters are set over MAVLink after the script has registered its `ERDI_*` table, then SITL is restarted so the script loads them. The read-back values are in each `summary.json`.
- `SCR_HEAP_SIZE=200000`, `SCR_DEBUG_OPTS=2` (runtime and memory messages from Lua).

| Case | Frames | Result in `RANGEFINDER` |
|---|---|---|
| `long-vb` (30 min): LRF22VB 4-byte frames in millimetres, 100 Hz, `ERDI_UNIT=0.001`, `RNGFND1_MAX=20` | 178181 | ramp 5.0 to 5.5 m, 7.321 m, 0.5 m exactly as sent; the 20000 marker gives 21.0 m (above `RNGFND1_MAX`, out of range high) |
| `long-h1500` (30 min): LRF1500H 5-byte frames, 20 Hz, `ERDI_LEN=5`, `ERDI_OOR=16777215`, `RNGFND1_MAX=1500` | 35867 | 1234.56 m, 800 to 810 m ramp, 3.25 m exactly as sent; marker gives 1501.0 m |
| `long-a` (30 min): A family polled (`ERDI_MODE=1`, 200 ms), simulated module answering after 50 ms | 7811 polls, 6506 replies | 1234.5, 2999.9, 12.3 m; the 10 s silent and 10 s `STA=0` phases per minute produce `PreArm: Rangefinder 1: No Data` 30 times |
| `long-aslow` (30 min): A family, poll 1000 ms, module answering after 800 ms | 1563 polls, 1303 replies | same values, but `No Data` 166 times: the Lua backend drops to NoData when replies arrive slowly |

Soak numbers (30 minutes each, four SITL processes in parallel): no Lua error or `ERDI:` warning message in any run; SITL process RSS flat (9.5 MB first to last sample); Lua memory 31 to 39 KB of the 200 KB heap, no growth (last sample 31 KB); Lua script runtime mean 0.23 to 0.38 ms with occasional spikes of 19 to 34 ms, which are scheduling jitter of the SITL host process and say nothing about an MCU. SITL CPU averaged 34.6 to 34.9 % of one host core including the simulator itself.

What this does not show: behaviour on a real flight controller (CPU budget, UART timing at 460800 baud), real module timing and noise, the A-family polling against a real module's response time.

Short runs (80 s) are kept in `short-vb`, `short-h1500`, `short-aslow-60s`.
