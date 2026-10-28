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
    def __init__(self, args, extra_env=None, executable=None):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, 0x5414, struct.pack('HHHH',32,115,0,0))
        self.proc = subprocess.Popen([str(executable or BIN),*map(str,args)],stdin=slave,stdout=slave,stderr=slave,
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
    def test_similar_without_index_keeps_review_available(self):
        t=self.start();t.wait('one.example');t.send('p');t.wait('Индекс не подключён')
        t.send('q');t.wait('one.example');t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
        self.assertEqual([r[3] for r in self.rows()[1:]],['',''])
    def test_similar_shows_reviewed_record_and_detail(self):
        with self.input.open(newline='') as f: rows=list(csv.reader(f,delimiter=';'))
        rows[2][3]='OK'
        with self.input.open('w',newline='') as f:csv.writer(f,delimiter=';').writerows(rows)
        self.original=self.input.read_bytes()
        index=self.root/'test.uremb'
        with index.open('wb') as f:
            f.write(b'UREMB01\n'+struct.pack('<II',2,384))
            for row in rows[1:]:
                h=14695981039346656037
                for byte in (row[0]+'\0'+row[4]).encode():h=((h^byte)*1099511628211)&((1<<64)-1)
                f.write(struct.pack('<Q384f',h,1.,*([0.]*383)))
        self.term=Terminal([self.input,self.output,'--guide',self.guide,'--embeddings',index])
        t=self.term;t.wait('one.example');t.send('p');t.wait('two.example')
        t.send('\n');t.wait('Принятая разметка')
        t.send('q');t.wait('two.example');t.send('q');t.wait('one.example')
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
        self.assertEqual(self.rows()[1][3],'')
    def test_category_explanation_follows_cursor_and_full_help_remains(self):
        self.guide.write_text('shopping\tМагазины и объявления о продаже\tПродажа товаров\t\nmusic\tИсполнители, записи, тексты песен, музыкальная индустрия, выступления, фестивали и концертные программы\tМузыкальные ресурсы\t\n')
        t=self.start();t.wait('one.example');t.send('2');t.wait('Суть: Магазины')
        t.send('j');t.wait('концертные программы')
        t.send('h');t.wait('Включает:');t.send('q');t.wait('Суть:')
        t.send(b'\x1b');t.wait('one.example');t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
        self.assertEqual(self.rows()[1][3],'')
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
    def test_small_window_does_not_confirm_unseen_decision(self):
        t=self.start();t.wait('one.example');t.send('2');t.wait('Категории')
        t.resize(7,25);time.sleep(.15);t.send('\n\n');time.sleep(.15)
        self.assertEqual(self.rows()[1][3],'')
        t.resize(32,115);time.sleep(.1);t.send('q');t.wait('Несохранённое');t.send('d')
        self.assertEqual(t.proc.wait(timeout=3),0)
    def test_long_confirmation_can_scroll_to_last_selected_category(self):
        codes=[f'category_{i}_'+('x'*35) for i in range(29)]+['zz_last_marker']
        self.guide.write_text(''.join(f'{c}\tКатегория\tОписание\t\n' for c in codes))
        t=self.start();t.wait('one.example');t.resize(18,65);time.sleep(.1)
        t.send('2');t.wait('Категории')
        t.send(''.join(f'{i}\n' for i in range(1,len(codes)+1))+'\n');t.wait('Подтверждение')
        t.send('G');t.wait('zz_last_marker')
        t.send('\n');time.sleep(.15)
        self.assertEqual(self.rows()[1][2],','.join(codes))
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    def test_uncertain_sync_warns_and_waits_for_retry(self):
        self.term=Terminal([self.input,self.output,'--guide',self.guide],executable=ROOT/'build/url-review-sync')
        t=self.term;t.wait('one.example');t.send('2');t.wait('Категории')
        t.send(' \n');t.wait('Подтверждение');t.send('\n');t.wait('переход остановлен')
        self.assertEqual(self.rows()[1][3],'ERROR')
        t.send(b'\x1b');time.sleep(.1);t.send('\n');t.wait('Второй сайт')
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    def browser_environment(self):
        bindir=self.root/'bin';bindir.mkdir()
        opener=bindir/'xdg-open'
        opener.write_text('#!/bin/sh\nprintf "%s\\n" "$#" "$1" >> "$URL_REVIEW_BROWSER_LOG"\n')
        opener.chmod(0o700)
        log=self.root/'browser.log'
        return log,{'PATH':str(bindir)+os.pathsep+os.environ.get('PATH',''), 'URL_REVIEW_BROWSER_LOG':str(log)}
    def wait_browser_calls(self,log,count):
        end=time.monotonic()+4
        while time.monotonic()<end:
            lines=log.read_text().splitlines() if log.exists() else []
            if len(lines)>=count*2:return lines
            time.sleep(.03)
        self.fail('Browser request was not received')
    def test_browser_opens_only_on_key_or_domain_click(self):
        log,env=self.browser_environment()
        self.term=Terminal([self.input,self.output,'--guide',self.guide],env)
        t=self.term;t.wait('one.example');self.assertFalse(log.exists())
        t.send('o');self.assertEqual(self.wait_browser_calls(log,1),['1','https://one.example'])
        t.send(b'\x1b[<0;3;4M\x1b[<0;3;4m')
        self.assertEqual(self.wait_browser_calls(log,2),['1','https://one.example','1','https://one.example'])
        t.send(b'\x1b[<0;3;9M\x1b[<0;3;9m');time.sleep(.1)
        self.assertEqual(len(log.read_text().splitlines()),4)
        self.assertEqual(self.rows()[1][3],'')
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    def test_browser_rejects_non_http_scheme(self):
        with self.input.open('w',newline='') as f:
            csv.writer(f,delimiter=';').writerows([HEADER,['file:///tmp/fiction','shopping','','','Test']])
        self.original=self.input.read_bytes()
        log,env=self.browser_environment()
        self.term=Terminal([self.input,self.output,'--guide',self.guide],env)
        t=self.term;t.wait('file:///tmp/fiction');t.send('o');t.wait('HTTP')
        self.assertFalse(log.exists());t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    def test_browser_launch_failure_leaves_record_unchanged(self):
        self.term=Terminal([self.input,self.output,'--guide',self.guide],{'PATH':str(self.root/'missing-bin')})
        t=self.term;t.wait('one.example');t.send('o');t.wait('xdg-open')
        self.assertEqual(self.rows()[1][3],'');t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    def test_mouse_wheel_scrolls_description(self):
        with self.input.open('w',newline='') as f:
            csv.writer(f,delimiter=';').writerows([HEADER,['wheel.example','shopping','','','\n'.join([f'line-{i}' for i in range(20)]+['MOUSE-WHEEL-TAIL'])]])
        self.original=self.input.read_bytes()
        t=self.start();t.wait('wheel.example');t.send(b'\x1b[<65;3;9M');t.wait('MOUSE-WHEEL-TAIL')
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)

if __name__=='__main__':unittest.main()
