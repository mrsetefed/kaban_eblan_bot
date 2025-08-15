import random
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

COMMENTS = [
    "🤡",
    "Тебе лучшей уйти, это место только для крутых",
    "Давно тебя не было в уличных гонках",
    "Это не твое...",
    "И̸̧͓͈͖͎̟̞͚̖̬̳̔̈́̈́͗̓͂̋̄̉̉̅̀͐̄͝ͅд̷̢̧̡̨̮̦̳̺̞̙͇͕̲͐̿̇и̸̧͍͙͙̫͉͕̥̺̜͇͙̻̃̆̊̔̕͝ͅ ̴̤̑̈͊̑͋̔̑̈́̊͒̕͜͝ͅн̵̛͖̏̀̒ӓ̶̫́х̵̧̣͎̤̍̑̽͐̒͝у̴̢͍͓̩̦̬̳̯͎͎̉̇̔͋͛̐ͅй̸̢̛͈̩͖͎̞̞̠͒̒̌͒́̂̃̿̏̌͝ͅ",
    "Лох",
    "Да ты знатный любитель копро-утех",
    "Ты удастаиваешься нового титула: Ишак",
    "Я хочу: отрыжку как у годзиллы ...",
    "... вонючий хуй и ...",
    "Потные яйца!!!",
    "У тебя нет ни ауры, ни крутости",
    "За разговор с такими как ты в клубе крутых обычно опускают",
    "Папапева гемабоди",
    "Твоя аура слаба",
    "Жалко тебя...",
    "Еще не крут, но уже и не лох",
    "За разговор с тобой больше не опустят в клубе крутых",
    "Я не придумал( Посмейся с этого, пожалуйста",
    "Я хочу пиццу...(",
    "А ты точно не читеришь?",
    "Лучший из худших.",
    "Добро пожаловать в клуб крутых",
    "Худший из лучших",
    "Знатная аура",
    "Ты даже можешь выдавать титулы всем, кто не участвует в клубе",
    "Еблобот одобряет.",
    "Пройден порог крутости обычного человека, теперь ты воистину КРУТОЙ, поздравляю.",
    "Тебе доступна бесплатная раздача кириешек, не забудь зайти.",
    "🧌",
    "Огромный хуй большие яйца",
    "Осталось совсем немного. Тебе нужно больше тренироваться.",
    "Еще совсем чуть чуть...",
    "Поздравляю, достигнута абсолютная крутость!"
]

# Память на время работы бота
user_results = {}

async def krutometr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Чистим старые записи (оставляем только сегодняшние)
    to_delete = [uid for uid, (date, _, _) in user_results.items() if date != today_str]
    for uid in to_delete:
        del user_results[uid]

    # Проверяем, есть ли результат за сегодня
    if user_id in user_results:
        saved_date, saved_score, saved_comment = user_results[user_id]
        message = f"Твой уровень крутости на сегодня: *{saved_score}%*\n{saved_comment}"
        await update.message.reply_text(message, parse_mode="Markdown")
        return

    # Если нет — генерируем новый
    score = random.randint(1, 100)
    index = min((score - 1) // 3, len(COMMENTS) - 1)
    comment = COMMENTS[index]

    # Сохраняем в память
    user_results[user_id] = (today_str, score, comment)

    message = f"Твой уровень крутости: *{score}%*\n{comment}"
    await update.message.reply_text(message, parse_mode="Markdown")