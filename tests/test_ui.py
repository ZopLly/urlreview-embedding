# О файле: Интеграционные тесты запускают настоящий ncurses-бинарник в псевдотерминале PTY. CSV и справочник вымышлены; xdg-open подменён локальным журналирующим скриптом.
# Пояснение: Документация: проверяем реальный UI через PTY только на вымышленных данных.
"""Drive the real ncurses executable through a PTY, using synthetic data only."""
# Пояснение: Подключаем csv: стандартный разбор и запись CSV с кавычками и переносами.
import csv
# Пояснение: Подключаем fcntl: управление параметрами PTY через ioctl.
import fcntl
# Пояснение: Подключаем os: системные операции с файлами, процессами, окружением и дескрипторами.
import os
# Пояснение: Импортируем выбранное имя из pathlib: Path для удобной работы с файловыми путями.
from pathlib import Path
# Пояснение: Подключаем pty: пару master/slave псевдотерминала для настоящего ncurses.
import pty
# Пояснение: Подключаем select: ожидание доступных байтов вывода PTY с тайм-аутом.
import select
# Пояснение: Подключаем signal: именованные сигналы, включая уведомление изменения размеров терминала.
import signal
# Пояснение: Подключаем struct: упаковку и распаковку чисел фиксированной ширины в байты.
import struct
# Пояснение: Подключаем subprocess: запуск внешних программ отдельным процессом.
import subprocess
# Пояснение: Подключаем tempfile: уникальные временные файлы и каталоги.
import tempfile
# Пояснение: Подключаем time: монотонные часы и ожидание в тестах.
import time
# Пояснение: Подключаем unittest: тестовый runner, фикстуры и проверочные assert-методы.
import unittest

# Пояснение: Корень проекта определяется относительно файла теста.
ROOT = Path(__file__).resolve().parents[1]
# Пояснение: Путь к обычному исполняемому приложению.
BIN = ROOT / 'url-review'
# Пояснение: Заголовок всех синтетических CSV.
HEADER = ['domain','class','label','action','description']

# Пояснение: Вспомогательный терминал: процесс приложения, ввод клавиш, чтение экрана и изменение размеров.
class Terminal:
    # Пояснение: Конструктор принимает аргументы, дополнительные переменные окружения и необязательный другой
    # Пояснение: бинарник.
    def __init__(self, args, extra_env=None, executable=None):
        # Пояснение: Создаём master для теста и slave, который станет терминалом приложения.
        self.master, slave = pty.openpty()
        # Пояснение: Linux TIOCSWINSZ=0x5414 задаёт 32 строки и 115 колонок; HHHH — четыре unsigned short.
        fcntl.ioctl(slave, 0x5414, struct.pack('HHHH',32,115,0,0))
        # Пояснение: Запускаем настоящий бинарник, подключая все три стандартных потока к slave.
        self.proc = subprocess.Popen([str(executable or BIN),*map(str,args)],stdin=slave,stdout=slave,stderr=slave,
                                     # Пояснение: Наследуем окружение и задаём терминал/UTF-8; extra_env имеет
                                     # Пояснение: последний приоритет.
                                     env={**os.environ,'TERM':'xterm-256color','LANG':'C.UTF-8',**(extra_env or {})})
        # Пояснение: Родитель закрывает ненужный slave: у дочернего процесса уже есть свои дескрипторы.
        os.close(slave)
        # Пояснение: Накопитель ещё не обработанного вывода PTY.
        self.output = b''
    # Пояснение: Ждёт нужную последовательность байтов на экране до тайм-аута.
    def wait(self, text, timeout=6):
        # Пояснение: Ожидаемый текст кодируем в UTF-8 для поиска в байтах терминала.
        target=text.encode()
        # Пояснение: Вычисляем предельное время по монотонным часам.
        end=time.monotonic()+timeout
        # Пояснение: Продолжаем читать, пока текст не появился в накопленном выводе.
        while target not in self.output:
            # Пояснение: Проверяем, не превышен ли тайм-аут.
            if time.monotonic()>end:
                # Пояснение: При зависании показываем ожидаемый текст, состояние процесса и хвост вывода для
                # Пояснение: диагностики.
                raise AssertionError(f'No {text!r}; exit={self.proc.poll()}; tail={self.output[-1600:]!r}')
            # Пояснение: select ждёт готовности чтения PTY не дольше 0.1 секунды.
            if select.select([self.master],[],[],.1)[0]:
                # Пояснение: Добавляем доступные байты к буферу экрана.
                try: self.output += os.read(self.master,65536)
                # Пояснение: Закрытый PTY до нужного текста означает провал ожидания, показываем хвост вывода.
                except OSError: raise AssertionError(f'PTY closed: {self.output[-1200:]!r}')
        # Пояснение: Сохраняем накопленный экран для вызывающего теста.
        output=self.output
        # Пояснение: Очищаем буфер, чтобы следующее wait не совпало со старым кадром.
        self.output=b''
        # Пояснение: Возвращаем полученные байты вывода.
        return output
    # Пояснение: Отправляет клавиши или готовую escape-последовательность в stdin приложения.
    def send(self, keys):
        # Пояснение: Строки кодируем, байтовые последовательности передаём напрямую.
        os.write(self.master,keys.encode() if isinstance(keys,str) else keys)
    # Пояснение: Меняет размеры тестового терминала.
    def resize(self,h,w):
        # Пояснение: Обновляем размер PTY через Linux ioctl.
        fcntl.ioctl(self.master,0x5414,struct.pack('HHHH',h,w,0,0))
        # Пояснение: Уведомляем приложение SIGWINCH, чтобы ncurses пересчитал геометрию.
        self.proc.send_signal(signal.SIGWINCH)
    # Пояснение: Закрывает процесс и дескриптор после теста.
    def close(self):
        # Пояснение: Если процесс ещё работает, его нужно остановить.
        if self.proc.poll() is None:
            # Пояснение: Сначала посылаем мягкое завершение SIGTERM.
            self.proc.terminate()
            # Пояснение: Ждём завершение до трёх секунд.
            try:self.proc.wait(timeout=3)
            # Пояснение: Зависший процесс убиваем и обязательно забираем его exit status.
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        # Пояснение: Освобождаем master-дескриптор PTY.
        os.close(self.master)

# Пояснение: Набор независимых сценариев интерфейса unittest.
class UITests(unittest.TestCase):
    # Пояснение: Перед каждым сценарием создаёт свежие файлы и окружение.
    def setUp(self):
        # Пояснение: Новый временный каталог изолирует результаты теста.
        self.tmp=tempfile.TemporaryDirectory()
        # Пояснение: Сохраняем Path корня временных данных.
        self.root=Path(self.tmp.name)
        # Пояснение: Пути исходника и отдельной рабочей копии.
        self.input=self.root/'input.csv';self.output=self.root/'work.csv'
        # Пояснение: Путь маленького тестового TSV-справочника.
        self.guide=self.root/'categories.tsv'
        # Пояснение: Создаём три категории с кодами, пояснениями и включениями.
        self.guide.write_text('shopping\tПокупки\tПродажа товаров\t\nmusic\tМузыка\tМузыкальные ресурсы\t\nfinance\tФинансы\tБанки\t\n')
        # Пояснение: Открываем синтетический CSV, доверяя обработку переносов csv.writer.
        with self.input.open('w',newline='') as f:
            # Пояснение: Записываем заголовок и следующие вымышленные записи.
            csv.writer(f,delimiter=';').writerows([HEADER,
                # Пояснение: Первый сайт содержит длинное описание, кавычки и перевод строки.
                ['one.example','shopping','','','Длинный текст; "товары"\n'+('Описание. '*1500)],
                # Пояснение: Второй сайт короткий; оба изначально непроверены.
                ['two.example','music','','','Второй сайт']])
        # Пояснение: Запоминаем точные исходные байты для общей проверки неизменности.
        self.original=self.input.read_bytes()
        # Пояснение: Пока PTY-процесс не запущен.
        self.term=None
    # Пояснение: Вспомогательный запуск стандартного тестового сеанса.
    def start(self):
        # Пояснение: Создаём терминал с тестовыми файлами и справочником.
        self.term=Terminal([self.input,self.output,'--guide',self.guide])
        # Пояснение: Возвращаем объект терминала для отправки клавиш.
        return self.term
    # Пояснение: Читает рабочую копию независимым стандартным CSV-парсером.
    def rows(self):
        # Пояснение: Открываем копию, сохраняем многострочные поля и возвращаем записи списком.
        with self.output.open(newline='') as f:return list(csv.reader(f,delimiter=';'))
    # Пояснение: Очистка и общая проверка после каждого сценария.
    def tearDown(self):
        # Пояснение: Закрываем процесс, если он был создан.
        if self.term:self.term.close()
        # Пояснение: Каждый сценарий обязан оставить исходный CSV побайтово прежним.
        self.assertEqual(self.input.read_bytes(),self.original)
        # Пояснение: Удаляем временный каталог со всеми созданными тестовыми артефактами.
        self.tmp.cleanup()
    # Пояснение: Проверяет, что отсутствие индекса не мешает ручной разметке.
    def test_similar_without_index_keeps_review_available(self):
        # Пояснение: Открываем первую карточку, нажимаем P и ждём объяснение отсутствующего индекса.
        t=self.start();t.wait('one.example');t.send('p');t.wait('Индекс не подключён')
        # Пояснение: Возвращаемся Q из окна поиска и затем выходим из приложения с кодом 0.
        t.send('q');t.wait('one.example');t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
        # Пояснение: Оба action должны остаться пустыми: просмотр ничего не разметил.
        self.assertEqual([r[3] for r in self.rows()[1:]],['',''])
    # Пояснение: Проверяет показ уже проверенного похожего сайта и его полной карточки.
    def test_similar_shows_reviewed_record_and_detail(self):
        # Пояснение: Читаем вымышленные записи для подготовки статуса второго сайта.
        with self.input.open(newline='') as f: rows=list(csv.reader(f,delimiter=';'))
        # Пояснение: Помечаем второй сайт OK, чтобы он прошёл фильтр проверенных.
        rows[2][3]='OK'
        # Пояснение: Записываем подготовленный CSV стандартным writer.
        with self.input.open('w',newline='') as f:csv.writer(f,delimiter=';').writerows(rows)
        # Пояснение: Обновляем эталон неизменности после осознанной подготовки данных тестом.
        self.original=self.input.read_bytes()
        # Пояснение: Путь синтетического бинарного индекса.
        index=self.root/'test.uremb'
        # Пояснение: Открываем индекс для байтовой записи.
        with index.open('wb') as f:
            # Пояснение: Заголовок .uremb: сигнатура, два сайта, размерность 384.
            f.write(b'UREMB01\n'+struct.pack('<II',2,384))
            # Пояснение: Строим индекс только для сайтов, пропуская заголовок.
            for row in rows[1:]:
                # Пояснение: Начальное значение FNV-1a.
                h=14695981039346656037
                # Пояснение: Вычисляем совместимый отпечаток домена, нулевого разделителя и описания.
                for byte in (row[0]+'\0'+row[4]).encode():h=((h^byte)*1099511628211)&((1<<64)-1)
                # Пояснение: Пишем хеш и единичный вектор [1,0,...,0], не загружая настоящую модель.
                f.write(struct.pack('<Q384f',h,1.,*([0.]*383)))
        # Пояснение: Запускаем UI с подготовленным индексом.
        self.term=Terminal([self.input,self.output,'--guide',self.guide,'--embeddings',index])
        # Пояснение: На первом сайте открываем P и ждём второй проверенный сайт в результатах.
        t=self.term;t.wait('one.example');t.send('p');t.wait('two.example')
        # Пояснение: Enter должен открыть подробности с принятой разметкой.
        t.send('\n');t.wait('Принятая разметка')
        # Пояснение: Q закрывает подробности, затем список, возвращая первую карточку.
        t.send('q');t.wait('two.example');t.send('q');t.wait('one.example')
        # Пояснение: Выходим из приложения и проверяем успешный exit status.
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
        # Пояснение: Поиск не должен заполнить action текущей записи.
        self.assertEqual(self.rows()[1][3],'')
    # Пояснение: Проверяет итоговые категории и различие номера записи от строки таблицы с заголовком.
    def test_similar_identifies_table_row_decision_and_final_categories(self):
        # Пояснение: Случаи OK без label и OK с дополнительной категорией.
        cases=[('OK','','music'),('OK','shopping','music, shopping'),
               # Пояснение: OK не дублирует исходный class в label; ERROR берёт только исправленные категории.
               ('OK','music, shopping','music, shopping'),('ERROR','shopping','shopping'),
               # Пояснение: Пустые ERROR/NOT_DESC отображаются как неопределённый итог.
               ('ERROR','',None),('NOT_DESC','',None),
               # Пояснение: NOT_DESC с заданным label отображает этот код.
               ('NOT_DESC','shopping',None)]
        # Пояснение: Повторяем сценарий для каждого action, label и ожидаемого итога.
        for action,label,expected in cases:
            # Пояснение: subTest показывает параметры конкретного случая при провале.
            with self.subTest(action=action,label=label):
                # Пояснение: Закрываем терминал прошлого случая и очищаем ссылку на него.
                if self.term:self.term.close();self.term=None
                # Пояснение: Удаляем прежнюю копию, чтобы каждый случай начинался независимо.
                self.output.unlink(missing_ok=True)
                # Пояснение: Читаем подготовленный исходник стандартным CSV reader.
                with self.input.open(newline='') as f:rows=list(csv.reader(f,delimiter=';'))
                # Пояснение: Устанавливаем второй записи label и action через срез двух ячеек.
                rows[2][2:4]=[label,action]
                # Пояснение: Сохраняем синтетический исходник после подготовки.
                with self.input.open('w',newline='') as f:csv.writer(f,delimiter=';').writerows(rows)
                # Пояснение: Запоминаем новый допустимый эталон исходных байтов.
                self.original=self.input.read_bytes()
                # Пояснение: Путь индекса для текущего случая.
                index=self.root/'test.uremb'
                # Пояснение: Пересоздаём бинарный индекс.
                with index.open('wb') as f:
                    # Пояснение: Пишем заголовок на два вектора.
                    f.write(b'UREMB01\n'+struct.pack('<II',2,384))
                    # Пояснение: Для каждой записи данных генерируем её индексный блок.
                    for row in rows[1:]:
                        # Пояснение: Начальное состояние FNV-1a.
                        h=14695981039346656037
                        # Пояснение: Отпечаток вычисляем с той же маской 64 бит, что production Python.
                        for byte in (row[0]+'\0'+row[4]).encode():h=((h^byte)*1099511628211)&((1<<64)-1)
                        # Пояснение: У всех сайтов одинаковые единичные векторы, поэтому ранжирование
                        # Пояснение: предсказуемо.
                        f.write(struct.pack('<Q384f',h,1.,*([0.]*383)))
                # Пояснение: Запускаем интерфейс с индексом и тестовым справочником.
                self.term=Terminal([self.input,self.output,'--guide',self.guide,'--embeddings',index])
                # Пояснение: Открываем поиск с первой записи.
                t=self.term;t.wait('one.example');t.send('p')
                # Недостаточное описание и ERROR без категории больше не служат подсказкой категории.
                if expected is None:
                    t.wait('Похожих проверенных записей пока нет')
                    t.send('q');t.wait('one.example');t.send('q')
                    self.assertEqual(t.proc.wait(timeout=3),0)
                    self.assertEqual(self.rows()[2][2:4],[label,action])
                    continue
                # Пояснение: Ждём нужный итог в списке и декодируем кадр для дополнительных проверок.
                screen=t.wait('Итог: '+expected).decode()
                # Пояснение: Проверяем человекочитаемый номер сайта без заголовка.
                self.assertIn('Запись №2',screen)
                # Пояснение: Номер CSV-записи с заголовком должен быть на единицу больше.
                self.assertIn('Строка таблицы: 3',screen)
                # Пояснение: Проверяем показ сохранённого решения.
                self.assertIn('Решение: '+action,screen)
                # Пояснение: Открываем подробности и ждём тот же итог категорий.
                t.send('\n');detail=t.wait('Итоговые категории: '+expected).decode()
                # Пояснение: В подробностях тоже должен быть номер сайта.
                self.assertIn('Запись №2',detail)
                # Пояснение: Проверяем номер строки таблицы с заголовком.
                self.assertIn('Строка таблицы: 3',detail)
                # Пояснение: Исходный class должен оставаться music независимо от исправления label.
                self.assertIn('Исходный class: music',detail)
                # Пояснение: Проверяем action в подробной карточке.
                self.assertIn('Решение: '+action,detail)
                # Пояснение: Закрываем оба вложенных окна и возвращаемся к исходной карточке.
                t.send('q');t.wait('two.example');t.send('q');t.wait('one.example')
                # Пояснение: Завершаем приложение с кодом 0.
                t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
                # Пояснение: Просмотр должен сохранить прежние label и action без изменений.
                self.assertEqual(self.rows()[2][2:4],[label,action])
    # Пояснение: Проверяет смену краткого пояснения с курсором и доступность полных критериев.
    def test_category_explanation_follows_cursor_and_full_help_remains(self):
        # Пояснение: Готовим категории с коротким и очень длинным пояснениями, требующим переноса.
        self.guide.write_text('shopping\tМагазины и объявления о продаже\tПродажа товаров\t\nmusic\tИсполнители, записи, тексты песен, музыкальная индустрия, выступления, фестивали и концертные программы\tМузыкальные ресурсы\t\n')
        # Пояснение: Открываем ERROR и ждём пояснение первого пункта.
        t=self.start();t.wait('one.example');t.send('2');t.wait('Суть: Магазины')
        # Пояснение: Сдвигаем курсор J и проверяем, что виден конец длинного пояснения.
        t.send('j');t.wait('концертные программы')
        # Пояснение: H открывает полные критерии; Q возвращает к краткому пояснению.
        t.send('h');t.wait('Включает:');t.send('q');t.wait('Суть:')
        # Пояснение: Escape отменяет выбор; выходим с кодом 0.
        t.send(b'\x1b');t.wait('one.example');t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
        # Пояснение: Просмотр справки и отмена не должны сохранять action.
        self.assertEqual(self.rows()[1][3],'')
    # Пояснение: Проверяет несколько выбранных категорий, момент подтверждения и возобновление сеанса.
    def test_multi_category_confirmation_and_resume(self):
        # Пояснение: Запускаем и ждём первую карточку.
        t=self.start();t.wait('one.example')
        # Пояснение: Выбираем ERROR и ждём список категорий.
        t.send('2');t.wait('Категории')
        # Пояснение: Пробел, J, пробел выбирают два пункта; Enter открывает подтверждение.
        t.send(' j ');t.send('\n');t.wait('Подтверждение')
        # Пояснение: До подтверждения action на диске должен оставаться пустым.
        self.assertEqual(self.rows()[1][3],'')
        # Пояснение: Второй Enter сохраняет и открывает следующий сайт.
        t.send('\n');t.wait('two.example')
        # Пояснение: Проверяем точный порядок и английские коды label плюс ERROR.
        self.assertEqual(self.rows()[1][2:4],['shopping,music','ERROR'])
        # Пояснение: Длинное исходное описание должно сохраниться целиком и без изменения.
        self.assertEqual(self.rows()[1][4],'Длинный текст; "товары"\n'+('Описание. '*1500))
        # Пояснение: Выходим, проверяем exit status, закрываем дескриптор и очищаем ссылку.
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0);t.close();self.term=None
        # Пояснение: При повторном запуске первая проверенная запись пропускается и открывается вторая.
        t=self.start();t.wait('two.example');t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    # Пояснение: Проверяет откладывание, повтор прохода, историю, редактирование и пустой NOT_DESC.
    def test_defer_return_back_edit_and_empty_not_desc(self):
        # Пояснение: Откладываем первый сайт и попадаем на второй.
        t=self.start();t.wait('one.example');t.send('s');t.wait('Второй сайт')
        # Пояснение: Подтверждаем OK второго сайта и доходим до итога прохода.
        t.send('1');t.wait('Категории');t.send('\n');t.wait('Подтверждение');t.send('\n');t.wait('Проход завершён')
        # Пояснение: R возвращает первый отложенный сайт; сохраняем NOT_DESC без категорий.
        t.send('r');t.wait('one.example');t.send('3');t.wait('Категории');t.send('\n');t.wait('Подтверждение');t.send('\n');t.wait('Проход завершён')
        # Пояснение: Проверяем разрешённый пустой label для NOT_DESC.
        self.assertEqual(self.rows()[1][2:4],['','NOT_DESC'])
        # Пояснение: B возвращает первый сайт; меняем решение на ERROR с shopping и снова подтверждаем.
        t.send('b');t.wait('one.example');t.send('2');t.wait('Категории');t.send(' ');t.send('\n');t.wait('Подтверждение');t.send('\n');t.wait('Проход завершён')
        # Пояснение: Проверяем, что редактирование заменило прежнее решение.
        self.assertEqual(self.rows()[1][2:4],['shopping','ERROR'])
        # Пояснение: Выходим успешно.
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    # Пояснение: Проверяет справку, изменение размеров окна, отмену и выход с отбрасыванием черновика.
    def test_cancel_help_resize_and_discard_exit(self):
        # Пояснение: Открываем общую справку и возвращаемся Escape.
        t=self.start();t.wait('one.example');t.send('h');t.wait('Справка');t.send(b'\x1b');t.wait('one.example')
        # Пояснение: Сжимаем и расширяем терминал, давая ncurses время обработать сигналы.
        t.resize(7,25);time.sleep(.15);t.resize(32,115);time.sleep(.15)
        # Пояснение: Открываем категории и их справку, затем возвращаемся Escape.
        t.send('2');t.wait('Категории');t.send('h');t.wait('Включает');t.send(b'\x1b');time.sleep(.1)
        # Пояснение: Создаём выбор, запрашиваем выход Q и отбрасываем черновик D.
        t.send(' ');t.send('q');t.wait('Несохранённое');t.send('d');self.assertEqual(t.proc.wait(timeout=3),0)
        # Пояснение: Ни одна запись не должна получить action.
        self.assertEqual([r[3] for r in self.rows()[1:]],['',''])
    # Пояснение: Проверяет переключение на UTF-8, даже если окружение задаёт ASCII-локаль C.
    def test_ascii_locale_still_displays_russian(self):
        # Пояснение: Явно запускаем приложение с LANG=C и LC_ALL=C.
        self.term=Terminal([self.input,self.output,'--guide',self.guide],{'LANG':'C','LC_ALL':'C'})
        # Пояснение: Кириллическая подпись подтверждает пригодную локаль интерфейса.
        self.term.wait('не проверено')
        # Пояснение: Выходим и проверяем код завершения.
        self.term.send('q');self.assertEqual(self.term.proc.wait(timeout=3),0)
    # Пояснение: Проверяет запрет подтверждения, если окно слишком мало для просмотра решения.
    def test_small_window_does_not_confirm_unseen_decision(self):
        # Пояснение: Открываем выбор категорий.
        t=self.start();t.wait('one.example');t.send('2');t.wait('Категории')
        # Пояснение: Сжимаем терминал и дважды посылаем Enter, имитируя потенциально опасное скрытое
        # Пояснение: подтверждение.
        t.resize(7,25);time.sleep(.15);t.send('\n\n');time.sleep(.15)
        # Пояснение: action должен оставаться пустым.
        self.assertEqual(self.rows()[1][3],'')
        # Пояснение: Восстанавливаем размеры, запрашиваем выход и отбрасываем черновик.
        t.resize(32,115);time.sleep(.1);t.send('q');t.wait('Несохранённое');t.send('d')
        # Пояснение: Приложение завершается успешно.
        self.assertEqual(t.proc.wait(timeout=3),0)
    # Пояснение: Проверяет прокрутку длинного подтверждения до последнего выбранного кода.
    def test_long_confirmation_can_scroll_to_last_selected_category(self):
        # Пояснение: Создаём 30 длинных кодов и уникальный маркер последнего.
        codes=[f'category_{i}_'+('x'*35) for i in range(29)]+['zz_last_marker']
        # Пояснение: Формируем соответствующий синтетический TSV-справочник.
        self.guide.write_text(''.join(f'{c}\tКатегория\tОписание\t\n' for c in codes))
        # Пояснение: Запускаем UI и устанавливаем минимальный допустимый размер 18×65.
        t=self.start();t.wait('one.example');t.resize(18,65);time.sleep(.1)
        # Пояснение: Открываем экран категорий.
        t.send('2');t.wait('Категории')
        # Пояснение: Отмечаем все категории номером+Enter; дополнительный Enter открывает подтверждение.
        t.send(''.join(f'{i}\n' for i in range(1,len(codes)+1))+'\n');t.wait('Подтверждение')
        # Пояснение: G прокручивает до конца, где должен появиться последний маркер.
        t.send('G');t.wait('zz_last_marker')
        # Пояснение: Подтверждаем сохранение и даём ему завершиться.
        t.send('\n');time.sleep(.15)
        # Пояснение: label должен содержать все коды, включая последний, в исходном порядке.
        self.assertEqual(self.rows()[1][2],','.join(codes))
        # Пояснение: Выходим успешно.
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    # Пояснение: Проверяет предупреждение и остановку перехода после ошибки fsync каталога.
    def test_uncertain_sync_warns_and_waits_for_retry(self):
        # Пояснение: Запускаем отдельный тестовый бинарник с подменой fsync, а не обычное приложение.
        self.term=Terminal([self.input,self.output,'--guide',self.guide],executable=ROOT/'build/url-review-sync')
        # Пояснение: Открываем ERROR первой записи.
        t=self.term;t.wait('one.example');t.send('2');t.wait('Категории')
        # Пояснение: Выбираем категорию, подтверждаем и ждём сообщение остановки перехода.
        t.send(' \n');t.wait('Подтверждение');t.send('\n');t.wait('переход остановлен')
        # Пояснение: Файл уже заменён: на диске должен быть новый ERROR, несмотря на предупреждение.
        self.assertEqual(self.rows()[1][3],'ERROR')
        # Пояснение: Закрываем сообщение и повторяем Enter; новая успешная попытка открывает второй сайт.
        t.send(b'\x1b');time.sleep(.1);t.send('\n');t.wait('Второй сайт')
        # Пояснение: Выходим с кодом 0.
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    # Пояснение: Создаёт подменный xdg-open, который только журналирует аргументы и не открывает настоящий
    # Пояснение: браузер.
    def browser_environment(self):
        # Пояснение: Создаём отдельный каталог исполняемых тестовых программ.
        bindir=self.root/'bin';bindir.mkdir()
        # Пояснение: Путь подменной команды называется точно xdg-open.
        opener=bindir/'xdg-open'
        # Пояснение: Записываем shell-скрипт: печатаем число аргументов и первый URL в файл журнала.
        opener.write_text('#!/bin/sh\nprintf "%s\\n" "$#" "$1" >> "$URL_REVIEW_BROWSER_LOG"\n')
        # Пояснение: Даём владельцу права чтения, записи и исполнения.
        opener.chmod(0o700)
        # Пояснение: Путь журнала вызовов.
        log=self.root/'browser.log'
        # Пояснение: Подставляем bin первым в PATH и передаём скрипту путь журнала через переменную окружения.
        return log,{'PATH':str(bindir)+os.pathsep+os.environ.get('PATH',''), 'URL_REVIEW_BROWSER_LOG':str(log)}
    # Пояснение: Ожидает нужное число записанных вызовов подменного браузера.
    def wait_browser_calls(self,log,count):
        # Пояснение: Ограничиваем ожидание четырьмя секундами.
        end=time.monotonic()+4
        # Пояснение: Периодически проверяем журнал до дедлайна.
        while time.monotonic()<end:
            # Пояснение: Если журнал уже создан, читаем его строки, иначе считаем список пустым.
            lines=log.read_text().splitlines() if log.exists() else []
            # Пояснение: На один вызов идут две строки: число аргументов и URL.
            if len(lines)>=count*2:return lines
            # Пояснение: Пауза 30 мс предотвращает активное ожидание без сна.
            time.sleep(.03)
        # Пояснение: Отсутствие нужных вызовов означает провал теста.
        self.fail('Browser request was not received')
    # Пояснение: Проверяет, что сайт открывается только по O или клику по домену.
    def test_browser_opens_only_on_key_or_domain_click(self):
        # Пояснение: Подготавливаем подменный браузер и его окружение.
        log,env=self.browser_environment()
        # Пояснение: Запускаем приложение с изменённым PATH.
        self.term=Terminal([self.input,self.output,'--guide',self.guide],env)
        # Пояснение: Само появление первой карточки не должно создавать журнал открытия сайта.
        t=self.term;t.wait('one.example');self.assertFalse(log.exists())
        # Пояснение: O передаёт ровно один аргумент, нормализованный в HTTPS.
        t.send('o');self.assertEqual(self.wait_browser_calls(log,1),['1','https://one.example'])
        # Пояснение: Посылаем SGR-последовательности нажатия и отпускания левой кнопки в координатах домена.
        t.send(b'\x1b[<0;3;4M\x1b[<0;3;4m')
        # Пояснение: Второй вызов должен повторить тот же один URL.
        self.assertEqual(self.wait_browser_calls(log,2),['1','https://one.example','1','https://one.example'])
        # Пояснение: Клик в области описания не должен открывать сайт; ждём обработку события.
        t.send(b'\x1b[<0;3;9M\x1b[<0;3;9m');time.sleep(.1)
        # Пояснение: Журнал остаётся длиной четыре строки — только два прошлых вызова.
        self.assertEqual(len(log.read_text().splitlines()),4)
        # Пояснение: Открытие браузера не размечает запись.
        self.assertEqual(self.rows()[1][3],'')
        # Пояснение: Завершаем сеанс успешно.
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    # Пояснение: Проверяет отказ открывать file:// через UI.
    def test_browser_rejects_non_http_scheme(self):
        # Пояснение: Переписываем только синтетический исходник для этого сценария.
        with self.input.open('w',newline='') as f:
            # Пояснение: Единственный адрес имеет запрещённую схему file://.
            csv.writer(f,delimiter=';').writerows([HEADER,['file:///tmp/fiction','shopping','','','Test']])
        # Пояснение: Обновляем эталон исходных байтов после подготовки.
        self.original=self.input.read_bytes()
        # Пояснение: Подготавливаем журналирующую подмену браузера.
        log,env=self.browser_environment()
        # Пояснение: Запускаем интерфейс в её окружении.
        self.term=Terminal([self.input,self.output,'--guide',self.guide],env)
        # Пояснение: Нажатие O на file:// должно показать ограничение HTTP.
        t=self.term;t.wait('file:///tmp/fiction');t.send('o');t.wait('HTTP')
        # Пояснение: xdg-open не должен вызываться; затем выходим с кодом 0.
        self.assertFalse(log.exists());t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    # Пояснение: Проверяет, что отсутствие xdg-open не повреждает состояние записи.
    def test_browser_launch_failure_leaves_record_unchanged(self):
        # Пояснение: PATH указывает на отсутствующий каталог, поэтому spawn не найдёт xdg-open.
        self.term=Terminal([self.input,self.output,'--guide',self.guide],{'PATH':str(self.root/'missing-bin')})
        # Пояснение: Пытаемся открыть сайт и ждём сообщение о неудаче запуска.
        t=self.term;t.wait('one.example');t.send('o');t.wait('xdg-open')
        # Пояснение: action должен остаться пустым; приложение по-прежнему успешно закрывается.
        self.assertEqual(self.rows()[1][3],'');t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)
    # Пояснение: Проверяет перевод колеса мыши в прокрутку описания.
    def test_mouse_wheel_scrolls_description(self):
        # Пояснение: Готовим отдельный синтетический CSV.
        with self.input.open('w',newline='') as f:
            # Пояснение: Описание состоит из 20 строк и уникального маркера в конце.
            csv.writer(f,delimiter=';').writerows([HEADER,['wheel.example','shopping','','','\n'.join([f'line-{i}' for i in range(20)]+['MOUSE-WHEEL-TAIL'])]])
        # Пояснение: Обновляем эталон неизменности исходника.
        self.original=self.input.read_bytes()
        # Пояснение: Посылаем SGR-событие колеса вниз и ждём появления хвостового маркера.
        t=self.start();t.wait('wheel.example');t.send(b'\x1b[<65;3;9M');t.wait('MOUSE-WHEEL-TAIL')
        # Пояснение: Выходим успешно.
        t.send('q');self.assertEqual(t.proc.wait(timeout=3),0)

# Пояснение: При прямом запуске файла включаем стандартный unittest runner.
if __name__=='__main__':unittest.main()
