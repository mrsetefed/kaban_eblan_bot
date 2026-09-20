import html
import random
import re
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

MAX_DICE = 100
MAX_SIDES = 1000
MAX_MODIFIER = 99999

# 2d6+3, d20, 3д8-2 (русская «д» тоже подходит), пробелы не важны
DICE_RE = re.compile(r"(\d{0,3})[dDдД](\d{1,4})(?:([+-])(\d{1,5}))?")

USAGE = (
    "Формат: /roll 2d6+3 (сколько кубиков, d, сколько граней, потом + или - модификатор).\n"
    "Примеры: /roll d20, /roll 3d8-2, /roll 4d6. Без параметров кидаю d20.\n"
    f"Лимиты: до {MAX_DICE} кубиков и до {MAX_SIDES} граней."
)


def parse_dice(text: str):
    """'2d6+3' -> (2, 6, +3). Возвращает None, если формат или лимиты не подходят."""
    match = DICE_RE.fullmatch("".join(text.split()))
    if not match:
        return None
    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    modifier = int(match.group(4)) if match.group(4) else 0
    if match.group(3) == "-":
        modifier = -modifier
    if not (1 <= count <= MAX_DICE and 2 <= sides <= MAX_SIDES and modifier <= MAX_MODIFIER):
        return None
    return count, sides, modifier, match.group(3) is not None


def roll_dice(count: int, sides: int, rng=random) -> list:
    return [rng.randint(1, sides) for _ in range(count)]


def format_roll(name: str, count: int, sides: int, modifier: int, has_modifier: bool, rolls: list) -> str:
    total = sum(rolls) + modifier
    expression = f"{count}d{sides}" + (f"{modifier:+d}" if has_modifier else "")
    mod = f" {'+' if modifier >= 0 else '-'} {abs(modifier)}" if has_modifier else ""
    # сначала каждый бросок в скобках, потом модификатор и итог
    lines = [
        f"🎲 <b>{name}</b> бросает <code>{expression}</code>",
        f"[{', '.join(map(str, rolls))}]{mod} = <b>{total}</b>",
    ]

    if count == 1 and sides == 20:  # натуральные 20 и 1 считаем по самому кубику, без модификатора
        if rolls[0] == 20:
            lines.append("💥 Критический успех!")
        elif rolls[0] == 1:
            lines.append("💀 Критический провал!")
    return "\n".join(lines)


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "".join(context.args) if context.args else "d20"
    parsed = parse_dice(text)
    if not parsed:
        await update.message.reply_text(USAGE)
        return

    count, sides, modifier, has_modifier = parsed
    name = html.escape(update.effective_user.full_name)
    await update.message.reply_text(
        format_roll(name, count, sides, modifier, has_modifier, roll_dice(count, sides)),
        parse_mode=ParseMode.HTML,
    )
