-- Space Invaders (1978) — RAM and video RAM trace for a selected frame interval.
-- Tested API style follows the prior MAME 0.282 second-demo tracer.
-- Read-only: no RAM writes, CPU hooks, timing changes, or debug breakpoints.
-- Sampling is emu.register_frame_done, NOT PC=$0010 / VBLANK debugger stop.

local FIRST_FRAME = 3220
local LAST_FRAME = 3250
local PREFIX = "invaders_verify"

local cpu, space, screen
local ramfile, vramfile, deltafile
local callback_frame = -1
local frame_mode = nil
local last_frame, previous_vram
local finished = false

local function screen_counter()
  if screen then
    local ok, v = pcall(function() return screen.frame_number end)
    if ok and type(v) == "number" then return v, "screen_property" end
    if ok and type(v) == "function" then
      local ok2, n = pcall(function() return screen:frame_number() end)
      if ok2 and type(n) == "number" then return n, "screen_method" end
    end
  end
  return callback_frame, "callback_from_zero"
end

local function get_pc()
  local ok, value = pcall(function() return cpu.state["PC"].value end)
  if ok and type(value) == "number" then return string.format("%04X", value % 65536) end
  return ""
end

local function init()
  cpu = manager.machine.devices[":maincpu"]
  assert(cpu, "Cannot find :maincpu")
  space = cpu.spaces["program"]
  assert(space, "Cannot find :maincpu program space")
  screen = manager.machine.screens[":screen"]
  if not screen then
    for _, s in pairs(manager.machine.screens) do screen = s; break end
  end
  assert(screen, "Cannot find the MAME screen")

  ramfile = assert(io.open(PREFIX .. "_ram.csv", "w"))
  vramfile = assert(io.open(PREFIX .. "_vram_frames.csv", "w"))
  deltafile = assert(io.open(PREFIX .. "_vram_changes.csv", "w"))

  local hdr = {"frame", "sample", "pc"}
  for a = 0x2000, 0x20ff do hdr[#hdr+1] = string.format("%04X", a) end
  ramfile:write(table.concat(hdr, ","), "\n")
  vramfile:write("frame,sample,pc,vram_2400_3fff_hex\n")
  deltafile:write("frame,sample,address,previous,current\n")
  print(string.format("Space Invaders VRAM tracer ready: frames %d-%d", FIRST_FRAME, LAST_FRAME))
end

local function close_all()
  for _, f in ipairs({ramfile, vramfile, deltafile}) do
    if f then f:flush(); f:close() end
  end
  ramfile, vramfile, deltafile = nil, nil, nil
end

local function tick()
  if finished then return end
  if not space then init() end
  callback_frame = callback_frame + 1
  local frame, source = screen_counter()
  if not frame_mode then
    frame_mode = source
    print("Frame numbering: " .. frame_mode)
  end
  if frame == last_frame then return end
  last_frame = frame
  if frame < FIRST_FRAME then return end
  if frame > LAST_FRAME then
    close_all()
    finished = true
    print("VRAM trace complete: " .. PREFIX .. "_*.csv")
    return
  end

  local pc = get_pc()
  local sample = "frame_done"
  local ram = {tostring(frame), sample, pc}
  for addr = 0x2000, 0x20ff do
    ram[#ram+1] = string.format("%02X", space:read_u8(addr))
  end
  ramfile:write(table.concat(ram, ","), "\n")

  local vram = {}
  local hex = {}
  local changes = {}
  for addr = 0x2400, 0x3fff do
    local i = addr - 0x2400 + 1
    local b = space:read_u8(addr)
    vram[i] = b
    hex[i] = string.format("%02X", b)
    if previous_vram and b ~= previous_vram[i] then
      changes[#changes+1] = string.format("%d,%s,%04X,%02X,%02X\n", frame, sample, addr, previous_vram[i], b)
    end
  end
  vramfile:write(tostring(frame), ",", sample, ",", pc, ",", table.concat(hex), "\n")
  if #changes > 0 then deltafile:write(table.concat(changes)) end
  previous_vram = vram

  -- Frequent flushing keeps data even if stopped at the debugger.
  ramfile:flush()
  vramfile:flush()
  deltafile:flush()
  if frame == LAST_FRAME then
    print(string.format("Verification trace captured frame %d; %d changed video bytes", frame, #changes))
  end
end

emu.register_frame_done(tick, "invaders_vram_trace")
