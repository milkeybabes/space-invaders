"""CSV listener: optionally trace actual OUT writes and named bit transitions."""
import csv

class CsvSoundLogger:
    def __init__(self, path):
        self.file = open(path, 'w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file)
        self.writer.writerow(('frame','record','port','value','previous','bit','name','edge','source'))

    def on_write(self, w):
        self.writer.writerow((w.frame,'WRITE',f'{w.port:02X}',f'{w.value:02X}',
                              f'{w.previous:02X}','','','',''+w.source))

    def on_event(self, e):
        self.writer.writerow((e.frame,'EDGE',f'{e.port:02X}','','',e.bit,
                              e.name,e.edge,e.source))

    def close(self):
        self.file.close()
