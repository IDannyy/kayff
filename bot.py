import re
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler, CommandHandler
)

TOKEN = os.environ["BOT_TOKEN"]

# Состояния
CHOOSE_ACTION, WAIT_LIST, WAIT_ITOG, WAIT_PRAIS_SUPPLIER, WAIT_PRAIS_TEXT, RESOLVE_CONFLICT = range(6)

# Админы
ADMINS = {400585777, 5346568515, 1868086123}

PRICE_FILE = "prices.json"

# ─── Конфликты по исполнителю ─────────────────────────────────

CONFLICTS = {
    "kayf": {
        6.0: [("YouTube", "3 month"), ("Gamma AI", "Plus")],
    },
    "md": {
        18.0: [("YouTube", "12 month"), ("Spotify India", "Platinum 4.5m")],
    },
    "usach": {},
}

# ─── Дефолтные прайсы ─────────────────────────────────────────

DEFAULT_PRICES = {
    "kayf": {
        "6.0":   ["YouTube",       "3 month"],
        "17.8":  ["YouTube",       "12 month"],
        "2.5":   ["Spotify India", "Standard 1m"],
        "17.0":  ["Spotify India", "Standard 12m"],
        "3.7":   ["Spotify India", "Platinum 1m"],
        "18.5":  ["Spotify India", "Platinum 4m 15d"],
        "1.8":   ["Spotify India", "Student 1m"],
        "14.7":  ["Gamma AI",      "Pro"],
        "10.1":  ["Suno AI",       "Pro plan 1m"],
        "29.3":  ["Suno AI",       "Premier plan 1m"],
        "101.0": ["Suno AI",       "Pro plan 12m"],
        "8.7":   ["Grok AI",       "Super grok 1m"],
        "85.0":  ["Grok AI",       "Super grok 12m"],
    },
    "md": {
        "5.8":    ["YouTube",       "3 month"],
        "2.2":    ["Spotify India", "Standard 1m"],
        "17.0":   ["Spotify India", "Standard 12m"],
        "4.0":    ["Spotify India", "Platinum 1m"],
        "10.3":   ["Suno AI",       "Pro plan 1m"],
        "29.0":   ["Suno AI",       "Premier plan 1m"],
        "95.0":   ["Suno AI",       "Pro plan 12m"],
        "290.0":  ["Suno AI",       "Premier plan 12m"],
        "0.7":    ["Grok AI",       "Super grok 3 day"],
        "8.5":    ["Grok AI",       "Super grok 1m"],
        "78.0":   ["Grok AI",       "Super grok 12m"],
        "6.4":    ["Gamma AI",      "Plus 1m"],
        "16.0":   ["Gamma AI",      "Pro 1m"],
        "106.0":  ["Gamma AI",      "Ultra 1m"],
        "60.0":   ["Gamma AI",      "Plus 12m"],
        "140.0":  ["Gamma AI",      "Pro 12m"],
        "1119.0": ["Gamma AI",      "Ultra 12m"],
    },
    "usach": {
        "1.8":   ["Spotify India", "ind 1m"],
        "6.0":   ["Spotify Egypt", "3m"],
        "11.5":  ["Spotify Egypt", "6m"],
        "20.5":  ["Spotify Egypt", "12m"],
        "2.1":   ["Spotify Egypt", "Duo 1m"],
        "8.0":   ["Spotify Egypt", "Duo 3m"],
        "15.0":  ["Spotify Egypt", "Duo 6m"],
        "30.0":  ["Spotify Egypt", "Duo 12m"],
        "2.6":   ["Spotify",       "Family 1m"],
        "7.5":   ["Midjourney",    "Basic"],
        "19.5":  ["Midjourney",    "Standard"],
        "38.0":  ["Midjourney",    "Pro"],
    },
}

SUPPLIER_NAMES = {
    "kayf":  "КАЙФ",
    "md":    "МД",
    "usach": "УСАЧ",
}

# ─── Прайс ────────────────────────────────────────────────────

def load_prices() -> dict:
    if os.path.exists(PRICE_FILE):
        try:
            with open(PRICE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {k: dict(v) for k, v in DEFAULT_PRICES.items()}

def save_prices(prices: dict):
    with open(PRICE_FILE, "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)

def get_price_map(supplier: str) -> dict:
    prices = load_prices()
    raw = prices.get(supplier, {})
    return {float(k): v for k, v in raw.items()}

def parse_new_prais(text: str) -> dict:
    result = {}
    current_service = "Неизвестно"
    service_keywords = {
        "youtube": "YouTube", "spotify": "Spotify",
        "suno": "Suno AI", "grok": "Grok AI",
        "gamma": "Gamma AI", "midjourney": "Midjourney",
    }
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        for kw, svc in service_keywords.items():
            if kw in lower and not re.search(r'\d', line):
                current_service = svc
                break
        price_match = re.search(r'([\d]+[.,][\d]+|[\d]+)\s*\$?', line)
        if not price_match:
            continue
        price_str = price_match.group(1).replace(",", ".")
        try:
            price_float = float(price_str)
        except ValueError:
            continue
        period = line[:price_match.start()].strip().rstrip("-— ").strip()
        if not period:
            continue
        result[str(price_float)] = [current_service, period]
    return result

# ─── Парсинг ──────────────────────────────────────────────────

def parse_supplier_list(text: str, supplier: str):
    """
    Возвращает:
      - для usach: ([], [(price, email), ...])
      - для остальных: ([(price, qty), ...], [])
    """
    if supplier == "usach":
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(
                r'^([\d][0-9]*[.,][0-9]+|[0-9]+)\s+УСАЧ\s+(\S+)',
                line, re.IGNORECASE
            )
            if not match:
                continue
            try:
                price = float(match.group(1).replace(",", "."))
            except ValueError:
                continue
            items.append((price, match.group(2)))
        return [], items
    else:
        word = SUPPLIER_NAMES[supplier]
        counts = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(
                rf'^([\d][0-9]*[.,][0-9]+|[0-9]+)\s+{re.escape(word)}\b',
                line, re.IGNORECASE
            )
            if not match:
                continue
            try:
                price = float(match.group(1).replace(",", "."))
            except ValueError:
                continue
            counts[price] = counts.get(price, 0) + 1
        return list(counts.items()), []

# ─── Форматирование ───────────────────────────────────────────

def build_result_text(resolved: list, supplier: str) -> str:
    """
    resolved: [(service, period, qty, price), ...]
    """
    service_lines = {}
    for service, period, qty, price in resolved:
        service_lines.setdefault(service, []).append((period, qty, price))

    lines = [f"<b>Исполнитель: {SUPPLIER_NAMES[supplier]}</b>\n"]
    totals = []
    grand_total = 0.0

    for service, items in service_lines.items():
        lines.append(f"<b>{service}</b>")
        for period, qty, price in items:
            subtotal = qty * price
            grand_total += subtotal
            totals.append(f"{subtotal:.2f}")
            lines.append(f"{period} {qty}×{price}={subtotal:.2f}")
        lines.append("")

    if totals:
        lines.append("+".join(totals) + f"={grand_total:.2f} USDT")

    return "\n".join(lines).strip()

def format_usach(items: list) -> str:
    if not items:
        return "❌ Не найдено ни одной строки формата «цена УСАЧ почта»."
    price_map = get_price_map("usach")
    lines = ["<b>Исполнитель: УСАЧ</b>\n"]
    grand_total = 0.0
    unknown = []
    for price, email in items:
        if price in price_map:
            service, period = price_map[price]
            lines.append(f"{period} {email} {price} usdt")
            grand_total += price
        else:
            unknown.append((price, email))
    if unknown:
        lines.append("\n<b>⚠️ Неизвестные цены</b>")
        for price, email in unknown:
            lines.append(f"{price} {email}")
    lines.append(f"\nTOTAL {grand_total:.2f} usdt")
    return "\n".join(lines).strip()

def format_itog(text: str) -> str:
    matches = re.findall(r'=([\d]+\.[\d]+)\s*USDT', text)
    if not matches:
        return "❌ Не найдено ни одной строки с итогом (формат: =XX.XX USDT)."
    total = 0.0
    lines = ["<b>📊 Итог</b>\n"]
    for val in matches:
        amount = float(val)
        total += amount
        lines.append(f"• {amount:.2f} USDT")
    lines.append(f"\n<b>TOTAL: {total:.2f} USDT</b>")
    return "\n".join(lines)

# ─── Обработка конфликтов ─────────────────────────────────────

def process_counts(counts: list, supplier: str):
    """
    Разбирает список (price, qty) на:
      resolved: [(service, period, qty, price)]
      conflicts_queue: [(price, qty, options)] — требуют уточнения
      unknown: [(price, qty)]
    """
    price_map = get_price_map(supplier)
    supplier_conflicts = CONFLICTS.get(supplier, {})
    resolved = []
    conflicts_queue = []
    unknown = []

    for price, qty in sorted(counts):
        if price in supplier_conflicts:
            # Добавляем в очередь qty раз (по одному)
            for _ in range(qty):
                conflicts_queue.append((price, 1, supplier_conflicts[price]))
        elif price in price_map:
            service, period = price_map[price]
            resolved.append((service, period, qty, price))
        else:
            unknown.append((price, qty))

    return resolved, conflicts_queue, unknown

# ─── Клавиатуры ───────────────────────────────────────────────

def main_keyboard(user_id: int):
    buttons = [
        [
            InlineKeyboardButton("Кайф",  callback_data="sup_kayf"),
            InlineKeyboardButton("МД",    callback_data="sup_md"),
            InlineKeyboardButton("Усач",  callback_data="sup_usach"),
        ],
        [InlineKeyboardButton("📊 Итог", callback_data="action_itog")],
    ]
    if user_id in ADMINS:
        buttons.append([InlineKeyboardButton("🔄 Обновить прайс", callback_data="action_prais")])
    return InlineKeyboardMarkup(buttons)

def conflict_keyboard(price: float, options: list):
    buttons = []
    for i, (service, period) in enumerate(options):
        buttons.append([InlineKeyboardButton(
            f"{service} {period}",
            callback_data=f"resolve_{i}"
        )])
    return InlineKeyboardMarkup(buttons)

def prais_supplier_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Кайф",  callback_data="prais_kayf"),
        InlineKeyboardButton("МД",    callback_data="prais_md"),
        InlineKeyboardButton("Усач",  callback_data="prais_usach"),
    ]])

# ─── Handlers ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "Выбери действие:",
        reply_markup=main_keyboard(user_id)
    )
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("sup_"):
        supplier = data[4:]
        context.user_data["supplier"] = supplier
        name = SUPPLIER_NAMES[supplier]
        hint = f"цена {name} почта" if supplier == "usach" else f"цена {name}"
        await query.edit_message_text(
            f"✅ Исполнитель: <b>{name}</b>\n\nОтправь список строк:\n<code>{hint}</code>",
            parse_mode="HTML"
        )
        return WAIT_LIST

    elif data == "action_itog":
        await query.edit_message_text(
            "📊 <b>Итог</b>\n\nОтправь выписки:",
            parse_mode="HTML"
        )
        return WAIT_ITOG

    elif data == "action_prais" and user_id in ADMINS:
        await query.edit_message_text(
            "🔄 <b>Обновление прайса</b>\n\nВыбери исполнителя:",
            parse_mode="HTML",
            reply_markup=prais_supplier_keyboard()
        )
        return WAIT_PRAIS_SUPPLIER

    return CHOOSE_ACTION

async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    supplier = context.user_data.get("supplier")
    user_id = update.effective_user.id
    if not supplier:
        await start(update, context)
        return CHOOSE_ACTION

    text = update.message.text or ""
    counts, usach_items = parse_supplier_list(text, supplier)

    if supplier == "usach":
        response = format_usach(usach_items)
        await update.message.reply_text(response, parse_mode="HTML")
        await update.message.reply_text("Выбери действие:", reply_markup=main_keyboard(user_id))
        return CHOOSE_ACTION

    resolved, conflicts_queue, unknown = process_counts(counts, supplier)

    # Сохраняем в контекст
    context.user_data["resolved"] = resolved
    context.user_data["conflicts_queue"] = conflicts_queue
    context.user_data["unknown"] = unknown

    if conflicts_queue:
        # Спрашиваем первый конфликт
        price, qty, options = conflicts_queue[0]
        await update.message.reply_text(
            f"❓ Цена <b>{price}$</b> — что это за товар?",
            parse_mode="HTML",
            reply_markup=conflict_keyboard(price, options)
        )
        return RESOLVE_CONFLICT

    # Конфликтов нет — сразу выводим
    await _send_result(update, context, resolved, unknown, supplier)
    return CHOOSE_ACTION

async def resolve_conflict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    choice_idx = int(query.data.split("_")[1])
    supplier = context.user_data.get("supplier")
    conflicts_queue = context.user_data.get("conflicts_queue", [])
    resolved = context.user_data.get("resolved", [])

    # Берём текущий конфликт
    price, qty, options = conflicts_queue.pop(0)
    service, period = options[choice_idx]
    resolved.append((service, period, qty, price))

    context.user_data["resolved"] = resolved
    context.user_data["conflicts_queue"] = conflicts_queue

    if conflicts_queue:
        # Следующий конфликт
        next_price, next_qty, next_options = conflicts_queue[0]
        await query.edit_message_text(
            f"❓ Цена <b>{next_price}$</b> — что это за товар?",
            parse_mode="HTML",
            reply_markup=conflict_keyboard(next_price, next_options)
        )
        return RESOLVE_CONFLICT

    # Все конфликты решены
    unknown = context.user_data.get("unknown", [])
    await query.delete_message()
    await _send_result_query(query, context, resolved, unknown, supplier, user_id)
    return CHOOSE_ACTION

async def _send_result(update, context, resolved, unknown, supplier):
    user_id = update.effective_user.id
    text = build_result_text(resolved, supplier)
    if unknown:
        text += "\n\n<b>⚠️ Неизвестные цены</b>\n"
        for price, qty in unknown:
            text += f"{price} — {qty} шт.\n"
    await update.message.reply_text(text, parse_mode="HTML")
    await update.message.reply_text("Выбери действие:", reply_markup=main_keyboard(user_id))

async def _send_result_query(query, context, resolved, unknown, supplier, user_id):
    text = build_result_text(resolved, supplier)
    if unknown:
        text += "\n\n<b>⚠️ Неизвестные цены</b>\n"
        for price, qty in unknown:
            text += f"{price} — {qty} шт.\n"
    await query.message.reply_text(text, parse_mode="HTML")
    await query.message.reply_text("Выбери действие:", reply_markup=main_keyboard(user_id))

async def handle_itog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text or ""
    response = format_itog(text)
    await update.message.reply_text(response, parse_mode="HTML")
    await update.message.reply_text("Выбери действие:", reply_markup=main_keyboard(user_id))
    return CHOOSE_ACTION

async def choose_prais_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    supplier = query.data[6:]
    context.user_data["prais_supplier"] = supplier
    name = SUPPLIER_NAMES[supplier]
    await query.edit_message_text(
        f"🔄 Обновление прайса <b>{name}</b>\n\nОтправь новый прайс текстом:",
        parse_mode="HTML"
    )
    return WAIT_PRAIS_TEXT

async def handle_prais_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("❌ Нет доступа.")
        return CHOOSE_ACTION

    supplier = context.user_data.get("prais_supplier")
    text = update.message.text or ""
    new_map = parse_new_prais(text)

    if not new_map:
        await update.message.reply_text(
            "❌ Не удалось распознать прайс.",
            reply_markup=main_keyboard(user_id)
        )
        return CHOOSE_ACTION

    prices = load_prices()
    prices[supplier] = new_map
    save_prices(prices)

    name = SUPPLIER_NAMES[supplier]
    lines = [f"✅ Прайс <b>{name}</b> обновлён ({len(new_map)} позиций):\n"]
    for k, v in new_map.items():
        lines.append(f"• {v[0]} {v[1]} — {k}$")

    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML",
        reply_markup=main_keyboard(user_id)
    )
    return CHOOSE_ACTION

async def handle_any(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return CHOOSE_ACTION

# ─── Main ─────────────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_any),
        ],
        states={
            CHOOSE_ACTION: [
                CallbackQueryHandler(choose_action, pattern="^(sup_|action_)"),
            ],
            WAIT_LIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_list),
            ],
            RESOLVE_CONFLICT: [
                CallbackQueryHandler(resolve_conflict, pattern="^resolve_"),
            ],
            WAIT_ITOG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_itog),
            ],
            WAIT_PRAIS_SUPPLIER: [
                CallbackQueryHandler(choose_prais_supplier, pattern="^prais_"),
            ],
            WAIT_PRAIS_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prais_text),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        per_user=True,
        per_chat=True,
    )

    app.add_handler(conv)
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
