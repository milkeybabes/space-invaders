"""The six original 16-byte alien graphics, from original ROM addresses 1C00-1C5F.

These are columns in the rotated arcade framebuffer, not Pygame sprites.
Source reference: https://computerarcheology.com/Arcade/SpaceInvaders/Code.html
"""
ALIEN_IMAGES = bytes.fromhex("""
00 00 39 79 7A 6E EC FA FA EC 6E 7A 79 39 00 00
00 00 00 78 1D BE 6C 3C 3C 3C 6C BE 1D 78 00 00
00 00 00 00 19 3A 6D FA FA 6D 3A 19 00 00 00 00
00 00 38 7A 7F 6D EC FA FA EC 6D 7F 7A 38 00 00
00 00 00 0E 18 BE 6D 3D 3C 3D 6D BE 18 0E 00 00
00 00 00 00 1A 3D 68 FC FC 68 3D 1A 00 00 00 00
""")
assert len(ALIEN_IMAGES) == 0x60
