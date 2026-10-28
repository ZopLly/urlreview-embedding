"""Generate fictional examples only; never reads a working dataset."""
import csv
from pathlib import Path

root=Path(__file__).resolve().parents[1]
description=(
    'Вымышленный магазин инструментов и оборудования для мастерских. '
    'Предлагает дрели, станки, измерительные приборы и защитную одежду. '
    'Можно выбрать товар, оформить заказ и уточнить условия доставки. '
    'Пример текста с разделителем; и "кавычками".\n'
)
rows=[['domain','class','label','action','description'],
      ['tools.example','electronic_commerce','','',description*55+'КОНЕЦ ДЛИННОГО ОПИСАНИЯ.'],
      ['books.example','reference_material','','','Вымышленный справочный ресурс: словари, энциклопедии и библиотечные каталоги.'],
      ['music.example','music','','','Вымышленный сайт о музыкальных исполнителях, альбомах и концертах.'],
      ['bank.example','finance','','OK','Вымышленный банк: счета, кредиты, карты и ипотека. Эта запись уже проверена для демонстрации продолжения работы.']]
with (root/'demo/synthetic.csv').open('w',encoding='utf-8',newline='') as f:
    csv.writer(f,delimiter=';',lineterminator='\r\n').writerows(rows)
print('Created fictional demo: 4 records; one description >12000 characters.')
