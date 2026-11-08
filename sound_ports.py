"""Space Invaders 1978 output-port bus. Standard library only.

Raw 8080 OUT writes are authoritative. Every write is forwarded, including
identical consecutive values; named edges are convenience events for clients.
"""
from dataclasses import dataclass

SOUND_BITS = {
    0x03: ('UFO_FLYING', 'PLAYER_SHOT', 'PLAYER_EXPLOSION',
           'INVADER_EXPLOSION', 'BONUS_SHIP', 'AMPLIFIER_ENABLE',
           'UNCONNECTED_3_6', 'UNCONNECTED_3_7'),
    0x05: ('FLEET_STEP_1', 'FLEET_STEP_2', 'FLEET_STEP_3',
           'FLEET_STEP_4', 'UFO_EXPLOSION', 'COCKTAIL_FLIP',
           'UNCONNECTED_5_6', 'UNCONNECTED_5_7'),
}

@dataclass(frozen=True)
class PortWrite:
    frame: int
    port: int
    value: int
    previous: int
    source: str = ''

@dataclass(frozen=True)
class SoundEvent:
    frame: int
    port: int
    bit: int
    name: str
    active: bool
    edge: str
    source: str = ''

class SoundPortBus:
    def __init__(self):
        self.values = {3: 0, 5: 0}
        self.backends = []

    def add_backend(self, backend):
        self.backends.append(backend)
        return backend

    def write(self, port, value, *, frame=0, source=''):
        if port not in SOUND_BITS:
            raise ValueError('Only original sound/control OUT ports $03 and $05 are supported')
        if not 0 <= value <= 255:
            raise ValueError('OUT value must be an unsigned byte')
        old = self.values[port]
        self.values[port] = value
        raw = PortWrite(frame, port, value, old, source)
        for backend in tuple(self.backends):
            callback = getattr(backend, 'on_write', None)
            if callback is not None:
                callback(raw)
        changed = old ^ value
        for bit, name in enumerate(SOUND_BITS[port]):
            if changed & (1 << bit):
                active = bool(value & (1 << bit))
                evt = SoundEvent(frame, port, bit, name, active,
                                 'rising' if active else 'falling', source)
                for backend in tuple(self.backends):
                    callback = getattr(backend, 'on_event', None)
                    if callback is not None:
                        callback(evt)
        return raw

    def reset(self, *, frame=0, source='RESET'):
        for port in (3, 5):
            self.write(port, 0, frame=frame, source=source)

    def close(self):
        for backend in tuple(self.backends):
            callback = getattr(backend, 'close', None)
            if callback is not None:
                callback()
