"""Decorative Pygame mouse cursor using the game's unmodified 1978 ROM pixels.

This is OS cursor artwork; it does not write to arcade video RAM or affect
input, timing, simulation or any original 8080 routines.
"""
from alien_data import ALIEN_IMAGES

# Original first alien frame, ROM $1C00-$1C0F: 16 columns of 8 pixels.
CURSOR_ROM = ALIEN_IMAGES[:16]


def cursor_pixel_grid():
    """Decode ROM columns as an upright top-to-bottom 16x8 cursor."""
    return tuple(
        tuple(bool(CURSOR_ROM[x] & (1 << (7 - y))) for x in range(16))
        for y in range(8)
    )


def install_invader_cursor(pygame):
    """Set a 32x32 mouse pointer; fail safely on unsupported window drivers."""
    try:
        surface = pygame.Surface((32, 32), flags=pygame.SRCALPHA, depth=32)
        grid = cursor_pixel_grid()
        for y, row in enumerate(grid):
            for x, on in enumerate(row):
                if on:
                    pygame.draw.rect(surface, (255, 255, 255, 255),
                                     (x * 2, y * 2 + 4, 2, 2))
        pygame.mouse.set_cursor(pygame.cursors.Cursor((0, 0), surface))
        return True
    except Exception:
        # A decorative feature must never stop gameplay on unsupported hosts.
        return False
