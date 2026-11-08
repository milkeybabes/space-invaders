"""Partial 8080 *source-level* interrupt dispatcher, NOT a CPU emulator.

Source: https://computerarcheology.com/Arcade/SpaceInvaders/Code.html
  $0008 -> $008C (scan line 96): video status = 0, non-player objects,
                          CursorNextAlien ($0141).
  $0010 (scan line 224): video status = $80, decrement $20C0,
                          game sound timing, shot sync, DrawAlien ($0100),
                          all game objects, TimeToSaucer.
  $081F-$0851 main loop is independent of interrupts. Stage-2 harness
  pumps ONE selected main-loop pass after each pair of interrupts, ONLY as
  a deterministic diagnostic. This is not an approximation to CPU cycles.

Stage 3 optionally invokes the original object dispatcher in these two
phases; only normal player movement has a translated callback. Unported
object handlers are explicit in the object event log, not simulated. The extant original pixel-overwrite/rainbow behaviour is
preserved. No audio hardware is emulated here.
"""
from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from rack import Rack

TraceHook = Callable[[dict[str, object]], None]


class InterruptScheduler:
    """Orchestrate verified ISR entry/branch order for the rack-only fixture.

    This class does not read instructions or registers; it calls translated
    algorithms at the moments the original ROM does.
    """

    def __init__(self, rack: 'Rack', trace_hook: TraceHook | None = None):
        self.rack = rack
        self.trace_hook = trace_hook
        self.mid_count = 0
        self.end_count = 0
        self.mainloop_count = 0

    def emit(self, phase: str, rom: str, name: str, status: str) -> None:
        if self.trace_hook is None:
            return
        rack = self.rack
        m = rack.mem
        self.trace_hook({
            'frame': rack.frames + 1,
            'phase': phase,
            'rom_address': rom,
            'operation': name,
            'status': status,
            'vblank_2072': f'{m[0x2072]:02X}',
            'wait_2000': m[0x2000],
            'cursor_2006': m[0x2006],
            'isr_delay_20C0': f'{m[0x20C0]:02X}',
            'shot_sync_2080': f'{m[0x2080]:02X}',
            'rack_steps': rack.rack_steps,
        })

    def scanline_96(self) -> None:
        """$0008 -> $008C-$00AE. Game-mode branch is translated."""
        m = self.rack.mem
        self.mid_count += 1
        m[0x2072] = 0                          # $008C-$008D
        self.emit('MID_96', '008C', 'Set vblankStatus = $00', 'PORT')
        if not m[0x20E9]:                     # $0090-$0094 suspendPlay
            self.emit('MID_96', '0090', 'Suspend game tasks', 'BRANCH')
            return
        if m[0x20EF]:                         # $0097-$009B gameMode
            # $00A5/$024B: process non-player objects from $2020.
            if self.rack.objects_enabled:
                self.rack.objects.run(0x2020)
                self.emit('MID_96', '00A5', 'Process non-player objects', 'PORT_DISPATCH_PARTIAL')
            else:
                self.emit('MID_96', '00A5', 'Process non-player objects', 'NOT_PORTED')
            self.rack.cursor_next_alien()     # $00AB -> $0141
            self.emit('MID_96', '00AB', 'CursorNextAlien', 'PORT')
            return
        # $009E: in attract/demo mode, odd $20C1 requests splash ISR work.
        if m[0x20C1] & 1:
            self.emit('MID_96', '009E', 'Demo-mode object service', 'NOT_PORTED')
        else:
            self.emit('MID_96', '009E', 'No demo task pending', 'BRANCH')

    def scanline_224(self) -> None:
        """$0010-$0087. The subroutines outside rack are NOT ported."""
        m = self.rack.mem
        self.end_count += 1
        m[0x2072] = 0x80                     # $0014-$0016
        self.emit('END_224', '0014', 'Set vblankStatus = $80', 'PORT')
        m[0x20C0] = (m[0x20C0] - 1) & 0xFF # $0019-$001C, DEC (HL)
        self.emit('END_224', '0019', 'Decrement isrDelay byte (wrap at 0)', 'PORT')
        # $001D-$006C: tilt/credit debouncing, splash/start not yet ported.
        self.emit('END_224', '001D', 'Tilt / coin / start dispatch', 'NOT_PORTED')
        if not m[0x20E9]:                    # $0042-$0046 suspendPlay
            self.emit('END_224', '0042', 'Suspend game tasks', 'BRANCH')
            return
        if not m[0x20EF]:                    # $0049-$0054 gameMode
            self.emit('END_224', '0049', 'Attract/credit service', 'NOT_PORTED')
            return
        self.emit('END_224', '006F', 'TimeFleetSound', 'NOT_PORTED')
        m[0x2080] = m[0x2032]             # $0072/$0075, shotSync
        self.emit('END_224', '0072', 'shotSync <- obj2TimerExtra', 'PORT')
        self.rack.draw_alien()            # $0078 -> $0100
        self.emit('END_224', '0078', 'DrawAlien', 'PORT')
        if self.rack.objects_enabled:
            self.rack.objects.run(0x2010)
            self.emit('END_224', '007B', 'RunGameObjs (includes player)', 'PORT_DISPATCH_PARTIAL')
        else:
            self.emit('END_224', '007B', 'RunGameObjs (includes player)', 'NOT_PORTED')
        if self.rack.saucer_enabled:
            self.rack.saucer.time_to_saucer()
            self.emit('END_224', '007E', 'TimeToSaucer', 'PORT_DIAGNOSTIC_SCHEDULE')
        else:
            self.emit('END_224', '007E', 'TimeToSaucer', 'NOT_PORTED')

    def main_loop_service(self) -> None:
        """Partial $081F-$0851, called ONCE per diagnostic frame.

        On the original hardware this loop is continuously running, NOT
        synchronized to the interrupts; the correct frequency cannot be
        modeled until the rest of the main loop and the timing dependencies
        are translated. This harness deliberately avoids pretending it can.
        """
        self.mainloop_count += 1
        if self.rack.combat_enabled:
            self.rack.combat.fire_from_controls()
            self.emit('MAIN_DIAG', '081F', 'PlrFireOrDemo', 'PORT_TIMING_PROVISIONAL')
            self.rack.combat.player_shot_hit()
            self.emit('MAIN_DIAG', '190A', 'PlayerShotHit', 'PORT_TIMING_PROVISIONAL')
        else:
            self.emit('MAIN_DIAG', '081F', 'PlrFireOrDemo', 'NOT_PORTED')
            self.emit('MAIN_DIAG', '190A', 'PlayerShotHit', 'NOT_PORTED')
        self.rack.rack_bump()                 # $0822 -> $190D -> $1597
        self.emit('MAIN_DIAG', '190D', 'RackBump edge scan', 'PORT_TIMING_PROVISIONAL')
        self.rack.mem[0x2082] = self.rack.alive  # $0825 -> $15F3, rack-only equivalence
        self.emit('MAIN_DIAG', '0825', 'CountAliens', 'RACK_ONLY')
        if self.rack.combat_enabled:
            self.rack.combat.adjust_score()
            self.emit('MAIN_DIAG', '0828', 'AdjustScore BCD + Print4Digits', 'PORT_TIMING_PROVISIONAL')
            # $082B branches to $09EF when the last alien has been removed.
            if self.rack.waves_enabled:
                self.rack.waves.service()
            # Original $0832/$0838 are AFTER CountAliens and AdjustScore.
            if self.rack.enemy_shots_enabled:
                self.rack.enemy_shots.set_reload_rate()
                self.rack.enemy_shots.speed_shots()
        else:
            self.emit('MAIN_DIAG', '0828', 'Score / shots / fleet sound / saucer', 'NOT_PORTED')

    def step_frame(self) -> None:
        """One diagnostic pair of interrupts + one synthetic main-loop pass."""
        if self.rack.lives_enabled and self.rack.lives.game_over:
            # $166D-$16E3 is a blocking game-over flow, advanced using
            # ISR timing.  $0B89 attract/splash is deliberately not fabricated.
            self.rack.lives.game_over_sequence.step_frame()
            self.rack.frames += 1
            return
        if self.rack.waves_enabled and self.rack.waves.phase == 'WAIT':
            # $09EF/$0A3C blocks the *main loop*, not the interrupt vectors.
            # Keep both ISR passes running so $0100 -> $1538 finishes/erases
            # the final alien explosion before the following wave is drawn.
            self.scanline_96()
            self.scanline_224()
            self.rack.waves.service()
            self.rack.frames += 1
            return
        if self.rack.enemy_demo_halted:
            self.rack.frames += 1
            return
        self.scanline_96()
        # $028E player-death state machine unported: halt the diagnostic
        # on the first player collision rather than faking player lives.
        if (self.rack.enemy_shots_enabled and not self.rack.lives_enabled
                and self.rack.mem[0x2015] != 0xFF):
            self.rack.enemy_demo_halted = True
            self.rack.frames += 1
            return
        self.scanline_224()
        self.main_loop_service()
        self.rack.frames += 1
