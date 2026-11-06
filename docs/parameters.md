# Parameter reference (Lua driver `scripts/erdi_lrf.lua`)

| Model | `ERDI_MODE` | `ERDI_BR` | `ERDI_UNIT` | `ERDI_LEN` | `ERDI_OOR` | `RNGFND1_MIN` (m) | `RNGFND1_MAX` (m) |
|---|---|---|---|---|---|---|---|
| LRF22VB | 0 | 460800 | 0.001 | 4 | 20000 | 0.05 | 20 |
| LRF50VB | 0 | 460800 | 0.001 | 4 | 50000 | 0.05 | 50 |
| LRF50H | 0 | 460800 | 0.01 | 4 | 65535 | 0.05 | 50 |
| LRF100H | 0 | 460800 | 0.01 | 4 | 65535 | 0.05 | 100 |
| LRF200H | 0 | 460800 | 0.01 | 4 | 65535 | 0.05 | 200 |
| LRF300H | 0 | 460800 | 0.01 | 4 | 65535 | 0.05 | 300 |
| LRF600H | 0 | 460800 | 0.01 | 4 | 65535 | 0.05 | 600 |
| LRF1500H | 0 | 460800 | 0.01 | 5 | 16777215 | 0.05 | 1500 |
| LRF1200A1 | 1 | 115200 | n/a | n/a | n/a | 5 | 1200 |
| LRF3000A1 | 1 | 115200 | n/a | n/a | n/a | 1 | 3000 |

Ranges are the "ranging range" rows of each model's technical table at the stated target reflectivity; real reach depends on target and light. Family A (`ERDI_MODE=1`) polls single shots; the unit is fixed at metres x 10 and the driver applies it.

| Parameter | Meaning |
|---|---|
| `ERDI_MODE` | 0 = `5C` stream (family B), 1 = `55 AA` polled (family A) |
| `ERDI_SP` | 1-based index of the `SERIALx` ports that have `SERIALx_PROTOCOL=28`; `1` = the first such port |
| `ERDI_BR` | UART baud rate used by the script |
| `ERDI_UNIT` | metres per family-B count (H series 0.01, VB series 0.001) |
| `ERDI_LEN` | family-B frame length: 4, or 5 for LRF1500H |
| `ERDI_OOR` | raw value the module outputs when out of range |
| `ERDI_POLL_MS` | family-A poll period (50 to 1000 ms) |
| `ERDI_MAX_BYTES` | serial bytes processed per script run; lower it if the board overruns |

ArduPilot's own `RNGFND1_MIN` / `RNGFND1_MAX` are in metres in current firmware (`RNGFND1_MIN_CM` / `RNGFND1_MAX_CM` before the rename). Set them from the table; the Lua backend maps readings above `RNGFND1_MAX` to out-of-range-high.
