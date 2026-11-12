# ERDI laser rangefinder on Pixhawk / ArduPilot

Datasheets and public prices are on the [LRF22VB page](https://erdilrf.com/models/lrf22vb/?utm_source=github&utm_medium=readme&utm_campaign=erdi-lrf-pixhawk-ardupilot) and in the [full ERDI laser rangefinder model list](https://erdilrf.com/models/?utm_source=github&utm_medium=readme&utm_campaign=erdi-lrf-pixhawk-ardupilot).

How to connect an **ERDI 905 nm laser rangefinder module to a Pixhawk flight controller running ArduPilot** (Copter, Plane, Rover): wiring diagram, parameter table, a **Lua scripting driver** you can use today on stock ArduPilot, and the status of the **native driver pull request [ArduPilot/ardupilot#34983](https://github.com/ArduPilot/ardupilot/pull/34983)**. Typical uses: **drone altimeter / terrain following / precision landing** with an LRF22VB (1.5 g, 20 m) or LRF50VB, longer-range H-series modules (50 to 1500 m) for survey and inspection, and A-series modules (LRF3000A1, 1 to 3000 m).

> **Status (2026-11-13).** The Lua driver has been run in ArduPilot SITL (ArduCopter V4.8.0-dev) with simulated modules: LRF22VB millimetre frames, LRF1500H 5-byte frames and A-family polling, 30 minutes each with no Lua errors and flat memory (details and raw logs in [docs/evidence/sitl-20261113](docs/evidence/sitl-20261113)). It has **not** been run on a flight controller or with a real module in the loop; bench-test with props off before any flight. The native driver PR is open and not merged. Do not describe either as "supported by ArduPilot" until upstream merges and documents it.

## Option 1: Lua scripting driver (stock firmware)

1. Wire the module to a free flight-controller UART ([wiring](docs/wiring.svg), diagram below).
2. Set parameters (example: SERIAL2 / TELEM2, LRF22VB), then reboot:

   | Parameter | Value |
   |---|---|
   | `SCR_ENABLE` | 1 |
   | `SCR_HEAP_SIZE` | 150000 or more |
   | `SERIAL2_PROTOCOL` | 28 (Scripting) |
   | `RNGFND1_TYPE` | 36 (Lua scripts) |
   | `RNGFND1_ORIENT` | 25 (downward) |
   | `RNGFND1_MIN` / `RNGFND1_MAX` | from [docs/parameters.md](docs/parameters.md) (metres) |

3. Copy [`scripts/erdi_lrf.lua`](scripts/erdi_lrf.lua) to the SD card folder `APM/scripts/` and reboot. With Mission Planner you can upload it over MAVFTP (Setup, MAVFTP, `APM/scripts`); if the folder does not exist, set `SCR_ENABLE=1`, reboot and it is created.
4. Set the `ERDI_*` parameters for your model (table in [docs/parameters.md](docs/parameters.md)): for LRF22VB `ERDI_MODE=0`, `ERDI_BR=460800`, `ERDI_UNIT=0.001`, `ERDI_LEN=4`, `ERDI_OOR=20000`.
5. Check `RFND` in the log or the Mission Planner / QGroundControl rangefinder display against a tape measure. Full procedure: [docs/hardware-test-checklist.md](docs/hardware-test-checklist.md).

```mermaid
flowchart LR
  M[ERDI module<br/>LRF22VB / LRF50VB / H / A series] -- TX --> RX[FC SERIALn RX]
  TX[FC SERIALn TX] -- RX --> M
  G[GND] --- M
  G --- RX
  P[module supply per manual] --> M
  RX --> L[Lua erdi_lrf.lua<br/>SERIALn_PROTOCOL=28]
  L --> R[RNGFND1_TYPE=36<br/>AP_RangeFinder]
```

![Wiring](docs/wiring.svg)

Cross TX and RX, share ground, and check the module's UART logic level against the flight controller's 3.3 V before connecting. Power the module from its own supply as its manual says; TELEM connector 5 V pins are not automatically right for every model (LRF22VB is a 3.0 to 3.6 V part). Pin order differs by flight controller: use your board's pinout page.

### Flight controller requirements and limits

- ArduPilot's scripting documentation (checked 2026-11-13) asks for at least 2 MB flash and 80 kB memory, says scripting is not available on F4 autopilots, and requires an SD card for the script. Check that your board's firmware includes `AP_SCRIPTING_ENABLED`.
- Set `SCR_ENABLE=1`, `SCR_HEAP_SIZE` of 150000 or more, then reboot before the `ERDI_*` and `RNGFND1_*` parameters appear.
- A-family modules (`ERDI_MODE=1`) are polled. In SITL, a module that answers after 800 ms with a 1 s poll made the rangefinder fall back to NoData 166 times in 30 minutes (`PreArm: Rangefinder 1: No Data`), against 30 with a fast module and deliberate silent periods. Long-range A-family shots that take close to a second can therefore drop out; keep `ERDI_POLL_MS` above the module's reply time and watch `RFND` status.
- `RANGEFINDER` shows readings above `RNGFND1_MAX` as out of range high (max plus 1 m). The MAVLink `DISTANCE_SENSOR` field is 16-bit centimetres and saturates at 655.35 m, so use the float `RANGEFINDER` message or the log for LRF1500H.

## Option 2: native driver (pull request, not merged)

[ArduPilot PR #34983](https://github.com/ArduPilot/ardupilot/pull/34983), "AP_RangeFinder: add ERDI VB and H series serial rangefinders", adds a C++ serial backend, a SITL simulator and autotest coverage for the 4-byte `0x5C` stream:

- `RNGFNDx_TYPE = 49` (ERDI-VB-Serial): LRF10VB, LRF22VB, LRF50VB, distance in millimetres
- `RNGFNDx_TYPE = 50` (ERDI-H-Serial): LRF50H, LRF100H, LRF200H, LRF300H, LRF600H, distance in centimetres

The PR notes SITL autotest results and a factory bench run of an LRF22VB and an LRF50H through a USB-TTL adapter; flight-controller logs are still to come. Bench evidence: <https://github.com/ErdiTech/erdi-lrf-drivers/tree/main/docs/evidence/ardupilot-bench-20261105>. Until the PR is merged and appears in a firmware release, use Option 1 or a companion computer ([erdi-lrf-raspberry-pi-python](https://github.com/ErdiTech/erdi-lrf-raspberry-pi-python) sends MAVLink `DISTANCE_SENSOR`).

## Models and units

The VB series counts **millimetres**, the H series **centimetres**: `5C 02 11 EC` is 4.354 m on an LRF22VB and 43.54 m on an LRF100H. Use the exact model's row in [docs/parameters.md](docs/parameters.md). Model pages, datasheets and prices: <https://erdilrf.com/models/?utm_source=github&utm_medium=readme&utm_campaign=erdi-lrf-pixhawk-ardupilot>.

## Tests

```bash
python3 tests/protocol_fixtures.py        # prints: PASS: 9 ERDI protocol assertions
python3 -m pytest -q tests
luac5.3 -p scripts/erdi_lrf.lua           # Lua syntax check (CI)
```

The fixtures check frame parsing rules against manual examples; they do not replace SITL or bench testing.

## Related projects

- [ErdiTech/erdi-lrf-drivers](https://github.com/ErdiTech/erdi-lrf-drivers): protocol library and flight-controller integration notes
- [drone-altimeter-laser-rangefinder-guide](https://github.com/ErdiTech/drone-altimeter-laser-rangefinder-guide): selection guide for drone laser altimeters
- [laser-rangefinder-module-database](https://github.com/ErdiTech/laser-rangefinder-module-database): dataset of laser rangefinder modules

## License

MIT — see [LICENSE](LICENSE).
