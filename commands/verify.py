import json
import logging
from telegram import Update
from telegram.ext import ContextTypes

ROLES_FILE = "roles.json"
SECRET_PASSWORD = "кебаб"  # Заменишь на свой

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("👉 Команда /verify вызвана")

    if not context.args:
        await update.message.reply_text("Введите пароль: `/verify ваш_пароль`", parse_mode="Markdown")
        logging.warning("⛔️ Пароль не был передан")
        return

    user_id = str(update.effective_user.id)
    password = context.args[0]
    logging.info(f"🔑 Получен пароль: {password} от пользователя {user_id}")

    try:
        with open(ROLES_FILE, "r", encoding="utf-8") as f:
            roles = json.load(f)
    except Exception as e:
        logging.error(f"❌ Ошибка чтения {ROLES_FILE}: {e}")
        roles = {}

    if password == SECRET_PASSWORD:
        roles[user_id] = "admin"

        try:
            with open(ROLES_FILE, "w", encoding="utf-8") as f:
                json.dump(roles, f, indent=2)
            await update.message.reply_text("✅ Верификация успешна. Вы получили роль admin.")
            logging.info(f"✅ Пользователю {user_id} присвоена роль admin")
        except Exception as e:
            logging.error(f"❌ Не удалось сохранить роли: {e}")
            await update.message.reply_text("Произошла ошибка при сохранении роли.")
    else:
        logging.warning(f"❌ Неверный пароль от пользователя {user_id}")
        await update.message.reply_text("⛔️ Неверный пароль.")