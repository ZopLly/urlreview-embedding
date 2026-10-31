"""Независимая маленькая OOXML-книга для тестов; настоящие файлы не читаются."""
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED


def book(duplicate_sheet=False, prefixed=False):
    """Разреженные строки, sharedStrings, стили и посторонний лист с формулой."""
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    names = ['Проверка', 'Ещё данные' if duplicate_sheet else 'Итоги']
    workbook = f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'
    workbook += ''.join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1))
    workbook += '</sheets></workbook>'
    strings = ['domain', 'class', 'label', 'action', 'description', 'extra', 'one.example', 'shopping',
               'Длинный текст; "товары"\n' + 'Описание. ' * 1500, 'two.example', 'music', 'Второй сайт']
    shared = f'<sst xmlns="{ns}" count="12" uniqueCount="12">' + ''.join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in strings) + '</sst>'
    header = ''.join(f'<c r="{letter}2" t="s"><v>{i}</v></c>' for i, letter in enumerate('ABCDEF'))
    # Строка 4 стилизована, но пустая: она не должна превратиться в запись сайта.
    sheet = f'<worksheet xmlns="{ns}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:custom="urn:keep" mc:Ignorable="custom"><sheetData>'
    sheet += f'<row r="2">{header}</row><row r="4" s="1"/>'
    sheet += '<row r="5"><c r="A5" t="s"><v>6</v></c><c r="B5" t="s"><v>7</v></c><c r="C5" s="1"/><c r="E5" t="s"><v>8</v></c><c r="F5"><f>1+1</f><v>2</v></c></row>'
    sheet += '<row r="9"><c r="A9" t="s"><v>9</v></c><c r="B9" t="s"><v>10</v></c><c r="D9" t="inlineStr"><is><t>OK</t></is></c><c r="E9" t="s"><v>11</v></c></row>'
    sheet += '</sheetData><custom:keep value="untouched"/></worksheet>'
    if prefixed:
        import re
        sheet = re.sub(r'<(/?)(worksheet|sheetData|row|c|v|f|is|t)(?=[\s/>])', r'<\1s:\2', sheet)
        sheet = sheet.replace(f'xmlns="{ns}"', f'xmlns:s="{ns}"')
    summary = sheet if duplicate_sheet else f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1"><f>SUM(1,2)</f><v>3</v></c></row></sheetData></worksheet>'
    content_types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
    for part, kind in [('workbook.xml', 'sheet.main'), ('worksheets/sheet1.xml', 'worksheet'), ('worksheets/sheet2.xml', 'worksheet'), ('sharedStrings.xml', 'sharedStrings'), ('styles.xml', 'styles')]:
        content_types += f'<Override PartName="/xl/{part}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.{kind}+xml"/>'
    content_types += '</Types>'
    styles = f'<styleSheet xmlns="{ns}"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf/><xf applyAlignment="1"><alignment wrapText="1"/></xf></cellXfs></styleSheet>'
    parts = {'[Content_Types].xml': content_types, 'xl/workbook.xml': workbook,
             '_rels/.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
             'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i}" Type="{rel}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in (1, 2)) + f'<Relationship Id="rId3" Type="{rel}/sharedStrings" Target="sharedStrings.xml"/><Relationship Id="rId4" Type="{rel}/styles" Target="styles.xml"/></Relationships>',
             'xl/sharedStrings.xml': shared, 'xl/styles.xml': styles,
             'xl/worksheets/sheet1.xml': sheet, 'xl/worksheets/sheet2.xml': summary,
             'docProps/custom.xml': '<untouched value="metadata"/>'}
    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as z:
        z.comment = b'preserve-comment'
        for name, text in parts.items():
            z.writestr(name, text.encode())
    return out.getvalue()


def replace_part(raw, part, transform):
    """Изменяет только указанную синтетическую часть для отрицательных сценариев."""
    out = BytesIO()
    with ZipFile(BytesIO(raw)) as source, ZipFile(out, 'w') as target:
        for entry in source.infolist():
            data = source.read(entry)
            target.writestr(entry, transform(data) if entry.filename == part else data)
    return out.getvalue()
