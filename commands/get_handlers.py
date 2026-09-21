from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, PollAnswerHandler
from . import poll_tracker, krutometr_stats, roll, quote, skoro, slot, taro, otmena, media, six_seven, ban
from . import start, ping, today, verify, krutometr, kogda_strad, kogda_wd, upd, help, vlasuka, tomorrow, week, kogda_kamputer, kogda_dnd, mog

def get_handlers():
    handlers = [
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
        CommandHandler("unquote", quote.unquote),
        CommandHandler("skoro", skoro.skoro),
        CommandHandler("otmena", otmena.otmena),
        CommandHandler("top", krutometr_stats.top),
        CommandHandler("media", media.media),
        CommandHandler("taro", taro.taro),
        PollAnswerHandler(poll_tracker.on_poll_answer),
        CallbackQueryHandler(upd.upd_callback, pattern=r"^u\|"),
        CallbackQueryHandler(vlasuka.vlasuka_callback, pattern=r"^v\|"),
        CallbackQueryHandler(media.media_callback, pattern=r"^m\|"),
        # медиа и ссылки от того, кто наполняет блок через /media (остальных фильтр не пропускает)
        MessageHandler(media.PENDING_INPUT, media.on_media),
        # ответ владельца календаря на запрос комментария; чужие сообщения фильтр не пропускает, они идут дальше
        MessageHandler(vlasuka.PENDING_REPLY, vlasuka.on_comment_reply),
        # 🎰 кубиком, стикером-эмодзи или просто текстом (с невидимым селектором или без)
        MessageHandler(slot.SLOT_MESSAGE, slot.react),
        # 67 в любом написании: ответ гифкой из блока
        MessageHandler(six_seven.SIX_SEVEN_MESSAGE, six_seven.react)
    ]
    commands = {name for handler in handlers if isinstance(handler, CommandHandler) for name in handler.commands}
    # обработчик «)» стоит первым: команды пользователя с ролью ban до остальных обработчиков не доходят
    return [ban.make_handler(commands)] + handlers
