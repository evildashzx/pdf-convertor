#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
diagnostic.py – Диагностика окружения для генерации PDF-отчётов
Проверяет версии библиотек, сохранение графиков в BytesIO,
вставку изображений в ReportLab и работу таблиц с переносом.
"""

import sys
import os
import platform
import io
import subprocess
from datetime import datetime

# --- Сбор версий ---
def get_versions():
    versions = {}
    try:
        import matplotlib
        versions['matplotlib'] = matplotlib.__version__
    except ImportError:
        versions['matplotlib'] = 'not installed'
    try:
        import reportlab
        versions['reportlab'] = reportlab.Version
    except ImportError:
        versions['reportlab'] = 'not installed'
    try:
        import pandas as pd
        versions['pandas'] = pd.__version__
    except ImportError:
        versions['pandas'] = 'not installed'
    try:
        import numpy as np
        versions['numpy'] = np.__version__
    except ImportError:
        versions['numpy'] = 'not installed'
    try:
        import seaborn as sns
        versions['seaborn'] = sns.__version__
    except ImportError:
        versions['seaborn'] = 'not installed'
    try:
        import PIL
        versions['Pillow'] = PIL.__version__
    except ImportError:
        versions['Pillow'] = 'not installed'
    return versions

def print_system_info():
    print("="*60)
    print("DIAGNOSTIC REPORT")
    print("="*60)
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"Current directory: {os.getcwd()}")
    print("\n--- Library versions ---")
    versions = get_versions()
    for lib, ver in versions.items():
        print(f"{lib:15s}: {ver}")

# --- Тест сохранения графика ---
def test_save_figure():
    print("\n--- Test 1: Saving figure to BytesIO ---")
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as e:
        print(f"FAIL: cannot import matplotlib: {e}")
        return None, None

    fig, ax = plt.subplots(figsize=(4,3))
    ax.plot([1,2,3], [1,4,9])
    ax.set_title("Test plot")

    # PNG
    png_data = io.BytesIO()
    try:
        fig.savefig(png_data, format='png', dpi=100)
        png_size = png_data.tell()
        png_data.seek(0)
        print(f"PNG saved, size: {png_size} bytes")
    except Exception as e:
        print(f"PNG save failed: {e}")
        png_data = None

    # SVG
    svg_data = io.BytesIO()
    try:
        fig.savefig(svg_data, format='svg')
        svg_size = svg_data.tell()
        svg_data.seek(0)
        print(f"SVG saved, size: {svg_size} bytes")
    except Exception as e:
        print(f"SVG save failed: {e}")
        svg_data = None

    plt.close(fig)
    return png_data, svg_data

# --- Тест вставки изображения в ReportLab ---
def test_reportlab_image(img_data, fmt='png'):
    print(f"\n--- Test 2: Insert {fmt.upper()} image into ReportLab PDF ---")
    if img_data is None:
        print("SKIP: no image data")
        return False

    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
    except ImportError as e:
        print(f"FAIL: cannot import reportlab: {e}")
        return False

    output_pdf = f"test_image_{fmt}.pdf"
    c = canvas.Canvas(output_pdf, pagesize=A4)
    try:
        if fmt == 'png':
            # Для PNG используем ImageReader (рабочий способ)
            img = ImageReader(img_data)
            c.drawImage(img, 100, 500, width=200, height=150)
        else:
            # Для SVG можно попробовать напрямую (но reportlab не поддерживает SVG)
            c.drawImage(img_data, 100, 500, width=200, height=150)
        c.save()
        print(f"PDF created: {output_pdf} (size: {os.path.getsize(output_pdf)} bytes)")
        return True
    except Exception as e:
        print(f"FAIL: {e}")
        return False

# --- Тест таблицы с длинным текстом ---
def test_table_wrap():
    print("\n--- Test 3: Table with long text ---")
    try:
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
    except ImportError as e:
        print(f"FAIL: cannot import reportlab platypus: {e}")
        return

    output_pdf = "test_table.pdf"
    doc = SimpleDocTemplate(output_pdf, pagesize=A4)
    elements = []

    # Стиль для ячейки с переносом
    cell_style = ParagraphStyle(
        'CellStyle',
        fontSize=8,
        leading=10,
        wordWrap='CJK',
    )

    data = [
        ["Short", Paragraph("This is a very long text that definitely should wrap inside the cell because it's longer than the column width", cell_style)],
        ["Another", Paragraph("Short text here", cell_style)],
    ]
    table = Table(data, colWidths=[3*cm, 10*cm])
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 1*cm))
    elements.append(Paragraph("If the long text is wrapped and not overflowing, the table is OK.", getSampleStyleSheet()['Normal']))

    try:
        doc.build(elements)
        print(f"PDF with table created: {output_pdf}")
    except Exception as e:
        print(f"FAIL: {e}")

# --- Основной запуск ---
def main():
    print_system_info()
    png_data, svg_data = test_save_figure()
    if png_data:
        test_reportlab_image(png_data, 'png')
    if svg_data:
        test_reportlab_image(svg_data, 'svg')
    test_table_wrap()
    print("\n" + "="*60)
    print("Diagnostic completed.")

if __name__ == '__main__':
    main()