"""XLSX читается и меняется настоящим backend, затем проверяется независимым XML-парсером."""
import copy
from io import BytesIO
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from xml.etree import ElementTree as E
from zipfile import ZipFile

from xlsx_fixture import book, replace_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import xlsx_io


class WorkbookTests(unittest.TestCase):
    def test_save_preserves_already_compressed_unchanged_members(self):
        # Иное начальное сжатие обнаружит даже ненужную распаковку/повторную упаковку без изменения значений.
        initial=BytesIO()
        with ZipFile(BytesIO(book())) as source,ZipFile(initial,'w') as target:
            for entry in source.infolist():
                target.writestr(entry,source.read(entry),compresslevel=1)
        raw=initial.getvalue()
        rows=copy.deepcopy(xlsx_io.read_workbook(raw).rows)
        rows[1][2:4]=['Travel','ERROR']
        saved=xlsx_io.patch_workbook(raw,rows)

        def compressed(data,entry):
            # В локальном ZIP-заголовке после 26 байтов идут длины имени и extra field.
            names,extra=struct.unpack_from('<HH',data,entry.header_offset+26)
            start=entry.header_offset+30+names+extra
            return data[start:start+entry.compress_size]

        with ZipFile(BytesIO(raw)) as before,ZipFile(BytesIO(saved)) as after:
            for entry in before.infolist():
                if entry.filename!='xl/worksheets/sheet1.xml':
                    self.assertEqual(compressed(raw,entry),compressed(saved,after.getinfo(entry.filename)),entry.filename)
            self.assertIsNone(after.testzip())
        self.assertEqual(xlsx_io.read_workbook(saved).rows,rows)

    def test_shared_strings_sparse_rows_and_long_description(self):
        view = xlsx_io.read_workbook(book())
        self.assertEqual(view.sheet, 'Проверка')
        self.assertEqual(view.physical_rows, [2, 5, 9])
        self.assertEqual(view.rows[0], ['domain','class','label','action','description','extra'])
        self.assertEqual(view.rows[1][:4], ['one.example','shopping','',''])
        self.assertTrue(view.rows[1][4].endswith('Описание. ' * 1500))
        self.assertEqual(view.rows[1][5], '2')

    def test_patch_changes_only_two_cells_and_preserves_every_other_part(self):
        for prefixed in (False, True):
            with self.subTest(prefixed=prefixed):
                raw = book(prefixed=prefixed)
                rows = copy.deepcopy(xlsx_io.read_workbook(raw).rows)
                rows[1][2:4] = ['Travel,education', 'ERROR']
                result = xlsx_io.patch_workbook(raw, rows)
                self.assertEqual(xlsx_io.read_workbook(result).rows, rows)
                with ZipFile(BytesIO(raw)) as before, ZipFile(BytesIO(result)) as after:
                    self.assertEqual(before.namelist(), after.namelist())
                    self.assertEqual(before.comment, after.comment)
                    for name in before.namelist():
                        if name != 'xl/worksheets/sheet1.xml':
                            self.assertEqual(before.read(name), after.read(name), name)
                    ns = {'s': xlsx_io.NS}
                    old = E.fromstring(before.read('xl/worksheets/sheet1.xml'))
                    new = E.fromstring(after.read('xl/worksheets/sheet1.xml'))
                    for tree in (old, new):
                        row = tree.find("s:sheetData/s:row[@r='5']", ns)
                        for cell in list(row):
                            if cell.get('r') in ('C5', 'D5'):
                                row.remove(cell)
                    self.assertEqual(E.tostring(old), E.tostring(new))
                    xml = after.read('xl/worksheets/sheet1.xml')
                    self.assertIn(b'xmlns:custom="urn:keep"', xml)
                    self.assertIn(b'r="C5" s="1"', xml)

    def test_ambiguous_sheet_requires_explicit_selection(self):
        raw = book(duplicate_sheet=True)
        with self.assertRaisesRegex(ValueError, 'несколько|Несколько'):
            xlsx_io.read_workbook(raw)
        self.assertEqual(xlsx_io.read_workbook(raw, 'Ещё данные').sheet, 'Ещё данные')
        with self.assertRaisesRegex(ValueError, 'лист|Лист'):
            xlsx_io.read_workbook(raw, 'Нет такого')

    def test_cell_like_xml_comments_and_foreign_cells_are_not_patched(self):
        # Комментарий или другой namespace не являются ячейкой, даже если текст похож на <c>.
        for decoy in (b'<!-- <c r="D5"/> -->', b'<custom:c r="D5"/>'):
            with self.subTest(decoy=decoy):
                raw=replace_part(book(), 'xl/worksheets/sheet1.xml', lambda xml: xml.replace(b'<c r="C5"', decoy+b'<c r="C5"'))
                rows=copy.deepcopy(xlsx_io.read_workbook(raw).rows)
                rows[1][3]='ERROR'
                saved=xlsx_io.patch_workbook(raw,rows)
                self.assertEqual(xlsx_io.read_workbook(saved).rows[1][3],'ERROR')
                with ZipFile(BytesIO(saved)) as z:
                    self.assertIn(decoy,z.read('xl/worksheets/sheet1.xml'))

    def test_shared_formula_group_is_rejected_before_breaking_other_cells(self):
        # C5 содержит определение общей формулы, а C9 — ссылку на него.
        def formulas(xml):
            xml=xml.replace(b'<c r="C5" s="1"/>',b'<c r="C5" t="str"><f t="shared" si="0" ref="C5:C9">A5</f><v>one.example</v></c>')
            return xml.replace(b'<c r="D9"',b'<c r="C9" t="str"><f t="shared" si="0"/><v>two.example</v></c><c r="D9"')
        raw=replace_part(book(),'xl/worksheets/sheet1.xml',formulas)
        rows=copy.deepcopy(xlsx_io.read_workbook(raw).rows)
        rows[1][2]='Travel'
        with self.assertRaisesRegex(ValueError,'формул|Формул'):
            xlsx_io.patch_workbook(raw,rows)

    def test_cached_empty_string_formula_is_a_valid_empty_label(self):
        raw=replace_part(book(),'xl/worksheets/sheet1.xml',lambda xml:xml.replace(b'<c r="C5" s="1"/>',b'<c r="C5" t="str"><f>IF(1=1,"","x")</f><v/></c>'))
        self.assertEqual(xlsx_io.read_workbook(raw).rows[1][2],'')

    def test_shared_strings_are_resolved_by_relationship(self):
        out=BytesIO()
        with ZipFile(BytesIO(book())) as source,ZipFile(out,'w') as target:
            for entry in source.infolist():
                name=entry.filename
                data=source.read(name)
                if name in ('xl/_rels/workbook.xml.rels','[Content_Types].xml'):
                    data=data.replace(b'sharedStrings.xml',b'strings.xml')
                target.writestr('xl/strings.xml' if name=='xl/sharedStrings.xml' else name,data)
        self.assertEqual(xlsx_io.read_workbook(out.getvalue()).rows[1][0],'one.example')

    def test_bad_action_reports_physical_excel_cell(self):
        raw=replace_part(book(),'xl/worksheets/sheet1.xml',lambda xml:xml.replace(b'<c r="C5" s="1"/>',b'<c r="C5" s="1"/><c r="D5" t="inlineStr"><is><t>wrong</t></is></c>'))
        with self.assertRaisesRegex(ValueError,'D5'):
            xlsx_io.read_workbook(raw)

    def test_negative_shared_string_index_is_not_python_last_item(self):
        raw=replace_part(book(),'xl/worksheets/sheet1.xml',lambda xml:xml.replace(b'<c r="A5" t="s"><v>6</v>',b'<c r="A5" t="s"><v>-1</v>'))
        with self.assertRaises(ValueError):
            xlsx_io.read_workbook(raw)

    def test_repeated_save_preserves_literal_excel_escape_text(self):
        raw=book()
        rows=copy.deepcopy(xlsx_io.read_workbook(raw).rows)
        rows[1][2:4]=['_x0041_ & <test>\rline','ERROR']
        saved=xlsx_io.patch_workbook(raw,rows)
        self.assertEqual(xlsx_io.read_workbook(saved).rows,rows)
        rows[1][2]='Travel'
        self.assertEqual(xlsx_io.read_workbook(xlsx_io.patch_workbook(saved,rows)).rows,rows)

    def test_no_rewrite_for_unchanged_and_refuse_immutable_changes(self):
        raw = book()
        rows = xlsx_io.read_workbook(raw).rows
        self.assertEqual(xlsx_io.patch_workbook(raw, rows), raw)
        rows[1][4] = 'Нельзя изменить описание через разметку'
        with self.assertRaisesRegex(ValueError, 'неизменяем|соответств'):
            xlsx_io.patch_workbook(raw, rows)

    def test_formula_without_cached_required_value_and_bad_archive_are_rejected(self):
        raw = replace_part(book(), 'xl/worksheets/sheet1.xml', lambda s: s.replace(b'<c r="E5" t="s"><v>8</v></c>', b'<c r="E5"><f>CONCAT("text")</f></c>'))
        with self.assertRaisesRegex(ValueError, 'формул|Формул'):
            xlsx_io.read_workbook(raw)
        for raw in (b'not an xlsx', b'PK\x03\x04broken'):
            with self.assertRaises(ValueError):
                xlsx_io.read_workbook(raw)

    def test_cli_check_and_real_ui_resume_preserve_original(self):
        from test_ui import Terminal
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'исходник.xlsx'
            target = Path(directory) / 'рабочая копия.xlsx'
            source.write_bytes(book())
            original = source.read_bytes()
            checked = subprocess.run([str(ROOT/'url-review'), '--check', str(source)], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertIn('Записей: 2', checked.stdout)
            self.assertFalse(target.exists())
            t = Terminal([source, target])
            try:
                t.wait('one.example'); t.send('2'); t.wait('Категории')
                t.send(' '); t.send('\n'); t.wait('Подтверждение'); t.send('\n'); t.wait('Проход завершён')
                t.send('q'); self.assertEqual(t.proc.wait(timeout=3), 0)
            finally:
                t.close()
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(xlsx_io.read_workbook(target.read_bytes()).rows[1][2:4], ['porno_and_erotics', 'ERROR'])
            t = Terminal([source, target])
            try:
                t.wait('Проход завершён'); t.send('q'); self.assertEqual(t.proc.wait(timeout=3), 0)
            finally:
                t.close()

    def test_external_edit_stops_save_and_sheet_cli_selects(self):
        from test_ui import Terminal
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'input.xlsx'; target = Path(directory)/'work.xlsx'
            source.write_bytes(book(duplicate_sheet=True))
            p = subprocess.run([str(ROOT/'url-review'), '--check', str(source), '--sheet', 'Ещё данные'], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            t = Terminal([source, target, '--sheet', 'Ещё данные'])
            try:
                t.wait('one.example')
                external = replace_part(target.read_bytes(), 'docProps/custom.xml', lambda _: b'<external/>')
                target.write_bytes(external)
                t.send('1'); t.wait('Категории'); t.send('\n'); t.wait('Подтверждение'); t.send('\n')
                t.wait('изменена другой программой')
                self.assertEqual(target.read_bytes(), external)
            finally:
                t.close()
