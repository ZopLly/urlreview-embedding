#!/usr/bin/env python3
"""Local E5 index builder. Only the explicit download subcommand uses networking."""
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import time

DIM = 384
REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
MODEL_ID = 'intfloat/multilingual-e5-small'
FILES = {
    'model.onnx': ('onnx/model_qint8_avx512_vnni.onnx', 'dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88'),
    'tokenizer.json': ('tokenizer.json', '0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39'),
}
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / 'models' / 'multilingual-e5-small'
MAX_BYTES = 256 * 1024 * 1024


def fingerprint(domain, description):
    h = 14695981039346656037
    for byte in (domain + '\0' + description).encode('utf-8'):
        h = ((h ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return h


def chunks(tokens, window=320, overlap=32):
    if window < 1 or not 0 <= overlap < window:
        raise ValueError('Invalid token window/overlap')
    for start in range(0, len(tokens), window - overlap):
        yield tokens[start:start + window]
        if start + window >= len(tokens):
            break


def build_index(source, output, encode, encoding='utf-8', delimiter=';', progress=None):
    source, output = Path(source), Path(output)
    if output.suffix != '.uremb' or source.resolve() == output.resolve():
        raise ValueError('Индекс должен иметь расширение .uremb и отдельный путь от CSV.')
    with source.open('rb') as f:
        raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('CSV больше 256 МиБ.')
    text = raw.decode(encoding).removeprefix('\ufeff')
    if '\0' in text:
        raise ValueError('CSV содержит нулевой байт.')
    csv.field_size_limit(MAX_BYTES)
    rows = list(csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True))
    if not rows:
        raise ValueError('CSV пуст.')
    header = rows.pop(0)
    required = ['domain', 'class', 'label', 'action', 'description']
    if any(header.count(name) != 1 for name in required):
        raise ValueError('Нужны уникальные domain, class, label, action, description.')
    domain, description = header.index('domain'), header.index('description')
    if any(len(row) != len(header) for row in rows):
        raise ValueError('Количество полей CSV не совпадает с заголовком.')
    if 16 + len(rows) * (8 + 4 * DIM) > MAX_BYTES:
        raise ValueError('Индекс превысит 256 МиБ.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=output.name + '.', suffix='.tmp', dir=output.parent, delete=False) as f:
            temporary = Path(f.name)
            f.write(b'UREMB01\n' + struct.pack('<II', len(rows), DIM))
            for number, row in enumerate(rows, 1):
                desc = row[description]
                vector = list(encode(desc)) if desc.strip() else [0.0] * DIM
                if len(vector) != DIM or any(not math.isfinite(v) for v in vector):
                    raise ValueError('Модель вернула неверный вектор.')
                norm = math.sqrt(sum(v * v for v in vector))
                if desc.strip() and norm == 0:
                    raise ValueError('Модель вернула нулевой вектор для непустого описания.')
                if norm:
                    vector = [v / norm for v in vector]
                f.write(struct.pack('<Q', fingerprint(row[domain], desc)))
                f.write(struct.pack('<384f', *vector))
                if progress:
                    progress(number, len(rows))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(rows)


def verify_model(directory):
    for name, (_, expected) in FILES.items():
        path = Path(directory) / name
        if not path.is_file():
            raise ValueError('Модель не установлена. Сначала scripts/setup-embeddings.sh')
        digest = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError(f'Контрольная сумма {name} не совпадает. Скачайте модель заново.')


def download_model(directory):
    import urllib.request
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, (remote, expected) in FILES.items():
        path = directory / name
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            print(f'{name}: уже скачан и проверен', flush=True)
            continue
        url = f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{remote}'
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, suffix='.download', delete=False) as f:
                temp = Path(f.name)
                digest = hashlib.sha256()
                with urllib.request.urlopen(url, timeout=60) as response:
                    while block := response.read(1024 * 1024):
                        digest.update(block)
                        f.write(block)
                if digest.hexdigest() != expected:
                    raise ValueError(f'Неверная контрольная сумма скачанного {name}')
            os.replace(temp, path)
            temp = None
            print(f'{name}: скачан и проверен', flush=True)
        finally:
            if temp:
                temp.unlink(missing_ok=True)
    (directory / 'model-info.json').write_text(json.dumps({'model': MODEL_ID, 'revision': REVISION, 'files': FILES}, indent=2))


class Encoder:
    def __init__(self, directory=DEFAULT_MODEL, threads=4):
        verify_model(directory)
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        self.tokenizer = Tokenizer.from_file(str(Path(directory) / 'tokenizer.json'))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(Path(directory) / 'model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        self.inputs = {entry.name for entry in self.session.get_inputs()}
        # E5 recommends query: on both sides for symmetric similarity tasks.
        self.prefix = self.tokenizer.encode('query: ', add_special_tokens=False).ids
        self.cls = self.tokenizer.token_to_id('<s>')
        self.sep = self.tokenizer.token_to_id('</s>')
        if self.cls is None or self.sep is None:
            raise ValueError('Токенизатор не содержит специальные токены E5.')

    def __call__(self, text):
        np = self.np
        # Only whitespace normalization: never summarize or discard the tail.
        tokens = self.tokenizer.encode(' '.join(text.split()), add_special_tokens=False).ids
        total = np.zeros(DIM, dtype=np.float64)
        for window in chunks(tokens):
            ids = np.asarray([[self.cls, *self.prefix, *window, self.sep]], dtype=np.int64)
            mask = np.ones_like(ids)
            feeds = {'input_ids': ids, 'attention_mask': mask, 'token_type_ids': np.zeros_like(ids)}
            outputs = self.session.run(None, {k: v for k, v in feeds.items() if k in self.inputs})
            hidden = outputs[0]
            if hidden.ndim != 3 or hidden.shape[2] != DIM:
                raise ValueError('Неожиданный выход ONNX-модели.')
            vector = hidden[0].mean(axis=0)
            norm = np.linalg.norm(vector)
            if not np.isfinite(norm) or norm == 0:
                raise ValueError('Неверный результат модели.')
            total += vector / norm
        norm = np.linalg.norm(total)
        return (total / norm if norm else total).tolist()


def main():
    parser = argparse.ArgumentParser(description='Локальные эмбеддинги E5 для URL Review')
    parser.add_argument('--model-dir', type=Path, default=DEFAULT_MODEL)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('download', help='Скачать модель: единственная команда с доступом в сеть')
    build = sub.add_parser('build', help='Создать индекс локально, без сети')
    build.add_argument('input', type=Path)
    build.add_argument('output', type=Path)
    build.add_argument('--encoding', choices=['utf-8', 'windows-1251'], default='utf-8')
    build.add_argument('--delimiter', choices=[';', ',', 'tab'], default=';')
    build.add_argument('--threads', type=int, choices=range(1, 17), default=4)
    sub.add_parser('smoke', help='Проверить настоящую модель на вымышленных русских описаниях')
    args = parser.parse_args()
    try:
        if args.command == 'download':
            download_model(args.model_dir)
            return
        start = time.monotonic()
        encoder = Encoder(args.model_dir, getattr(args, 'threads', 4))
        if args.command == 'smoke':
            texts = ['Интернет-магазин ручных инструментов, дрелей и оборудования для мастерской.',
                     'Продажа электроинструментов: дрели, шуруповёрты, товары для ремонта.',
                     'Музыкальная школа: уроки фортепиано, вокал и обучение игре на скрипке.']
            vectors = [encoder(text) for text in texts]
            similar = sum(a*b for a,b in zip(vectors[0],vectors[1]))
            different = sum(a*b for a,b in zip(vectors[0],vectors[2]))
            print(f'Магазин ↔ магазин: {similar:.4f}; магазин ↔ музыкальная школа: {different:.4f}')
            if similar <= different:
                raise ValueError('Проверка смыслового сходства не пройдена.')
        else:
            print('Локальная обработка. CSV не изменяется. Ctrl+C — отмена.', flush=True)
            def progress(done, total):
                if done == 1 or done % 10 == 0 or done == total:
                    print(f'{done}/{total}: {time.monotonic()-start:.1f} с', flush=True)
            count = build_index(args.input, args.output, encoder, args.encoding, '\t' if args.delimiter == 'tab' else args.delimiter, progress)
            print(f'Готово: {count} записей → {args.output}')
        print(f'Время с загрузкой модели: {time.monotonic()-start:.2f} с')
    except (OSError, ValueError, csv.Error, ImportError, RuntimeError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nОтменено; CSV не изменён.', file=sys.stderr)
        sys.exit(130)


if __name__ == '__main__':
    main()
