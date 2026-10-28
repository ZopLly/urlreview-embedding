"""Drive the real ncurses executable through a PTY, using synthetic data only."""
import csv
import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'url-review'
HEADER = ['domain','class','label','action','description']

class Terminal:
    def __init__(self, args, extra_env=None):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, 0x5414, struct.pack('HHHH',32,115,0,0))
        self.proc = subprocess.Popen([str(BIN),*map(str,args)],stdin=slave,stdout=slave,stderr=slave,
                                     env={**os.environ,'TERM':'xterm-256color','LANG':'C.UTF-8',**(extra_env or {})})
        os.close(slave)
        self.output = b''
    def wait(self, text, timeout=6):
        target=text.encode()
        end=time.monotonic()+timeout
        while target not in self.output:
            if time.monotonic()>end:
                raise AssertionError(f'No {text!r}; exit={self.proc.poll()}; tail={self.output[-1600:]!r}')
            if select.select([self.master],[],[],.1)[0]:
                try: self.output += os.read(self.master,65536)
                except OSError: raise AssertionError(f'PTY closed: {self.output[-1200:]!r}')
        self.output=b''
    def send(self, keys):
        os.write(self.master,keys.encode() if isinstance(keys,str) else keys)
    def resize(self,h,w):
        fcntl.ioctl(self.master,0x5414,struct.pack('HHHH',h,w,0,0))
        self.proc.send_signal(signal.SIGWINCH)
    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        os.close(self.master)

class UITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.input=self.root/'input.csv';self.output=self.root/'work.csv'
        self.guide=self.root/'categories.tsv'
        self.guide.write_text('shopping\tПокупки\tПродажа товаров\t\nmusic\tМузыка\tМузыкальные ресурсы\t\nfinance\tФинансы\tБанки\t\n')
        with self.input.open('w',newline='') as f:
            csv.writer(f,delimiter=';').writerows([HEADER,
                ['one.example','shopping','','','Длинный текст; "товары"\n'+('Описание. '*1500)],
                ['two.example','music','','','Второй сайт']])
        self.original=self.input.read_bytes()
        self.term=None
    def start(self):
        self.term=Terminal([self.input,self.output,'--guide',self.guide])
        return self.term
    def rows(self):
        with self.output.open(newline='') as f:return list(csv.reader(f,delimiter=';'))
    def tearDown(self):
        if self.term:self.term.close()
        self.assertEqual(self.input.read_bytes(),self.original)
        self.tmp.cleanup()
    def test_multi_category_confirmation_and_resume(self):
        t=self.start();t.wait('one.example')
        t.send('2');t.wait('Категории')
        t.send(' j ');t.send('\n');t.wait('Подтверждение')
        self.assertEqual(self.rows()[1][3],'')
        t.send('\n');t.wait('two.example')
        self.assertEqual(self.rows()[1][2:4],['shopping,music','ERROR'])
        self.assertEqual(self.rows()[1][4],'Длинный текст; "товары"\n'+('Описание. '*1500))
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0);t.close();self.term=None
        t=self.start();t.wait('two.example');t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    def test_defer_return_back_edit_and_empty_not_desc(self):
        t=self.start();t.wait('one.example');t.send('s');t.wait('Второй сайт')
        t.send('1');t.wait('Категории');t.send('\n');t.wait('Подтверждение');t.send('\n');t.wait('Проход завершён')
        t.send('r');t.wait('one.example');t.send('3');t.wait('Категории');t.send('\n');t.wait('Подтверждение');t.send('\n');t.wait('Проход завершён')
        self.assertEqual(self.rows()[1][2:4],['','NOT_DESC'])
        t.send('b');t.wait('one.example');t.send('2');t.wait('Категории');t.send(' ');t.send('\n');t.wait('Подтверждение');t.send('\n');t.wait('Проход завершён')
        self.assertEqual(self.rows()[1][2:4],['shopping','ERROR'])
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    def test_cancel_help_resize_and_discard_exit(self):
        t=self.start();t.wait('one.example');t.send('h');t.wait('Справка');t.send(b'\x1b');t.wait('one.example')
        t.resize(7,25);time.sleep(.15);t.resize(32,115);time.sleep(.15)
        t.send('2');t.wait('Категории');t.send('h');t.wait('Включает');t.send(b'\x1b');time.sleep(.1)
        t.send(' ');t.send('q');t.wait('Несохранённое');t.send('d');self.assertEqual(t.proc.wait(timeout=3),0)
        self.assertEqual([r[3] for r in self.rows()[1:]],['',''])
    def test_ascii_locale_still_displays_russian(self):
        self.term=Terminal([self.input,self.output,'--guide',self.guide],{'LANG':'C','LC_ALL':'C'})
        self.term.wait('не проверено')
        self.term.send('q');self.assertEqual(self.term.proc.wait(timeout=3),0)

if __name__=='__main__':unittest.main()
