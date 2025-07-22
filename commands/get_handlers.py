from telegram.ext import CommandHandler
from . import start, ping, today, tomorrow, week, verify, krutometr

def get_handlers():
    return [
        CommandHandler("start", start.start),
        CommandHandler("ping", ping.ping),
        CommandHandler("today", today.today),
        CommandHandler("tomorrow", tomorrow.tomorrow),
        CommandHandler("week", week.week),
        CommandHandler("verify",verify.verify),
        CommandHandler("krutometr",krutometr.krutometr),
    ]