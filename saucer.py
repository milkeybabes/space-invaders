"""Stage 10: ROM $0682-$075F and $0913 saucer path, using original RAM fields.
The demo main-loop/ISR scheduling is still a per-frame approximation, not cycle-exact.
"""
SAUCER_TABLE = bytes.fromhex('10 05 05 10 15 10 10 05 30 10 10 10 05 15 10 05')
SAUCER_SPRITE = bytes.fromhex('00 00 00 00 04 0C 1E 37 3E 7C 74 7E 7E 74 7C 3E 37 1E 0C 04 00 00 00 00')
SAUCER_EXPLOSION = bytes.fromhex('00 22 00 A5 40 08 98 3D B6 3C 36 1D 10 48 62 B6 1D 98 08 42 90 08 00 00')
SCORE_LABELS = {0x05: (0x1F,0x1A), 0x10:(0x1B,0x1A,0x1A), 0x15:(0x1B,0x1F,0x1A), 0x30:(0x1D,0x1A,0x1A)}

class Saucer:
    def __init__(self,rack):
        self.rack = rack
        self.events=[]
        self.awarded=[]
        m=rack.mem
        m[0x1D54:0x1D64]=SAUCER_TABLE
        m[0x1D64:0x1D7C]=SAUCER_SPRITE
        m[0x1D7C:0x1D94]=SAUCER_EXPLOSION
        # $1B83-$1B8C 10-byte original ROM structure.
        self.reset()
        m[0x2091]=0x00
        m[0x2092]=0x06

    def emit(self,name,*args):
        self.events.append((self.rack.frames+1,name,*args))

    def reset(self):
        self.rack.mem[0x2083:0x208D]=bytes.fromhex('00 00 00 20 64 1D D0 29 18 02')

    def time_to_saucer(self):
        """$0913: only ticks after the rack drops from its initial $78."""
        m=self.rack.mem
        if m[0x2009]>=0x78:
            return
        timer=m[0x2091]|m[0x2092]<<8
        if timer==0:
            timer=0x0600
            m[0x2083]=1
            self.emit('SAUCER_DUE')
        timer=(timer-1)&0xffff
        m[0x2091]=timer&255
        m[0x2092]=timer>>8

    def draw(self):
        m=self.rack.mem
        sprite=m[0x2087]|m[0x2088]<<8
        self.rack.draw_simple_sprite(m[0x2089],m[0x208A],sprite, m[0x208B])

    def clear(self):
        m=self.rack.mem
        start,_=self.rack.pixel_to_address(m[0x2089],m[0x208A])
        for col in range(24):
            addr=start+32*col
            if 0x2400<=addr<0x4000:m[addr]=0

    def handler(self,base):
        """$0682 GameObj4 saucer branch; defer squiggly handling when inactive."""
        m=self.rack.mem
        if base!=0x2050: raise ValueError(base)
        if m[0x2080]!=2 or not m[0x2083] or m[0x2056]:
            return self.rack.enemy_shots.handler('squiggly',base)
        if not m[0x2084]:
            if m[0x2082]<8:
                return self.rack.enemy_shots.handler('squiggly',base)
            m[0x2084]=1
            self.draw()
            self.emit('SAUCER_APPEARED',m[0x208A])
        if (m[0x208A]&0x80)!=m[0x2072]:return 'SAUCER_WRONG_BEAM'
        if m[0x2085]:
            m[0x2086]=(m[0x2086]-1)&255
            n=m[0x2086]
            if n==0x1F:
                m[0x2087:0x2089]=bytes((0x7C,0x1D))
                self.draw()
                self.emit('SAUCER_EXPLOSION')
            elif n==0x18:
                score=m[m[0x208D] | (m[0x208E]<<8)]
                m[0x20F1]=1
                m[0x20F2]=(score<<4)&255
                m[0x20F3]=(score>>4)&255
                points=((score>>4)*10+(score&15))*10
                self.awarded.append(points)
                self.emit('SAUCER_SCORE',points)
                self.clear()
                # $08F1 prints the ROM's three digit point label at saucer location.
                pos,_=self.rack.pixel_to_address(m[0x2089],m[0x208A])
                for digit in SCORE_LABELS[score]:
                    pos=self.rack.score_display.draw_char(digit,pos)
            elif n==0:
                self.clear()
                self.reset()
                self.emit('SAUCER_FINISHED')
            return 'SAUCER_HIT_SEQUENCE'
        self.clear()
        m[0x208A]=(m[0x208A]+m[0x208C])&255
        if m[0x208A]<0x28 or m[0x208A]>=0xE1:
            self.reset()
            self.emit('SAUCER_LEFT')
            return 'SAUCER_LEFT'
        self.draw()
        return 'SAUCER_MOVE'
