import json
import os
from telegram import Update
from telegram.ext import ContextTypes

ROLES_FILE = "roles.json"
SECRET_PASSWORD = "трюфель"  # заменишь потом

def load_roles():
    if os.path.exists(ROLES_FILE):
        with open(ROLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_roles(roles):
    with open(ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(roles, f, indent=2, ensure_ascii=False)

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args

    if not args:
        await update.message.reply_text("Че ты написал, придурь?? Вот так надо: `/verify пароль`", parse_mode="Markdown")
        return

    if args[0] != SECRET_PASSWORD:
        await update.message.reply_text("Пошел нахуй")
        return

    roles = load_roles()
    roles[user_id] = "trusted"
    save_roles(roles)

    await update.message.reply_text("Получено кабанье благословение")