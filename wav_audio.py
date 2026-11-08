"""Optional Pygame WAV playback adapter; no game logic imported.

Supply unmodified sample names 0.wav..8.wav in sounds/. Missing files are
silent; the game and the independent port decoder continue to work.
"""
from pathlib import Path

SAMPLE_NAMES = {
    'UFO_FLYING': '0.wav', 'PLAYER_SHOT': '1.wav',
    'PLAYER_EXPLOSION': '2.wav', 'INVADER_EXPLOSION': '3.wav',
    'FLEET_STEP_1': '4.wav', 'FLEET_STEP_2': '5.wav',
    'FLEET_STEP_3': '6.wav', 'FLEET_STEP_4': '7.wav',
    'UFO_EXPLOSION': '8.wav',
    'BONUS_SHIP': '9.wav',  # optional extra-ship sample, not in basic nine-sample set
}

class WavBackend:
    def __init__(self, pygame, folder='sounds'):
        self.pygame = pygame
        self.folder = Path(folder)
        self.samples = {}
        self.channels = {}
        self.available = False
        self.muted = False
        self.ufo_active = False
        # Headless tests and a few display drivers supply no mixer at all.
        if not hasattr(pygame, 'mixer'):
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            self.available = True
        except (Exception,):
            return
        for name, filename in SAMPLE_NAMES.items():
            path = self.folder / filename
            if path.is_file():
                try:
                    self.samples[name] = pygame.mixer.Sound(str(path))
                except (Exception,):
                    pass
        # Reserve two channels for the UFO loop and its one-shot effects.
        pygame.mixer.set_num_channels(max(12, pygame.mixer.get_num_channels()))
        self.channels['UFO_FLYING'] = pygame.mixer.Channel(10)

    def set_muted(self, muted):
        """Silence playback only; do not alter game sound-port state/timing."""
        self.muted = bool(muted)
        if not self.available:
            return
        if self.muted:
            self.pygame.mixer.stop()  # Also cancels looping UFO and active one-shots.
        elif self.ufo_active:
            sample = self.samples.get('UFO_FLYING')
            if sample is not None:
                self.channels['UFO_FLYING'].play(sample, loops=-1)

    def on_event(self, event):
        if event.name == 'UFO_FLYING':
            self.ufo_active = bool(event.active)
        if self.muted or not self.available or event.name not in SAMPLE_NAMES:
            return
        sample = self.samples.get(event.name)
        if sample is None:
            return
        if event.name == 'UFO_FLYING':
            channel = self.channels['UFO_FLYING']
            if event.active:
                channel.play(sample, loops=-1)
            else:
                channel.stop()
        elif event.active:
            sample.play()

    def close(self):
        for channel in self.channels.values():
            channel.stop()
