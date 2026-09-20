from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, PollAnswerHandler
from . import poll_tracker, krutometr_stats, roll, quote, skoro, slot, taro
from . import start, ping, today, verify, krutometr, kogda_strad, kogda_wd, upd, help, vlasuka, tomorrow, week, kogda_kamputer, kogda_dnd, mog

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
        CommandHandler("upd", upd.upd),
        CommandHandler("kogda_kamputer", kogda_kamputer.kogda_kamputer),
        CommandHandler("kogda_dnd", kogda_dnd.kogda_dnd),
        CommandHandler("mog", mog.mog),
        CommandHandler("roll", roll.roll),
        CommandHandler("quote", quote.quote),
        CommandHandler("skoro", skoro.skoro),
        CommandHandler("top", krutometr_stats.top),
        CommandHandler("taro", taro.taro),
        PollAnswerHandler(poll_tracker.on_poll_answer),
        CallbackQueryHandler(upd.upd_callback, pattern=r"^u\|"),
        # 🎰 кубиком, стикером-эмодзи или просто текстом (с невидимым селектором или без)
        MessageHandler(slot.SLOT_MESSAGE, slot.react)
    ]