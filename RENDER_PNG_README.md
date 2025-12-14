# Render PNG Schedules

Інструкція для локального запуску скрипта рендерингу PNG графіків відключень.

## Вимоги

- Python 3.9+
- matplotlib

## Встановлення залежностей

```bash
pip install -r requirements.txt
```

Або:

```bash
pip install matplotlib
```

## Локальний запуск

### Генерувати все для сьогодні

```bash
python scripts/render_png.py --json data/Vinnytsiaoblenerho.json --out images/
```

### Генерувати конкретну чергу

```bash
python scripts/render_png.py --json data/Vinnytsiaoblenerho.json --gpv GPV1.2 --out images/gpv-1-2.png
```

### Генерувати для завтра

```bash
python scripts/render_png.py --json data/Vinnytsiaoblenerho.json --day tomorrow --out images/
```

### Генерувати для всіх регіонів

```bash
for json_file in data/*.json; do
  if [ -f "$json_file" ]; then
    region_name=$(basename "$json_file" .json)
    python scripts/render_png.py --json "$json_file" --out "images/$region_name/"
  fi
done
```

## Автоматичний запуск (GitHub Actions)

워크플로우 `.github/workflows/render-png.yml` автоматично запускається при:
- Оновленні файлів у папці `data/`
- Оновленні `scripts/render_png.py`
- Ручному запуску через "Workflow dispatch"

PNG графіки будуть автоматично згенеровані и закомічені у репозиторій.

## Структура виводу

```
images/
├── Vinnytsiaoblenerho/
│   ├── GPV1.1_today.png
│   ├── GPV1.2_today.png
│   ├── GPV1.1_tomorrow.png
│   └── ...
├── kyiv/
│   └── ...
└── ...
```

## Параметри скрипта

| Параметр | Обов'язковий | Опис |
|----------|------------|------|
| `--json` | Так | Шлях до JSON файлу з даними |
| `--gpv` | Ні | Конкретна черга (e.g. GPV1.2). Якщо не вказано, обробити всі |
| `--day` | Ні | День: `today` або `tomorrow` (за замовчуванням: `today`) |
| `--out` | Ні | Вихідний файл або директорія |
