"""Проверки ZIP-границы: дескрипторы данных, комментарий, смещения и запасной путь."""
from io import BytesIO
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from zip_update import replace_member


class ZipUpdateTests(unittest.TestCase):
    def test_streamed_data_descriptors_comment_and_repeated_relocation(self):
        # Поток без seek вынуждает zipfile писать data descriptor после compressed payload.
        class Stream:
            def __init__(self): self.data=bytearray()
            def write(self,data): self.data.extend(data);return len(data)
            def flush(self): pass
        output=Stream()
        with ZipFile(output,'w',ZIP_DEFLATED) as z:
            z.comment=b'comment with PK\x01\x02 inside'
            z.writestr('first.xml',b'first'*100)
            z.writestr('sheet.xml',b'old sheet')
            z.writestr('last.xml',b'last'*100)
        raw=bytes(output.data)
        for value in (b'new'*10000,b'short',b''):
            with ZipFile(BytesIO(raw)) as z:
                self.assertTrue(z.getinfo('last.xml').flag_bits & 8)
                updated=replace_member(raw,z,'sheet.xml',value)
            with ZipFile(BytesIO(updated)) as z:
                self.assertEqual(z.read('first.xml'),b'first'*100)
                self.assertEqual(z.read('sheet.xml'),value)
                self.assertEqual(z.read('last.xml'),b'last'*100)
                self.assertEqual(z.comment,b'comment with PK\x01\x02 inside')
                self.assertIsNone(z.testzip())
                self.assertEqual(len(z.infolist()),3)
            raw=updated

    def test_prefixed_archive_uses_compatible_rewrite(self):
        output=BytesIO()
        with ZipFile(output,'w',ZIP_DEFLATED) as z:
            z.writestr('sheet.xml',b'old')
            z.writestr('other.xml',b'unchanged')
        # ZipFile поддерживает ZIP после произвольного префикса; fast path его не переписывает вручную.
        raw=b'prefix before ZIP'+output.getvalue()
        with ZipFile(BytesIO(raw)) as z:
            updated=replace_member(raw,z,'sheet.xml',b'new')
        with ZipFile(BytesIO(updated)) as z:
            self.assertEqual(z.read('sheet.xml'),b'new')
            self.assertEqual(z.read('other.xml'),b'unchanged')
            self.assertIsNone(z.testzip())
