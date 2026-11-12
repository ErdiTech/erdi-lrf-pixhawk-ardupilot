# ERDI Lua rangefinder hardware-test checklist


tested or submitting a wiki/driver change. The implementation target is
ArduPilot's Lua rangefinder backend (`RNGFNDx_TYPE=36`).

## 0. Test record

- [ ] Date, operator, board, vehicle firmware/version and SD-card contents recorded
- [ ] ERDI model, hardware revision, firmware revision and serial number recorded
- [ ] Protocol family recorded: B (`0x5C` stream) or A (`0x55 AA` poll)
- [ ] Datasheet revision and supply voltage copied into the record
- [ ] No production vehicle, account, credential or network service is involved

## 1. Protocol fixtures and static checks

- [ ] Run the local parser tests from this directory:

  ```text
  python tests/protocol_fixtures.py
  ```

- [ ] Expected output is `PASS: 9 ERDI protocol assertions` (or a higher count
  if fixtures are added). A failed checksum test is a failure, not a warning.
- [ ] Confirm the selected model's sample frame, unit and out-of-range marker
  against its controlled manual from the manufacturer.
- [ ] For LRF1500H, explicitly record whether the source's contradictory
  `5C 02 11 03 EC` example or the formula-correct `... E9` is implemented;
  do not silently accept both.

## 2. SITL / script integration before hardware

1. Use a clean ArduPilot SITL build with Lua scripting and the Lua rangefinder
   feature enabled. Do not use a live aircraft.
2. Set `SCR_ENABLE=1`, `SCR_HEAP_SIZE>=150000`,
   `SERIALx_PROTOCOL=28`, and `RNGFND1_TYPE=36`; reboot SITL.
3. Copy `erdi_lrf.lua` to `APM/scripts` and restart scripting/SITL.
4. Confirm the `ERDI_` parameters appear. For a B-family fixture set:

   ```text
   ERDI_MODE=0
   ERDI_SP=<first scripting serial instance>
   ERDI_BR=460800
   ERDI_UNIT=0.01     # H series; use 0.001 for VB
   ERDI_LEN=4         # 5 for LRF1500H
   ERDI_OOR=<model marker>
   RNGFND1_MIN=<model minimum in metres>
   RNGFND1_MAX=<model maximum in metres>
   ```

5. Feed the documented byte fixtures through a SITL serial/device harness or
   an equivalent deterministic test shim. Verify:

   - [ ] valid `5C` frame reaches the Lua backend in metres;
   - [ ] garbage before a header is discarded and the parser resynchronises;
   - [ ] bad checksum produces no reading;
   - [ ] the model's OOR marker maps to `OutOfRangeHigh` (or timeout if
     `RNGFND1_MAX` is unavailable);
   - [ ] a valid A-family reply is accepted only with `STA=1` and `0x88`;
   - [ ] a failed A-family reply does not create a stale valid reading;
   - [ ] no scripting overrun, heap exhaustion or repeated `ERDI:` error text.

6. Save the SITL parameter file, console output and a short dataflash log.

## 3. Bench wiring and electrical safety

- [ ] Remove propellers/actuators and use a bench supply/current limit.
- [ ] Verify the ERDI manual's supply voltage with a meter **before** wiring.
  H-series manuals reviewed for this draft specify 9--36 V DC; do not connect
  that supply to a flight controller 5 V pin.
- [ ] Verify signal level (TTL voltage), polarity and connector pinout for the
  exact model; do not infer VB pinout from H-series hardware.
- [ ] Wire sensor TX -> autopilot serial RX, sensor RX -> autopilot serial TX,
  and connect grounds. Leave unused control pins insulated.
- [ ] Add a common ground and strain relief. Check for reverse polarity and
  over-voltage protection (the LRF50H manual says it has none).
- [ ] Keep the laser aperture pointed into a safe, non-reflective target and
  follow the model's laser-safety instructions.
- [ ] Photograph the wiring and record measured supply voltage/current.

## 4. First powered serial test

1. Power only the sensor and autopilot on the bench. Confirm no brownout or
   excessive current before enabling the script.
2. Configure the exact `ERDI_` values and reboot. Confirm the script does not
   emit an error or repeatedly reset.
3. With a stationary diffuse target at a measured distance, collect at least
   60 seconds of readings. Repeat at three distances spanning near, mid and
   far range. For B-family modules, check both the default rate and a reduced
   rate if the sensor supports the documented frequency command.
4. For A-family modules, verify the 0x88 poll/reply exchange at the configured
   baud. Do not enable 0x89 continuous mode until ERDI engineering resolves
   the manual's request/reply mismatch.

## 5. Dataflash / Mission Planner acceptance

- [ ] Mission Planner Flight Data -> Status shows `rangefinder1` changing to
  the measured target distance.
- [ ] Download the onboard `.bin` log and confirm `RFND` messages are present.
- [ ] In `RFND`, verify the expected sensor instance, distance (`Dist`),
  orientation and quality/status fields; record the exact column names for the
  firmware build used.
- [ ] Disconnect TX or power off the sensor for >1 second. Confirm the
  rangefinder transitions to no-data/timeout and does not hold a stale value.
- [ ] Restore the sensor and confirm valid readings resume without rebooting.
- [ ] Move the target beyond the configured maximum or use the documented OOR
  fixture. Confirm the status is out-of-range and not a plausible in-range
  distance.
- [ ] Check scheduler/CPU and Lua heap telemetry; no persistent overrun or
  memory growth is acceptable.

## 6. Minimum evidence bundle for review

- [ ] Firmware version, board and complete relevant parameters
- [ ] Model/revision/serial, supply measurement and wiring photo
- [ ] Raw serial capture showing at least one valid and one invalid frame
- [ ] Mission Planner screenshot of `rangefinder1`
- [ ] `.bin` log excerpt containing `RFND` for valid, timeout and OOR cases
- [ ] Test date, target distances, environment and known limitations

Until every item above is complete, describe the script and wiki page as
**untested drafts**. No PR or forum/wiki publication is part of this checklist.
