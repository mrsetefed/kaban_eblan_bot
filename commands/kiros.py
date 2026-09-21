from telegram import Message, Update
from telegram.ext import ContextTypes, MessageHandler
from telegram.ext.filters import MessageFilter

from utils import get_user_role

MUTED_ROLE = "kiros"  # роль в USER_ROLES, которой на любую команду бота приходит только это:
ANSWER = ")"


def has_muted_role(user_id) -> bool:
    roles = get_user_role(str(user_id)) if user_id else None
    return MUTED_ROLE in ([roles] if isinstance(roles, str) else (roles or []))


def command_name(message: Message):
    """'/roll@bot 2d6' -> ('roll', 'bot'). None, если сообщение не начинается с команды."""
    text = message.text or ""
    if not text.startswith("/"):
        return None
    head = text[1:].split(maxsplit=1)[0] if len(text) > 1 else ""
    name, _, target = head.partition("@")
    return name.lower(), target.lower()


class MutedUserCommand(MessageFilter):
    """Команда, которую бот знает и которая адресована ему (без @другого_бота), от пользователя с ролью kiros."""

    def __init__(self, commands):
        super().__init__()
        self.commands = {c.lower() for c in commands}

    def filter(self, message: Message) -> bool:
        if not message.from_user or not has_muted_role(message.from_user.id):
            return False
        parsed = command_name(message)
        if not parsed or parsed[0] not in self.commands:
            return False
        name, target = parsed
        if target:
            try:
                return target == (message.get_bot().username or "").lower()
            except Exception:
                return False
        return True


async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ANSWER)


def make_handler(commands) -> MessageHandler:
    """Ставится первым в списке обработчиков: в одной группе срабатывает только первый подошедший,
    поэтому сама команда до своего обработчика уже не доходит."""
    return MessageHandler(MutedUserCommand(commands), reply)
