# О файле: Независимая проверка CSV: Python writer → C reader/serializer → Python reader. Сравниваем значения, включая случайные кавычки, переводы строк и Unicode.
# Пояснение: Подключаем csv: стандартный разбор и запись CSV с кавычками и переносами.
import csv
# Пояснение: Подключаем io: текстовые потоки в памяти для стандартного CSV-парсера.
import io
# Пояснение: Импортируем выбранное имя из pathlib: Path для удобной работы с файловыми путями.
from pathlib import Path
# Пояснение: Подключаем random: воспроизводимую генерацию случайных тестовых значений.
import random
# Пояснение: Подключаем subprocess: запуск внешних программ отдельным процессом.
import subprocess
# Пояснение: Подключаем tempfile: уникальные временные файлы и каталоги.
import tempfile
# Пояснение: Подключаем unittest: тестовый runner, фикстуры и проверочные assert-методы.
import unittest

# Пояснение: Находим корень проекта.
ROOT=Path(__file__).resolve().parents[1]

# Пояснение: Набор проверок полного чтения/записи.
class RoundtripTests(unittest.TestCase):
    # Пояснение: Проверяет, что результат C совпадает с независимой стандартной реализацией Python.
    def test_random_valid_quoted_csv_matches_independent_reader(self):
        # Пояснение: Фиксируем seed, чтобы случайные данные воспроизводились при каждом запуске.
        rng=random.Random(20261028)
        # Пояснение: Временный каталог автоматически удалится после теста.
        with tempfile.TemporaryDirectory() as directory:
            # Пояснение: Разные пути исходного и выходного CSV.
            source=Path(directory)/'input.csv';target=Path(directory)/'output.csv'
            # Пояснение: Проверяем UTF-8 и Windows-1251.
            for encoding in ['utf-8','cp1251']:
                # Пояснение: Для каждой кодировки проверяем три разделителя.
                for delimiter in [';',',','\t']:
                    # Пояснение: Для каждого разделителя проверяем LF, CRLF и CR между записями.
                    for eol in ['\n','\r\n','\r']:
                        # Пояснение: Начинаем с обязательного заголовка и дополнительного столбца.
                        rows=[['domain','class','label','action','description','extra']]
                        # Пояснение: Алфавит включает кириллицу, пробелы, разделители, кавычки и управляющие
                        # Пояснение: переводы строк.
                        alphabet='абЁ a;,"\n\r\t123'
                        # Пояснение: Для UTF-8 добавляем символы, непредставимые в CP1251.
                        if encoding=='utf-8':alphabet+='中é😀'
                        # Пояснение: Создаём 35 вымышленных сайтов для каждой комбинации формата.
                        for i in range(35):
                            # Пояснение: Случайное описание имеет от 0 до 179 символов из заданного алфавита.
                            description=''.join(rng.choice(alphabet) for _ in range(rng.randrange(0,180)))
                            # Пояснение: Домены намеренно повторяются; action берём из допустимых вариантов.
                            rows.append([f'fiction-{i%4}.example','shopping','',rng.choice(['','OK','ERROR','NOT_DESC']),description,''])
                        # Пояснение: Создаём текстовый поток в памяти, сохраняя переносы как данные.
                        data=io.StringIO(newline='')
                        # Пояснение: Стандартный writer заключает все поля в кавычки и использует выбранный
                        # Пояснение: формат.
                        csv.writer(data,delimiter=delimiter,lineterminator=eol,quoting=csv.QUOTE_ALL).writerows(rows)
                        # Пояснение: Только UTF-8 вариант получает начальный BOM.
                        prefix='\ufeff' if encoding=='utf-8' else ''
                        # Пояснение: Кодируем текст и записываем синтетический источник.
                        source.write_bytes((prefix+data.getvalue()).encode(encoding))
                        # Пояснение: C roundtrip читает и сериализует файл, затем возвращает его в исходную
                        # Пояснение: кодировку.
                        p=subprocess.run([str(ROOT/'build/roundtrip'),str(source),str(target),encoding,'tab' if delimiter=='\t' else delimiter],capture_output=True,text=True)
                        # Пояснение: Процесс должен завершиться успешно.
                        self.assertEqual(p.returncode,0,p.stderr)
                        # Пояснение: Python читает результат; utf-8-sig снимает только начальный BOM.
                        with target.open(encoding='utf-8-sig' if encoding=='utf-8' else encoding,newline='') as f:
                            # Пояснение: Независимый csv.reader восстанавливает значения полей.
                            result=list(csv.reader(f,delimiter=delimiter))
                        # Пояснение: Сравниваем все значения всех ячеек, а не оформление кавычек.
                        self.assertEqual(result,rows)

# Пояснение: Прямой запуск включает unittest runner.
if __name__=='__main__':unittest.main()
