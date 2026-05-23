import re
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler, CommandHandler
)

TOKEN = os.environ["BOT_TOKEN"]

CHOOSE_SUPPLIER, WAIT_LIST = range(2)

# ─── Прайсы ───────────────────────────────────────────────────

PRICE_MAP_KAYF = {
    6.1:   ("YouTube",       "3 month"),
    18.0:  ("YouTube",       "12 month"),
    2.5:   ("Spotify India", "Standard 1m"),
    17.5:  ("Spotify India", "Standard 12m"),
    3.7:   ("Spotify India", "Platinum 1m"),
    18.5:  ("Spotify India", "Platinum 4m 15d"),
    1.8:   ("Spotify India", "Student 1m"),
    6.0:   ("Gamma AI",      "Plus"),
    15.0:  ("Gamma AI",      "Pro"),
    10.1:  ("Suno AI",       "Pro plan 1m"),
    29.3:  ("Suno AI",       "Premier plan 1m"),
    101.0: ("Suno AI",       "Pro plan 12m"),
    8.7:   ("Grok AI",       "Super grok 1m"),
    85.0:  ("Grok AI",       "Super grok 12m"),
}

PRICE_MAP_MD = {
    5.8:    ("YouTube",       "3 month"),
    18.0:   ("YouTube",       "12 month"),
    2.2:    ("Spotify India", "Standard 1m"),
    17.0:   ("Spotify India", "Standard 12m"),
    4.0:    ("Spotify India", "Platinum 1m"),
    10.3:   ("Suno AI",       "Pro plan 1m"),
    29.0:   ("Suno AI",       "Premier plan 1m"),
    95.0:   ("Suno AI",       "Pro plan 12m"),
    290.0:  ("Suno AI",       "Premier plan 12m"),
    0.7:    ("Grok AI",       "Super grok 3 day"),
    8.5:    ("Grok AI",       "Super grok 1m"),
    78.0:   ("Grok AI",       "Super grok 12m"),
    6.4:    ("Gamma AI",      "Plus 1m"),
    16.0:   ("Gamma AI",      "Pro 1m"),
    106.0:  ("Gamma AI",      "Ultra 1m"),
    60.0:   ("Gamma AI",      "Plus 12m"),
    140.0:  ("Gamma AI",      "Pro 12m"),
    1119.0: ("Gamma AI",      "Ultra 12m"),
}

MD_CONFLICTS = {
    18.0: [("YouTube", "12 month"), ("Spotify India", "Platinum 4.5m")],
}

PRICE_MAP_USACH = {
    1.8:   ("Spotify India", "ind 1m"),
    6.0:   ("Spotify Egypt", "3m"),
    11.5:  ("Spotify Egypt", "6m"),
    20.5:  ("Spotify Egypt", "12m"),
    2.1:   ("Spotify Egypt", "Duo 1m"),
    8.0:   ("Spotify Egypt", "Duo 3m"),
    15.0:  ("Spotify Egypt", "Duo 6m"),
    30.0:  ("Spotify Egypt", "Duo 12m"),
    2.6:   ("Spotify",       "Family 1m"),
    7.5:   ("Midjourney",    "Basic"),
    19.5:  ("Midjourney",    "Standard"),
    38.0:  ("Midjourney",    "Pro"),
}

SUPPLIER_NAMES = {
    "kayf":  "КАЙФ",
    "md":    "МД",
    "usach": "УСАЧ",
}

# ─── Парсинг ──────────────────────────────────────────────────

def parse_kayf_md(text: str, supplier: str) -> dict:
    """
    Парсит строки вида: цена ИСПОЛНИТЕЛЬ
    Возвращает {цена: количество}
    """
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
    return counts

def parse_usach(text: str) -> list:
    """
    Парсит строки вида: цена УСАЧ почта
    Возвращает список [(цена, email)]
    """
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
        email = match.group(2)
        items.append((price, email))
    return items

# ─── Форматирование ───────────────────────────────────────────

def format_kayf_md(counts: dict, supplier: str) -> str:
    if not counts:
        return "❌ Не найдено ни одной строки в нужном формате."

    price_map = PRICE_MAP_KAYF if supplier == "kayf" else PRICE_MAP_MD
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
        lines.append("<b>⚠️ Уточните товар (цена совпадает у нескольких)</b>")
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

    lines = ["<b>Исполнитель: УСАЧ</b>\n"]
    grand_total = 0.0
    unknown = []

    for price, email in items:
        if price in PRICE_MAP_USACH:
            service, period = PRICE_MAP_USACH[price]
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

# ─── Handlers ────────────────────────────────────────────────

def supplier_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Кайф",  callback_data="kayf"),
        InlineKeyboardButton("МД",    callback_data="md"),
        InlineKeyboardButton("Усач",  callback_data="usach"),
    ]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери исполнителя:",
        reply_markup=supplier_keyboard()
    )
    return CHOOSE_SUPPLIER

async def choose_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    supplier = query.data
    context.user_data["supplier"] = supplier
    name = SUPPLIER_NAMES[supplier]

    if supplier == "usach":
        hint = f"Отправь список строк в формате:\n<code>цена {name} почта</code>"
    else:
        hint = f"Отправь список строк в формате:\n<code>цена {name}</code>"

    await query.edit_message_text(
        f"✅ Исполнитель: <b>{name}</b>\n\n{hint}",
        parse_mode="HTML"
    )
    return WAIT_LIST

async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    supplier = context.user_data.get("supplier")
    if not supplier:
        await start(update, context)
        return CHOOSE_SUPPLIER

    text = update.message.text or ""

    if supplier == "usach":
        items = parse_usach(text)
        response = format_usach(items)
    else:
        counts = parse_kayf_md(text, supplier)
        response = format_kayf_md(counts, supplier)

    await update.message.reply_text(response, parse_mode="HTML")
    await update.message.reply_text(
        "Выбери исполнителя для следующего списка:",
        reply_markup=supplier_keyboard()
    )
    return CHOOSE_SUPPLIER

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return CHOOSE_SUPPLIER

# ─── Main ─────────────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_any_message),
        ],
        states={
            CHOOSE_SUPPLIER: [CallbackQueryHandler(choose_supplier, pattern="^(kayf|md|usach)$")],
            WAIT_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_list)],
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
