"""Source-oriented Stage 16 sound signal translation.

Outputs are real named 8080 OUT ports, but this first pass is NOT a cycle-exact
port of the $1740/$1775 fleet timer or the continuous $081F main loop.
Events derive from the existing translated game state; the limited scheduling
is clearly identified here rather than concealed in a sound backend.
"""
from sound_ports import SoundPortBus

class RomSoundDriver:
    def __init__(self, bus=None):
        self.bus = bus if bus is not None else SoundPortBus()
        self.rack = None
        self.frame = 0
        self.counts = {}
        self.last_rack_steps = 0
        self.fleet_index = 0
        self.last_player_alive = True
        self.extra_hold = 0
        self.death_hold = 0
        self.alien_hold = 0
        self.ufo_hit_hold = 0
        self.fleet_hold = 0

    def attach(self, rack):
        if rack is self.rack:
            return
        self.bus.reset(frame=self.frame, source='RACK_CHANGE')
        self.rack = rack
        self.counts = {}
        self.last_rack_steps = rack.rack_steps
        self.fleet_index = 0
        self.last_player_alive = True
        self.extra_hold = self.death_hold = self.alien_hold = 0
        self.ufo_hit_hold = self.fleet_hold = 0
        for name in ('combat','saucer','lives'):
            obj = getattr(rack, name, None)
            self.counts[name] = len(getattr(obj, 'events', ()))
        rack.mem[0x2094] = 0
        rack.mem[0x2098] = 0

    def _events(self, key):
        obj = getattr(self.rack, key, None)
        events = getattr(obj, 'events', ())
        start = min(self.counts.get(key, 0), len(events))
        self.counts[key] = len(events)
        return events[start:]

    def _out(self, port, value, source):
        # Original ROM mirrors port values in $2094/$2098. Do not confuse
        # RAM writes with physical OUT; this method deliberately performs both.
        self.rack.mem[0x2094 if port == 3 else 0x2098] = value
        self.bus.write(port, value, frame=self.frame, source=source)

    def _bit(self, port, bit, on, source):
        old = self.bus.values[port]
        value = (old | (1 << bit)) if on else (old & ~(1 << bit))
        if value != old:
            self._out(port, value, source)

    def stop(self):
        if self.rack is not None:
            self._out(3, 0, 'DISABLE_SOUND')
            self._out(5, 0, 'DISABLE_SOUND')

    def step(self, rack, *, playing=True):
        self.frame += 1
        self.attach(rack)
        if not playing or not rack.combat_enabled:
            self.stop()
            return
        m = rack.mem
        # Original $081A SoundBits3On amplifier; $172C ShotSound tests $2025.
        self._bit(3, 5, True, '081A AMPLIFIER_ENABLE')
        self._bit(3, 1, bool(m[0x2025]), '172C ShotSound')

        for event in self._events('combat'):
            name = event[1]
            if name in ('ALIEN_HIT', 'ALIEN_DESTROYED', 'ALIEN_EXPLOSION'):
                self.alien_hold = 5
        # Original scoring flag $20F1 and $2062 alien explosion already flow
        # through Combat; use its actual event names when present.
        for event in self._events('saucer'):
            if event[1] == 'SAUCER_EXPLOSION':
                self.ufo_hit_hold = 18
        for event in self._events('lives'):
            if event[1] == 'EXTRA_SHIP_AWARDED':
                self.extra_hold = 45
        alive = (m[0x2015] == 0xFF)
        if self.last_player_alive and not alive:
            self.death_hold = 38
        self.last_player_alive = alive

        saucer_on = bool(m[0x2084] and not m[0x2085])
        self._bit(3, 0, saucer_on, '1804 CtrlSaucerSound')
        self._bit(3, 2, self.death_hold > 0, '0844 PlayerHit')
        self._bit(3, 3, self.alien_hold > 0, '0A5F ScoreForAlien')
        self._bit(3, 4, self.extra_hold > 0, '0935 ExtraShip')
        self._bit(5, 4, self.ufo_hit_hold > 0, 'SAUCER_HIT')
        for timer in ('death_hold', 'alien_hold', 'extra_hold', 'ufo_hit_hold'):
            value = getattr(self, timer)
            if value:
                setattr(self, timer, value-1)

        # First-pass rhythm uses original complete-rack movement edges.
        # The actual $1740/$1775 fleet sound timers must replace this in a
        # later timing-fidelity pass; do not call it ROM-exact scheduling.
        if self.fleet_hold:
            self.fleet_hold -= 1
            if self.fleet_hold == 0:
                self._out(5, self.bus.values[5] & 0xF0, '176D FleetSoundOff')
        if rack.rack_steps != self.last_rack_steps:
            self.last_rack_steps = rack.rack_steps
            self._out(5, self.bus.values[5] & 0xF0, '176D FleetSoundOff')
            if rack.alive and alive:
                self._bit(5, self.fleet_index, True, '1775 FleetStep PROVISIONAL')
                self.fleet_index = (self.fleet_index + 1) % 4
                self.fleet_hold = 4
