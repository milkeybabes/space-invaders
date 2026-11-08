"""Stage 14e continuation of the original attract loop (bounded source translation).

Original $0AB1: 64 ISR ticks; $0A93: preload 7, wait until 1 (6 ISR ticks);
$0B02 / $0B08: ROM messages; $1815: score advance table.
The three moving-Y sprite descriptors are now translated ($1868), but demo
The $0B89 credit presentation and $0BDA restart are implemented. The
$0BCE animated C/alien-shot sequence remains a verified translation gap.
"""
from alien_data import ALIEN_IMAGES
from saucer import SAUCER_SPRITE

ROM_PLAY_NORMAL = bytes.fromhex('0F 0B 00 18')  # $1DAB normal Y
ROM_PLAY = bytes.fromhex('0F 0B 00 29')  # ROM $1CFA: upside-down Y
ROM_INVADERS = bytes.fromhex('12 0F 00 02 04 26 26 08 0D 15 00 03 04 11 12')
ROM_ADV = bytes.fromhex('28 12 02 0E 11 04 26 00 03 15 00 0D 02 04 26 13 00 01 0B 04 28')
ROM_LABELS = (bytes.fromhex('27 38 26 0C 18 12 13 04 11 18'),
              bytes.fromhex('27 1D 1A 26 0F 0E 08 0D 13 12'),
              bytes.fromhex('27 1C 1A 26 0F 0E 08 0D 13 12'),
              bytes.fromhex('27 1B 1A 26 0F 0E 08 0D 13 12'))
ROM_IMAGES = (SAUCER_SPRITE[4:20],
              ALIEN_IMAGES[32:48], ALIEN_IMAGES[64:80], ALIEN_IMAGES[:16])

class AttractIntro:
    def __init__(self, front, cold_start=True):
        self.front = front
        self.phase = 'opening_delay'
        # Native MAME AVI (hard reset): P of PLAY appears at frame 74.
        # The previous 72-frame cold startup was two video frames early.
        self.ticks = 74 if cold_start else 64
        self.opening_frame = 0
        self.cold_start = cold_start
        self.checkpoints = {}  # first cold-start MAME-compatible PC landmarks
        self.index = 0
        self.glyph_ticks = 0
        self.sequence = ()
        m = front.rack.mem
        if cold_start:
            # $18D9 copies $1BE0-$1BFF into $20E0-$20FF ONCE at
            # machine initialization. $1BED/$1BEE contain $74/$1F.
            # Later $0B4A demo entries copy only $2000-$20BF, so
            # this ROM script pointer must persist between demonstrations.
            m[0x20ED:0x20EF] = bytes((0x74, 0x1F))
        # $09D6 clears only central playfield, leaving score/credits intact.
        for col in range(224):
            for row in range(2,28):
                m[0x2400+col*32+row] = 0
        self._install_splash_glyphs(m)
        self.splash_animate = m[0x20EC] & 1
        # On COLD power-up the original 8080 spends eight frames clearing VRAM
        # and another drawing the status header. The Python score display
        # has already been initialized, so hide its pre-rendered pixels
        # until the measured frame-9 milestone. ROM/work RAM is untouched.
        if cold_start:
            m[0x2400:0x4000] = bytes(0x1C00)
        self.front.events.append(('ATTRACT_INTRO', '0AEA'))

    @staticmethod
    def _install_splash_glyphs(m):
        """Restore ROM splash glyphs in any freshly initialised Rack RAM.

        $0B4A resets the demo's RAM state.  In this native translation the
        ROM image lives in the same memory array, so rebuilding the Rack
        must also re-copy the special font data ($1F40 contains '*').
        Otherwise both original $28 prefixes print as empty characters.
        """
        m[0x1F38:0x1F50] = bytes.fromhex(
            '00 14 14 14 14 14 00 00 '
            '00 22 14 7F 14 22 00 00 '
            '00 03 04 78 04 03 00 00')
        m[0x1FC0:0x1FC8] = bytes.fromhex('00 20 40 4D 50 20 00 00')

    def _checkpoint(self, pc):
        # Diagnostic only: record an entry once per cold-start trace.
        self.checkpoints.setdefault(pc, self.opening_frame)

    def _draw_initial_status(self):
        """$1959-$0AF3: render the original scoreboard on native frame 9."""
        sd = self.front.rack.score_display
        sd.initialised = True
        sd.draw_header()
        # At MAME frame 9 the ROM has already completed player-one's
        # four zeros and started player-two's first zero; the remaining
        # seven digits and the CREDIT footer appear during frame 10.
        sd.draw_score(0x20F8)
        sd.draw_char(0x1A, 0x391C)
        self._checkpoint(0x0AF3)

    def _draw_initial_credit(self):
        """Frame 10: three score numerals then the CREDIT 00 row."""
        sd = self.front.rack.score_display
        for base in (0x20F8, 0x20FC, 0x20F4):
            sd.draw_score(base)
        self.front._write('CREDIT', 0x3501)
        self.front._draw_credit_number()

    def _printing_tick(self):
        """$0A93: each glyph consumes six end-screen ISR decrements.

        The wait is performed after every character, including the last.
        At the end of PLAY the ROM jumps directly to $0B0B: there is no
        extra seven-frame gap between the two messages.
        """
        if self.glyph_ticks:
            self.glyph_ticks -= 1
            return
        if self.index == len(self.sequence):
            if self.sequence in (ROM_PLAY, ROM_PLAY_NORMAL):
                self._checkpoint(0x0B0B)
                self._message(ROM_INVADERS, 0x2B14)
                self._printing_tick()  # first SPACE glyph in this frame
            else:
                self._checkpoint(0x0B0E)
                self.phase = 'title_wait'
                self.ticks = 64
            return
        self.address = self.front.rack.score_display.draw_char(
            self.sequence[self.index], self.address)
        self.index += 1
        # First character immediately, next at +6 frames. Five intervening
        # callbacks, then the sixth draws the following character.
        self.glyph_ticks = 5

    # $09D6 ClearPlayField writes 224 * 26 VRAM bytes, not a whole-frame
    # framebuffer reset. Each byte costs 66 8080 T-states; the jump to the
    # next 32-byte column adds 20 at each of the 224 row boundaries.
    # Approximate T-states per arcade video frame: 1,996,800 / 59.542.
    # This translates the ROM write order and instruction workload without
    # interpreting 8080 opcodes or disturbing our 60-Hz gameplay scheduler.
    DEMO_CLEAR_CYCLES_PER_FRAME = 33536
    DEMO_CLEAR_BYTES = 224 * 26

    @classmethod
    def _clear_playfield_budget(cls, mem, written, remainder):
        """Translate $09D6's ordered VRAM stores for *either* caller.

        Both $0B4A (demo startup) and $0B90->$1988 (post-death credit)
        call exactly the same ROM routine.  Preserve the low-five-bit
        2..27 address order, 8080 instruction costs, and the old margins.
        This routine updates video RAM; it never fabricates a screen wipe.
        """
        budget = cls.DEMO_CLEAR_CYCLES_PER_FRAME + remainder
        while written < cls.DEMO_CLEAR_BYTES:
            offset = written % 26
            cost = 66 + (20 if offset == 25 else 0)
            if budget < cost:
                break
            column = written // 26
            mem[0x2400 + 32 * column + 2 + offset] = 0
            written += 1
            budget -= cost
        return written, budget

    def _advance_demo_clear(self):
        self.demo_clear_written, self.demo_clear_remainder = (
            self._clear_playfield_budget(self.front.rack.mem,
                                         self.demo_clear_written,
                                         self.demo_clear_remainder))

    def _begin_credit_clear(self):
        """$0B90->$1988->$09D6, after the ROM's OneSecDelay."""
        self.phase = 'credit_clear'
        self.credit_clear_written = 0
        self.credit_clear_remainder = 0
        self._advance_credit_clear()  # original CPU enters $09D6 this frame

    def _draw_credit_header_characters(self, count):
        """$0B93/$08F3: PrintMessage is *not* PrintMessageDel ($0A93)."""
        for _ in range(count):
            if self.index == len(self.sequence):
                break
            self.address = self.front.rack.score_display.draw_char(
                self.sequence[self.index], self.address)
            self.index += 1
        if self.index == len(self.sequence):
            self._credit_descriptors()
            # $0BB1 begins immediately after ordinary PrintMessage returns.
            # The first slow descriptor glyph is already visible in MAME
            # frame 1360, alongside the completed INSERT COIN heading.
            self._credit_descriptor_tick()

    def _advance_credit_clear(self):
        """Clear the post-death playfield; then resume the same ROM PC flow.

        MAME native AVI: writes are visible frames 1348..1359. During the
        remaining CPU time in frame 1359, $08F3 prints "INSERT"; the
        remaining six message bytes and first delayed descriptor glyph
        become visible in frame 1360.  This phase split is a presentation
        approximation of the uninterrupted original 8080 routine, not a
        gameplay-frame delay or a new animation.
        """
        m = self.front.rack.mem
        self.credit_clear_written, self.credit_clear_remainder = (
            self._clear_playfield_budget(m,
                                         self.credit_clear_written,
                                         self.credit_clear_remainder))
        if self.credit_clear_written == self.DEMO_CLEAR_BYTES:
            self._message(bytes.fromhex('08 0D 12 04 11 13 26 26 02 0E 08 0D'), 0x2C11)
            self.phase = 'credit_print'
            self._draw_credit_header_characters(6)

    def _begin_demo_setup(self):
        """$0B4A: ROM-ordered video clear and display build, demo only.

        MAME hard-reset observation: start 618, reserve ships 631,
        count/partial shields 632, shields/line 633, first invader 634.
        The existing demo object/shot scheduler is left untouched.
        """
        self._checkpoint(0x0B4A)
        self.phase = 'demo_setup'
        self.ticks = 14
        self.demo_setup_frame = 0
        self.demo_clear_written = 0
        self.demo_clear_remainder = 0
        self.demo_shield_rows_written = 0
        self.demo_visual_finish_pending = False
        # $0B4D tests $21FF: first demo allocates ships, later demos jump
        # directly to $0B5D. Preserve that original RAM-dependent branch.
        self.demo_existing_ships = bool(self.front.rack.mem[0x21FF])
        self._demo_setup_tick()  # entry to $0B4A takes place in this frame

    def _restore_demo_shield_rows(self, upto):
        """$021A/$1A69: OR shield bytes in the source's left-to-right order."""
        from shields import SHIELD_START, SHIELD_PITCH, SHIELD_ROWS, SHIELD_IMAGE
        m = self.front.rack.mem
        base = self.front.rack.shields.buffer_for_player(1)
        for index in range(self.demo_shield_rows_written, upto):
            shield, col = divmod(index, SHIELD_ROWS)
            screen = SHIELD_START + (shield * SHIELD_PITCH + col) * 32
            saved = base + shield * len(SHIELD_IMAGE) + 2 * col
            m[screen] |= m[saved]
            m[screen + 1] |= m[saved + 1]
        self.demo_shield_rows_written = upto

    def _demo_setup_tick(self):
        """Expose the CPU's original initialization writes one frame at a time."""
        self.demo_setup_frame += 1
        position = self.demo_setup_frame
        if position <= 12:
            self._advance_demo_clear()  # 12-frame original $09D6 VRAM write
            if position == 12 and self.demo_existing_ships:
                # $0B4D/$0B51: when the existing $21FF count is nonzero,
                # $0B54 GetShipsPerCred and $0B5A RemoveShip are skipped.
                # The RAM mirror and invader initialization can start in
                # the remaining CPU time following $09D6's return.
                self._start_demo(staged=True)
                if getattr(self.front, 'experimental_rom_ram_lifecycle', False):
                    # $001D still runs during the final clearing frame;
                    # the old Python setup path skipped this END IRQ.
                    ram = self.front.rack.mem
                    ram[0x20C0] = (ram[0x20C0] - 1) & 0xFF
                if getattr(self.front, 'experimental_rom_ram_lifecycle', False) and getattr(self.front, 'experimental_continuation', False):
                    # $0B5D reaches the end-screen interrupt before frame
                    # 3004's MID ISR: the $2020..$2060 continuation is
                    # pending just as at cold-start frame 632.  This is the
                    # existing ROM dispatcher, not a fabricated missile tick.
                    self._demo_tail_pending = True
        elif position == 13 and self.demo_existing_ships:
            # The shorter $0B5D branch goes directly through $0B63/$0B66
            # and $0B6E rather than re-allocating the reserve ships.
            self._restore_demo_shield_rows(4 * 22)
            self.front.rack.shields.draw_bottom_line()
            self._checkpoint(0x0B71)
            self.phase = 'demo_play'
            self.demo_visual_finish_pending = False
            # On the already-initialized $21FF branch the original reaches
            # the demo loop in time for this frame's end-screen interrupt.
            # Preserve the scanned image prior to that ISR's alien redraw.
            r = self.front.rack
            r._presentation_luma_override = None
            before_end_irq = r.portrait_luma()
            self._demo_tick()
            if getattr(self.front, 'demo_video_phase', 'pre') == 'pre':
                r._presentation_luma_override = before_end_irq
        elif position == 13:
            # First-ever demo, $0B54..$0B5A executes RemoveShip.
            assert self.demo_clear_written == self.DEMO_CLEAR_BYTES
        elif position == 14:
            # Frame 631: $0B54->RemoveShip renders the reserve-ship icons.
            self._start_demo(staged=True)
        elif position == 15:
            # Frame 632: $1A8B lives numeral then $021A shield restoration.
            # MAME frame 632 has exactly eight columns of shield four.
            r = self.front.rack
            r.lives.draw_lives_number(self.front.starting_lives)
            self._restore_demo_shield_rows(3 * 22 + 8)
            self._checkpoint(0x0B71)
            self.phase = 'demo_play'
            self.demo_visual_finish_pending = True
            if getattr(self.front, 'experimental_continuation', False):
                # The original END-screen interrupt can service $2010 in
                # frame 632 after the demo-loop entry at $0B71. The older
                # per-frame approximation waited until frame 633, leaving
                # both the $0080 countdown and the rolling-shot task phase
                # one interrupt behind MAME. Execute the *whole* original
                # interrupt-derived dispatcher pass (not a reduced timer or
                # an extra player step), with its continuation suspended
                # at the $2010/$2020 object boundary just like the ROM.
                self._demo_tick_continuation()

    def _finish_demo_visual_setup(self):
        """Frame 633: remaining fourth-shield columns and $01CF floor."""
        self._restore_demo_shield_rows(4 * 22)
        self.front.rack.shields.draw_bottom_line()
        self.demo_visual_finish_pending = False

    def _begin_restart_clear(self):
        """$0BE2->$09D6: the credit-to-title wipe also takes CPU time."""
        self.phase = 'attract_restart_clear'
        self.restart_clear_written = 0
        self.restart_clear_remainder = 0
        self._advance_restart_clear()

    def _advance_restart_clear(self):
        self.restart_clear_written, self.restart_clear_remainder = (
            self._clear_playfield_budget(self.front.rack.mem,
                                         self.restart_clear_written,
                                         self.restart_clear_remainder))
        if self.restart_clear_written == self.DEMO_CLEAR_BYTES:
            self._next_attract_pass()  # $0BE5: jump to attract outer loop

    def _message(self, data, addr):
        self.phase = 'printing'
        self.sequence = data
        self.address = addr
        self.index = 0
        self.glyph_ticks = 0

    def _draw_table(self):
        """$1815: 21 glyphs and four ROM sprites at $2C0E/0C/0A/08."""
        self._checkpoint(0x0B11)
        sd = self.front.rack.score_display
        address = 0x2810
        for code in ROM_ADV:
            address = sd.draw_char(code, address)
        m = self.front.rack.mem
        for y, sprite in zip((0x0E, 0x0C, 0x0A, 0x08), ROM_IMAGES):
            # $1844 -> $1439: 16 bytes, one per vertical VRAM row.
            address = 0x2C00 | y
            for k,byte in enumerate(sprite):
                dest = address + k*32
                if 0x2400 <= dest < 0x4000:
                    m[dest] = byte
        # $182B jumps directly to $1837 when the four image records end.
        # The $1834 OneSecDelay is unreachable on this path.
        # Execute the first character in the entry frame, matching $0B11.
        self._draw_table_labels()
        self._table_label_tick()

    def _draw_table_labels(self):
        """$1837-$1855: start four slow, ten-character point-value lines.

        $184C calls $0A93 PrintMessageDel, with a six-interrupt delay
        after EACH glyph.  This applies on both the normal and animated
        attract passes; the earlier port drew the 40 characters immediately.
        """
        self.phase = 'table_label_print'
        self.label_index = 0
        self.label_glyph_index = 0
        self.label_address = 0x2E0E
        self.label_glyph_ticks = 0

    def _table_label_tick(self):
        if self.label_glyph_ticks:
            self.label_glyph_ticks -= 1
            return
        label = ROM_LABELS[self.label_index]
        code = label[self.label_glyph_index]
        self.label_address = self.front.rack.score_display.draw_char(
            code, self.label_address)
        self.label_glyph_index += 1
        # $0A99 writes 7, but $0A9E-$0AA2 exits when the counter
        # reaches 1, so exactly SIX end-screen decrements are needed.
        # This first glyph's frame plus five waiting ticks yields a new
        # glyph every six frames; including the last glyph's delay,
        # 40 characters take exactly 240 frames ($0B11 -> $0B14).
        self.label_glyph_ticks = 5
        if self.label_glyph_index == len(label):
            self.label_index += 1
            self.label_glyph_index = 0
            if self.label_index == len(ROM_LABELS):
                # $0B14: two-second pause after score advance table.
                # Keep the final glyph's delay as part of the printing step.
                self.phase = 'table_last_glyph_delay'
            else:
                self.label_address = (0x2E0C, 0x2E0A, 0x2E08)[self.label_index - 1]

    def _continue_after_table(self):
        # $0B17-$0B1B: first normal PLAY skips the moving-Y animation.
        if self.splash_animate:
            self._begin_demo_setup()
        else:
            self._start_animation(0)


    # Byte-perfect 12-byte $0AE2 animation descriptors.
    ANIM_DESCRIPTORS = (
        bytes.fromhex('00 00 FF B8 FE 20 1C 10 9E 00 20 1C'),
        bytes.fromhex('00 00 01 B8 98 A0 1B 10 FF 00 A0 1B'),
        bytes.fromhex('00 00 FF B8 FF 80 1F 10 97 00 80 1F'),
        bytes.fromhex('00 00 01 D0 22 20 1C 10 94 00 20 1C'), # $1FD5 CCOIN alien
    )
    ANIM_IMAGES = {
        0x1C20: bytes.fromhex('00 00 00 00 19 3A 6D FA FA 6D 3A 19 00 00 00 00'),
        0x1C50: bytes.fromhex('00 00 00 00 1A 3D 68 FC FC 68 3D 1A 00 00 00 00'),
        0x1BA0: bytes.fromhex('00 03 04 78 14 13 08 1A 3D 68 FC FC 68 3D 1A 00'),
        0x1BD0: bytes.fromhex('00 00 03 04 78 14 0B 19 3A 6D FA FA 6D 3A 19 00'),
        0x1F80: bytes.fromhex('60 10 0F 10 60 30 18 1A 3D 68 FC FC 68 3D 1A 00'),
        0x1FB0: bytes.fromhex('00 60 10 0F 10 60 38 19 3A 6D FA FA 6D 3A 19 00'),
    }

    def _start_animation(self, index):
        self.animation_index = index
        self.phase = 'y_animation'
        self.front.rack.mem[0x20C2:0x20CE] = self.ANIM_DESCRIPTORS[index]
        self.front.rack.mem[0x20C1] = 2
        self.front.events.append(('ATTRACT_ANIMATE', ('1A95', '1BB0', '1FC9', '1FD5')[index]))

    def _animate_tick(self):
        """$1868 ISR: move signed deltas, flip image each 4 steps, draw $15D3."""
        m = self.front.rack.mem
        m[0x20C2] = (m[0x20C2] + 1) & 255
        m[0x20C5] = (m[0x20C5] + (m[0x20C3] if m[0x20C3]<128 else m[0x20C3]-256)) & 255
        m[0x20C6] = (m[0x20C6] + (m[0x20C4] if m[0x20C4]<128 else m[0x20C4]-256)) & 255
        if m[0x20C6] == m[0x20CA]:
            m[0x20CB] = 1
            m[0x20C1] = 0
            if self.animation_index == 3:
                self._start_c_shot()
            elif self.animation_index == 0:
                self._start_animation(1)
            elif self.animation_index == 1:
                self.phase = 'y_one_sec_wait'
                self.ticks = 64
            else:
                self.phase = 'y_final_wait'
                self.ticks = 64
            return
        image = m[0x20CC] | (m[0x20CD]<<8)
        if not (m[0x20C2] & 4):
            image += 0x30
        m[0x20C7] = image & 255
        m[0x20C8] = image >> 8
        sprite = self.ANIM_IMAGES.get(image)
        if sprite is None:
            raise AssertionError(f'Unverified splash image {image:04X}')
        x, y = m[0x20C5], m[0x20C6]
        addr, shift = self.front.rack.pixel_to_address(x, y)
        for i, byte in enumerate(sprite):
            dest=addr+i*32
            if 0x2400 <= dest < 0x4000:
                m[dest] = (byte << shift)&255
            if 0x2400 <= dest+1 < 0x4000:
                m[dest+1] = (byte >> (8-shift)) if shift else 0

    def _start_demo(self, *, staged=False):
        """$0B4A-$0B6E: clear field, initialise rack and demo commands.

        Separate from normal gameplay; the 8080 $20EF gameMode stays zero.
        The rest of $0B71-$0B86 is incrementally translated below.
        """
        from rack import Rack
        previous = self.front.rack
        # $0B4A reinitialises the demonstration as a new rack. Re-enabling
        # game objects on the OLD Rack retains $2100 alien flags and
        # $2009/$200A formation coordinates from the preceding demo.
        # Create a fresh RAM/rack state while preserving the persistent
        # top-of-screen high score and attract-cycle selection.
        saved_hi_score = bytes(previous.mem[0x20F4:0x20F6])
        saved_splash = previous.mem[0x20EC]
        saved_demo_pointer = bytes(previous.mem[0x20ED:0x20EF])
        r = Rack()
        self.front.rack = r
        # $0B4A reinitialises RAM, but the original ROM remains readable.
        # Reinstall the non-alphabet ROM glyphs needed by the later credit
        # presentation, notably the asterisks at $1F40.
        self._install_splash_glyphs(r.mem)
        r.mem[0x20F4:0x20F6] = saved_hi_score
        r.mem[0x20EC] = saved_splash
        if staged and getattr(self.front, 'experimental_rom_ram_lifecycle', False):
            # ROM $0B5D -> $01E4 writes only $2000..$20BF.
            # $20C0..$20FF and the player reserve/buffers survive; the ROM's
            # $01C0 separately resets the 55 alien flags at $2100..$2136.
            # Mirror only those *untouched* bytes from the old physical RAM.
            # This is an experiment in the actual ROM write boundaries,
            # not a missile value/phase override.
            r.mem[0x20C0:0x2100] = previous.mem[0x20C0:0x2100]
            r.mem[0x2137:0x2400] = previous.mem[0x2137:0x2400]
        r.enable_saucer_demo(starting_lives=self.front.starting_lives,
                             bonus_life=self.front.bonus_life)
        # $0B5D/$01E4 copies the original 16-bit player wait ($0080).
        # The Stage-3 diagnostic's immediate-player=True shortcut is useful
        # for movement tests, but must NOT leak into the attract demo.
        r.mem[0x2010] = 0x00
        r.mem[0x2011] = 0x80
        # Cold-start reference (MAME Shift+F3): $0B4A retains the lives
        # HUD established by initialization/RemoveShip. Never blank it
        # unconditionally: MAME shows the DIP lives and reserve ships on
        # the first and following attract demonstration cycles.
        r.lives.life_decrement = 0  # demo doesn't consume real player credits
        r.mem[0x20EF] = 0
        r.mem[0x1F74:0x1F80] = bytes.fromhex('01 01 00 00 01 00 02 01 00 02 01 00')
        # $18D9 initially seeds $20ED/$20EE from ROM $1BED/$1BEE.
        # Crucially, $0B5D->CopyRAMMirror at subsequent demo starts
        # rewrites only $2000-$20BF. The demo pointer at $20ED/$20EE
        # therefore keeps its last $1652 value from the previous run.
        # Do NOT put it back to $1F74 every time: that forced identical
        # demo gameplay on every attract cycle.
        r.mem[0x20ED:0x20EF] = saved_demo_pointer
        r.mem[0x20C1] = 1
        r.mem[0x20CF] = 8  # $18DF attract reload threshold
        # SECOND-DEMO MISSILE PHASE DIAGNOSTIC (not an established ROM port):
        # The original $1B32 mirror byte is $02. Stage17w's second demo
        # currently advances the rolling task in a different phase from
        # observed MAME firing: Python first fires squiggly at 3180 whereas
        # MAME selects rolling at ~3179. Seeding $2032=$00 at the fresh-Rack
        # handoff reproduces rolling at Python 3180 without editing handlers,
        # screen/shot scheduler, or the first demo. Investigate the *cause*
        # (exact ROM second-demo object dispatch phase) before making default.
        if (staged and getattr(self, 'demo_existing_ships', False)
                and getattr(self.front, 'experimental_second_demo_phase', False)):
            r.mem[0x2032] = 0
        if not getattr(self.front, 'experimental_rom_ram_lifecycle', False):
            # Legacy Stage17w fixture; retain its established behaviour.
            r.mem[0x201D] = 0
        # ROM $01E4 copies $1B1D -> $201D (01), and does not clear it
        # afterward on the repeated-demo path. Keep this actual mirror byte
        # when testing the ROM RAM lifecycle, rather than forcing zero.
        r.mem[0x20F1] = 0
        if staged:
            # The game's state was prepared on a fresh Rack, but the original
            # video RAM was NOT reset: retain the progressive $09D6 wipe and
            # its persistent score/credit margins. The new Rack initializer
            # draws shields/HUD for other modes; replace only its video bytes
            # with the actual preceding framebuffer before plotting ships.
            r.mem[0x2400:0x4000] = previous.mem[0x2400:0x4000]
            if not getattr(self, 'demo_existing_ships', False):
                r.lives.draw_reserve_ships()  # $0B54-$0B5A only on zero ship count
        else:
            # Legacy direct-start API for deterministic gameplay diagnostics.
            # Its outputs and all existing unit-test fixtures remain intact.
            for col in range(224):
                for row in range(2,28):
                    r.mem[0x2400+col*32+row] = 0
            r.shields.transfer_shields(1)
            r.shields.draw_bottom_line()
        # $0B4A preserves the credit footer on original hardware.  This
        # translation rebuilds the Rack (and thus framebuffer) for each demo,
        # so restore the persistent CREDIT label and two BCD digits explicitly.
        # Preserve the initialized reserve ships and count glyph as well.
        if not staged:
            self.front._write('CREDIT', 0x3501)
            self.front._draw_credit_number()
            self.phase = 'demo_play'
        self.demo_frames = 0
        self._demo_tail_pending = False
        self.demo_command_trace = []
        self.front.events.append(('ATTRACT_DEMO_STARTED', '0B4A'))

    def _issue_demo_command(self):
        """$1618/$1652: main-loop command issue when previous shot is idle.

        This is a state-driven check, NOT a one-second clock. The real
        $0B71 loop runs continuously between the two interrupt handlers.
        It can therefore observe a $2025 clear before the next video frame.
        Returns True only when a new command/shot is issued.
        """
        m = self.front.rack.mem
        if (m[0x2015] != 0xFF or m[0x2010] or m[0x2011]
                or m[0x2025]):
            return False
        m[0x2025] = 1
        ptr = (m[0x20ED] + 1) & 0xFF
        if ptr >= 0x7E:
            ptr = 0x74
        m[0x20ED] = ptr
        m[0x201D] = m[0x1F00 + ptr]
        # Diagnostic only; does not influence original RAM or drawing.
        self.demo_command_trace.append(
            (self.demo_frames, 0x1F00 + ptr, m[0x201D]))
        return True

    def _demo_tick_phase_probe(self):
        """EXPERIMENT: service late shot continuation before current DrawAlien.

        Stage17r missile dispatcher remains unchanged: two original calls
        in same MID/END phases. The previous END shot continuation reaches
        current frame before DrawAlien. The main loop can then consume the
        shot result and issue the new command before player movement.
        """
        r=self.front.rack;m=r.mem
        self.demo_frames+=1
        if m[0x2015]!=0xFF:
            m[0x2025]=0
            self.phase='demo_death_wait'
            return
        player_timer_before=(m[0x2010]<<8)|m[0x2011]
        issued=self._issue_demo_command()
        m[0x2072]=0
        if m[0x20E9]:
            r.objects.run(0x2020)
            if getattr(self.front,'demo_video_phase','pre')=='mid':
                self._video_mid_screen=r.portrait_luma()
            if m[0x2002] and m[0x2025]==2:
                r.combat.player_shot_hit()
            r.cursor_next_alien()
        m[0x2072]=0x80
        m[0x20C0]=(m[0x20C0]-1)&255
        if m[0x20E9]:
            # Previous END IRQ's player-shot handler can finish early
            # in current frame, while new END handler will redraw aliens.
            before=m[0x2025]
            r.objects.run(0x2020,stop=0x2030)
            r.combat.player_shot_hit()
            if before!=0 and m[0x2025]==0 and not issued:
                issued=self._issue_demo_command()
                if issued and m[0x2025]==1:
                    m[0x2072]=0
                    r.objects.run(0x2020,stop=0x2030)
                    m[0x2072]=0x80
            m[0x2080]=m[0x2032]
            r.draw_alien()
            r.objects.run(0x2010,stop=0x2020)
            r.objects.run(0x2030)
            r.saucer.time_to_saucer()
        r.combat.player_shot_hit()
        r.rack_bump()
        m[0x2082]=r.alive
        if not issued and m[0x2015]==0xFF:
            newly=self._issue_demo_command()
            if (newly and player_timer_before==1
                    and not (m[0x2020] or m[0x2021] or m[0x2022])
                    and m[0x2025]==1):
                previous=m[0x2072]
                m[0x2072]=0
                r.combat.player_shot(0x2020)
                m[0x2072]=previous
        r.frames+=1

    def _demo_death_wait_interrupts(self):
        # $0B7F-$0B86 blocks only the attract MAIN loop, not the
        # hardware interrupts. $20C1 bit 0 keeps SplashDemo active:
        #   MID $009E->$00A5:  non-player objects, then alien cursor
        #   END $0ABB->$0072:  shot sync, DrawAlien, all game objects,
        #                       TimeToSaucer (no TimeFleetSound).
        # This is also how *existing* alien missiles can continue their
        # natural motion and expiration after the demo ship is struck.
        # New fire and invader movement are controlled by the original
        # $2069/$2068 death flags, not by a Python-wide pause.
        if (getattr(self.front, 'experimental_death_handoff', False)
                and getattr(self, '_death_main_loop_return_pending', False)):
            self._death_main_loop_return_pending = False
            self.phase = 'credit_initial_delay'
            self.ticks = 65 if getattr(self.front, 'experimental_continuation', False) else 64
            self.front.rack.mem[0x20C1] = 0
            self.front.events.append(('ATTRACT_CREDIT_INFO', '0B89'))
            return
        r = self.front.rack
        m = r.mem
        r._presentation_luma_override = None  # release last demo snapshot
        prior_rolling_phase = m[0x2032]
        if (getattr(self.front, 'experimental_continuation', False)
                and getattr(self, '_demo_tail_pending', False)):
            # Finish the END-screen task-list work that survived the
            # final live-demo frame. IRQs continue after $0B7F.
            m[0x2072] = 0x80
            if (getattr(self.front, 'experimental_death_handoff', False)
                    and getattr(self.front, 'experimental_isr_player_order', False)
                    and getattr(self, 'demo_existing_ships', False)):
                m[0x2080] = prior_rolling_phase
            if m[0x20E9] and (m[0x20C1] & 1):
                r.objects.run(0x2020)
                r.saucer.time_to_saucer()
            self._demo_tail_pending = False
        if m[0x20E9]:
            m[0x2072] = 0x00
            if m[0x20C1] & 1:
                r.objects.run(0x2020)          # $00A5 / $024B
                r.cursor_next_alien()          # $00AB / $0141
        m[0x2072] = 0x80
        m[0x20C0] = (m[0x20C0] - 1) & 0xFF
        if m[0x20E9] and (m[0x20C1] & 1):
            m[0x2080] = (prior_rolling_phase if getattr(self.front, 'experimental_death_handoff', False) and getattr(self.front, 'experimental_isr_player_order', False) and getattr(self, 'demo_existing_ships', False) else m[0x2032])             # $0072 / $0075
            r.draw_alien()                     # $0078 / $0100
            if getattr(self.front, 'experimental_continuation', False):
                r.objects.run(0x2010, stop=0x2020)
                self._demo_tail_pending = True
            else:
                r.objects.run(0x2010)          # $007B / $0248
                r.saucer.time_to_saucer()      # $007E / $0913
        r.frames += 1
        if m[0x2015] == 0xFF:
            if getattr(self.front, 'experimental_death_handoff', False):
                # $0B83 main loop observes completion after the END ISR.
                self._death_main_loop_return_pending = True
            else:
                # Exact Stage 17y default baseline behaviour.
                self.phase = 'credit_initial_delay'
                self.ticks = (65 if getattr(self.front, 'experimental_continuation', False) else 64)
                m[0x20C1] = 0
                self.front.events.append(('ATTRACT_CREDIT_INFO', '0B89'))
    def _demo_tick_continuation(self):
        """Stage 17w opt-in source-order $0B71/$00A5/$007B continuation.

        The END-screen ($007B) dispatcher starts at player object $2010
        around scanline 250. The remaining objects $2020..$2060 continue
        into the next displayed frame, BEFORE the next MID IRQ at y=96.
        Keep the actual ROM object timer and handler functions unchanged.
        Do not issue an extra object-list pass at either IRQ boundary.

        Main loop $0B71/$14D8 may act between interrupted object dispatches;
        in particular it observes the shot completion after MID and before
        the following END player-movement call. When $2010's initial timer
        JUST reaches zero at END, however, the CPU doesn't issue a demo
        command until it regains control early in the next frame. This
        boundary is derived from MAME's frame-759/760 ROM trace.
        """
        r = self.front.rack
        m = r.mem
        self.demo_frames += 1
        if m[0x2015] != 0xFF:
            # Main loop $0B80 cleared the player shot; it does not
            # suspend the interrupt object dispatcher at $0B83.
            m[0x2025] = 0
            self.phase = 'demo_death_wait'
            if getattr(self.front, 'experimental_death_handoff', False):
                self._demo_death_wait_interrupts()
            return
        player_timer_before = (m[0x2010] << 8) | m[0x2011]
        # Record the rolling-task phase at the beginning of this displayed
        # frame. The MAME $0072 sync read belongs to the previous END IRQ;
        # after an already-initialized demo branch this is the old phase,
        # not the value mutated by today's resumed tail and MID pass.
        prior_rolling_phase = m[0x2032]

        # ORDER TRIAL: model the END-player object at the beginning of
        # the observation interval instead of its end (existing-ships only).
        reordered = (getattr(self.front, 'experimental_isr_player_order', False)
                     and getattr(self.front, 'experimental_rom_ram_lifecycle', False)
                     and getattr(self, 'demo_existing_ships', False))
        if reordered and m[0x20E9]:
            m[0x2072] = 0x80
            r.objects.run(0x2010, stop=0x2020)

        # Resume only the unfinished END-screen object-list continuation.
        if self._demo_tail_pending:
            m[0x2072] = 0x80
            if reordered:
                # The END ISR's $0072/$0075 shotSync write belongs to
                # the continuation entering this frame, before the remaining
                # $2020..$2060 objects are serviced.  Previously it was
                # visible only after MID, one object pass too late.
                m[0x2080] = prior_rolling_phase
            if m[0x20E9]:
                r.objects.run(0x2020)
                r.saucer.time_to_saucer()
            self._demo_tail_pending = False

        # Run the waiting main-loop operations after the prior END tail.
        r.combat.player_shot_hit()
        r.rack_bump()
        m[0x2082] = r.alive
        issued = self._issue_demo_command()
        if (getattr(self.front, 'experimental_death_handoff', False)
                and m[0x2015] != 0xFF):
            # $0B79/$0B80 clears player shot at the main-loop return,
            # before the MID IRQ. Alien missiles remain active.
            m[0x2025] = 0

        # IRQ MID: original non-player object list and alien cursor.
        m[0x2072] = 0
        if m[0x20E9]:
            r.objects.run(0x2020)
            if getattr(self.front, 'demo_video_phase', 'pre') == 'mid':
                self._video_mid_screen = r.portrait_luma()
            if m[0x2002] and m[0x2025] == 2:
                r.combat.player_shot_hit()
            r.cursor_next_alien()
            if not issued and m[0x2015] == 0xFF:
                issued = self._issue_demo_command()

        # IRQ END: sync first, invader draw, then the PLAYER object only.
        # In the original, the CPU resumes $2020 after the frame boundary.
        m[0x2072] = 0x80
        m[0x20C0] = (m[0x20C0] - 1) & 0xFF
        if m[0x20E9]:
            if (getattr(self.front, 'experimental_rom_ram_lifecycle', False)
                    and getattr(self, 'demo_existing_ships', False)):
                m[0x2080] = prior_rolling_phase
            else:
                m[0x2080] = m[0x2032]
            r.draw_alien()
            if not reordered:
                r.objects.run(0x2010, stop=0x2020)
            self._demo_tail_pending = True

        # A shot can finish after END. Allow only one command per tick.
        # If $2010's timer just crossed 1 -> 0, wait for the next
        # main-loop opportunity before command issue ($0B71 -> $1652).
        if not issued and player_timer_before != 1 and m[0x2015] == 0xFF:
            self._issue_demo_command()
        r.frames += 1

    def _demo_tick(self):
        if getattr(self.front, "experimental_continuation", False):
            return self._demo_tick_continuation()
        if getattr(self.front, "experimental_ordered_shot", False):
            return self._demo_tick_phase_probe()
        """$0B71 demo loop interleaved with mid/end IRQ object scheduling.

        Stage 17a fixes a phase-ordering discrepancy: a shot can complete
        during an interrupt, and the continuous original main loop can issue
        the next demo command in that SAME displayed frame (MAME frame 960).
        The Stage 16e implementation only checked before either interrupt,
        adding up to one frame of latency. We service that same-frame window
        after the object/shot state transitions; at most one issue per tick.
        This is still phase-level translation, not 8080 cycle emulation.
        """
        r = self.front.rack
        m = r.mem
        self.demo_frames += 1
        # Original 16-bit countdown is checked before the ISR pair.  Keep
        # the pre-decrement value so a newly eligible *first* shot can use
        # the measured terminal-count interrupt phase.
        player_timer_before = (m[0x2010] << 8) | m[0x2011]
        if m[0x2015] != 0xFF:
            # $0B7F: stop new player shots, wait for death animation.
            m[0x2025] = 0
            self.phase = 'demo_death_wait'
            return
        issued = self._issue_demo_command()
        # $009E/$00A5 mid-screen objects, followed by $0057/$006F
        # end-screen object service. Original sprite, shield and missile
        # collision algorithms from Stage 16e are deliberately unchanged.
        m[0x2072] = 0
        if m[0x20E9]:
            r.objects.run(0x2020)
            # Experimental video-observation tap only. The original mid-screen
            # object handler has now returned, but CursorNextAlien and the
            # end-screen ISR have not run. Do not edit game RAM or scheduling.
            if getattr(self.front, 'demo_video_phase', 'pre') == 'mid':
                self._video_mid_screen = r.portrait_luma()
            # $0B71's main loop runs independently of the two interrupts.
            # Give the translated $14D8 shot-status handler an opportunity
            # after the mid-screen object pass, before the end-screen draw.
            # This is an experimental *scheduling point*, not an invader
            # movement override or a frame-number exception. Do not consume
            # the flag for explosion states: $14D8 only services a flying shot.
            # LIMITATION: MAME's true explosion pause around frame 944 has
            # not yet been reproduced exactly by this phase-level model.
            if m[0x2002] and m[0x2025] == 2:
                r.combat.player_shot_hit()
            r.cursor_next_alien()
        m[0x2072] = 0x80
        m[0x20C0] = (m[0x20C0] - 1) & 255
        if m[0x20E9]:
            m[0x2080] = m[0x2032]
            r.draw_alien()
            r.objects.run(0x2010)
            r.saucer.time_to_saucer()
        r.combat.player_shot_hit()
        r.rack_bump()
        m[0x2082] = r.alive
        # Attract $0B71-$0B7C does not call the normal gameplay routines
        # $170E (AShotReloadRate) or $08D8 (SpeedShots). The splash loop
        # set $20CF = $08; repeatedly running the score-based reload code
        # replaced that with $30 and prevented overlapping alien missiles.
        # Gameplay still calls these routines in InterruptScheduler.
        # Main CPU isn't synchronized to the 60 Hz screen. On the original
        # hardware it can loop $0B71 again immediately after the IRQ/shot
        # cleanup. Do not delay until the next displayed frame, but also do
        # not fabricate two new demo commands within one synthetic tick.
        if not issued and m[0x2015] == 0xFF:
            newly_issued = self._issue_demo_command()
            # On the terminal tick of the original $0080 player countdown,
            # MAME writes $2025=$01 at $1657 then $02 at $03FC *within the
            # same emulated frame* (frame 760).  Our synthetic MID/END pair
            # has already run when the player timer becomes zero, so the
            # shot handler would otherwise wait one extra frame.  Service
            # ONLY that newly eligible shot's original handler, not the
            # entire object scheduler or the other alien-shot objects.
            # Later shots (e.g. MAME frame 820 -> $02 in frame 821) still
            # use the normal IRQ object schedule without acceleration.
            shot_ready = not (m[0x2020] or m[0x2021] or m[0x2022])
            if (newly_issued and player_timer_before == 1
                    and shot_ready and m[0x2025] == 1):
                previous_beam_phase = m[0x2072]
                try:
                    m[0x2072] = 0x00  # shot's initial screen-half gate
                    r.combat.player_shot(0x2020)
                finally:
                    m[0x2072] = previous_beam_phase
        r.frames += 1

    def step(self):
        self.opening_frame += 1
        if self.phase == 'opening_delay':
            if self.cold_start and self.opening_frame == 9:
                self._draw_initial_status()
            elif self.cold_start and self.opening_frame == 10:
                self._draw_initial_credit()
            self.ticks -= 1
            if self.ticks <= 0:
                self._checkpoint(0x0BEB)
                self._message(ROM_PLAY if not self.splash_animate else ROM_PLAY_NORMAL, 0x3017)
                self._printing_tick()  # first PLAY glyph in entry frame
        elif self.phase == 'printing':
            self._printing_tick()
        elif self.phase == 'title_wait':
            self.ticks -= 1
            if self.ticks <= 0:
                self._draw_table()
        elif self.phase == 'table_label_print':
            self._table_label_tick()
        elif self.phase == 'table_last_glyph_delay':
            if self.label_glyph_ticks:
                self.label_glyph_ticks -= 1
            else:
                self._checkpoint(0x0B14)
                self.phase = 'table_final_hold'
                # Shift the cold-start text to its observed MAME frames,
                # but retain the independently verified 618 setup entry.
                self.ticks = 126 if self.cold_start else 128
        elif self.phase == 'table_final_hold':
            self.ticks -= 1
            if self.ticks <= 0:
                self._continue_after_table()
        elif self.phase == 'demo_setup':
            self.ticks -= 1
            self._demo_setup_tick()
        elif self.phase == 'y_animation':
            self._animate_tick()
        elif self.phase == 'y_one_sec_wait':
            self.ticks -= 1
            if self.ticks == 0:
                self._start_animation(2)
        elif self.phase == 'y_final_wait':
            self.ticks -= 1
            if self.ticks == 0:
                # $0B3F clears final sprite before two-second pause.
                m = self.front.rack.mem
                for i in range(10):
                    m[0x33B7+i*32] = 0
                self.phase = 'before_demo_wait'
                self.ticks = 128
        elif self.phase == 'before_demo_wait':
            # Original $001D decrements $20C0 on EVERY end-screen IRQ,
            # including the $0B47 TwoSecDelay before re-entering demo.
            # Stage17w's abstract delay omitted these 128 hardware writes.
            if getattr(self.front, 'experimental_rom_ram_lifecycle', False):
                m = self.front.rack.mem
                m[0x20C0] = (m[0x20C0] - 1) & 0xFF
            self.ticks -= 1
            if self.ticks == 0:
                self._begin_demo_setup()
        elif self.phase == 'demo_play':
            if getattr(self, 'demo_visual_finish_pending', False):
                self._finish_demo_visual_setup()
            # Native 8080 beam-phase observation: MAME video frame 634
            # shows Python's internal frame-633 alien, and the same +1
            # presentation offset persists through first shot frame 760.
            # Capture PRE-update video for presentation, but still perform
            # the actual frame's complete RAM/interrupt/shot logic normally.
            # Never skip or reorder any game-object execution to match video.
            r = self.front.rack
            r._presentation_luma_override = None
            previous_scanout = r.portrait_luma()
            self._video_mid_screen = None
            self._demo_tick()
            # Presentation-only sampling experiment. The ROM-derived game
            # state and sequence of calls are IDENTICAL in every option.
            # 'pre' remains the Stage 17n reference; 'mid' reads live pixels
            # after the mid-screen objects; 'end' reads the completed frame.
            video_phase = getattr(self.front, 'demo_video_phase', 'pre')
            if video_phase == 'mid':
                r._presentation_luma_override = (
                    self._video_mid_screen if self._video_mid_screen is not None
                    else previous_scanout)
            elif video_phase == 'end':
                r._presentation_luma_override = None
            else:
                r._presentation_luma_override = previous_scanout
        elif self.phase == 'demo_death_wait':
            self._demo_death_wait_interrupts()

        elif self.phase == 'credit_initial_delay':
            self.ticks -= 1
            if self.ticks <= 0:
                # ROM $0B90->$1988 jumps to the SAME $09D6 clear used
                # before the demo.  Never clear all 5824 bytes at once.
                self._begin_credit_clear()
        elif self.phase == 'credit_clear':
            self._advance_credit_clear()
        elif self.phase == 'credit_print':
            # ROM $0B93/$08F3 prints the 12 glyphs continuously; the
            # original delayed character routine is used only afterward.
            self._draw_credit_header_characters(6)
        elif self.phase == 'credit_descriptor_print':
            self._credit_descriptor_tick()
        elif self.phase == 'credit_last_glyph_delay':
            if self.credit_glyph_ticks:
                self.credit_glyph_ticks -= 1
            else:
                self.phase = 'credit_hold'
                self.ticks = 128  # $0BC3: original TwoSecDelay
        elif self.phase == 'credit_hold':
            self.ticks -= 1
            if self.ticks <= 0:
                if not self.splash_animate:
                    # $0BCE-$0BD7 C/alien-shot animation before $0BDA.
                    self._start_animation(3)
                else:
                    self._begin_restart_clear()  # $0BE2 -> $09D6
        elif self.phase == 'credit_c_shot':
            self._credit_shot_tick()
        elif self.phase == 'credit_c_postshot_delay':
            self.ticks -= 1
            if self.ticks <= 0:
                self._begin_restart_clear()  # $0BE2 -> $09D6
        elif self.phase == 'attract_restart_clear':
            self._advance_restart_clear()

    # Original $1BC0 (16 bytes). $189E copies this to the shared $2050
    # squiggly-shot object before enabling the special splash task.
    C_SHOT_DESCRIPTOR = bytes.fromhex(
        '00 10 00 0E 05 00 00 00 00 00 07 D0 1C C8 9B 03'
    )

    def _start_c_shot(self):
        """$189E-$18B5: initiate the ROM squiggly shot against the extra C."""
        r = self.front.rack
        m = r.mem
        if r.combat is None:
            from combat import Combat
            r.combat = Combat(r)
        if r.enemy_shots is None:
            # Earlier credit-screen unit tests jump directly here without
            # running the demo setup that normally initializes shot graphics.
            from enemy_shots import EnemyShots, SHOT_IMAGES
            m[0x1CD0:0x1CFA] = SHOT_IMAGES
            r.enemy_shots = EnemyShots(r)
        m[0x2050:0x2060] = self.C_SHOT_DESCRIPTOR
        m[0x2080] = 2
        m[0x207E] = 0xFF # original signed delta, -1 pixel per movement
        m[0x20C1] = 4
        self.phase = 'credit_c_shot'
        self.c_shot_collided = False
        self.front.events.append(('ATTRACT_C_SHOT_START', '189E'))

    def _credit_shot_tick(self):
        """The special $050E/$0563 path; reuse existing shifted-ROM collision.

        This calls the same enemy missile sprite/erase/blow-up logic, with the
        splash-specific initial status path from $056F/$05B7. Frame cadence
        is provisional pending a normal-speed reference capture.
        """
        r = self.front.rack
        m = r.mem
        # The original object scheduler uses an initial 16-bit timer of $0010.
        if m[0x2050] or m[0x2051]:
            counter = ((m[0x2050] << 8) | m[0x2051]) - 1
            m[0x2050] = (counter >> 8) & 255
            m[0x2051] = counter & 255
            return
        m[0x2072] = 0x80  # shot's horizontal coordinate is in END beam half
        # The game-object task has its own +2 extra-timer, initially zero.
        r.enemy_shots.handle_splash_c()
        if m[0x2055] & 1:
            self.c_shot_collided = True
        if self.c_shot_collided and not (m[0x2055] & 1):
            # $18C8: only AFTER the missile blowup is complete replace the C
            # with a blank ROM glyph. It is deliberately NOT erased early.
            r.score_display.draw_char(0x26, 0x3311)
            m[0x20C1] = 0
            self.phase = 'credit_c_postshot_delay'
            self.ticks = 128  # $18D1 -> $0AB6 TwoSecDelay
            self.front.events.append(('ATTRACT_C_SHOT_DONE', '18C8'))

    # Original $1F9C-$1FA8: byte pairs (screen HL, message DE).
    # Do NOT replace these with visually chosen coordinates.  The source ROM
    # positions are also the regression reference for MAME comparison.
    CREDIT_DESCRIPTORS = bytes.fromhex(
        '0D 2A 50 1F  0A 2A 62 1F  07 2A E1 1F  FF'
    )
    CREDIT_MESSAGES = {
        0x1F50: bytes.fromhex(
            '24 1B 26 0E 11 26 1C 26 0F 0B 00 18 04 11 12 25 26 26'),
        0x1F62: bytes.fromhex(
            '28 1B 26 0F 0B 00 18 04 11 26 26 1B 26 02 0E 08 0D 26'),
        0x1FE1: bytes.fromhex(
            '28 1C 26 0F 0B 00 18 04 11 12 26 1C 26 02 0E 08 0D 12'),
    }

    def _credit_descriptors(self):
        """$0BA6-$0BC0: ROM-positioned, delayed credit instructions.

        The header at $0B9B uses ordinary PrintMessage. These three lower
        instruction lines instead pass through $184C -> $0A93 PrintMessageDel,
        with seven interrupt delays between successive ROM characters.
        Leave the exact descriptor addresses and glyph bytes untouched.
        """
        if not self.splash_animate:
            self.front.rack.score_display.draw_char(2, 0x3311)
        data = self.CREDIT_DESCRIPTORS
        self.credit_lines = []
        for offset in range(0, len(data), 4):
            if data[offset] == 0xFF:
                break
            if offset and getattr(self.front, 'hide_coin_info', False):
                break
            address = data[offset] | (data[offset+1] << 8)
            ptr = data[offset+2] | (data[offset+3] << 8)
            self.credit_lines.append((address, self.CREDIT_MESSAGES[ptr]))
        self.credit_line_index = 0
        self.credit_glyph_index = 0
        self.credit_address = self.credit_lines[0][0]
        self.credit_glyph_ticks = 0
        self.phase = 'credit_descriptor_print'

    def _credit_descriptor_tick(self):
        """$184C/$0A93: one ROM glyph every six end-screen interrupts."""
        if self.credit_glyph_ticks:
            self.credit_glyph_ticks -= 1
            return
        _, message = self.credit_lines[self.credit_line_index]
        self.credit_address = self.front.rack.score_display.draw_char(
            message[self.credit_glyph_index], self.credit_address)
        self.credit_glyph_index += 1
        # ROM $0A93 loads 7 and leaves the wait at 1: six ISR periods
        # between characters (not seven).
        self.credit_glyph_ticks = 5
        if self.credit_glyph_index == len(message):
            self.credit_line_index += 1
            self.credit_glyph_index = 0
            if self.credit_line_index == len(self.credit_lines):
                self.phase = 'credit_last_glyph_delay'
            else:
                self.credit_address = self.credit_lines[self.credit_line_index][0]

    def _next_attract_pass(self):
        """$0BDA-$0BE5 toggles the splash animation bit and loops."""
        m = self.front.rack.mem
        m[0x20EC] = (m[0x20EC] + 1) & 1
        self.front.events.append(('ATTRACT_LOOP', m[0x20EC]))
        self.__init__(self.front, cold_start=False)
