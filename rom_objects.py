"""Exact bytes from the 1978 ROM's $1B10-$1B6F RAM-init mirror.

The original $01E4 CopyRAMMirror transfers $1B00-$1BBF to $2000-$20BF.
For our opt-in Stage-3 *object diagnostic* we load only the relevant
$2010-$206F range; Stage-2's rack-only boot fixture is untouched.
See https://computerarcheology.com/Arcade/SpaceInvaders/Code.html#1B00
"""
OBJECT_MIRROR = bytes.fromhex('''
00 80 00 8E 02 FF 05 0C 60 1C 20 30 10 01 00 00
00 00 00 BB 03 00 10 90 1C 28 30 01 04 00 FF FF
00 00 02 76 04 00 00 00 00 00 04 EE 1C 00 00 03
00 00 00 B6 04 00 00 01 00 1D 04 E2 1C 00 00 03
00 00 00 82 06 00 00 01 06 1D 04 D0 1C 00 00 03
FF 00 C0 1C 00 00 10 21 01 00 30 00 12 00 00 00
''')
PLAYER_SPRITE = bytes.fromhex('00 00 0F 1F 1F 1F 1F 7F FF 7F 1F 1F 1F 1F 0F 00')
assert len(OBJECT_MIRROR) == 0x60
assert len(PLAYER_SPRITE) == 0x10
