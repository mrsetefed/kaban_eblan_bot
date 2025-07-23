from telegram.ext import CommandHandler
from . import start, ping, today, tomorrow, week, verify, krutometr, kogda_strad, kogda_wd, upd, help, vlasuka

def get_handlers():
    return [
        CommandHandler("help", help.help),
        CommandHandler("start", start.start),
        CommandHandler("ping", ping.ping),
        CommandHandler("today", today.today),
        CommandHandler("tomorrow", tomorrow.tomorrow),
        CommandHandler("week", week.week),
        CommandHandler("verify",verify.verify),
        CommandHandler("krutometr",krutometr.krutometr),
        CommandHandler("kogda_strad", kogda_strad.kogda_strad),
        CommandHandler("kogda_wd", kogda_wd.kogda_wd),
        CommandHandler("vlasuka", vlasuka.vlasuka),
        CommandHandler("upd", upd.upd)
    ]