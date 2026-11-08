"""8080 $0248-$028D game-object list and normal-player movement source port.

This is NOT an 8080 interpreter. We translate the memory state and control
flow of the ROM dispatcher directly to Python. Handlers are keyed by the
actual 16-bit address stored in the original $2010+16*N descriptors.

Ported handler: $028E GameObj0, $033B-$0398. Stage 7 enables
the original explosion branch $0296-$02CF through lives.py.
Unported shot handlers are recorded as such; no made-up shot motion occurs.
Input uses the original active-high control-port bits:
$20=left, $40=right, $10=fire. Fire logic lives in the main loop and is
not included here yet. The original sprite is copied from ROM $1C60.

Reference: https://computerarcheology.com/Arcade/SpaceInvaders/Code.html
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from rack import Rack

PLAYER_HANDLER = 0x028E
UNPORTED_HANDLERS = {0x03BB: 'player shot', 0x0476: 'rolling shot',
                     0x04B6: 'plunger shot', 0x0682: 'squiggly shot and saucer'}


class UnportedPlayerState(RuntimeError):
    """Never silently fabricate the not-yet-translated player-death path."""


class GameObjectDispatcher:
    def __init__(self, rack: 'Rack'):
        self.rack = rack
        self.handlers: dict[int, Callable[[int], str]] = {PLAYER_HANDLER: self.player_normal}
        self.trace_hook: Callable[[dict], None] | None = None
        self.calls = 0
        self.player_draws = 0

    def record(self, base: int, handler: int | None, action: str) -> None:
        if self.trace_hook is None:
            return
        m = self.rack.mem
        self.trace_hook({'frame': self.rack.frames + 1,
                         'phase': 'MID_96' if m[0x2072] == 0 else 'END_224',
                         'object_base': f'{base:04X}',
                         'handler': f'{handler:04X}' if handler is not None else '',
                         'timer_hi': f'{m[base]:02X}',
                         'timer_lo': f'{m[base+1]:02X}',
                         'timer_extra': f'{m[base+2]:02X}',
                         'operation': action,
                         'player_x_201B': f'{m[0x201B]:02X}'})

    def run(self, start: int = 0x2010, stop: int | None = None) -> None:
        """Source port of $024B-$028D; starts at $2020 for scanline-96.

        Each 16-byte structure contains a big-endian two-byte countdown at
        +0/+1, an additional byte countdown at +2, and a little-endian
        handler address at +3/+4. In the assembly, a handler receives a
        pointer to structure+4 via the stack; Python receives the structure
        base, which is equivalent for decoding its fields.
        """
        if (start - 0x2010) % 16 or not 0x2010 <= start <= 0x2060:
            raise ValueError('object list must start at original aligned object boundary')
        m = self.rack.mem
        if stop is not None and (stop - 0x2010) % 16:
            raise ValueError("object stop boundary must be aligned")
        for base in range(start, stop if stop is not None else 0x2070, 0x10):
            status = m[base]
            if status == 0xFF:                 # $024B-$024E list terminator
                self.record(base, None, 'END_FF')
                return
            if status == 0xFE:                 # $024F-$0251 inactive object
                self.record(base, None, 'SKIP_FE')
                continue
            # $0254-$0259; $0277-$0280, 16-bit countdown is FIRST.
            # Original DEC/INC B sequences implement a borrow. Its two bytes
            # are (high,low) at +0,+1, not little endian.
            counter = (status << 8) | m[base + 1]
            if counter:
                counter = (counter - 1) & 0xFFFF
                m[base] = counter >> 8
                m[base + 1] = counter & 0xFF
                self.record(base, None, 'DECREMENT_16')
                continue
            if m[base + 2]:                   # $025C-$025F; $0288-$028D
                m[base + 2] = (m[base + 2] - 1) & 0xFF
                self.record(base, None, 'DECREMENT_8')
                continue
            handler = m[base + 3] | (m[base + 4] << 8)
            self.calls += 1
            method = self.handlers.get(handler)
            if method:
                action = method(base)
            else:
                action = 'NOT_PORTED_' + UNPORTED_HANDLERS.get(handler, f'{handler:04X}').upper().replace(' ', '_')
            self.record(base, handler, action)
        if stop is None:
            raise ValueError('original $2060 FF terminator was not encountered')

    def player_shot(self, base: int) -> str:
        """$03BB GameObj1 handler, only enabled in the Stage-4 combat mode."""
        if not self.rack.combat_enabled:
            return 'SHOT_NOT_PORTED'
        return self.rack.combat.player_shot(base)

    def player_normal(self, base: int) -> str:
        """Port normal movement path in $033B-$0398, excluding explosion.

        We retain the original memory object and 1-pixel-per-call steps,
        right-priority, and $30/$D9 limit checks. No artificial time multiplier.
        The simple sprite overwrites the 16 columns of VRAM directly.
        """
        m = self.rack.mem
        if base != 0x2010:
            raise ValueError('Player handler called with non-player structure')
        if m[0x2015] != 0xFF:             # $0290-$0293: death branch
            if self.rack.lives_enabled:
                return self.rack.lives.player_death_tick(base)
            raise UnportedPlayerState('GameObj0 blow-up path $0296-$0332 not yet translated')
        m[0x2068] = 1                   # $033B: player OK
        if m[0x2069] == 0:              # $03B0: alien firing enable delay
            m[0x206A] = (m[0x206A] - 1) & 0xFF
            if m[0x206A] == 0:
                m[0x2069] = 1           # $0346-$0348
        x = m[0x201B]                  # $034A: player X (cabinet horizontal)
        if m[0x20EF]:                  # $0351: gameplay / inputs
            controls = self.rack.read_inputs()  # $17C0
            right, left = bool(controls & 0x40), bool(controls & 0x20)
        else:                           # $0355 demo movement path
            cmd = m[0x201D]
            right, left = bool(cmd & 0x01), bool(cmd & 0x02)
        if right:                       # $0366-$0368, $0381
            if x != 0xD9:
                m[0x201B] = (x + 1) & 0xFF
        elif left:                      # $036B-$036C, $038E
            if x != 0x30:
                m[0x201B] = (x - 1) & 0xFF
        # $036F-$0378: ReadDesc $2018, ConvToScr, DrawSimpSprite
        sprite = m[0x2018] | (m[0x2019] << 8)
        pixel_low, pixel_high, size = m[0x201A], m[0x201B], m[0x201C]
        self.rack.draw_simple_sprite(pixel_low, pixel_high, sprite, size)
        m[0x2012] = 0                  # $037B-$037D: extra timer always 0
        self.player_draws += 1
        return 'PLAYER_NORMAL'
