"""Presentation-only 1080p artwork compositor. Never accesses or alters game RAM.

Art supplied by the user: backdrop_moon_midway.png and Bezel - The Bezel Project.png.
The bezel's native transparent screen opening is used as supplied.
"""
from pathlib import Path

ART_W, ART_H = 1920, 1080
# 16:9 fixed window presets: (width, height, *native game pixel scale*).
# Pixel scaling is always 1x / 2x / 3x (no fractional game pixels).
# The cabinet art alone may be resized for the window.
WINDOW_PRESETS = (
    (1920, 1080, 3),  # higher-resolution desktops
    (1728,  972, 3),  # standard 1080p desktop; room for title/task bar
    (1536,  864, 2),
    (1280,  720, 2),
    (1152,  648, 2),
    ( 960,  540, 1),
    ( 768,  432, 1),
)


def choose_window(desktop_width: int, desktop_height: int):
    # Reserve space for the Windows title bar and taskbar. Fixed, never
    # resizable; the user can still drag the window by its title bar.
    max_width = max(0, desktop_width - 24)
    max_height = max(0, desktop_height - 90)
    for width, height, game_scale in WINDOW_PRESETS:
        if width <= max_width and height <= max_height:
            return width, height, game_scale
    return WINDOW_PRESETS[-1]


def load_artwork(pygame):
    base = Path(__file__).with_name('artwork')
    backdrop = pygame.image.load(str(base / 'moon_backdrop.png')).convert_alpha()
    bezel = pygame.image.load(str(base / 'cabinet_bezel.png')).convert_alpha()
    if bezel.get_size() != (ART_W, ART_H):
        raise ValueError('Cabinet bezel artwork must be 1920x1080')
    # MAME's backdrop dimensions/position from default.lay (Cab Artwork view).
    background = pygame.Surface((ART_W, ART_H)).convert()
    background.fill((0, 0, 0))
    background.blit(backdrop, (191, 115))
    return background, bezel


def draw(pygame, destination, native_rgb, background, bezel=None, game_scale=3):
    """Scale the 224x256 native RGB surface by a whole number, no filtering.

    Black game pixels are transparent in artwork modes to reveal the original
    moon backdrop, just as the physical 1978 backdrop appeared behind the CRT.
    """
    window_size = destination.get_size()
    # Decorative artwork is allowed to resize; the original game is not.
    if window_size == (ART_W, ART_H):
        background_scaled = background
        bezel_scaled = bezel
    else:
        background_scaled = pygame.transform.smoothscale(background, window_size)
        bezel_scaled = (pygame.transform.smoothscale(bezel, window_size)
                        if bezel is not None else None)
    destination.blit(background_scaled, (0, 0))
    native_rgb.set_colorkey((0, 0, 0))
    game_w, game_h = 224 * game_scale, 256 * game_scale
    scaled = pygame.transform.scale(native_rgb, (game_w, game_h))
    scaled.set_colorkey((0, 0, 0))
    destination.blit(scaled, ((window_size[0] - game_w) // 2,
                              (window_size[1] - game_h) // 2))
    if bezel_scaled is not None:
        destination.blit(bezel_scaled, (0, 0))
