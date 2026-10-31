"""XLSX backend на стандартной библиотеке: чтение OOXML и точечная замена action/label.

Остальные ячейки и части ZIP сохраняются как исходные байты. Модуль не вычисляет
формулы, не запускает макросы и не обращается в сеть. CLI служит мостом из C.
"""
# Потоки в памяти нужны для ZIP и независимого CSV-представления таблицы.
from io import BytesIO, StringIO
# Path/PurePosixPath не нужны: внутренние имена ZIP нормализуются как POSIX-пути.
import posixpath
# Регулярные выражения находят исходные XML-фрагменты, не пересобирая весь лист.
import re
# CSV используется только как внутренний протокол между Python и существующим C-парсером.
import csv
# Числа фиксированной ширины в протоколе имеют little-endian порядок.
import struct
# stdin/stdout передают байты, argv задаёт режим и выбранный лист.
import sys
# Простая структура объединяет значения таблицы и физические координаты Excel.
from dataclasses import dataclass
# ElementTree проверяет XML и извлекает значения, но не переписывает исходный лист.
from xml.etree import ElementTree as ET
# Expat сообщает байтовые границы настоящих XML-элементов, пропуская комментарии.
from xml.parsers import expat
# XML-экранирование защищает текст новых ячеек, включая амперсанды и угловые скобки.
from xml.sax.saxutils import escape
# XLSX — ZIP-контейнер с XML; ZipInfo сохраняет параметры неизменённых частей.
from zipfile import ZipFile, BadZipFile

# Стандартные пространства имён SpreadsheetML и связей OOXML.
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
# Максимум совпадает с лимитом байтов в C; проверяется и распакованный размер.
LIMIT = 256 * 1024 * 1024
# Внутреннее CSV-представление сохраняет старые обязательные имена.
REQUIRED = ('domain', 'class', 'label', 'action', 'description')



@dataclass
class WorkbookView:
    # rows содержит заголовок и записи; пропущенные физические строки не создают пустых сайтов.
    rows: list
    # physical_rows сопоставляет каждую rows[i] настоящему номеру строки Excel.
    physical_rows: list
    # sheet — отображаемое имя листа, part — путь его XML внутри ZIP.
    sheet: str
    part: str


def _xml(data):
    # DTD здесь не нужен; запрещаем его и объявления entities до разбора XML.
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('XLSX содержит недопустимое объявление XML.')
    # Некорректный XML станет понятной ошибкой верхнего уровня.
    return ET.fromstring(data)


def _archive(raw):
    # Проверяем исходный размер ещё до распаковки.
    if len(raw) > LIMIT:
        raise ValueError('XLSX больше 256 МиБ.')
    # BytesIO не создаёт распакованные файлы на диске.
    archive = ZipFile(BytesIO(raw))
    # Проверяем весь каталог архива, включая неиспользуемые листы и вложения.
    entries = archive.infolist()
    # Неоднозначные повторные имена и слишком большой распакованный архив запрещены.
    if len({e.filename for e in entries}) != len(entries) or sum(e.file_size for e in entries) > LIMIT:
        archive.close()
        raise ValueError('Повторные части XLSX или распакованный размер больше 256 МиБ.')
    # Шифрованные контейнеры без пароля не поддерживаются.
    if any(e.flag_bits & 1 for e in entries):
        archive.close()
        raise ValueError('Зашифрованный XLSX не поддерживается.')
    return archive


def _text(element):
    # Rich text может содержать несколько runs; берём именно t, а не фонетические подсказки rPh.
    if element is None:
        return ''
    pieces = [child.text or '' for child in element.findall(f'{{{NS}}}t')]
    pieces += [t.text or '' for run in element.findall(f'{{{NS}}}r') for t in run.findall(f'{{{NS}}}t')]
    # Excel ST_Xstring кодирует некоторые символы как _xHHHH_; заменяем только одним проходом.
    return re.sub(r'_x([0-9a-fA-F]{4})_', lambda m: chr(int(m[1], 16)), ''.join(pieces))


def _column(reference):
    # Индексы Excel: A=0, Z=25, AA=26; строковая часть должна быть положительной.
    match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', reference)
    if not match:
        raise ValueError('Неверная координата ячейки XLSX.')
    result = 0
    # Позиционная система счисления с цифрами A..Z от 1 до 26.
    for letter in match[1]:
        result = result * 26 + ord(letter) - ord('A') + 1
    # Физические пределы формата Excel защищают от огромных разреженных индексов.
    if result > 16384 or int(match[2]) > 1048576:
        raise ValueError('Координата вне пределов XLSX.')
    return result - 1


def _letter(column):
    # Обратное преобразование индекса 0..16383 в A..XFD.
    result = ''
    column += 1
    while column:
        column, digit = divmod(column - 1, 26)
        result = chr(65 + digit) + result
    return result


def _sheet_rows(archive, part, shared):
    # Читаем только выбранную внутреннюю часть ZIP; ссылки на внешние файлы не открываются.
    document = _xml(archive.read(part))
    records, previous_row = [], 0
    # Только настоящие SpreadsheetML-строки в sheetData являются данными.
    for row in document.findall(f'{{{NS}}}sheetData/{{{NS}}}row'):
        number = int(row.get('r', previous_row + 1))
        if number <= previous_row or number > 1048576:
            raise ValueError('Повторные или неупорядоченные строки XLSX.')
        previous_row = number
        values, missing_formula, previous_col = {}, set(), -1
        for cell in row.findall(f'{{{NS}}}c'):
            reference = cell.get('r', f'{_letter(previous_col + 1)}{number}')
            column = _column(reference)
            if column <= previous_col or int(re.search(r'[0-9]+$', reference)[0]) != number:
                raise ValueError('Повторные или неупорядоченные ячейки XLSX.')
            previous_col = column
            kind, value = cell.get('t', 'n'), cell.find(f'{{{NS}}}v')
            if kind == 'inlineStr':
                text = _text(cell.find(f'{{{NS}}}is'))
            elif kind == 's':
                # Отрицательный индекс в Python выбрал бы строку с конца, что не является форматом XLSX.
                index = int(value.text) if value is not None else -1
                if not 0 <= index < len(shared):
                    raise ValueError('Недопустимый индекс sharedStrings в XLSX.')
                text = shared[index]
            else:
                text = value.text or '' if value is not None else ''
            if cell.find(f'{{{NS}}}f') is not None and (value is None or (value.text is None and kind != 'str')):
                missing_formula.add(column)
            if kind == 'e':
                missing_formula.add(column)
            values[column] = text
        # Строки с одним форматированием пропускаем, сохраняя их физические номера в XML.
        if any(values.values()) or missing_formula:
            records.append((number, values, missing_formula))
    return records


def read_workbook(raw, sheet=None):
    """Выбирает единственный подходящий лист либо явно названный, возвращает таблицу и координаты."""
    try:
        with _archive(raw) as archive:
            workbook = _xml(archive.read('xl/workbook.xml'))
            relations = _xml(archive.read('xl/_rels/workbook.xml.rels'))
            # Рабочий лист определяется связью, а не предположением о sheet1.xml.
            targets = {r.get('Id'): r.get('Target') for r in relations if r.get('Type', '').endswith('/worksheet') and r.get('TargetMode') != 'External'}
            shared = []
            # Таблица общих строк определяется связью книги, а не фиксированным именем файла.
            string_links = [r.get('Target') for r in relations if r.get('Type', '').endswith('/sharedStrings') and r.get('TargetMode') != 'External']
            if len(string_links) > 1:
                raise ValueError('Повторная связь sharedStrings в XLSX.')
            if string_links:
                target = string_links[0]
                part = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
                if not part.startswith('xl/'):
                    raise ValueError('Неверная ссылка sharedStrings в XLSX.')
                shared = [_text(item) for item in _xml(archive.read(part))]
            candidates = []
            for item in workbook.findall(f'{{{NS}}}sheets/{{{NS}}}sheet'):
                name = item.get('name')
                if sheet is not None and name != sheet:
                    continue
                target = targets.get(item.get(f'{{{REL}}}id'))
                if not target:
                    continue
                part = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
                if not part.startswith('xl/') or part not in archive.namelist():
                    raise ValueError('Неверная внутренняя ссылка листа XLSX.')
                records = _sheet_rows(archive, part, shared)
                if not records:
                    continue
                header_values = records[0][1]
                width = max(header_values) + 1 if header_values else 0
                header = [header_values.get(c, '') for c in range(width)]
                if any(header.count(name) != 1 for name in REQUIRED):
                    continue
                required_columns = {header.index(name) for name in REQUIRED}
                # Ошибка статуса должна показывать настоящую ячейку Excel, включая пустые строки до неё.
                action_column = header.index('action')
                rows, physical = [], []
                for number, values, formulas in records:
                    if formulas & required_columns:
                        raise ValueError(f'Лист {name}, строка {number}: формула без сохранённого результата или ошибка Excel. Пересчитайте и сохраните книгу в Excel.')
                    if any(c >= width and text for c, text in values.items()):
                        raise ValueError(f'Лист {name}: данные за пределами заголовка.')
                    # Заголовок action не является значением статуса; остальные строки проверяем строго.
                    if rows and values.get(action_column, '') not in ('', 'OK', 'ERROR', 'NOT_DESC'):
                        raise ValueError(f'Лист {name}, ячейка {_letter(action_column)}{number}: недопустимый action; ожидается OK, ERROR, NOT_DESC или пусто.')
                    rows.append([values.get(c, '') for c in range(width)])
                    physical.append(number)
                candidates.append(WorkbookView(rows, physical, name, part))
            if not candidates:
                raise ValueError('Не найден лист с заголовками domain, class, label, action, description.' if sheet is None else f'Лист «{sheet}» отсутствует или не содержит обязательных заголовков.')
            if len(candidates) != 1:
                raise ValueError('В книге несколько подходящих листов. Укажите --sheet ИМЯ.')
            return candidates[0]
    except (BadZipFile, ET.ParseError, KeyError, IndexError, TypeError, UnicodeError, RuntimeError) as exc:
        raise ValueError(f'Не удалось прочитать XLSX: {exc}') from exc


def _attribute(attrs, name):
    # Находим обычный атрибут, не смешивая r с namespace:r; допустимы оба вида кавычек XML.
    found = re.search(r'(?<![\w:])' + name + r'\s*=\s*([\'\"])(.*?)\1', attrs, re.S)
    return found[2] if found else None


def _inline(tag, attrs, reference, value):
    # Excel считает длину ячейки в кодовых единицах UTF-16.
    if len(value.encode('utf-16-le')) // 2 > 32767:
        raise ValueError('Значение action/label превышает предел ячейки Excel 32767 символов.')
    # Убираем прежний тип (shared string, numeric и пр.), сохраняя стиль и прочие атрибуты.
    attrs = re.sub(r'\s+t\s*=\s*([\'\"]).*?\1', '', attrs, flags=re.S).rstrip()
    if _attribute(attrs, 'r') is None:
        attrs += f' r="{reference}"'
    # Защищаем литеральные _xHHHH_ от специального декодирования Excel.
    value = re.sub(r'_x[0-9a-fA-F]{4}_', lambda m: '_x005F_' + m[0][1:], value)
    # Символы, недопустимые в XML 1.0, кодируются по правилам строк Excel.
    value = ''.join(f'_x{ord(c):04X}_' if ord(c) < 32 and c not in '\n\t' else c for c in value)
    prefix = tag[:-1]
    # Новое содержимое только этой ячейки: inline string не требует менять sharedStrings.xml.
    return f'<{tag}{attrs} t="inlineStr"><{prefix}is><{prefix}t xml:space="preserve">{escape(value)}</{prefix}t></{prefix}is></{tag}>'


def _tag_end(raw, start):
    # Символ > внутри кавычек атрибута не завершает открывающий XML-тег.
    quote = None
    for pos in range(start, len(raw)):
        byte = raw[pos]
        if quote is not None:
            if byte == quote:
                quote = None
        elif byte in (34, 39):
            quote = byte
        elif byte == 62:
            return pos + 1
    raise ValueError('Незавершённый XML-тег XLSX.')


def _worksheet_spans(raw):
    # Подстановки формируются в UTF-8, иная кодировка не должна молча смешиваться с ними.
    raw.decode('utf-8-sig')
    parser = expat.ParserCreate(namespace_separator='}')
    rows, path = {}, []
    active_row, active_cell = None, None
    previous_row = 0
    base = [NS+'}worksheet', NS+'}sheetData']

    def start(name, attributes):
        nonlocal active_row, active_cell, previous_row
        # parser.CurrentByteIndex указывает на < именно разобранного элемента.
        path.append(name)
        if path == base + [NS+'}row'] or (active_row is not None and path == base + [NS+'}row', NS+'}c']):
            begin = parser.CurrentByteIndex
            end = _tag_end(raw, begin)
            opening = raw[begin+1:end-1].decode('utf-8').rstrip()
            empty = opening.endswith('/')
            if empty:
                opening = opening[:-1]
            tag, attrs = re.match(r'([^\s/>]+)(.*)', opening, re.S).groups()
            if name == NS+'}row':
                number = int(attributes.get('r', previous_row + 1))
                previous_row = number
                active_row = {'number': number, 'start': begin, 'open_end': end, 'empty': empty,
                              'prefix': tag[:-3], 'cells': []}
                rows[number] = active_row
            else:
                column = _column(attributes['r']) if 'r' in attributes else (active_row['cells'][-1]['column']+1 if active_row['cells'] else 0)
                active_cell = {'start': begin, 'open_end': end, 'empty': empty, 'tag': tag,
                               'attrs': attrs, 'column': column, 'formula': None}
                active_row['cells'].append(active_cell)
        elif active_cell is not None and path == base + [NS+'}row', NS+'}c', NS+'}f']:
            # Запоминаем тип и диапазон формулы, не изменяя её текст.
            active_cell['formula'] = dict(attributes)

    def end(name):
        nonlocal active_row, active_cell
        if active_cell is not None and path == base + [NS+'}row', NS+'}c']:
            active_cell['end'] = active_cell['open_end'] if active_cell['empty'] else _tag_end(raw, parser.CurrentByteIndex)
            active_cell = None
        elif active_row is not None and path == base + [NS+'}row']:
            active_row = None
        path.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(raw, True)
    return rows


def _check_formula_groups(spans, number, column):
    # Обычную формулу изменяемой ячейки заменять можно; общие диапазоны требуют Excel.
    for row in spans.values():
        for cell in row['cells']:
            formula = cell['formula']
            if not formula or formula.get('t') not in ('shared', 'array', 'dataTable'):
                continue
            affected = row['number'] == number and cell['column'] == column
            reference = formula.get('ref')
            if reference:
                bounds = reference.replace('$', '').split(':')
                first, last = bounds[0], bounds[-1]
                low_row, high_row = int(re.search(r'[0-9]+$', first)[0]), int(re.search(r'[0-9]+$', last)[0])
                affected |= low_row <= number <= high_row and _column(first) <= column <= _column(last)
            if affected:
                raise ValueError('Ячейка action/label входит в связанную или массивную формулу. Сначала замените формулы в этих столбцах значениями в Excel.')


def patch_workbook(raw, rows, sheet=None):
    """Меняет лишь отличающиеся action/label; неизменяемые значения должны совпадать."""
    view = read_workbook(raw, sheet)
    if len(rows) != len(view.rows) or not rows or rows[0] != view.rows[0]:
        raise ValueError('Таблица не соответствует исходной книге XLSX.')
    editable = {rows[0].index('action'), rows[0].index('label')}
    changes = {}
    for r, (before, after) in enumerate(zip(view.rows, rows)):
        if len(before) != len(after):
            raise ValueError('Таблица не соответствует исходной книге XLSX.')
        for c, (old, new) in enumerate(zip(before, after)):
            if old == new:
                continue
            if not r or c not in editable:
                raise ValueError('Изменён неизменяемый столбец XLSX.')
            changes.setdefault(view.physical_rows[r], {})[c] = new
    if not changes:
        return raw
    with _archive(raw) as archive:
        original = archive.read(view.part)
        # Expat находит только реальные SpreadsheetML-ячейки, а не похожий текст комментариев.
        spans = _worksheet_spans(original)
        replacements = []
        for number, wanted in changes.items():
            if number not in spans:
                raise ValueError('Не найдены изменяемые строки XLSX; запись отменена.')
            row = spans[number]
            by_column = {cell['column']: cell for cell in row['cells']}
            for column, value in sorted(wanted.items()):
                # Не удаляем определение общей/массивной формулы и не ломаем её зависимые ячейки.
                _check_formula_groups(spans, number, column)
                reference = f'{_letter(column)}{number}'
                if column in by_column:
                    cell = by_column[column]
                    new = _inline(cell['tag'], cell['attrs'], reference, value).encode('utf-8')
                    replacements.append((cell['start'], cell['end'], new))
                else:
                    # Вставляем перед следующей настоящей ячейкой либо сразу после последней.
                    following = [c for c in row['cells'] if c['column'] > column]
                    position = following[0]['start'] if following else (row['cells'][-1]['end'] if row['cells'] else row['open_end'])
                    new = _inline(row['prefix']+'c', '', reference, value).encode('utf-8')
                    replacements.append((position, position, new))
        payload = original
        # Стабильная сортировка сохраняет порядок нескольких вставок в одно смещение.
        for start, end, new in reversed(sorted(replacements, key=lambda item: (item[0], item[1]))):
            payload = payload[:start] + new + payload[end:]
        out = BytesIO()
        with ZipFile(out, 'w') as target:
            target.comment = archive.comment
            for entry in archive.infolist():
                target.writestr(entry, payload if entry.filename == view.part else archive.read(entry))
        result = out.getvalue()
        if len(result) > LIMIT:
            raise ValueError('Результат XLSX превышает 256 МиБ.')
        # Повторное чтение не позволяет сообщить успех, если записались другие значения.
        verified = read_workbook(result, view.sheet)
        if verified.rows != rows or verified.physical_rows != view.physical_rows:
            raise ValueError('Проверка сохранённого XLSX не пройдена; замена отменена.')
        return result


def main():
    # C передаёт stdin из временного дескриптора; stdout содержит OK\n+байты либо ERR\n+сообщение.
    try:
        mode, sheet = sys.argv[1], sys.argv[2] or None
        # Большие описания из XLSX не должны упираться в стандартные 128 КиБ CSV-парсера.
        csv.field_size_limit(LIMIT)
        data = sys.stdin.buffer.read(2 * LIMIT + 9)
        if mode == 'read':
            view = read_workbook(data, sheet)
            text = StringIO(newline='')
            csv.writer(text, delimiter=';', lineterminator='\n').writerows(view.rows)
            name = view.sheet.encode('utf-8')
            payload = struct.pack('<II', len(name), len(view.rows)) + name
            payload += struct.pack(f'<{len(view.rows)}I', *view.physical_rows)
            payload += text.getvalue().encode('utf-8')
        elif mode == 'write':
            length = struct.unpack_from('<Q', data)[0]
            if length > LIMIT or length + 8 > len(data):
                raise ValueError('Неверный запрос сохранения XLSX.')
            rows = list(csv.reader(StringIO(data[8+length:].decode('utf-8'), newline=''), delimiter=';', strict=True))
            payload = patch_workbook(data[8:8+length], rows, sheet)
        else:
            raise ValueError('Неизвестная операция XLSX.')
        sys.stdout.buffer.write(b'OK\n' + payload)
    except (OSError, ValueError, csv.Error, struct.error, IndexError) as exc:
        sys.stdout.buffer.write(b'ERR\n' + str(exc).encode('utf-8'))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
