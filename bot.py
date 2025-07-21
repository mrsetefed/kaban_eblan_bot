import os
import csv
import datetime
import aiohttp

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from aiohttp import web

TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_PATH = "/"
GITHUB_CSV_URL = "https://raw.githubusercontent.com/mrsetefed/kaban_eblan_bot/master/schedule.csv"

app = ApplicationBuilder().token(TOKEN).build()

# === Чтение CSV с GitHub ===
async def fetch_schedule():
    async with aiohttp.ClientSession() as session:
        async with session.get(GITHUB_CSV_URL) as response:
            if response.status != 200:
                return {}
            text = await response.text()
            reader = csv.DictReader(text.strip().splitlines())
            return {row["date"]: row["text"] for row in reader}

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отъебись.")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    today_str = datetime.date.today().isoformat()
    msg = schedule.get(today_str, "Нет данных на сегодня.")
    await update.message.reply_text(f"📅 Сегодня ({today_str}): {msg}")

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    tomorrow_str = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    msg = schedule.get(tomorrow_str, "Нет данных на завтра.")
    await update.message.reply_text(f"📅 Завтра ({tomorrow_str}): {msg}")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    today = datetime.date.today()
    result = "📅 Расписание на неделю:\n"
    for i in range(7):
        d = today + datetime.timedelta(days=i)
        d_str = d.isoformat()
        result += f"{d_str}: {schedule.get(d_str, 'нет данных')}\n"
    await update.message.reply_text(result.strip())

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    schedule = await fetch_schedule()
    today = datetime.date.today()
    result = "📅 Расписание на месяц:\n"
    for i in range(31):
        d = today + datetime.timedelta(days=i)
        d_str = d.isoformat()
        result += f"{d_str}: {schedule.get(d_str, 'нет данных')}\n"
    await update.message.reply_text(result.strip())

# === Роутинг ===
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))
app.add_handler(CommandHandler("today", today))
app.add_handler(CommandHandler("tomorrow", tomorrow))
app.add_handler(CommandHandler("week", week))
app.add_handler(CommandHandler("month", month))

# === Webhook handler ===
aio_app = web.Application()

async def handle(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(text="OK")

aio_app.add_routes([web.post(WEBHOOK_PATH, handle)])

# === Startup hook ===
async def on_startup(app_):
    await app.initialize()
    webhook_url = f"https://kaban-eblan-bot.onrender.com{WEBHOOK_PATH}"
    await app.bot.set_webhook(webhook_url)
    print(f"✅ Webhook установлен: {webhook_url}")

aio_app.on_startup.append(on_startup)

# === Запуск ===
if __name__ == "__main__":
    print("🚀 Бот запускается через вебхук...")
    web.run_app(aio_app, port=PORT)