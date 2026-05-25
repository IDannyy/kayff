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
CHOOSE_ACTION, CHOOSE_SUPPLIER, WAIT_LIST, WAIT_ITOG, WAIT_PRAIS_SUPPLIER, WAIT_PRAIS_TEXT = range(6)

# Админы
ADMINS = {400585777, 5346568515, 1868086123}

# Файл с прайсами
PRICE_FILE = "prices.json"

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
        "15.0":  ["Gamma AI",      "Pro"],
        "10.1":  ["Suno AI",       "Pro plan 1m"],
        "29.3":  ["Suno AI",       "Premier plan 1m"],
        "101.0": ["Suno AI",       "Pro plan 12m"],
        "8.7":   ["Grok AI",       "Super grok 1m"],
        "85.0":  ["Grok AI",       "Super grok 12m"],
    },
    "md": {
        "5.8":    ["YouTube",       "3 month"],
        "18.0":   ["YouTube",       "12 month"],
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

MD_CONFLICTS = {
    18.0: [("YouTube", "12 month"), ("Spotify India", "Platinum 4.5m")],
}

SUPPLIER_NAMES = {
    "kayf":  "КАЙФ",
    "md":    "МД",
    "usach": "УСАЧ",
}

# ─── Работа с прайсом ─────────────────────────────────────────

def load_prices() -> dict:
    if os.path.exists(PRICE_FILE):
        try:
            with open(PRICE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_PRICES.copy()

def save_prices(prices: dict):
    with open(PRICE_FILE, "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)

def get_price_map(supplier: str) -> dict:
    prices = load_prices()
    raw = prices.get(supplier, {})
    return {float(k): v for k, v in raw.items()}

def parse_new_prais(text: str) -> dict:
    """
    Парсит новый прайс в формате:
    YouTube 3 month 6,1$
    Standard 12m 17,5$
    Возвращает {цена_str: [сервис, период]} или None если не распознан.
    """
    result = {}
    current_service = "Неизвестно"
    service_keywords = {
        "youtube": "YouTube",
        "spotify": "Spotify",
        "suno": "Suno AI",
        "grok": "Grok AI",
        "gamma": "Gamma AI",
        "midjourney": "Midjourney",
    }
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Проверяем заголовок сервиса
        lower = line.lower()
        for kw, svc in service_keywords.items():
            if kw in lower and not re.search(r'\d', line):
                current_service = svc
                break
        # Ищем цену в строке
        price_match = re.search(r'([\d]+[.,][\d]+|[\d]+)\s*\$?', line)
        if not price_match:
            continue
        price_str = price_match.group(1).replace(",", ".")
        try:
            price_float = float(price_str)
        except ValueError:
            continue
        # Период — всё до цены
        period = line[:price_match.start()].strip().rstrip("-— ").strip()
        if not period:
            continue
        key = str(price_float)
        result[key] = [current_service, period]
    return result

# ─── Парсинг выписок ──────────────────────────────────────────

def parse_supplier_list(text: str, supplier: str) -> tuple:
    """Возвращает (counts_dict, items_list) — items только для усача."""
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
        return {}, items
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
        return counts, []

# ─── Форматирование ───────────────────────────────────────────

def format_kayf_md(counts: dict, supplier: str) -> str:
    if not counts:
        return "❌ Не найдено ни одной строки в нужном формате."

    price_map = get_price_map(supplier)
    conflicts = MD_CONFLICTS if supplier == "md" else {}
    service_lines = {}
    unknown = []
    conflict_found = []

    for price, qty in sorted(counts.items()):
        if price in conflicts:
            conflict_found.append((price, qty))
        elif price in price_map:
            service, period = price_map[price]
            service_lines.setdefault(service, []).append((period, qty, price))
        else:
            unknown.append((price, qty))

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

    if conflict_found:
        lines.append("<b>⚠️ Уточните товар</b>")
        for price, qty in conflict_found:
            options = ", ".join(f"{s} {p}" for s, p in conflicts[price])
            lines.append(f"{price}$ × {qty} шт. — варианты: {options}")
        lines.append("")

    if unknown:
        lines.append("<b>⚠️ Неизвестные цены</b>")
        for price, qty in unknown:
            lines.append(f"{price} — {qty} шт.")
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
    """Парсит готовые выписки, суммирует все =X.XX USDT."""
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
            f"✅ Исполнитель: <b>{name}</b>\n\nОтправь список строк в формате:\n<code>{hint}</code>",
            parse_mode="HTML"
        )
        return WAIT_LIST

    elif data == "action_itog":
        await query.edit_message_text(
            "📊 <b>Итог</b>\n\nОтправь выписки — бот найдёт все суммы и сложит total.",
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

async def choose_prais_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    supplier = query.data[6:]  # prais_kayf → kayf
    context.user_data["prais_supplier"] = supplier
    name = SUPPLIER_NAMES[supplier]
    await query.edit_message_text(
        f"🔄 Обновление прайса <b>{name}</b>\n\nОтправь новый прайс текстом, например:\n"
        f"<code>YouTube 3 month 6,1$\n12 month 18$\nSpotify Standard 1m 2.5$</code>",
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
            "❌ Не удалось распознать прайс. Проверь формат.",
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
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=main_keyboard(user_id)
    )
    return CHOOSE_ACTION

async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    supplier = context.user_data.get("supplier")
    user_id = update.effective_user.id
    if not supplier:
        await start(update, context)
        return CHOOSE_ACTION

    text = update.message.text or ""
    counts, items = parse_supplier_list(text, supplier)

    if supplier == "usach":
        response = format_usach(items)
    else:
        response = format_kayf_md(counts, supplier)

    await update.message.reply_text(response, parse_mode="HTML")
    await update.message.reply_text(
        "Выбери действие:",
        reply_markup=main_keyboard(user_id)
    )
    return CHOOSE_ACTION

async def handle_itog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text or ""
    response = format_itog(text)
    await update.message.reply_text(response, parse_mode="HTML")
    await update.message.reply_text(
        "Выбери действие:",
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
