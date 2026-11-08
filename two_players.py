"""Stage 15: 8080 $02ED-$0335 two-player state-bank handoff.

Shared game objects at $2010..$206F are reinitialized at each turn;
per-player aliens, shields, rack coordinates and lives use $21xx/$22xx.
This intentionally does not duplicate combat code or sprite logic.
"""
from rom_objects import OBJECT_MIRROR

class TwoPlayerController:
    def __init__(self, rack, starting_lives):
        self.rack = rack
        self.pending_switch = False
        self.events = []
        m = rack.mem
        m[0x20CE] = 1
        m[0x20E7] = m[0x20E8] = 1
        m[0x20E5] = m[0x20E6] = 1
        m[0x21FF] = starting_lives - 1  # P1 active ship was already taken by PlayerLives
        m[0x22FF] = starting_lives
        m[0x21FE] = m[0x22FE] = 0
        m[0x2100:0x2137] = b'\x01'*55
        m[0x2200:0x2237] = b'\x01'*55
        m[0x21FB:0x21FE] = m[0x22FB:0x22FE] = bytes((2, 0x78, 0x38))
        rack.shields.init_shields(2)
        rack.two_player_controller = self

    def other_alive(self):
        m = self.rack.mem
        return bool(m[0x20E8] if m[0x2067] == 0x21 else m[0x20E7])

    def switch(self):
        """$02ED: remember shields/rack direction/coords, restore mirror and other bank."""
        r = self.rack
        m = r.mem
        outgoing = 1 if m[0x2067] == 0x21 else 2
        incoming = 3 - outgoing
        from_bank = m[0x2067] << 8
        r.shields.transfer_shields(outgoing, remember=True)
        m[from_bank + 0xFB] = m[0x2008]
        m[from_bank + 0xFC] = m[0x2009]
        m[from_bank + 0xFD] = m[0x200A]
        m[0x2010:0x2070] = OBJECT_MIRROR
        m[0x2067] = 0x21 if incoming == 1 else 0x22
        incoming_bank = m[0x2067] << 8
        m[0x2008] = m[incoming_bank + 0xFB]
        m[0x2009] = m[0x200B] = m[incoming_bank + 0xFC]
        m[0x200A] = m[0x200C] = m[incoming_bank + 0xFD]
        m[0x2007] = 0
        m[0x200D] = int(m[0x2008] & 0x80 != 0)
        m[0x2000] = 1
        m[0x2002] = m[0x2003] = m[0x2006] = 0
        m[0x2082] = r.alive
        m[0x2069] = 0
        m[0x206A] = 0x30
        m[0x2011] = 0  # original $0318
        r.is_over = False
        r.last_drawn = None
        r.waves.phase = 'PLAY'
        r.waves.delay = 0
        r.lives.game_over = False
        if r.lives.life_decrement:
            r.lives.remove_ship()  # original $0326, incoming active ship
        else:
            # Debug changes only the arithmetic of reserve subtraction.
            r.lives.draw_reserve_ships()
            r.lives.draw_lives_number(min(6, r.lives.stash + 1))
        self.pending_switch = False
        self.events.append(('SWITCH', outgoing, incoming))

    def note_player_game_over(self):
        self.events.append(('PLAYER_GAME_OVER', 1 if self.rack.mem[0x2067] == 0x21 else 2))
