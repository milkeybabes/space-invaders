"""Space Invaders 1978 - source port, Stage 7: player death, respawn, lives.

Run with `python main.py --scale 3` after installing pygame-ce. Headless
validation needs only the Python standard library.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import struct
import time
from interrupts import InterruptScheduler
import zlib

from rack import Rack, SCREEN_WIDTH, SCREEN_HEIGHT


def save_native_png(path: Path, rack: Rack) -> None:
    """Save exact native 1-bit-derived portrait pixels as a grayscale PNG."""
    pixels = rack.portrait_luma()
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + name + data + struct.pack(
            '>I', zlib.crc32(name + data) & 0xFFFFFFFF
        )
    scanlines = b''.join(
        b'\x00' + pixels[row * SCREEN_WIDTH:(row + 1) * SCREEN_WIDTH]
        for row in range(SCREEN_HEIGHT)
    )
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', SCREEN_WIDTH, SCREEN_HEIGHT,
                                         8, 0, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(scanlines, 9))
           + chunk(b'IEND', b''))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def load_input_script(path: Path) -> dict[int, tuple[bool, bool, bool]]:
    """Deterministic external player controls: no new gameplay logic.

    CSV headers: frame,left,right,fire ; 1-based frame, 0/1 controls.
    Unspecified frames mean all controls released.
    """
    result: dict[int, tuple[bool, bool, bool]] = {}
    with path.open(newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            frame = int(row['frame'])
            if frame < 1 or frame in result:
                raise ValueError(f'duplicate or invalid input frame: {frame}')
            vals = tuple(row[key].strip() for key in ('left', 'right', 'fire'))
            if not all(v in ('0', '1') for v in vals):
                raise ValueError(f'control bits must be 0 or 1 (frame {frame})')
            result[frame] = tuple(v == '1' for v in vals)
    return result


def run_headless(rack: Rack, frames: int, snapshot: Path | None,
                 trace: Path | None, interrupt_trace: Path | None = None,
                 object_trace: Path | None = None,
                 combat_trace: Path | None = None,
                 input_script: dict[int, tuple[bool, bool, bool]] | None = None,
                 enemy_trace: Path | None = None,
                 lives_trace: Path | None = None) -> None:
    writer = None
    f = None
    isr_file = None
    object_file = None
    if object_trace:
        object_trace.parent.mkdir(parents=True, exist_ok=True)
        object_file = object_trace.open('w', newline='', encoding='utf-8')
        fields = ('frame', 'phase', 'object_base', 'handler', 'timer_hi', 'timer_lo', 'timer_extra', 'operation', 'player_x_201B')
        obj_writer = csv.DictWriter(object_file, fieldnames=fields)
        obj_writer.writeheader()
        rack.objects.trace_hook = obj_writer.writerow
    if interrupt_trace:
        interrupt_trace.parent.mkdir(parents=True, exist_ok=True)
        isr_file = interrupt_trace.open('w', newline='', encoding='utf-8')
        fieldnames = ('frame', 'phase', 'rom_address', 'operation', 'status',
                      'vblank_2072', 'wait_2000', 'cursor_2006',
                      'isr_delay_20C0', 'shot_sync_2080', 'rack_steps')
        isr_writer = csv.DictWriter(isr_file, fieldnames=fieldnames)
        isr_writer.writeheader()
        rack.scheduler.trace_hook = isr_writer.writerow
    try:
        if trace:
            trace.parent.mkdir(parents=True, exist_ok=True)
            f = trace.open('w', newline='', encoding='utf-8')
            writer = csv.writer(f)
            writer.writerow(['frame', 'cursor_index', 'reference_x', 'reference_y',
                             'animation', 'direction', 'alien_count', 'rack_steps',
                             'framebuffer_sha256'])
        for n in range(1, frames + 1):
            if rack.objects_enabled and input_script is not None:
                left, right, fire = input_script.get(n, (False, False, False))
                rack.set_controls(left=left, right=right, fire=fire)
            rack.step_frame()
            if writer:
                x, y = rack.reference
                writer.writerow([rack.frames, rack.current, x, y, rack.frame_number,
                                 'left' if rack.mem[0x200D] else 'right', rack.alive,
                                 rack.rack_steps, rack.framebuffer_digest()])
        if snapshot:
            save_native_png(snapshot, rack)
        print(f'frames={rack.frames}  alive={rack.alive}  cursor={rack.current}  '
              f'ref={rack.reference}  rack_steps={rack.rack_steps}\n'
              f'vram_sha256={rack.framebuffer_digest()}')
        if snapshot:
            print(f'saved {snapshot}')
        if trace:
            print(f'saved {trace}')
        if interrupt_trace:
            print(f'saved {interrupt_trace}')
        if object_trace:
            print(f'saved {object_trace}')
        if combat_trace and rack.combat_enabled:
            combat_trace.parent.mkdir(parents=True, exist_ok=True)
            with combat_trace.open('w', newline='', encoding='utf-8') as ef:
                event_writer = csv.writer(ef)
                event_writer.writerow(['frame', 'event', 'value'])
                event_writer.writerows(rack.combat.events)
            print(f'saved {combat_trace}')
        if rack.objects_enabled:
            print(f'player_x_201B={rack.mem[0x201B]:02X}, player_draws={rack.objects.player_draws}, ' 
                  f'object_handler_calls={rack.objects.calls}')
        if rack.combat_enabled:
            print(f'score={rack.combat.score:04d}, shots_fired={rack.combat.shots_fired}, '
                  f'aliens_hit={rack.combat.hits}, shot_status={rack.mem[0x2025]}')
        if rack.lives_enabled:
            print(f'ships_in_reserve={rack.lives.stash} deaths={rack.lives.deaths} '
                  f'respawns={rack.lives.respawns} game_over={rack.lives.game_over}')
        if rack.lives_enabled and lives_trace:
            lives_trace.parent.mkdir(parents=True, exist_ok=True)
            with lives_trace.open('w', newline='', encoding='utf-8') as ef:
                lw = csv.writer(ef)
                lw.writerow(['frame', 'event', 'value'])
                lw.writerows(rack.lives.events)
            print(f'saved {lives_trace}')
        if rack.enemy_shots_enabled:
            print(f'enemy_shots={rack.enemy_shots.counts} '
                  f'player_hit_at={rack.enemy_shots.player_hit_frame}')
            if enemy_trace:
                enemy_trace.parent.mkdir(parents=True, exist_ok=True)
                with enemy_trace.open('w', newline='', encoding='utf-8') as ef:
                    ew = csv.writer(ef)
                    ew.writerow(['frame', 'operation', 'shot_type', 'value'])
                    ew.writerows(rack.enemy_shots.events)
                print(f'saved {enemy_trace}')
    finally:
        if f:
            f.close()
        if isr_file:
            isr_file.close()
        if object_file:
            object_file.close()


def enable_native_windows_pixels() -> None:
    """Avoid Windows display-DPI bitmap scaling of the Pygame window.

    The source framebuffer and Pygame integer scale are already pixel exact.
    On a 200%-scaled Windows desktop, a DPI-unaware Python process can get
    silently magnified again by the OS. Opt in before importing/starting SDL.
    This is presentation-only: game logic, frame timing and AVI are unchanged.
    """
    import sys
    if sys.platform != 'win32':
        return

    import ctypes
    try:
        # Windows 10+: per-monitor awareness, including dynamic DPI changes.
        user32 = ctypes.WinDLL('user32')
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = (ctypes.c_void_p,)
        set_context.restype = ctypes.c_bool
        if set_context(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass

    try:
        # Windows 8.1 fallback: per-monitor DPI awareness.
        shcore = ctypes.WinDLL('shcore')
        set_awareness = shcore.SetProcessDpiAwareness
        set_awareness.argtypes = (ctypes.c_int,)
        set_awareness.restype = ctypes.c_long
        if set_awareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass

    try:
        # Vista+ fallback: system-DPI awareness is still better than unaware.
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def run_window(rack: Rack, scale: int, debug: bool, front=None,
               record_avi: str | None = None, overlay: str = "none",
               artwork: str = "none") -> None:
    enable_native_windows_pixels()  # Must happen before SDL/Pygame initializes.
    try:
        import pygame
    except ImportError as exc:
        raise SystemExit('Pygame is needed only for the window. '
                         'Install it with: python -m pip install pygame-ce') from exc

    from native_avi import NativeAVIRecorder, MAME_AVI_RATE, next_recording_path

    pygame.init()
    from cabinet_artwork import choose_window, load_artwork, draw as draw_cabinet
    artwork_mode = artwork
    artwork_background = artwork_bezel = None
    cabinet_pixel_scale = 3
    def set_display(mode: str, integer_scale: int):
        nonlocal cabinet_pixel_scale
        # Movable title-bar window; not RESIZABLE and not NOFRAME.
        # Pick a fixed preset that fits the current desktop, with space for
        # Windows chrome. The native 224x256 game ALWAYS uses integer pixels.
        if mode in ('backdrop', 'cabinet'):
            desktop = pygame.display.get_desktop_sizes()[0]
            win_w, win_h, cabinet_pixel_scale = choose_window(*desktop)
            print(f'Cabinet window: {win_w}x{win_h}, game: {cabinet_pixel_scale}x integer pixels')
            return pygame.display.set_mode((win_w, win_h))
        return pygame.display.set_mode((SCREEN_WIDTH * integer_scale, SCREEN_HEIGHT * integer_scale))

    screen = set_display(artwork_mode, scale)
    # Decorative OS mouse cursor only: no game state or framebuffer changes.
    from invader_cursor import install_invader_cursor
    install_invader_cursor(pygame)
    base_caption = 'Space Invaders 1978 - Arcade' if front is not None else 'Space Invaders 1978 - diagnostic'
    pygame.display.set_caption(base_caption)
    from sound_ports import SoundPortBus
    from sound_driver import RomSoundDriver
    from wav_audio import WavBackend
    bus = SoundPortBus()
    wav_backend = bus.add_backend(WavBackend(pygame, Path(__file__).with_name('sounds')))
    audio = RomSoundDriver(bus)
    from pause_control import PauseControl
    from screen_capture import ScreenCaptures
    from ram_snapshot import RamSnapshots
    captures = ScreenCaptures(Path(__file__).with_name('captures'))
    ram_snapshots = RamSnapshots(Path(__file__).with_name('captures'))
    simulation_tick = 0  # monotonic in this window, even when the Rack resets
    pause = PauseControl()
    clock = pygame.time.Clock()
    frame_duration = 1 / 60
    accumulated = 0.0
    last = time.perf_counter()
    running = True
    rgb_lut = (b'\x00\x00\x00', b'\xff\xff\xff')
    from classic_overlay import tint_luma
    overlay_enabled = overlay == 'classic'
    def ensure_artwork():
        nonlocal artwork_background, artwork_bezel
        if artwork_background is None:
            artwork_background, artwork_bezel = load_artwork(pygame)

    if artwork_mode in ('backdrop', 'cabinet'):
        ensure_artwork()
    recorder = None
    recording_folder = Path(__file__).with_name('recordings')

    def capture_avi_frame() -> None:
        """Record the current emulated frame, never the scaled desktop window."""
        nonlocal recorder
        if recorder is None:
            return
        active = front.rack if front is not None else rack
        mode = front.mode if front is not None else 'diagnostic'
        intro = getattr(front, 'attract_intro', None) if front is not None else None
        phase = intro.phase if intro is not None else mode
        try:
            recorder.write_frame(active.portrait_luma(), simulation_tick,
                                 active.frames, mode, phase, active)
        except (OSError, OverflowError, ValueError) as exc:
            print(f'AVI recording stopped after write error: {exc}')
            stop_recording()

    def start_recording(path: Path | None = None) -> None:
        nonlocal recorder
        if recorder is not None:
            return
        try:
            path = path if path is not None else next_recording_path(recording_folder)
            # Match the original MAME AVI's rational display timebase for
            # native one-to-one video comparisons.  The Python simulation
            # stays at 60 Hz; timestamps/recording playback change only.
            recording_rate = MAME_AVI_RATE if front is not None else 60
            recorder = NativeAVIRecorder(path, SCREEN_WIDTH, SCREEN_HEIGHT,
                                         fps=recording_rate)
            print(f'AVI recording STARTED: {recorder.path}')
            print(f'Frame index: {recorder.csv_path} ({recorder.fps:.3f} fps, silent, native pixels)')
            capture_avi_frame()  # Include the state at start, frame 0 for --record-avi.
        except (OSError, ValueError) as exc:
            recorder = None
            print(f'AVI recording could not start: {exc}')

    def stop_recording() -> None:
        nonlocal recorder
        if recorder is None:
            return
        previous = recorder
        recorder = None
        try:
            previous.close()
            print(f'AVI saved: {previous.path} ({previous.frames} frames)')
            print(f'Frame CSV saved: {previous.csv_path}')
        except OSError as exc:
            print(f'AVI finalize error: {exc}')

    if record_avi is not None:
        start_recording(None if record_avi == 'auto' else Path(record_avi))

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F8 and not getattr(event, 'repeat', False):
                        if recorder is None:
                            start_recording()
                        else:
                            stop_recording()
                            pygame.display.set_caption(base_caption
                                + (' [PAUSED - F5 to resume]' if pause.paused else ''))
                        continue
                    # F9 toggles sound; Shift+F9 preserves the RAM snapshot.
                    # F10 changes presentation only; it does not touch game state.
                    if event.key == pygame.K_F11 and not getattr(event, 'repeat', False):
                        # Presentation-only cycle. The game and its clock continue unchanged.
                        sequence = (('none', False), ('none', True),
                                    ('backdrop', True), ('cabinet', True))
                        current = (artwork_mode, overlay_enabled)
                        index = sequence.index(current) if current in sequence else -1
                        artwork_mode, overlay_enabled = sequence[(index + 1) % len(sequence)]
                        if artwork_mode in ('backdrop', 'cabinet'):
                            ensure_artwork()
                        screen = set_display(artwork_mode, scale)
                        pygame.display.set_caption(base_caption)
                        print(f'Presentation mode: {artwork_mode}; colour strip: {overlay_enabled}')
                        continue
                    if event.key == pygame.K_F10 and not getattr(event, 'repeat', False):
                        overlay_enabled = not overlay_enabled
                        print('Classic colour overlay: ' + ('ON' if overlay_enabled else 'OFF'))
                        continue
                    if event.key == pygame.K_F9 and not getattr(event, 'repeat', False):
                        if not (event.mod & pygame.KMOD_SHIFT):
                            wav_backend.set_muted(not wav_backend.muted)
                            print('Sound: ' + ('OFF (muted)' if wav_backend.muted else 'ON'))
                            continue
                        current = front.rack if front is not None else rack
                        phase = (front.attract_intro.phase if front is not None
                                 and front.mode == 'attract' else 'not_attract')
                        mode = front.mode if front is not None else 'diagnostic'
                        try:
                            saved = ram_snapshots.capture(current, simulation_tick,
                                                           phase=phase, mode=mode)
                            print(f'Shift+F9 RAM snapshot: {saved}')
                        except OSError as exc:
                            print(f'Shift+F9 snapshot failed: {exc}')
                        continue
                    if event.key == pygame.K_F12 and not getattr(event, 'repeat', False):
                        # Capture live VRAM directly, not scaled window pixels; allow
                        # this even when F5 has frozen the game and audio.
                        capture_rack = front.rack if front is not None else rack
                        try:
                            saved = captures.capture(capture_rack, simulation_tick)
                            print(f'F12 screenshot: {saved}')
                            pygame.display.set_caption(base_caption +
                                ((' [PAUSED - F5 to resume]' if pause.paused else '')) +
                                f' [saved {saved.name}]')
                        except OSError as exc:
                            print(f'F12 screenshot failed: {exc}')
                        continue
                    if event.key == pygame.K_F5 and not getattr(event, 'repeat', False):
                        paused = pause.toggle()
                        # Stop an in-progress UFO loop and other channel audio;
                        # resume it from the same position when unpaused.
                        if pygame.mixer.get_init():
                            (pygame.mixer.pause if paused else pygame.mixer.unpause)()
                        pygame.display.set_caption(base_caption + (' [PAUSED - F5 to resume]' if paused else ''))
                        accumulated = 0.0  # never catch up time spent paused
                        last = time.perf_counter()
                        continue
                    # While paused, freeze operator/game input as well as simulation.
                    # Escape and keyboard integer scaling continue to work below.
                    if pause.paused and event.key not in (pygame.K_ESCAPE, pygame.K_F9, pygame.K_F10, pygame.K_F11, pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_MINUS, pygame.K_KP_MINUS):
                        continue
                    if front is not None and not getattr(event, 'repeat', False):
                        if event.key == pygame.K_F3:
                            front.machine_reset()
                        elif event.key == pygame.K_5:
                            front.insert_coin()
                        elif event.key in (pygame.K_1, pygame.K_2):
                            front.start(1 if event.key == pygame.K_1 else 2)
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                        scale = min(6, scale + 1)
                        if artwork_mode == 'none':
                            screen = set_display(artwork_mode, scale)
                    elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                        scale = max(1, scale - 1)
                        if artwork_mode == 'none':
                            screen = set_display(artwork_mode, scale)
            now = time.perf_counter()
            accumulated = pause.advance_time(accumulated, now - last, frame_duration)
            last = now
            while not pause.paused and accumulated >= frame_duration:
                if front is not None:
                    rack = front.rack
                if rack.objects_enabled and (front is None or front.mode == 'playing'):
                    keys = pygame.key.get_pressed()
                    rack.set_controls(
                        left=keys[pygame.K_LEFT] or keys[pygame.K_a],
                        right=keys[pygame.K_RIGHT] or keys[pygame.K_d],
                        fire=keys[pygame.K_SPACE] or keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL],
                    )
                if front is not None:
                    front.step_frame()
                    rack = front.rack
                else:
                    rack.step_frame()
                audio.step(rack, playing=(front is None or front.mode == 'playing'))
                simulation_tick += 1
                capture_avi_frame()  # Every simulation tick, even if display skipped it.
                accumulated -= frame_duration
            luma = rack.portrait_luma()
            rgb = tint_luma(luma) if overlay_enabled else b''.join(rgb_lut[bool(pixel)] for pixel in luma)
            # RGB bytes create a 24-bit Surface, while the display is typically
            # 32-bit. pygame-ce requires the source and supplied destination
            # of transform.scale() to have identical pixel formats.
            native = pygame.image.frombytes(
                rgb, (SCREEN_WIDTH, SCREEN_HEIGHT), 'RGB'
            ).convert(screen)
            if artwork_mode in ('backdrop', 'cabinet'):
                draw_cabinet(pygame, screen, native, artwork_background,
                             artwork_bezel if artwork_mode == 'cabinet' else None,
                             game_scale=cabinet_pixel_scale)
            elif scale == 1:
                screen.blit(native, (0, 0))
            else:
                pygame.transform.scale(native, screen.get_size(), screen)
            if not pause.paused and front is None and (debug or rack.combat_enabled) and rack.frames % 20 == 0:
                pygame.display.set_caption(
                    f'STAGE 7 (diagnostic only) | frame {rack.frames} | '
                    f'alien {rack.current:02d} | {rack.alive} alive | '
                    f'animation {rack.frame_number} | ref {rack.reference}'
                     + (f' | Player X {rack.mem[0x201B]:02X}' if rack.objects_enabled else '')
                    + (f' | SCORE {rack.combat.score:04d} | SHOT {rack.mem[0x2025]}' if rack.combat_enabled else '')
                    + (f' | SHIPS {rack.lives.stash} reserve + active | DEATHS {rack.lives.deaths}' if rack.lives_enabled else '')
                )
            if not pause.paused and front is None and rack.lives_enabled and rack.lives.game_over:
                pygame.display.set_caption('Stage 8 - GAME OVER / ' + rack.lives.game_over_sequence.phase + ' (attract splash pending)')
            elif not pause.paused and front is None and rack.enemy_shots_enabled and rack.enemy_demo_halted:
                pygame.display.set_caption(
                    f'Stage 6 — PLAYER HIT on frame {rack.enemy_shots.player_hit_frame}; '
                    'death animation still unported (diagnostic paused)')
            # Recording indicator belongs in the OS caption, not the VRAM/AVI.
            if recorder is not None:
                pygame.display.set_caption(base_caption + ' [AVI REC]'
                                           + (' [PAUSED - F5 to resume]' if pause.paused else ''))
            pygame.display.flip()
            clock.tick(120)
    finally:
        stop_recording()
        audio.stop()
        bus.close()
        pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-avi', nargs='?', const='auto', default=None,
                        metavar='FILE.avi',
                        help='record lossless native AVI from startup with MAME matching timestamps (or press F8 in-game)')
    parser.add_argument('--artwork', choices=('none', 'backdrop', 'cabinet'), default='none',
                        help='optional 1080p moon backdrop or full Bezel Project cabinet; F11 cycles')
    parser.add_argument('--overlay', choices=('none', 'classic'), default='none',
                        help='presentation-only original red/green colour-strip overlay; F10 toggles')
    parser.add_argument('--scale', type=int, choices=range(1, 7), metavar='1..6',
                        default=3, help='integer pixel scale (default: 3)')
    parser.add_argument('--aliens', type=int, choices=range(1, 56), metavar='1..55',
                        default=55, help='diagnostic: initialise with N surviving aliens (not a game rule)')
    parser.add_argument('--last-alien-index', type=int, choices=range(55), metavar='0..54',
                        default=None, help='diagnostic with --aliens 1: choose original grid slot, 0=bottom-left, 44=top-left')
    parser.add_argument('--frames', type=int, metavar='N',
                        help='run N frames headlessly and exit')
    parser.add_argument('--snapshot', type=Path, metavar='FILE.png',
                        help='write native-resolution PNG (requires --frames)')
    parser.add_argument('--trace', type=Path, metavar='FILE.csv',
                        help='write per-frame RAM and framebuffer trace (requires --frames)')
    parser.add_argument('--interrupt-trace', type=Path, metavar='FILE.csv',
                        help='write source-address ISR/main-loop events (requires --frames)')
    parser.add_argument('--debug', action='store_true', help='no reserve ship lost upon death (Stage 13 in --arcade mode)')
    parser.add_argument('--attract-preview', action='store_true', help='Original zero-credit attract presentation and repeating demonstration')
    parser.add_argument('--experimental-ordered-shot', action='store_true', help='Stage 17u superseded ordered-shot diagnostic')
    parser.add_argument('--experimental-continuation', action='store_true', help='Stage 17w opt-in ROM dispatcher continuation scheduling')
    parser.add_argument('--experimental-second-demo-phase', action='store_true',
                        help='DIAGNOSTIC ONLY: vary second-demo rolling-object phase, not a verified ROM correction')
    parser.add_argument('--experimental-rom-ram-lifecycle', action='store_true',
                        help='DIAGNOSTIC: preserve ROM-untouched RAM and $20C0 ISR countdown between demos')
    parser.add_argument('--experimental-isr-player-order', action='store_true',
                        help='DIAGNOSTIC: move repeated-demo END player-object phase before MID')
    parser.add_argument('--experimental-death-handoff', action='store_true',
                        help='Stage 17z: preserve original ISR object-list continuation during demo death')
    parser.add_argument('--video-phase', choices=('pre', 'mid', 'end'), default='pre',
                        help='Stage 17o diagnostic: sample demo image before ISR pair, after mid-screen objects, or after end-screen (default: pre; game logic unchanged)')
    parser.add_argument('--arcade', action='store_true', help='Arcade mode with credits, attract sequence and two-player switching')
    parser.add_argument('--player-demo', action='store_true',
                        help='opt in to original object-table + normal player movement (diagnostic only)')
    parser.add_argument('--saucer', action='store_true', help='Stage 10 flying saucer and initial alien-fire delay diagnostic')
    parser.add_argument('--waves', action='store_true', help='Stage 11: new rack after clearing last alien (single-player diagnostic)')
    parser.add_argument('--no-barriers', action='store_true', help='DIAGNOSTIC ONLY: remove shields; keep original bottom line, shot/explosion rules and saucer')
    parser.add_argument('--lives', action='store_true',
                        help='Stage 7: original death sprites, reserve ships, respawn and last-life stop')
    parser.add_argument('--bonus-life', '-bonus', type=int, choices=(1000, 1500), default=1000,
                        help='DIP setting: one extra ship at 1000 or 1500 points (default 1000)')
    parser.add_argument('--starting-lives', '-lives', type=int, choices=range(3, 7), default=3,
                        metavar='3..6', help='original DIP switch: 3 through 6 ships (default 3)')
    parser.add_argument('--shields', action='store_true',
                        help='Stage 6: original ROM shields + ground line + Stage 5 combat diagnostics')
    parser.add_argument('--enemy-shots', action='store_true',
                        help='Stage 5: original three enemy-shot handlers; pause at player hit')
    parser.add_argument('--combat-demo', action='store_true',
                        help='Stage-4: player shot, original pixel collisions, BCD scoring; no enemy fire yet')
    parser.add_argument('--rom-player-delay', action='store_true',
                        help='with --player-demo, keep original $0080 object-start delay')
    parser.add_argument('--object-trace', type=Path, metavar='FILE.csv',
                        help='per-dispatch object timer/status events (requires --player-demo and --frames)')
    parser.add_argument('--lives-trace', type=Path, metavar='FILE.csv',
                        help='Stage 7 death/explosion/ship event trace (requires --lives and --frames)')
    parser.add_argument('--enemy-trace', type=Path, metavar='FILE.csv',
                        help='Stage 5 alien-shot event trace (requires --enemy-shots and --frames)')
    parser.add_argument('--combat-trace', type=Path, metavar='FILE.csv',
                        help='Shot/hit/score events (requires a combat mode and --frames)')
    parser.add_argument('--input-script', type=Path, metavar='FILE.csv',
                        help='frame,left,right,fire controls CSV for deterministic tests (requires --player-demo and --frames)')
    args = parser.parse_args()
    if (args.snapshot or args.trace or args.interrupt_trace or args.object_trace or args.combat_trace or args.enemy_trace or args.lives_trace or args.input_script) and args.frames is None:
        parser.error('--snapshot, --trace, --interrupt-trace, --object-trace, --combat-trace, --input-script require --frames N')
    if args.record_avi is not None and args.frames is not None:
        parser.error('--record-avi is for the interactive window (omit --frames)')
    if args.frames is not None and args.frames < 0:
        parser.error('--frames must be >= 0')
    if args.lives_trace and not args.lives:
        parser.error('--lives-trace requires --lives')
    if args.enemy_trace and not (args.enemy_shots or args.shields or args.lives or args.saucer or args.waves):
        parser.error('--enemy-trace requires --enemy-shots or --shields')
    if args.combat_trace and not (args.combat_demo or args.enemy_shots or args.shields or args.lives or args.saucer or args.waves):
        parser.error('--combat-trace requires --combat-demo')
    if args.starting_lives != 3 and not (args.arcade or args.lives or args.saucer or args.waves):
        parser.error("--starting-lives requires --lives")
    if args.rom_player_delay and args.combat_demo:
        parser.error('--rom-player-delay is only available for --player-demo')
    if args.last_alien_index is not None and args.aliens != 1:
        parser.error('--last-alien-index is only valid with --aliens 1')
    if (args.object_trace or args.input_script or args.rom_player_delay) and not (args.player_demo or args.combat_demo or args.enemy_shots or args.shields or args.lives or args.saucer or args.waves):
        parser.error('--object-trace, --input-script, --rom-player-delay require --player-demo or --combat-demo')
    if args.no_barriers and not (args.saucer or args.lives or args.shields):
        parser.error('--no-barriers requires --saucer, --lives or --shields')
    if args.arcade:
        if args.frames is not None:
            parser.error('--arcade currently requires an interactive window')
        from arcade_frontend import ArcadeFrontEnd
        front = ArcadeFrontEnd(starting_lives=args.starting_lives,
                              bonus_life=args.bonus_life, debug=args.debug,
                              attract_preview=args.attract_preview,
                              experimental_ordered_shot=args.experimental_ordered_shot,
                              experimental_continuation=args.experimental_continuation,
                              experimental_second_demo_phase=args.experimental_second_demo_phase,
                              experimental_rom_ram_lifecycle=args.experimental_rom_ram_lifecycle,
                              experimental_isr_player_order=args.experimental_isr_player_order,
                              experimental_death_handoff=args.experimental_death_handoff)
        front.demo_video_phase = args.video_phase
        run_window(front.rack, args.scale, args.debug, front=front, record_avi=args.record_avi, overlay=args.overlay, artwork=args.artwork)
        return
    rack = Rack(args.aliens)
    if args.waves:
        rack.enable_waves_demo(starting_lives=args.starting_lives, bonus_life=args.bonus_life)
    elif args.saucer:
        rack.enable_saucer_demo(starting_lives=args.starting_lives, bonus_life=args.bonus_life)
    elif args.lives:
        rack.enable_lives_demo(starting_lives=args.starting_lives, bonus_life=args.bonus_life)
    elif args.shields:
        rack.enable_shields_demo()
    elif args.enemy_shots:
        rack.enable_enemy_shots_demo()
    elif args.combat_demo:
        rack.enable_combat_demo()
    elif args.player_demo:
        rack.enable_game_objects(immediate_player=not args.rom_player_delay)
    if args.debug and rack.lives_enabled:
        rack.lives.life_decrement = 0
    if args.no_barriers:
        rack.shields.remove_barriers_for_diagnostic()
    if args.last_alien_index is not None:
        # Test setup only: this preserves the original flag/index mapping.
        # No change to any translated movement, sprite or VRAM logic.
        rack.mem[0x2100:0x2137] = bytes(55)
        rack.mem[0x2100 + args.last_alien_index] = 1
    if args.frames is not None:
        run_headless(rack, args.frames, args.snapshot, args.trace, args.interrupt_trace,
                     args.object_trace, args.combat_trace,
                     load_input_script(args.input_script) if args.input_script else None,
                     args.enemy_trace, args.lives_trace)
    else:
        run_window(rack, args.scale, args.debug, record_avi=args.record_avi, overlay=args.overlay, artwork=args.artwork)


if __name__ == '__main__':
    main()
