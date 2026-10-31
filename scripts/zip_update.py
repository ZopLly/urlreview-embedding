"""Заменяет одну часть ZIP без повторного сжатия остальных.

Смещения стандартного каталога ZIP: PKWARE APPNOTE 4.3.12 и 4.3.16:
https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
ZIP64 и необычные контейнеры сохраняются прежним способом через zipfile.
"""
# Копия ZipInfo не позволяет writestr изменить метаданные открытого исходного архива.
from copy import copy
# Выходной ZIP собирается в памяти до атомарной записи из C.
from io import BytesIO
# Все поля каталога ZIP имеют little-endian порядок байтов.
import struct
# Сжатие изменённого элемента и совместимый запасной путь выполняет стандартная библиотека.
from zipfile import ZipFile


def _directory(raw, archive):
    """Возвращает обычный каталог ZIP либо None для совместимого запасного пути."""
    # EOCD имеет 22 фиксированных байта и комментарий, длина которого уже проверена ZipFile.
    end = len(raw) - 22 - len(archive.comment)
    if end < 0 or raw[end:end+4] != b'PK\x05\x06':
        return None
    # Диски, число элементов, размер каталога, смещение каталога и длина комментария.
    _, disk, start_disk, disk_count, count, size, offset, comment_len = struct.unpack_from('<4s4H2IH', raw, end)
    infos = archive.infolist()
    # Sentinel-значения требуют ZIP64; нестандартные хвосты/диски не переносим вручную.
    if disk or start_disk or disk_count != count or count != len(infos) or count == 65535:
        return None
    if comment_len != len(archive.comment) or offset + size != end:
        return None
    # Каждый центральный заголовок содержит 46 фиксированных байтов и три переменных поля.
    position, records = offset, []
    for entry in infos:
        if position + 46 > end or raw[position:position+4] != b'PK\x01\x02':
            return None
        names, extra, comment = struct.unpack_from('<HHH', raw, position+28)
        length = 46 + names + extra + comment
        local_offset = struct.unpack_from('<I', raw, position+42)[0]
        # Для самораспаковывающихся ZIP относительные смещения отличаются: используем zipfile.
        if position + length > end or local_offset != entry.header_offset:
            return None
        if struct.unpack_from('<H', raw, position+34)[0] or entry.file_size >= 0xffffffff or entry.compress_size >= 0xffffffff:
            return None
        records.append(raw[position:position+length])
        position += length
    if position != end:
        return None
    # Локальные блоки могут идти в другом порядке, чем записи центрального каталога.
    ordered = sorted(infos, key=lambda entry: entry.header_offset)
    if not ordered or ordered[0].header_offset != 0:
        return None
    bounds = {}
    for i, entry in enumerate(ordered):
        begin = entry.header_offset
        finish = ordered[i+1].header_offset if i+1 < len(ordered) else offset
        if begin + 30 > finish or raw[begin:begin+4] != b'PK\x03\x04':
            return None
        names, extra = struct.unpack_from('<HH', raw, begin+26)
        # Весь compressed payload должен лежать внутри своего блока; data descriptor сохраняется вместе с ним.
        if begin + 30 + names + extra + entry.compress_size > finish:
            return None
        bounds[entry.filename] = (begin, finish)
    return offset, records, ordered, bounds


def replace_member(raw, archive, part, payload):
    """Сохраняет исходные compressed payload и метаданные всех неизменённых частей."""
    layout = _directory(raw, archive)
    if layout is None:
        # Совместимость с ZIP64 и дополнительными ZIP-записями важнее ускорения редкого формата.
        out = BytesIO()
        with ZipFile(out, 'w') as target:
            target.comment = archive.comment
            for entry in archive.infolist():
                target.writestr(copy(entry), payload if entry.filename == part else archive.read(entry))
        return out.getvalue()
    # Стандартный zipfile вычисляет CRC и сжимает только изменённую часть, обычно XML одного листа.
    single = BytesIO()
    with ZipFile(single, 'w') as target:
        target.writestr(copy(archive.getinfo(part)), payload)
    replacement = single.getvalue()
    with ZipFile(BytesIO(replacement)) as generated:
        generated_layout = _directory(replacement, generated)
    if generated_layout is None:
        raise ValueError('Не удалось подготовить изменённую часть XLSX.')
    new_start, new_records, _, _ = generated_layout
    _, records, ordered, bounds = layout
    # bytearray позволяет записывать части по очереди, не распаковывая их и не меняя дескрипторы данных.
    result, offsets = bytearray(), {}
    for entry in ordered:
        offsets[entry.filename] = len(result)
        begin, finish = bounds[entry.filename]
        result.extend(replacement[:new_start] if entry.filename == part else memoryview(raw)[begin:finish])
    directory_start = len(result)
    # Каталог сохраняет исходный порядок; меняются лишь смещения локальных блоков и запись нового листа.
    for entry, record in zip(archive.infolist(), records):
        revised = bytearray(new_records[0] if entry.filename == part else record)
        struct.pack_into('<I', revised, 42, offsets[entry.filename])
        result.extend(revised)
    directory_size, count = len(result) - directory_start, len(records)
    # Новый EOCD с прежним комментарием; дубликат записи изменённого листа не добавляется.
    result.extend(struct.pack('<4s4H2IH', b'PK\x05\x06', 0, 0, count, count, directory_size, directory_start, len(archive.comment)))
    result.extend(archive.comment)
    return bytes(result)
