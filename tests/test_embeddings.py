# О файле: Проверки Python-построителя: модель заменена предсказуемой функцией encode; отдельно проверяется чтение Python-индекса настоящей C-программой.
# Пояснение: Документация: вымышленные CSV и подмена необязательной нейросетевой среды.
"""Only synthetic CSV; encoder double isolates the optional neural runtime."""
# Пояснение: Подключаем csv: стандартный разбор и запись CSV с кавычками и переносами.
import csv
# Пояснение: Подключаем importlib.util: загрузку тестируемого модуля по пути файла.
import importlib.util
# Пояснение: Импортируем выбранное имя из pathlib: Path для удобной работы с файловыми путями.
from pathlib import Path
# Пояснение: Подключаем struct: упаковку и распаковку чисел фиксированной ширины в байты.
import struct
# Пояснение: Подключаем subprocess: запуск внешних программ отдельным процессом.
import subprocess
# Пояснение: Подключаем tempfile: уникальные временные файлы и каталоги.
import tempfile
# Пояснение: Подключаем unittest: тестовый runner, фикстуры и проверочные assert-методы.
import unittest

# Пояснение: Корень проекта вычисляется из пути теста.
ROOT=Path(__file__).resolve().parents[1]
# Пояснение: Готовим загрузку Python-модуля напрямую по файлу без требования оформить пакет.
SPEC=importlib.util.spec_from_file_location('local_embeddings',ROOT/'embeddings/local_embeddings.py')
# Пояснение: Набор тестов построителя индекса.
class EmbeddingBuilderTests(unittest.TestCase):
    # Пояснение: Декоратор classmethod передаёт класс, а не экземпляр теста.
    @classmethod
    # Пояснение: Однократная подготовка модуля на весь набор тестов.
    def setUpClass(cls):
        # Пояснение: Создаём объект модуля из спецификации загрузки.
        cls.module=importlib.util.module_from_spec(SPEC)
        # Пояснение: Выполняем код модуля; ветка __main__ при таком импорте не запускается.
        if SPEC.loader:SPEC.loader.exec_module(cls.module)
    # Пояснение: Проверяет сохранение хвоста и отсутствие лишнего окна из одного перекрытия.
    def test_windows_keep_tail_without_duplicate_only_window(self):
        # Пояснение: Сокращаем обращение к загруженному модулю.
        m=self.module
        # Пояснение: Девять токенов при окне 4 и перекрытии 1 должны дать три конкретных окна.
        self.assertEqual(list(m.chunks(list(range(9)),4,1)),[[0,1,2,3],[3,4,5,6],[6,7,8]])
        # Пояснение: Ровно одно полное окно не должно порождать дополнительный хвост перекрытия.
        self.assertEqual(list(m.chunks([0,1,2,3],4,1)),[[0,1,2,3]])
        # Пояснение: Пустой вход даёт ноль окон.
        self.assertEqual(list(m.chunks([],4,1)),[])
        # Пояснение: Перекрытие размером с окно недопустимо и должно вызвать ValueError.
        with self.assertRaises(ValueError):list(m.chunks([1],4,4))
    # Пояснение: Проверяет точные байты формата и неизменность CP1251 CSV.
    def test_index_bytes_and_csv_stay_intact(self):
        # Пояснение: Локальное имя тестируемого модуля.
        m=self.module
        # Пояснение: Все временные файлы автоматически удалятся после блока.
        with tempfile.TemporaryDirectory() as tmp:
            # Пояснение: Отдельные пути CSV и индекса.
            source=Path(tmp)/'source.csv';out=Path(tmp)/'test.uremb'
            # Пояснение: Два синтетических сайта: один с описанием, второй без него.
            text='domain;class;label;action;description\none.example;shopping;;;Инструменты\ntwo.example;music;;OK;\n'
            # Пояснение: Сохраняем исходник именно в Windows-1251.
            source.write_bytes(text.encode('cp1251'))
            # Пояснение: Журнал обращений к подменной модели.
            calls=[]
            # Пояснение: Подменный encoder возвращает известный единичный вектор.
            def encode(text):
                # Пояснение: Запоминаем, какое описание реально попросили закодировать.
                calls.append(text)
                # Пояснение: Предсказуемый результат [1,0,...,0] из 384 чисел.
                return [1.0]+[0.0]*383
            # Пояснение: Строим настоящий бинарный индекс, используя подмену вычислений.
            m.build_index(source,out,encode,'windows-1251',';')
            # Пояснение: Пустое описание второго сайта не должно вызывать encoder.
            self.assertEqual(calls,['Инструменты'])
            # Пояснение: Читаем полученный бинарный файл.
            raw=out.read_bytes()
            # Пояснение: Проверяем сигнатуру, число записей и размерность в первых 16 байтах.
            self.assertEqual(raw[:16],b'UREMB01\n'+struct.pack('<II',2,384))
            # Пояснение: По смещению 16 проверяем известный FNV-1a отпечаток.
            self.assertEqual(struct.unpack_from('<Q',raw,16)[0],0x1952e5c4f4004a9)
            # Пояснение: Первый вектор начинается после заголовка 16 и хеша 8 байтов.
            self.assertEqual(struct.unpack_from('<384f',raw,24),(1.,)+(0.,)*383)
            # Пояснение: Вектор второго сайта должен быть нулевым; 1544 — байтовый размер одного индексного
            # Пояснение: блока.
            self.assertEqual(struct.unpack_from('<384f',raw,16+1544+8),(0.,)*384)
            # Пояснение: Построение индекса не должно изменить байты исходного CSV.
            self.assertEqual(source.read_bytes(),text.encode('cp1251'))
    # Пояснение: Проверяет совместимость формата Python → C и обнаружение устаревания описания.
    def test_python_index_is_read_by_c_and_detects_stale_description(self):
        # Пояснение: Локальное имя модуля построения.
        m=self.module
        # Пояснение: Изолируем файлы этого сценария во временном каталоге.
        with tempfile.TemporaryDirectory() as tmp:
            # Пояснение: Задаём пути синтетического CSV и .uremb.
            source=Path(tmp)/'source.csv';out=Path(tmp)/'test.uremb'
            # Пояснение: Пишем исходный CSV с одним непроверенным сайтом.
            source.write_text('domain;class;label;action;description\nx.example;shopping;;;товары\n')
            # Пояснение: Строим индекс с единичным вектором вместо настоящего инференса.
            m.build_index(source,out,lambda _: [1.]+[0.]*383)
            # Пояснение: Вспомогательная функция запускает C-приложение --check вместе с --embeddings, собирая
            # Пояснение: stdout/stderr.
            def check():return subprocess.run([str(ROOT/'url-review'),'--check',str(source),'--embeddings',str(out)],capture_output=True,text=True)
            # Пояснение: Исходный индекс должен успешно читаться C-кодом.
            self.assertEqual(check().returncode,0)
            # Пояснение: Меняем только label/action, сохраняя домен и описание.
            source.write_text('domain;class;label;action;description\nx.example;shopping;music;ERROR;товары\n')
            # Пояснение: Такая разметка не делает индекс устаревшим.
            self.assertEqual(check().returncode,0)
            # Пояснение: Теперь меняем само описание.
            source.write_text('domain;class;label;action;description\nx.example;shopping;music;ERROR;другой текст\n')
            # Пояснение: C-приложение должно завершиться с ошибкой и объяснить устаревание.
            result=check();self.assertNotEqual(result.returncode,0);self.assertIn('устарел',result.stderr)
    # Пояснение: Проверяет сохранность прежнего индекса и CSV при ошибке построения.
    def test_failures_do_not_replace_existing_index_or_source(self):
        # Пояснение: Локальное имя тестируемого модуля.
        m=self.module
        # Пояснение: Создаём отдельный временный каталог.
        with tempfile.TemporaryDirectory() as tmp:
            # Пояснение: Пути исходника и существующего индекса.
            source=Path(tmp)/'source.csv';out=Path(tmp)/'test.uremb'
            # Пояснение: Минимальный корректный вымышленный CSV.
            text='domain;class;label;action;description\nx;shopping;;;text\n'
            # Пояснение: Создаём исходник и прежнее содержимое индекса.
            source.write_text(text);out.write_bytes(b'previous')
            # Пояснение: Подмена encoder намеренно бросает ошибку инференса.
            def fail(text):raise RuntimeError('inference failed')
            # Пояснение: Ошибка должна выйти наружу из build_index.
            with self.assertRaises(RuntimeError):m.build_index(source,out,fail)
            # Пояснение: Прежние байты индекса должны остаться.
            self.assertEqual(out.read_bytes(),b'previous')
            # Пояснение: Исходный CSV тоже остаётся прежним.
            self.assertEqual(source.read_text(),text)
            # Пояснение: Передача CSV как выходного пути должна отклоняться.
            with self.assertRaises(ValueError):m.build_index(source,source,fail)
            # Пояснение: Выход с расширением .csv вместо .uremb тоже запрещён.
            with self.assertRaises(ValueError):m.build_index(source,Path(tmp)/'oops.csv',fail)
            # Пояснение: Незавершённые временные файлы должны быть удалены finally-блоком.
            self.assertEqual(list(Path(tmp).glob('*.tmp')),[])
    # Пояснение: Проверяет отказы для NaN-векторов и неполной схемы CSV.
    def test_invalid_headers_and_nonfinite_vectors_rejected(self):
        # Пояснение: Локальное имя модуля.
        m=self.module
        # Пояснение: Изолируем синтетические файлы этого теста.
        with tempfile.TemporaryDirectory() as tmp:
            # Пояснение: Готовим пути CSV и индекса.
            source=Path(tmp)/'source.csv';out=Path(tmp)/'test.uremb'
            # Пояснение: Пишем корректную схему, чтобы проверить именно ошибку вектора.
            source.write_text('domain;class;label;action;description\nx;shopping;;;text\n')
            # Пояснение: Возвращаем 384 NaN и ожидаем ValueError.
            with self.assertRaises(ValueError):m.build_index(source,out,lambda _: [float('nan')]*384)
            # Пояснение: После ошибки итоговый индекс не должен появиться.
            self.assertFalse(out.exists())
            # Пояснение: Теперь пишем неполный заголовок с двумя полями.
            source.write_text('domain;description\nx;text\n')
            # Пояснение: Даже численно допустимый вектор не должен позволить индексировать неверную схему.
            with self.assertRaises(ValueError):m.build_index(source,out,lambda _: [1.]*384)

    def test_xlsx_index_matches_sheet_and_is_read_by_c(self):
        # Индекс и интерфейс обязаны видеть одни и те же строки разреженной XLSX-книги.
        from xlsx_fixture import book
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.xlsx';out=Path(tmp)/'test.uremb'
            source.write_bytes(book(duplicate_sheet=True))
            self.module.build_index(source,out,lambda _: [1.]+[0.]*383,sheet='Ещё данные')
            result=subprocess.run([str(ROOT/'url-review'),'--check',str(source),'--sheet','Ещё данные','--embeddings',str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
