# О файле: Интеграционные проверки CLI запускают настоящий бинарник без терминала; проверяют --check, аргументы, кодировки и отсутствие записи при ошибках.
# Пояснение: Подключаем csv: стандартный разбор и запись CSV с кавычками и переносами.
import csv
# Пояснение: Подключаем os: системные операции с файлами, процессами, окружением и дескрипторами.
import os
# Пояснение: Импортируем выбранное имя из pathlib: Path для удобной работы с файловыми путями.
from pathlib import Path
# Пояснение: Подключаем subprocess: запуск внешних программ отдельным процессом.
import subprocess
# Пояснение: Подключаем tempfile: уникальные временные файлы и каталоги.
import tempfile
# Пояснение: Подключаем unittest: тестовый runner, фикстуры и проверочные assert-методы.
import unittest

# Пояснение: Находим корень проекта относительно тестового файла.
ROOT=Path(__file__).resolve().parents[1]
# Пояснение: Путь к собранному приложению.
BIN=ROOT/'url-review'

# Пояснение: Набор сценариев командной строки unittest.
class CLITests(unittest.TestCase):
    # Пояснение: Подготовка перед каждым тестом.
    def setUp(self):
        # Пояснение: Создаём независимый временный каталог и сохраняем Path к нему.
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    # Пояснение: После теста удаляем каталог и его содержимое.
    def tearDown(self):self.tmp.cleanup()
    # Пояснение: Обёртка запуска CLI с произвольными аргументами.
    def call(self,*args):
        # Пояснение: Превращаем пути в строки; собираем stdout/stderr, декодируя их как текст.
        return subprocess.run([str(BIN),*map(str,args)],capture_output=True,text=True)
    # Пояснение: Проверяет корректное чтение CP1251 в режиме без записи.
    def test_check_is_read_only_and_handles_cp1251(self):
        # Пояснение: Путь синтетического входного CSV.
        path=self.root/'input.csv'
        # Пояснение: Кириллица, разделитель и CRLF внутри quoted-поля проверяют кодировку и многострочность.
        text='domain;class;label;action;description\r\nx.example;shopping;;OK;"Кириллица; ёжик\r\nПродолжение"\r\n'
        # Пояснение: Записываем CP1251 и сохраняем точные байты как эталон.
        path.write_bytes(text.encode('cp1251'));original=path.read_bytes()
        # Пояснение: Запускаем --check с правильной кодировкой.
        p=self.call('--check',path,'--encoding','windows-1251')
        # Пояснение: Код 0 и число записей 1 подтверждают успешный разбор.
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn('Записей: 1',p.stdout)
        # Пояснение: Исходные байты должны совпасть с эталоном.
        self.assertEqual(path.read_bytes(),original)
        # Пояснение: Никаких дополнительных файлов, включая рабочую копию, создаваться не должно.
        self.assertEqual(list(self.root.iterdir()),[path])
        # Пояснение: Тот же CP1251-файл без нужного параметра UTF-8 не должен приниматься.
        self.assertNotEqual(self.call('--check',path).returncode,0)
    # Пояснение: Проверяет ошибки заголовков, кавычек и action.
    def test_missing_or_duplicate_headers_and_bad_quoting(self):
        # Пояснение: Файл, перезаписываемый синтетическим случаем внутри цикла.
        path=self.root/'input.csv'
        # Пояснение: Первый случай — отсутствующие обязательные заголовки.
        for data in ['a;b;c\n1;2;3\n',
                     # Пояснение: Второй случай — повторный domain.
                     'domain;class;label;action;description;domain\na;b;;;x;dup\n',
                     # Пояснение: Третий случай — незакрытая кавычка.
                     'domain;class;label;action;description\na;b;;;"not closed',
                     # Пояснение: Четвёртый случай — недопустимый статус action.
                     'domain;class;label;action;description\na;b;;invalid;\n']:
            # Пояснение: Каждый вариант выводится отдельным subTest при провале.
            with self.subTest(data=data):
                # Пояснение: Записываем случай и проверяем его через --check.
                path.write_text(data);p=self.call('--check',path)
                # Пояснение: Ожидаем ненулевой код и непустое сообщение stderr.
                self.assertNotEqual(p.returncode,0);self.assertTrue(p.stderr)
                # Пояснение: Проверка некорректного файла тоже не должна менять его содержимое.
                self.assertEqual(path.read_text(),data)
    # Пояснение: Проверяет альтернативные разделители, перестановку столбцов и длинное описание.
    def test_comma_tab_extra_fields_and_long_text(self):
        # Пояснение: Повторяем тест для запятой и настоящей табуляции с CLI-именем tab.
        for sep,option in [(',',','),('\t','tab')]:
            # Пояснение: Путь временного CSV.
            path=self.root/'input.csv'
            # Пояснение: newline='' оставляет обработку переносов CSV writer.
            with path.open('w',newline='') as f:
                # Пояснение: Создаём CSV стандартным независимым writer с выбранным разделителем.
                csv.writer(f,delimiter=sep).writerows([
                    # Пояснение: Заголовки переставлены, дополнительный столбец стоит первым.
                    ['extra','description','domain','label','action','class'],
                    # Пояснение: Длинное описание содержит кавычки и переносы; лишний столбец пустой.
                    ['',('Длинное описание; "привет"\n'*1000),'x.example','','','shopping']])
            # Пояснение: Передаём соответствующий разделитель в C CLI.
            p=self.call('--check',path,'--delimiter',option)
            # Пояснение: Ожидаем успешный разбор; stderr добавляется к диагностике провала.
            self.assertEqual(p.returncode,0,p.stderr)
    # Пояснение: Проверяет справку, неверные опции, отсутствие файлов и запуск UI без терминала.
    def test_invalid_options_no_terminal_and_missing_file(self):
        # Пояснение: --help должен завершиться успешно.
        self.assertEqual(self.call('--help').returncode,0)
        # Пояснение: Перебираем отсутствие аргументов, неизвестные значения, незавершённый --check и
        # Пояснение: отсутствующий файл.
        for args in [[],['--encoding','bad'],['--delimiter','bad'],['--check'],['--check',self.root/'missing.csv']]:
            # Пояснение: Каждый неверный запуск должен дать ненулевой код.
            with self.subTest(args=args):self.assertNotEqual(self.call(*args).returncode,0)
        # Пояснение: Создаём минимальный валидный синтетический CSV-заголовок.
        source=self.root/'input.csv';source.write_text('domain;class;label;action;description\n')
        # Пояснение: Пробуем обычный UI-запуск через захваченные pipe, без PTY.
        out=self.root/'work.csv';p=self.call(source,out)
        # Пояснение: Запуск должен отказать до создания рабочей копии.
        self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())

# Пояснение: Прямой запуск файла вызывает unittest runner.
if __name__=='__main__':unittest.main()
