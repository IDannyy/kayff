import re
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]

# Прайс — цена: (название, период)
PRICE_MAP = {
    6.1:   ("YouTube",          "3 month"),
    18.0:  ("YouTube",          "12 month"),
    2.5:   ("Spotify India",    "Standard 1m"),
    17.5:  ("Spotify India",    "Standard 12m"),
    3.7:   ("Spotify India",    "Platinum 1m"),
    18.5:  ("Spotify India",    "Platinum 4m 15d"),
    1.8:   ("Spotify India",    "Student 1m"),
    6.0:   ("Gamma AI",         "Plus"),
    15.0:  ("Gamma AI",         "Pro"),
    10.1:  ("Suno AI",          "Pro plan 1m"),
    29.3:  ("Suno AI",          "Premier plan 1m"),
    101.0: ("Suno AI",          "Pro plan 12m"),
    8.7:   ("Grok AI",          "Super grok 1m"),
    85.0:  ("Grok AI",          "Super grok 12m"),
}

def parse_message(text: str) -> dict:
    counts = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^([\d][0-9]*[.,][0-9]+|[0-9]+)\s+Кайф\b', line, re.IGNORECASE)
        if not match:
            continue
        price_str = match.group(1).replace(",", ".")
        try:
            price = float(price_str)
        except ValueError:
            continue
        counts[price] = counts.get(price, 0) + 1
    return counts

def format_response(counts: dict) -> str:
    if not counts:
        return "❌ Не найдено ни одной строки формата «цена Кайф»."

    service_lines = {}
    unknown = []

    for price, qty in sorted(counts.items()):
        if price in PRICE_MAP:
            service, period = PRICE_MAP[price]
            service_lines.setdefault(service, []).append((period, qty, price))
        else:
            unknown.append((price, qty))

    lines = []
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

    if unknown:
        lines.append("<b>⚠️ Неизвестные цены</b>")
        for price, qty in unknown:
            lines.append(f"{price} — {qty} шт. (не найдено в прайсе)")
        lines.append("")

    sum_str = "+".join(totals) + f"={grand_total:.2f} USDT"
    lines.append(sum_str)

    return "\n".join(lines).strip()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    counts = parse_message(text)
    response = format_response(counts)
    await update.message.reply_text(response, parse_mode="HTML")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
