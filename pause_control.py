"""Pure-Python emulation pause state for the Pygame window (F5).

Simulation and sound port writes are frozen while paused. Rendering and
window event processing continue; no arcade RAM or framebuffer is changed.
"""

class PauseControl:
    def __init__(self):
        self.paused = False

    def toggle(self):
        self.paused = not self.paused
        return self.paused

    def advance_time(self, accumulated, elapsed, frame_duration):
        """Advance game-clock accumulator, discarding time spent paused."""
        if self.paused:
            return accumulated
        return accumulated + min(elapsed, 0.25)
