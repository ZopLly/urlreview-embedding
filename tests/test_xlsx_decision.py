"""Точечный протокол сохранения проверяем независимо через полное чтение книги."""
import copy
from io import BytesIO
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from zipfile import ZipFile
from xlsx_fixture import book, replace_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import xlsx_io


def decision(raw, row=5, action='ERROR', label='Travel', sheet='Проверка', columns=(3, 2), changed=3):
    a, l = action.encode(), label.encode()
    request = struct.pack('<Q', len(raw)) + raw
    request += struct.pack('<6I', row, *columns, len(a), len(l), changed) + a + l
    return subprocess.run([sys.executable, str(ROOT/'scripts/xlsx_io.py'), 'decision', sheet],
                          input=request, capture_output=True)


class DecisionTests(unittest.TestCase):
    def test_unchanged_formula_label_is_preserved(self):
        raw = replace_part(book(), 'xl/worksheets/sheet1.xml', lambda data: data.replace(
            b'<c r="C5" s="1"/>', b'<c r="C5" t="str"><f t="array" ref="C5">IF(1,"","")</f><v/></c>'))
        reply = decision(raw, action='OK', label='', changed=1)
        self.assertEqual(reply.returncode, 0, reply.stdout)
        saved = reply.stdout[3:]
        self.assertEqual(xlsx_io.read_workbook(saved).rows[1][2:4], ['', 'OK'])
        with ZipFile(BytesIO(saved)) as z:
            self.assertIn(b'<f t="array" ref="C5">IF(1,"","")</f>', z.read('xl/worksheets/sheet1.xml'))

    def test_implicit_row_coordinate_matches_reader(self):
        raw = replace_part(book(), 'xl/worksheets/sheet1.xml',
                           lambda data: data.replace(b'<row r="5">', b'<row>'))
        self.assertEqual(xlsx_io.read_workbook(raw).physical_rows, [2, 5, 9])
        reply = decision(raw)
        self.assertEqual(reply.returncode, 0, reply.stdout)
        self.assertEqual(xlsx_io.read_workbook(reply.stdout[3:]).rows[1][2:4], ['Travel', 'ERROR'])

    def test_decision_matches_full_save_and_preserves_other_parts(self):
        for prefixed in (False, True):
            with self.subTest(prefixed=prefixed):
                raw = book(prefixed=prefixed)
                view = xlsx_io.read_workbook(raw)
                rows = copy.deepcopy(view.rows)
                rows[1][2:4] = ['Travel,education; <>& "_x0041_"\nрусский', 'ERROR']
                reply = decision(raw, label=rows[1][2])
                self.assertEqual(reply.returncode, 0, reply.stdout)
                self.assertTrue(reply.stdout.startswith(b'OK\n'))
                saved = reply.stdout[3:]
                self.assertEqual(xlsx_io.read_workbook(saved).rows, rows)
                self.assertEqual(xlsx_io.read_workbook(saved).physical_rows, view.physical_rows)
                with ZipFile(BytesIO(raw)) as before, ZipFile(BytesIO(saved)) as after:
                    self.assertIsNone(after.testzip())
                    for name in before.namelist():
                        if name != 'xl/worksheets/sheet1.xml':
                            self.assertEqual(before.read(name), after.read(name), name)
                # Перезапись и пустая категория также должны сохраняться после полного чтения.
                again = decision(saved, action='OK', label='')
                self.assertEqual(again.returncode, 0, again.stdout)
                rows[1][2:4] = ['', 'OK']
                self.assertEqual(xlsx_io.read_workbook(again.stdout[3:]).rows, rows)

    def test_decision_refuses_formula_group(self):
        raw = replace_part(book(), 'xl/worksheets/sheet1.xml', lambda data: data.replace(
            b'<c r="C5" s="1"/>', b'<c r="C5"><f t="array" ref="C5:D5">1</f><v>0</v></c>'))
        reply = decision(raw)
        self.assertNotEqual(reply.returncode, 0)
        self.assertIn('формул', reply.stdout.decode())

    def test_decision_refuses_missing_row_bad_action_and_bad_request(self):
        for kwargs in ({'row': 6}, {'action': 'BAD'}, {'columns': (3, 3)}, {'row': 0}):
            with self.subTest(kwargs=kwargs):
                reply = decision(book(), **kwargs)
                self.assertNotEqual(reply.returncode, 0)
                self.assertTrue(reply.stdout.startswith(b'ERR\n'))
        raw = book()
        reply = subprocess.run([sys.executable, str(ROOT/'scripts/xlsx_io.py'), 'decision', 'Проверка'],
                               input=struct.pack('<Q', len(raw))+raw+b'bad', capture_output=True)
        self.assertNotEqual(reply.returncode, 0)
        self.assertTrue(reply.stdout.startswith(b'ERR\n'))
