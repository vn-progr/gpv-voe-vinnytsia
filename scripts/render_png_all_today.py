def render_all_schedules(json_path, out_path=None, force=False):
    """Рендерити всі графіки на сьогодні в одну таблицю"""
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fact_data = data.get('fact', {}).get('data', {})
    sch_names = data.get('preset', {}).get('sch_names', {})
    last_updated = data.get('fact', {}).get('update', '')

    if not fact_data:
        print("[SKIP] gpv-all-today.png (fact.data is empty)")
        return

    # Безпечне визначення сьогоднішнього timestamp
    available_days = sorted(list(fact_data.keys()))
    today_ts = str(data.get('fact', {}).get('today', ''))
    if today_ts not in fact_data:
        today_ts = available_days[0]

    today_data = fact_data.get(today_ts, {})

    out_p = Path(out_path) if out_path else Path('.')
    out_p.mkdir(parents=True, exist_ok=True)
    hash_dir = out_p / 'hash'

    new_hash = calculate_all_today_hash(today_data)
    prev_hash = load_previous_hash(hash_dir)
    output_file = out_p / 'gpv-all-today.png'

    today_date = datetime.fromtimestamp(int(today_ts), tz=KYIV_TZ)
    today_date_code = today_date.strftime('%Y-%m-%d')
    prev_date = load_previous_date(hash_dir)

    date_changed = (prev_date != today_date_code)
    hash_changed = (new_hash != prev_hash)

    if force:
        print(f"[REGEN] gpv-all-today.png (forced)")
        regenerate = True
    elif not output_file.exists():
        print(f"[REGEN] gpv-all-today.png (file not found)")
        regenerate = True
    elif hash_changed:
        print(f"[REGEN] gpv-all-today.png (hash changed)")
        regenerate = True
    elif date_changed:
        print(f"[REGEN] gpv-all-today.png (date changed: {prev_date} → {today_date_code})")
        regenerate = True
    else:
        print(f"[SKIP] gpv-all-today.png (no changes)")
        regenerate = False

    if not regenerate:
        return

    months_uk = {
        1: 'січня', 2: 'лютого', 3: 'березня', 4: 'квітня',
        5: 'травня', 6: 'червня', 7: 'липня', 8: 'серпня',
        9: 'вересня', 10: 'жовтня', 11: 'листопада', 12: 'грудня'
    }
    today_str = f'{today_date.day:02d} {months_uk[today_date.month]}'

    gpv_keys = sorted([k for k in today_data if k.startswith('GPV')])
    num_schedules = len(gpv_keys)

    if num_schedules == 0:
        print(f"[SKIP] gpv-all-today.png (No GPV schedules found in ts {today_ts})")
        return

    print(f"[GENERATE] gpv-all-today.png for {today_date.strftime('%d.%m.%Y')}")

    cell_w, cell_h, label_w, header_h = 1.0, 0.55, 2.4, 1.3
    table_width = label_w + 24 * cell_w
    table_height = header_h + num_schedules * cell_h
    fig_height = 2.0 + (num_schedules * 0.45)

    fig, ax = plt.subplots(figsize=(18, fig_height), dpi=160)
    fig.patch.set_facecolor(WHITE)
    ax.set_facecolor(WHITE)

    y_pos = 0

    # Шапка
    rect = Rectangle((0, y_pos), label_w, header_h, linewidth=1.2, edgecolor=BORDER, facecolor=GRAY_HEADER)
    ax.add_patch(rect)
    ax.text(label_w/2, y_pos + header_h/2, 'Черга', fontsize=12, ha='center', va='center', fontweight='bold', color=TEXT_DARK)

    for i in range(24):
        x = label_w + i * cell_w
        rect = Rectangle((x, y_pos), cell_w, header_h, linewidth=1.2, edgecolor=BORDER, facecolor=GRAY_HEADER)
        ax.add_patch(rect)
        ax.text(x + cell_w/2, y_pos + header_h/2, HOURS_TEXT[i], fontsize=10, ha='center', va='center', fontweight='bold', color=TEXT_DARK, linespacing=1.2)

    y_pos += header_h

    # Рядки
    for gpv_key in gpv_keys:
        slots = today_data.get(gpv_key, {str(i): 'yes' for i in range(1, 25)})
        queue_name = sch_names.get(gpv_key, gpv_key)

        rect = Rectangle((0, y_pos), label_w, cell_h, linewidth=1.2, edgecolor=BORDER, facecolor=GRAY_LABEL)
        ax.add_patch(rect)
        ax.text(label_w/2, y_pos + cell_h/2, queue_name, fontsize=11, ha='center', va='center', fontweight='bold', color=TEXT_DARK)

        for i, slot_num in enumerate(SLOTS):
            x = label_w + i * cell_w
            state = slots.get(str(slot_num), 'yes')

            rect = Rectangle((x, y_pos), cell_w, cell_h, linewidth=1.2, edgecolor=BORDER, facecolor=WHITE)
            ax.add_patch(rect)

            if state == 'no':
                ax.add_patch(Rectangle((x, y_pos), cell_w, cell_h, linewidth=0, facecolor=ORANGE))
            elif state == 'first':
                ax.add_patch(Rectangle((x, y_pos), cell_w/2, cell_h, linewidth=0, facecolor=ORANGE))
            elif state == 'second':
                ax.add_patch(Rectangle((x + cell_w/2, y_pos), cell_w/2, cell_h, linewidth=0, facecolor=ORANGE))

            ax.add_patch(Rectangle((x, y_pos), cell_w, cell_h, linewidth=1.2, edgecolor=BORDER, facecolor='none'))

        y_pos += cell_h

    ax.set_xlim(0, table_width)
    ax.set_ylim(0, table_height)
    ax.invert_yaxis()
    ax.axis('off')

    # Оновлений заголовок
    fig.text(0.05, 0.96, f'Графік відключень на сьогодні — {today_str} (Вінницька обл.)',
             fontsize=17, fontweight='bold', color=TEXT_DARK)

    # Легенда
    legend_y = 0.02
    fig.patches.clear()

    rect1 = Rectangle((0.08, legend_y), 0.03, 0.035, linewidth=1, edgecolor=BORDER, facecolor=WHITE, transform=fig.transFigure)
    fig.patches.append(rect1)
    fig.text(0.12, legend_y + 0.015, 'Світло є', fontsize=11, va='center', color=TEXT_DARK)

    rect2 = Rectangle((0.26, legend_y), 0.03, 0.035, linewidth=1, edgecolor=BORDER, facecolor=ORANGE, transform=fig.transFigure)
    fig.patches.append(rect2)
    fig.text(0.30, legend_y + 0.015, 'Світла нема', fontsize=11, va='center', color=TEXT_DARK)

    rect3_bg = Rectangle((0.45, legend_y), 0.03, 0.035, linewidth=1, edgecolor=BORDER, facecolor=WHITE, transform=fig.transFigure)
    rect3_fill = Rectangle((0.45, legend_y), 0.015, 0.035, linewidth=0, facecolor=ORANGE, transform=fig.transFigure)
    fig.patches.extend([rect3_bg, rect3_fill])
    fig.text(0.49, legend_y + 0.015, 'Світла нема перші 30 хв.', fontsize=11, va='center', color=TEXT_DARK)

    rect4_bg = Rectangle((0.68, legend_y), 0.03, 0.035, linewidth=1, edgecolor=BORDER, facecolor=WHITE, transform=fig.transFigure)
    rect4_fill = Rectangle((0.68 + 0.015, legend_y), 0.015, 0.035, linewidth=0, facecolor=ORANGE, transform=fig.transFigure)
    fig.patches.extend([rect4_bg, rect4_fill])
    fig.text(0.72, legend_y + 0.015, 'Світла нема другі 30 хв.', fontsize=11, va='center', color=TEXT_DARK)

    if last_updated:
        fig.text(0.95, 0.005, f'Оновлено {last_updated}', fontsize=10, ha='right', style='italic', color='#555555')

    plt.savefig(output_file, facecolor=WHITE, dpi=160, bbox_inches='tight', pad_inches=0.15)
    print(f"[OK] Saved {output_file}")

    save_hash(hash_dir, new_hash)
    save_date(hash_dir, today_date_code)
    plt.close()
