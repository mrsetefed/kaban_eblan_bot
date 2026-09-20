import asyncio
import html
import json
import logging
import math
import os
import random
from telegram import Update, MessageEntity
from telegram.constants import ParseMode
from telegram.error import RetryAfter
from telegram.ext import ContextTypes
from utils import get_user_role, mention_html

# Эффект печати: сколько строк добавляется за шаг и пауза между правками.
# Telegram режет частые правки (в группах ~20 сообщений в минуту), так что быстрее нельзя.
TYPING_LINES_PER_STEP = 4
TYPING_DELAY = 1.0
CURSOR = " ▌"

# (нижняя граница балла 0-100, тир) — от лучшего к худшему.
# Одна шкала для каждого пункта и для итогового среднего.
TIER_SCALE = [
    (90, "TRUE ADAM"),
    (80, "GIGACHAD"),
    (68, "CHAD"),
    (57, "CHADLITE"),
    (44, "HTN"),
    (32, "MTN"),
    (18, "LTN"),
    (0, "SUB-3"),
]

# Среднее из семи блоков «сжимается» к середине, поэтому у итога своя, более узкая шкала.
# Подобрана по распределению: SUB-3 ~8.5%, LTN ~18%, MTN ~28%, HTN ~23%, CHADLITE ~13%, CHAD ~6.5%, GIGACHAD ~2.5%, TRUE ADAM ~0.5%
FINAL_TIER_SCALE = [
    (74, "TRUE ADAM"),
    (69, "GIGACHAD"),
    (65, "CHAD"),
    (61, "CHADLITE"),
    (56, "HTN"),
    (50, "MTN"),
    (43, "LTN"),
    (0, "SUB-3"),
]

# Варианты для блоков Eyes, Skin, Hair и Style: (подпись, базовый балл 0-100, вес выпадения)
EYE_TYPES = [
    ("hunter eyes", 95, 2),
    ("almond eyes", 75, 3),
    ("neutral eyes", 55, 4),
    ("prey eyes", 25, 3),
    ("bugeyes", 10, 1),
]
SKIN_TYPES = [
    ("glass skin", 95, 1),
    ("clear skin", 78, 3),
    ("normal skin", 55, 4),
    ("oily and acne", 28, 3),
    ("лунная поверхность", 8, 1),
]
HAIR_TYPES = [
    ("thick hair, low hairline", 92, 2),
    ("good hairline", 76, 3),
    ("average hair", 55, 4),
    ("receding hairline", 32, 3),
    ("Norwood 4+", 12, 2),
]
STYLE_TYPES = [
    ("full drip", 92, 2),
    ("clean fit", 76, 3),
    ("basic", 55, 4),
    ("худи из 2015-го", 28, 3),
    ("спортивки и шлёпки", 10, 2),
]
# Финальная реплика, когда человек проверяет только себя (по итоговому тиру)
SOLO_VERDICTS = {
    "TRUE ADAM": [
        "Ты вышел за пределы шкалы. Учёные в панике",
        "Зеркала при тебе просят автограф",
    ],
    "GIGACHAD": [
        "Гигачад подтверждён. Поклонись предкам",
        "Прохожие оборачиваются, даже банкоматы",
    ],
    "CHAD": [
        "Настоящий Chad. Зеркало довольно",
        "Чад в чате, всем встать",
    ],
    "CHADLITE": [
        "Почти Chad. Ещё немного максинга, и всё",
        "Chadlite: на шаг от трона, но уже неплохо",
    ],
    "HTN": [
        "Крепкий HTN. Жить можно, моговать пока рано",
        "HTN: не красавец, но и не позор семьи",
    ],
    "MTN": [
        "Середнячок. Ни рыба ни мясо, зато свой",
        "MTN: тебя не заметят, но и не забудут случайно",
    ],
    "LTN": [
        "LTN. Есть куда расти, начни с душа и мьюинга",
        "LTN: не расстраивайся, харизма ещё никого не подводила",
    ],
    "SUB-3": [
        "SUB-3. Скажи спасибо, что прибор вообще запустился",
        "SUB-3: сканер просит больше так не делать",
    ],
}

SCORE_JITTER = 6  # разброс балла внутри одного варианта, чтобы одинаковые подписи не давали одинаковый тир


def clamp(value, low, high):
    return max(low, min(high, value))


def score_tier(score: float, scale=TIER_SCALE) -> str:
    for threshold, name in scale:
        if score >= threshold:
            return name
    return scale[-1][1]


# Чтобы мемные результаты выпадали чаще, у каждого броска есть «сдвиг» в баллах: в плюс, в минус или ноль.
# Сдвиг применяется к исходным значениям (PSL, угол челюсти, веса вариантов и т.д.), а не к итоговому числу,
# поэтому значения в блоках и их тиры остаются согласованными.
HIGH_CHANCE = 0.25      # шанс сдвига вверх (получается CHAD и выше)
LOW_CHANCE = 0.35       # шанс сдвига вниз (получается SUB-3 и около). Остальное: обычный бросок без сдвига
HIGH_SHIFT = 25         # средний сдвиг «вверх»
LOW_SHIFT = 24          # средний сдвиг «вниз»
SHIFT_SPREAD = 7        # разброс сдвига, чтобы крайности не были одинаковыми
WEIGHT_TILT = 400       # чем меньше, тем сильнее сдвиг перетягивает выбор вариантов (skin, hair...)

# Личная подкрутка отдельного игрока. Общая «крайность» на него не накладывается: сильный бросок (65+) идёт по
# отдельному правилу, а все остальные броски обычные, как без подкруток вообще.
STRONG_ROLL_FROM = 65   # порог «сильного» результата
STRONG_SHIFT = 10       # средний сдвиг сильного броска: даёт разброс CHAD ~25%, GIGACHAD ~33%, TRUE ADAM ~42%
STRONG_SPREAD = 8
MAX_STRONG_TRIES = 100
P_NATURAL_65 = 0.098    # доля результатов 65+ при обычном броске без подкруток (измерено симуляцией, см. тесты)


def pick(rng: random.Random, options: list, shift: float = 0.0) -> tuple[str, float]:
    weights = [w * math.exp(shift * (score - 50) / WEIGHT_TILT) for _, score, w in options]
    label, base, _ = rng.choices(options, weights=weights)[0]
    return label, clamp(base + rng.uniform(-SCORE_JITTER, SCORE_JITTER), 0, 100)


def strong_roll_share(user_id, username):
    """Какую долю сильных результатов (65+) нужно игроку. Задаётся переменной окружения MOG_TUNING
    вида {"имя роли или ник": доля}, например {"someone": 0.5}. Без переменной подкрутки нет."""
    raw = os.environ.get("MOG_TUNING")
    if not raw:
        return None
    try:
        tuning = {str(key).lower().lstrip("@"): float(value) for key, value in json.loads(raw).items()}
    except Exception as e:
        logging.warning(f"MOG_TUNING не разобран: {e}")
        return None

    names = set()
    if username:
        names.add(username.lower())
    roles = get_user_role(user_id) if user_id else None
    for role in [roles] if isinstance(roles, str) else (roles or []):
        names.add(str(role).lower())
    shares = [tuning[name] for name in names if name in tuning]
    return max(shares) if shares else None


def pick_shift(rng: random.Random) -> float:
    """Общая подкрутка для всех: чаще крайности, вниз чуть чаще, чем вверх."""
    roll = rng.random()
    if roll < HIGH_CHANCE:
        return rng.gauss(HIGH_SHIFT, SHIFT_SPREAD)
    if roll < HIGH_CHANCE + LOW_CHANCE:
        return rng.gauss(-LOW_SHIFT, SHIFT_SPREAD)
    return 0.0


def roll_stats(rng: random.Random, shift: float = 0.0) -> dict:
    psl = round(clamp(rng.gauss(4.3 + shift * 0.07, 1.3), 1.0, 8.0), 1)
    fwhr = round(clamp(rng.gauss(1.85 + shift * 0.008, 0.15), 1.5, 2.3), 2)

    tilt = round(clamp(rng.gauss(2.0 + shift * 0.18, 3.5), -8.0, 10.0), 1)
    if tilt < 0:
        tilt_label = "negative canthal tilt"
    elif tilt < 3:
        tilt_label = "neutral canthal tilt"
    else:
        tilt_label = "positive canthal tilt"
    eyes, eyes_type_score = pick(rng, EYE_TYPES, shift)

    # идеал челюсти около 115°, поэтому вверх сдвигаем к нему (не дальше), а вниз уводим от него
    gonial_shift = min(shift, 25)
    gonial = round(clamp(rng.gauss(122 - gonial_shift * 0.28, 7), 105, 145))
    if gonial <= 118:
        jaw_label = "sharp jawline"
    elif gonial <= 128:
        jaw_label = "average jaw"
    else:
        jaw_label = "recessed jaw"

    skin, skin_score = pick(rng, SKIN_TYPES, shift)
    hair, hair_score = pick(rng, HAIR_TYPES, shift)
    style, style_score = pick(rng, STYLE_TYPES, shift)
    aura = round(clamp(rng.gauss(shift * 200, 3000), -10000, 10000) / 100) * 100

    # (название блока, значение для показа, балл 0-100)
    raw_metrics = [
        ("Face", f"PSL {psl}, FWHR {fwhr}", ((psl - 1.0) / 7.0 * 100 + (fwhr - 1.5) / 0.8 * 100) / 2),
        ("Eyes", f"{eyes}, {tilt:+.1f}° ({tilt_label})", ((tilt + 8.0) / 18.0 * 100 + eyes_type_score) / 2),
        ("Jawline", f"{gonial}° ({jaw_label})", max(0.0, 100 - abs(gonial - 115) * 3.5)),
        ("Skin", skin, skin_score),
        ("Hair", hair, hair_score),
        ("Style", style, style_score),
        ("Aura", f"{aura:+d} aura points", (aura + 10000) / 200),
    ]
    metrics = [
        {"name": name, "value": value, "tier": score_tier(score), "score": score}
        for name, value, score in raw_metrics
    ]
    average = round(sum(m["score"] for m in metrics) / len(metrics), 1)
    return {"metrics": metrics, "average": average, "tier": score_tier(average, FINAL_TIER_SCALE)}


def roll_strong(rng: random.Random) -> dict:
    """Принудительно сильный бросок: результат всегда 65+, а блоки и тиры при этом остаются согласованными."""
    stats = None
    for _ in range(MAX_STRONG_TRIES):
        stats = roll_stats(rng, max(0.0, rng.gauss(STRONG_SHIFT, STRONG_SPREAD)))
        if stats["average"] >= STRONG_ROLL_FROM:
            break
    return stats


def roll_for(rng: random.Random, strong_share=None) -> dict:
    """Бросок для игрока. Без личной подкрутки действует общая. С личной подкруткой доля strong_share всех
    бросков получается 65+ (по принудительному правилу), остальные обычные, без общей подкрутки."""
    if strong_share:
        forced = clamp((strong_share - P_NATURAL_65) / (1 - P_NATURAL_65), 0.0, 1.0)
        return roll_strong(rng) if rng.random() < forced else roll_stats(rng)
    return roll_stats(rng, pick_shift(rng))


def format_player(name: str, stats: dict) -> str:
    lines = [f"<b>{name}</b>"]
    for m in stats["metrics"]:
        lines.append(f"• {m['name']}: {m['value']} — <b>{m['tier']}</b>")
    lines.append(f"Средний показатель: <b>{stats['average']}</b>/100")
    return "\n".join(lines)


def verdict(margin: float) -> str:
    if margin >= 25:
        return "TOTAL FRAMEMOG. Противника размотали и закопали"
    if margin >= 10:
        return "MOG. Уверенный разъёб по фейсу"
    return "Слабый mog, почти looksmatch"


def find_target(update: Update):
    """Возвращает (html-имя, user_id или None, username или None) цели или None."""
    message = update.message

    replied = message.reply_to_message
    # в форумах ответ «в никуда» приходит как реплай на служебное сообщение о создании темы
    if replied and replied.from_user and not replied.forum_topic_created:
        user = replied.from_user
        return mention_html(user), user.id, (user.username or "").lower() or None

    for entity, text in message.parse_entities(
        [MessageEntity.TEXT_MENTION, MessageEntity.MENTION]
    ).items():
        if entity.type == MessageEntity.TEXT_MENTION and entity.user:
            return mention_html(entity.user), entity.user.id, (entity.user.username or "").lower() or None
        if entity.type == MessageEntity.MENTION:
            return html.escape(text), None, text.lstrip("@").lower()

    return None


async def edit_text(message, text: str):
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML)
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await message.edit_text(text, parse_mode=ParseMode.HTML)


async def type_out(update: Update, text: str):
    """Отправляет текст и «допечатывает» его правками сообщения."""
    lines = text.split("\n")
    boundaries = list(range(TYPING_LINES_PER_STEP, len(lines), TYPING_LINES_PER_STEP)) + [len(lines)]

    first = "\n".join(lines[:boundaries[0]])
    is_last = boundaries[0] == len(lines)
    message = await update.message.reply_text(
        first if is_last else first + CURSOR, parse_mode=ParseMode.HTML
    )

    for end in boundaries[1:]:
        await asyncio.sleep(TYPING_DELAY)
        partial = "\n".join(lines[:end])
        try:
            await edit_text(message, partial if end == len(lines) else partial + CURSOR)
        except Exception as e:
            # промежуточная правка не прошла — не страшно, но финал нужен обязательно
            logging.warning(f"Не удалось отредактировать сообщение /mog: {e}")
            if end == len(lines):
                await update.message.reply_text(text, parse_mode=ParseMode.HTML)


def build_solo_text(name: str, stats: dict, rng: random.Random) -> str:
    return (
        f"🗿 Сканирую PSL у {name}...\n\n"
        f"{format_player(name, stats)}\n\n"
        f"📊 <b>ИТОГОВЫЙ ТИР</b>: <b>{stats['tier']}</b>\n\n"
        f"{rng.choice(SOLO_VERDICTS[stats['tier']])}"
    )


def build_battle_text(author_name: str, author_stats: dict, target_name: str, target_stats: dict) -> str:
    margin = author_stats["average"] - target_stats["average"]

    if margin == 0:
        result = "🤝 Ничья. Оба одинаково ЛТН, расходимся"
    else:
        winner_name = author_name if margin > 0 else target_name
        result = f"🏆 <b>{winner_name}</b> — {verdict(abs(margin))} (+{abs(margin):.1f})"

    return (
        # оба тега в первых строках: они уходят при отправке, а упоминания в правках Telegram не пингует
        f"🗿 Инициировано сражение между {author_name} и {target_name}, сканирую PSL...\n\n"
        f"{format_player(author_name, author_stats)}\n\n"
        "⚔️ <b>VS</b> ⚔️\n\n"
        f"{format_player(target_name, target_stats)}\n\n"
        "📊 <b>ИТОГОВЫЙ ТИР</b>\n"
        f"{author_name}: {author_stats['average']} → <b>{author_stats['tier']}</b>\n"
        f"{target_name}: {target_stats['average']} → <b>{target_stats['tier']}</b>\n\n"
        f"{result}"
    )


async def mog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    author = update.effective_user
    target = find_target(update)

    if not target:
        # ни реплая, ни тега: просто замеряем автора, без сравнения и без тегов
        rng = random.Random()
        author_stats = roll_for(rng, strong_roll_share(author.id, author.username))
        text = build_solo_text(html.escape(author.full_name), author_stats, rng)
        context.application.create_task(type_out(update, text), update=update)
        return

    target_name, target_id, target_username = target
    is_self = target_id == author.id or (
        target_username and target_username == (author.username or "").lower()
    )
    if is_self:
        await update.message.reply_text(
            f"{mention_html(author)}, самого себя замогать не получится. Даже TRUE ADAM не может замогать своё отражение. "
            "Хочешь просто проверить себя, напиши /mog без реплая и тега.",
            parse_mode=ParseMode.HTML,
        )
        return

    rng = random.Random()
    author_stats = roll_for(rng, strong_roll_share(author.id, author.username))
    target_stats = roll_for(rng, strong_roll_share(target_id, target_username))
    text = build_battle_text(mention_html(author), author_stats, target_name, target_stats)

    # Печать идёт в фоне, чтобы вебхук ответил Telegram сразу и не получил повторную доставку апдейта.
    context.application.create_task(type_out(update, text), update=update)
