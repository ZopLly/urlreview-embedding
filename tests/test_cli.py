import csv
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'url-review'

class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def call(self,*args):
        return subprocess.run([str(BIN),*map(str,args)],capture_output=True,text=True)
    def test_check_is_read_only_and_handles_cp1251(self):
        path=self.root/'input.csv'
        text='domain;class;label;action;description\r\nx.example;shopping;;OK;"Кириллица; ёжик\r\nПродолжение"\r\n'
        path.write_bytes(text.encode('cp1251'));original=path.read_bytes()
        p=self.call('--check',path,'--encoding','windows-1251')
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn('Записей: 1',p.stdout)
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(list(self.root.iterdir()),[path])
        self.assertNotEqual(self.call('--check',path).returncode,0)
    def test_missing_or_duplicate_headers_and_bad_quoting(self):
        path=self.root/'input.csv'
        for data in ['a;b;c\n1;2;3\n',
                     'domain;class;label;action;description;domain\na;b;;;x;dup\n',
                     'domain;class;label;action;description\na;b;;;"not closed',
                     'domain;class;label;action;description\na;b;;invalid;\n']:
            with self.subTest(data=data):
                path.write_text(data);p=self.call('--check',path)
                self.assertNotEqual(p.returncode,0);self.assertTrue(p.stderr)
                self.assertEqual(path.read_text(),data)
    def test_comma_tab_extra_fields_and_long_text(self):
        for sep,option in [(',',','),('\t','tab')]:
            path=self.root/'input.csv'
            with path.open('w',newline='') as f:
                csv.writer(f,delimiter=sep).writerows([
                    ['extra','description','domain','label','action','class'],
                    ['',('Длинное описание; "привет"\n'*1000),'x.example','','','shopping']])
            p=self.call('--check',path,'--delimiter',option)
            self.assertEqual(p.returncode,0,p.stderr)
    def test_invalid_options_no_terminal_and_missing_file(self):
        self.assertEqual(self.call('--help').returncode,0)
        for args in [[],['--encoding','bad'],['--delimiter','bad'],['--check'],['--check',self.root/'missing.csv']]:
            with self.subTest(args=args):self.assertNotEqual(self.call(*args).returncode,0)
        source=self.root/'input.csv';source.write_text('domain;class;label;action;description\n')
        out=self.root/'work.csv';p=self.call(source,out)
        self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
