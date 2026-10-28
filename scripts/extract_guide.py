"""Extract the provided category PDF by its table coordinates (no dataset access).

Usage: python3 scripts/extract_guide.py CATEGORY_PDF data/categories.tsv
Requires Poppler pdftotext only when regenerating the supplied guide.
"""
import bisect
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

def main():
    xml = subprocess.check_output(['pdftotext', '-bbox-layout', sys.argv[1], '-'])
    tree = ET.fromstring(xml)
    ns = {'h': 'http://www.w3.org/1999/xhtml'}
    words, anchors = [], []
    for page_number, page in enumerate(tree.findall('.//h:page', ns)):
        for w in page.findall('.//h:word', ns):
            x, y = float(w.get('xMin')), float(w.get('yMin'))
            text = w.text or ''
            key = page_number * 1000 + y
            words.append((key, x, text))
            if abs(x-210.26)<1 and re.fullmatch('[a-z][a-z_0-9]*', text):
                anchors.append((key, text))
    anchors.sort()
    keys = [k for k,_ in anchors]
    fields = [[[],[],[]] for _ in anchors]
    for key,x,text in sorted(words):
        idx = bisect.bisect_right(keys,key+2)-1
        if idx<0 or x<209:
            continue
        if x<379.5:
            if text != anchors[idx][1]: fields[idx][0].append(text)
        elif x<659.5:
            fields[idx][1].append(text)
        else:
            fields[idx][2].append(text)
    lines=[]
    for (_,code),(title,inc,exc) in zip(anchors,fields):
        title=' '.join(title).strip('() ')
        # Short code-only categories in the source retain their code as title.
        title=title or code
        values=[code,title,' '.join(inc),' '.join(exc)]
        lines.append('\t'.join(re.sub(r'\s+',' ',v).strip() for v in values))
    Path(sys.argv[2]).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'{len(lines)} categories extracted')

if __name__=='__main__':
    main()
