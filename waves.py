"""Stage 11: source-led single-player rack transition ($081F, $09EF-$0A39).

The delay is stepped by the existing diagnostic frame scheduler; the original
blocking $0A3C wait is interrupt-driven. No claim of cycle equivalence.
"""
from rom_objects import OBJECT_MIRROR

START_HEIGHTS = bytes.fromhex('60 50 48 48 48 40 40 40')  # ROM $1DA3-$1DAA

class WaveTransitions:
    def __init__(self, rack):
        self.rack = rack
        self.phase = 'PLAY'
        self.delay = 0
        self.completed = 0
        self.events = []
        rack.mem[0x1DA3:0x1DAB] = START_HEIGHTS
        rack.mem[0x21FE] = 0  # original new-game first rack counter

    def emit(self, action):
        self.events.append((self.rack.frames + 1, action, self.rack.mem[(self.rack.mem[0x2067] << 8) | 0xFE]))

    def service(self):
        m = self.rack.mem
        if self.phase == 'PLAY':
            # $082B/$09EF: based on CountAliens, not a special kill event.
            if not self.rack.alive and not self.rack.lives.game_over:
                self.phase = 'WAIT'
                self.delay = 0x30  # $0A42; ISR-based original delay
                self.emit('WAVE_CLEARED')
            return
        if self.phase == 'WAIT':
            if m[0x2015] != 0xFF:
                return  # original $0A3C waits for player-hit state to resolve
            # Do not count the between-rack pause until the last alien's
            # original 16-tick $1538 explosion is erased by the END ISR.
            if m[0x2002] or m[0x2025] == 5:
                return
            self.delay -= 1
            if self.delay <= 0:
                self.new_rack()

    def new_rack(self):
        r = self.rack
        m = r.mem
        # $0A09-$0A1F: count cycles 1..8, selecting original ROM height.
        player_bank = m[0x2067] << 8
        rack_number = ((m[player_bank + 0xFE] & 7) + 1)
        m[player_bank + 0xFE] = rack_number
        y = START_HEIGHTS[rack_number - 1]
        m[player_bank + 0xFC] = y
        m[player_bank + 0xFD] = 0x38
        # $09F2-$0A00: stop tasks, clear center, copy original 2000-20BF
        # init mirror (the game's score/lives are outside that area).
        m[0x20E9] = 0
        # $09D6 clears video bytes $2402..$3FFF in columns 02..1B.
        # Keep scoreboard and reserve-ship HUD outside the playfield.
        for pos in range(0x2402, 0x4000):
            if (pos & 31) < 0x1C and (pos & 31) >= 2:
                m[pos] = 0
        m[0x2010:0x2070] = OBJECT_MIRROR
        m[0x2067] = player_bank >> 8  # preserve current player across mirror reload
        m[0x2000:0x2010] = bytes.fromhex('01 00 00 10 00 00 00 00 02 78 38 78 38 00 F8 00')
        m[0x2009] = y
        m[0x200A] = 0x38
        m[0x200B] = y
        m[0x200C] = 0x38
        m[0x2000] = 1
        m[0x2006] = 0
        m[0x2068] = 1
        m[0x2082] = 55
        m[player_bank:player_bank + 55] = bytes([1])*55  # $01C0
        m[0x2069] = 0
        m[0x206A] = 0x30
        m[0x20CF] = 0x30
        m[0x20F1] = 0
        r.is_over = False
        r.last_drawn = None
        # reset the active player-shot and three missile descriptors; these
        # were restored by the original ROM mirror above.
        if r.saucer_enabled:
            r.saucer.reset()
            m[0x2091], m[0x2092] = 0, 6
        # $0A33: reset and restore original shield image for the next rack.
        if r.shields_enabled:
            active_player = 1 if m[0x2067] == 0x21 else 2
            r.shields.init_shields(player=active_player)
            r.shields.transfer_shields(player=active_player)
            r.shields.draw_bottom_line()
        m[0x20E9] = 1
        self.phase = 'PLAY'
        self.completed += 1
        self.emit('NEW_RACK')
