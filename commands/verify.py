from telegram import Update
from telegram.ext import ContextTypes
from utils import get_user_role

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role(user_id)

    if role:
        await update.message.reply_text(f"👤 Твоя роль: *{role}*", parse_mode="Markdown")
    else:
        message = (
            "⛔ У тебя пока нет роли.\n"
            f"🪪 Твой ID: `{user_id}`\n"
            "📨 Скинь это кабану, если роль быть должна."
        )
        await update.message.reply_text(message, parse_mode="Markdown")