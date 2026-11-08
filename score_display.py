"""Stage 9: direct translation of ROM score display $191A, $1931, $09AD.
Original character sprites, BCD descriptors and VRAM addressing.
"""
from game_over import ROM_FONT

DIGITS = bytes.fromhex("""
00 3E 45 49 51 3E 00 00
00 00 21 7F 01 00 00 00
00 23 45 49 49 31 00 00
00 42 41 49 59 66 00 00
00 0C 14 24 7F 04 00 00
00 72 51 51 51 4E 00 00
00 1E 29 49 49 46 00 00
00 40 47 48 50 60 00 00
00 36 49 49 49 36 00 00
00 31 49 49 4A 3C 00 00
""")
# $1AE4-$1AFF exactly, 28 codes including <1>/<2> markers.
SCORE_HEADER = bytes.fromhex('26 12 02 0E 11 04 24 1B 25 26 07 08 3F 12 02 0E 11 04 26 12 02 0E 11 04 24 1C 25 26')

class ScoreDisplay:
    def __init__(self, rack):
        self.rack = rack
        self.initialised = False
        m = rack.mem
        m[0x1E00:0x1ED0] = ROM_FONT
        m[0x1ED0:0x1F20] = DIGITS
        m[0x1F30:0x1F38] = bytes(8)  # space
        m[0x1FF8:0x2000] = bytes.fromhex('00 08 08 08 08 08 00 00')  # hyphen $3F
        m[0x1AE4:0x1B00] = SCORE_HEADER
        m[0x1F20:0x1F30] = bytes.fromhex('00 08 14 22 41 00 00 00 00 00 41 22 14 08 00 00')
        # $1BF4-$1BFF -> $20F4-$20FF, original ROM startup descriptors.
        # Preserve existing score values if any.
        for base, address in ((0x20F4,0x2F1C),(0x20F8,0x271C),(0x20FC,0x391C)):
            m[base+2] = address & 255
            m[base+3] = address >> 8

    def draw_char(self, code, address):
        """$08FF/$1439 DrawChar: each 8-byte character advances HL by $0100."""
        m = self.rack.mem
        for i in range(8):
            dest = (address + i*32) & 0xffff
            if 0x2400 <= dest < 0x4000:
                m[dest] = m[(0x1E00 + code*8 + i) & 0x3fff]
        return (address + 0x100) & 0xffff

    def draw_header(self):
        address=0x241E
        for code in SCORE_HEADER:
            address=self.draw_char(code,address)

    def draw_score(self, base):
        m=self.rack.mem
        address=m[base+2] | m[base+3]<<8
        for byte in (m[base+1], m[base]):
            address=self.draw_char(0x1A+(byte>>4),address)
            address=self.draw_char(0x1A+(byte&15),address)

    def initialise(self):
        if self.initialised: return
        self.initialised=True
        self.draw_header()
        for base in (0x20F8,0x20FC,0x20F4):
            self.draw_score(base)

    def score_adjusted(self, base):
        if self.initialised:
            self.draw_score(base)

    def high_score_updated(self):
        if self.initialised:
            self.draw_score(0x20F4)
