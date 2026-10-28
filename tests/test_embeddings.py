"""Only synthetic CSV; encoder double isolates the optional neural runtime."""
import csv
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('local_embeddings',ROOT/'embeddings/local_embeddings.py')
class EmbeddingBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module=importlib.util.module_from_spec(SPEC)
        if SPEC.loader:SPEC.loader.exec_module(cls.module)
    def test_windows_keep_tail_without_duplicate_only_window(self):
        m=self.module
        self.assertEqual(list(m.chunks(list(range(9)),4,1)),[[0,1,2,3],[3,4,5,6],[6,7,8]])
        self.assertEqual(list(m.chunks([0,1,2,3],4,1)),[[0,1,2,3]])
        self.assertEqual(list(m.chunks([],4,1)),[])
        with self.assertRaises(ValueError):list(m.chunks([1],4,4))
    def test_index_bytes_and_csv_stay_intact(self):
        m=self.module
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.csv';out=Path(tmp)/'test.uremb'
            text='domain;class;label;action;description\none.example;shopping;;;Инструменты\ntwo.example;music;;OK;\n'
            source.write_bytes(text.encode('cp1251'))
            calls=[]
            def encode(text):
                calls.append(text)
                return [1.0]+[0.0]*383
            m.build_index(source,out,encode,'windows-1251',';')
            self.assertEqual(calls,['Инструменты'])
            raw=out.read_bytes()
            self.assertEqual(raw[:16],b'UREMB01\n'+struct.pack('<II',2,384))
            self.assertEqual(struct.unpack_from('<Q',raw,16)[0],0x1952e5c4f4004a9)
            self.assertEqual(struct.unpack_from('<384f',raw,24),(1.,)+(0.,)*383)
            self.assertEqual(struct.unpack_from('<384f',raw,16+1544+8),(0.,)*384)
            self.assertEqual(source.read_bytes(),text.encode('cp1251'))
    def test_python_index_is_read_by_c_and_detects_stale_description(self):
        m=self.module
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.csv';out=Path(tmp)/'test.uremb'
            source.write_text('domain;class;label;action;description\nx.example;shopping;;;товары\n')
            m.build_index(source,out,lambda _: [1.]+[0.]*383)
            def check():return subprocess.run([str(ROOT/'url-review'),'--check',str(source),'--embeddings',str(out)],capture_output=True,text=True)
            self.assertEqual(check().returncode,0)
            source.write_text('domain;class;label;action;description\nx.example;shopping;music;ERROR;товары\n')
            self.assertEqual(check().returncode,0)
            source.write_text('domain;class;label;action;description\nx.example;shopping;music;ERROR;другой текст\n')
            result=check();self.assertNotEqual(result.returncode,0);self.assertIn('устарел',result.stderr)
    def test_failures_do_not_replace_existing_index_or_source(self):
        m=self.module
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.csv';out=Path(tmp)/'test.uremb'
            text='domain;class;label;action;description\nx;shopping;;;text\n'
            source.write_text(text);out.write_bytes(b'previous')
            def fail(text):raise RuntimeError('inference failed')
            with self.assertRaises(RuntimeError):m.build_index(source,out,fail)
            self.assertEqual(out.read_bytes(),b'previous')
            self.assertEqual(source.read_text(),text)
            with self.assertRaises(ValueError):m.build_index(source,source,fail)
            with self.assertRaises(ValueError):m.build_index(source,Path(tmp)/'oops.csv',fail)
            self.assertEqual(list(Path(tmp).glob('*.tmp')),[])
    def test_invalid_headers_and_nonfinite_vectors_rejected(self):
        m=self.module
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.csv';out=Path(tmp)/'test.uremb'
            source.write_text('domain;class;label;action;description\nx;shopping;;;text\n')
            with self.assertRaises(ValueError):m.build_index(source,out,lambda _: [float('nan')]*384)
            self.assertFalse(out.exists())
            source.write_text('domain;description\nx;text\n')
            with self.assertRaises(ValueError):m.build_index(source,out,lambda _: [1.]*384)
