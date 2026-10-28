import csv
import io
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RoundtripTests(unittest.TestCase):
    def test_random_valid_quoted_csv_matches_independent_reader(self):
        rng=random.Random(20261028)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'input.csv';target=Path(directory)/'output.csv'
            for encoding in ['utf-8','cp1251']:
                for delimiter in [';',',','\t']:
                    for eol in ['\n','\r\n','\r']:
                        rows=[['domain','class','label','action','description','extra']]
                        alphabet='абЁ a;,"\n\r\t123'
                        if encoding=='utf-8':alphabet+='中é😀'
                        for i in range(35):
                            description=''.join(rng.choice(alphabet) for _ in range(rng.randrange(0,180)))
                            rows.append([f'fiction-{i%4}.example','shopping','',rng.choice(['','OK','ERROR','NOT_DESC']),description,''])
                        data=io.StringIO(newline='')
                        csv.writer(data,delimiter=delimiter,lineterminator=eol,quoting=csv.QUOTE_ALL).writerows(rows)
                        prefix='\ufeff' if encoding=='utf-8' else ''
                        source.write_bytes((prefix+data.getvalue()).encode(encoding))
                        p=subprocess.run([str(ROOT/'build/roundtrip'),str(source),str(target),encoding,'tab' if delimiter=='\t' else delimiter],capture_output=True,text=True)
                        self.assertEqual(p.returncode,0,p.stderr)
                        with target.open(encoding='utf-8-sig' if encoding=='utf-8' else encoding,newline='') as f:
                            result=list(csv.reader(f,delimiter=delimiter))
                        self.assertEqual(result,rows)

if __name__=='__main__':unittest.main()
