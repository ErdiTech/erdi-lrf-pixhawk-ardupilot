-- ERDI laser rangefinder Lua driver (draft; not flight-tested)
--
-- Supported protocol families from the ERDI KB:
--   B / 0x5C stream: 4-byte H/VB frames and 5-byte LRF1500H frames.
--   A / 0x55 0xAA: 8-byte command/reply frames, polled with single-ranging
--                  command 0x88. Continuous command 0x89 is deliberately not
--                  used because the A1 manuals have a request/reply mismatch.
--
-- ArduPilot master API references checked 2026-11-02:
--   libraries/AP_Scripting/drivers/TOFSense-M/TOFSense-M_Serial.lua
--   libraries/AP_Scripting/docs/docs.lua
--   libraries/AP_Scripting/generator/description/bindings.desc
--   libraries/AP_Scripting/examples/rangefinder_quality_test.lua
--
-- QUICK SETUP (Serial2 example)
--   SCR_ENABLE=1, SCR_HEAP_SIZE>=150000, SERIAL2_PROTOCOL=28,
--   RNGFND1_TYPE=36, copy this file to APM/scripts, reboot.
--   ERDI_SP is the 1-based index of the scripting serial port (1 = first).
--   Set ERDI_MODE=0 for the 0x5C streaming family (default), or 1 for the
--   0x55AA polled A family. Set ERDI_UNIT per model (H=0.01, VB=0.001).
--
-- This is a draft. Verify the parameter-table key, UART electrical levels,
-- timing/CPU budget and all model-specific supply limits on a real target.

---@diagnostic disable: param-type-mismatch
---@diagnostic disable: undefined-global

local MAV_SEVERITY = { ERROR = 3, WARNING = 4, INFO = 6, DEBUG = 7 }

-- Keep this key unique among scripts installed on the vehicle. 143 is selected
-- for this draft; re-check the upstream/current vehicle script inventory before
-- publishing or merging.
local PARAM_TABLE_KEY = 143
local PARAM_TABLE_PREFIX = "ERDI_"
local LUA_RANGEFINDER_TYPE = 36
local UPDATE_MS = 10
local MAX_BYTES_PER_RUN = 200

local function bind_add_param(name, index, default_value)
    assert(param:add_param(PARAM_TABLE_KEY, index, name, default_value),
           string.format("ERDI: could not add parameter %s", name))
    local p = Parameter()
    assert(p:init(PARAM_TABLE_PREFIX .. name),
           string.format("ERDI: could not bind parameter %s", name))
    return p
end

assert(param:add_table(PARAM_TABLE_KEY, PARAM_TABLE_PREFIX, 8),
       "ERDI: could not add parameter table")

--[[
// @Param: ERDI_MODE
// @DisplayName: ERDI protocol family
// @Description: 0 = 0x5C streaming B family; 1 = 0x55AA polled A family
// @Values: 0:5C streaming,1:55AA polled
// @User: Standard
--]]
local P_MODE = bind_add_param("MODE", 1, 0)
--[[
// @Param: ERDI_SP
// @DisplayName: ERDI scripting serial instance
// @Description: 1-based index of SERIALx ports configured with PROTOCOL=28
// @Range: 1 10
// @User: Standard
--]]
local P_SP = bind_add_param("SP", 2, 1)
--[[
// @Param: ERDI_BR
// @DisplayName: ERDI UART baud rate
// @Description: 460800 for B family; 115200 is the A-family default
// @User: Standard
--]]
local P_BR = bind_add_param("BR", 3, 460800)
--[[
// @Param: ERDI_UNIT
// @DisplayName: ERDI metres per B-frame count
// @Description: H series 0.01 (cm); VB series 0.001 (mm)
// @Range: 0.0001 1
// @User: Standard
--]]
local P_UNIT = bind_add_param("UNIT", 4, 0.01)
--[[
// @Param: ERDI_LEN
// @DisplayName: ERDI B-frame length
// @Description: 4 for 16-bit 0x5C frames; 5 for LRF1500H 24-bit frames
// @Values: 4:4 bytes,5:5 bytes
// @User: Standard
--]]
local P_LEN = bind_add_param("LEN", 5, 4)
--[[
// @Param: ERDI_OOR
// @DisplayName: ERDI out-of-range marker
// @Description: Raw B-frame marker (H=65535, LRF22VB=20000, LRF50VB=50000, LRF1500H=16777215)
// @User: Standard
--]]
local P_OOR = bind_add_param("OOR", 6, 65535)
--[[
// @Param: ERDI_POLL_MS
// @DisplayName: ERDI A-family poll period
// @Description: Period for the single-ranging 0x88 command; ignored in mode 0
// @Range: 50 1000
// @User: Standard
--]]
local P_POLL_MS = bind_add_param("POLL_MS", 7, 200)
--[[
// @Param: ERDI_MAX_BYTES
// @DisplayName: ERDI serial bytes per update
// @Description: Bound Lua work per scheduler tick; lower if the board overruns
// @Range: 16 500
// @User: Standard
--]]
local P_MAX_BYTES = bind_add_param("MAX_BYTES", 8, MAX_BYTES_PER_RUN)

local mode = math.floor(P_MODE:get())
local serial_instance = math.floor(P_SP:get()) - 1
local baud = math.floor(P_BR:get())
local unit_m = P_UNIT:get()
local frame_len = math.floor(P_LEN:get())
local oor_raw = math.floor(P_OOR:get())
local poll_ms = math.max(50, math.floor(P_POLL_MS:get()))
local max_bytes = math.max(16, math.floor(P_MAX_BYTES:get()))

assert(mode == 0 or mode == 1, "ERDI: ERDI_MODE must be 0 or 1")
assert(unit_m > 0, "ERDI: ERDI_UNIT must be positive")
if mode == 0 then
    assert(frame_len == 4 or frame_len == 5, "ERDI: ERDI_LEN must be 4 or 5")
else
    frame_len = 8
end

local port = serial:find_serial(serial_instance)
if not port then
    gcs:send_text(MAV_SEVERITY.ERROR, "ERDI: no SERIALx_PROTOCOL=28 port")
    local function retry()
        return retry, 1000
    end
    return retry()
end
port:begin(baud)
port:configure_parity(0) -- 8N1
port:set_stop_bits(1)
port:set_flow_control(0)

local backend = nil
local max_param = nil
local poll_elapsed_ms = poll_ms
local frame = {}
local frame_count = 0

local function find_backend()
    for i = 0, rangefinder:num_sensors() - 1 do
        local candidate = rangefinder:get_backend(i)
        if candidate and candidate:type() == LUA_RANGEFINDER_TYPE then
            backend = candidate
            return true
        end
    end
    return false
end

local function report_out_of_range()
    -- The Lua backend's state update maps a distance above RNGFND1_MAX to
    -- OutOfRangeHigh. If the parameter is not available yet, simply let the
    -- backend timeout rather than inventing a distance.
    if not max_param then
        max_param = Parameter()
        if not max_param:init("RNGFND1_MAX") then
            max_param = false
        end
    end
    if max_param then
        local max_m = max_param:get()
        if max_m and max_m > 0 then
            backend:handle_script_msg(max_m + 1.0)
        end
    end
end

local function parse_b_frame()
    if frame_count ~= frame_len or frame[1] ~= 0x5C then
        return nil
    end
    local sum = 0
    for i = 2, frame_len - 1 do
        sum = (sum + frame[i]) % 256
    end
    if ((255 - sum) % 256) ~= frame[frame_len] then
        return nil
    end
    local raw = 0
    local multiplier = 1
    for i = 2, frame_len - 1 do
        raw = raw + frame[i] * multiplier
        multiplier = multiplier * 256
    end
    if raw >= oor_raw then
        return "oor"
    end
    return raw * unit_m
end

local function parse_a_frame()
    if frame_count ~= 8 or frame[1] ~= 0x55 or frame[2] ~= 0xAA then
        return nil
    end
    local sum = 0
    for i = 1, 7 do
        sum = (sum + frame[i]) % 256
    end
    if sum ~= frame[8] then
        return nil
    end
    -- 0x88 is the documented single-ranging function. STA=1 means success.
    if frame[3] ~= 0x88 or frame[4] ~= 1 then
        return "invalid"
    end
    local decimetres = frame[6] * 256 + frame[7]
    return decimetres / 10.0
end

local function reset_frame()
    frame = {}
    frame_count = 0
end

local function consume_b_byte(c)
    if frame_count == 0 then
        if c == 0x5C then
            frame_count = 1
            frame[1] = c
        end
        return nil
    end
    frame_count = frame_count + 1
    frame[frame_count] = c
    if frame_count < frame_len then
        return nil
    end
    local result = parse_b_frame()
    reset_frame()
    return result
end

local function consume_a_byte(c)
    if frame_count == 0 then
        if c == 0x55 then
            frame_count = 1
            frame[1] = c
        end
        return nil
    elseif frame_count == 1 then
        if c == 0xAA then
            frame_count = 2
            frame[2] = c
        else
            reset_frame()
            if c == 0x55 then
                frame_count = 1
                frame[1] = c
            end
        end
        return nil
    end
    frame_count = frame_count + 1
    frame[frame_count] = c
    if frame_count < 8 then
        return nil
    end
    local result = parse_a_frame()
    reset_frame()
    return result
end

local function send_a_poll()
    -- 55 AA 88 FF FF FF FF 84, documented single-ranging request.
    port:writestring(string.char(0x55, 0xAA, 0x88, 0xFF, 0xFF, 0xFF, 0xFF, 0x84))
end

local function update()
    if not backend and not find_backend() then
        return update, UPDATE_MS
    end

    if mode == 1 then
        poll_elapsed_ms = poll_elapsed_ms + UPDATE_MS
        if poll_elapsed_ms >= poll_ms then
            poll_elapsed_ms = 0
            send_a_poll()
        end
    end

    local available = math.min(port:available(), max_bytes)
    local out_of_range = false
    while available > 0 do
        available = available - 1
        local byte = port:read()
        if byte < 0 then
            break
        end
        local result
        if mode == 0 then
            result = consume_b_byte(byte)
        else
            result = consume_a_byte(byte)
        end
        if result == "oor" then
            out_of_range = true
        elseif type(result) == "number" then
            local ok = backend:handle_script_msg(result)
            if not ok then
                gcs:send_text(MAV_SEVERITY.WARNING, "ERDI: rangefinder backend rejected sample")
            end
        end
    end
    if out_of_range then
        report_out_of_range()
    end
    return update, UPDATE_MS
end

local function protected_update()
    local ok, next_or_err, delay = pcall(update)
    if not ok then
        gcs:send_text(MAV_SEVERITY.ERROR, "ERDI: " .. tostring(next_or_err))
        return protected_update, 1000
    end
    return protected_update, delay or UPDATE_MS
end

return protected_update()
