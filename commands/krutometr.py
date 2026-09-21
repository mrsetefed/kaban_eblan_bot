import html
import logging
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils import mention_html
from .krutometr_stats import record_roll
from . import media_store
from .media_store import media_kind, send_media  # media_kind импортируют и другие модули отсюда

MSK = timezone(timedelta(hours=3))

# Ссылки на картинки и гифки лежат в media/krutometr_links.txt по диапазонам, файлы в репозитории не хранятся:
# Telegram сам скачивает их по ссылке. Инструкция — в шапке самого файла.
MEDIA_FILE = Path(__file__).resolve().parent.parent / "media" / "krutometr_links.txt"
MEDIA_CHANCE = 0.5  # шанс, что ответ придёт с картинкой/гифкой, если для диапазона она есть

BAR_LENGTH = 10

# Ответ на чужое сообщение: если у цели крутость ниже порога, бот над ней издевается
MOCK_BELOW = 60
MOCK_SEVERE_BELOW = 30

# Шаблоны издёвок над целью, {name} — имя цели
MOCK_SEVERE = [
    "{name} опущен",
    "Крутометр отказывается работать с {name}: от него несёт",
    "{name} — живое доказательство того, что эволюция иногда даёт сбой",
    "Даже ишаки в клубе крутых смотрят на {name} свысока",
    "Сообщаем: {name} официально занесён в реестр лохов",
    "Крутость {name} пришлось изучать под лупой",
    "Прибор попросил {name} выйти из комнаты, среднее значение стало слишком низким",
    "{name}, ты где-то на уровне панды. Даже немного жалко тебя"

]
MOCK_MILD = [
    "{name} старается, но крутость — это не про старания",
    "Ну такое, {name}. Ни рыба, ни мясо, ни аура",
    "{name} крут ровно настолько, чтобы не пускали в клуб крутых",
    "Если бы крутость была шаурмой, {name} был бы веганской",
    "Аура {name} держится на честном слове",
    "{name}, мы бы посоветовали сменить хобби, но врятли это поможет",
    "{name} крутой только в своих мыслях, и то не всегда",
    "{name}, еще пара лет тренировок, и, может быть, дорастёшь до среднего",
]

# (максимальный балл диапазона, [фразы]). Диапазоны идут подряд от 1 до 100.
# Фраза выбирается случайно из своего диапазона, так что одинаковый результат не даёт одну и ту же реплику.
BANDS = [
    (12, [
        "🤡",
        "Тебе лучше уйти, это место только для крутых",
        "Давно тебя не было в уличных гонках",
        "Это не твое...",
        "Крутометр показал минус, но мы округлили до плюса из жалости",
        "Сканер ауры сообщает: ошибка 404, аура не найдена",
        "Не смей трогать кириешки",
    ]),
    (24, [
        "И̸̧͓͈͖͎̟̞͚̖̬̳̔̈́̈́͗̓͂̋̄̉̉̅̀͐̄͝ͅд̷̢̧̡̨̮̦̳̺̞̙͇͕̲͐̿̇и̸̧͍͙͙̫͉͕̥̺̜͇͙̻̃̆̊̔̕͝ͅ ̴̤̑̈͊̑͋̔̑̈́̊͒̕͜͝ͅн̵̛͖̏̀̒ӓ̶̫́х̵̧̣͎̤̍̑̽͐̒͝у̴̢͍͓̩̦̬̳̯͎͎̉̇̔͋͛̐ͅй̸̢̛͈̩͖͎̞̞̠͒̒̌͒́̂̃̿̏̌͝ͅ",
        "Лох",
        "Да ты знатный любитель копро-утех",
        "Ты удостаиваешься нового титула: Ишак",
        "Твоя крутость сейчас на уровне позавчерашнего хлеба",
        "Прибор дымится, но не от восторга",
        "Уровень: NPC без диалога",
        "Тебе бы поменьше говорить.",
    ]),
    (36, [
        "Я хочу: отрыжку как у годзиллы ...",
        "... вонючий хуй и ...",
        "Потные яйца!!!",
        "У тебя нет ни ауры, ни крутости",
        "Пахнет не крутостью, а вчерашним пивом",
        "Сомнительно, но окэй",
    ]),
    (48, [
        "За разговор с такими как ты в клубе крутых обычно опускают",
        "Папапева гемабоди",
        "Твоя аура слаба",
        "Жалко тебя...",
        "Клуб крутых рассмотрел твою заявку и потерял её",
        "Ты почти как крутой, только без крутости",
        "Аура мерцает как ргб подсветка",
        "Ну хоть стараешься, и на том спасибо",
    ]),
    (60, [
        "Еще не крут, но уже и не лох",
        "За разговор с тобой больше не опустят в клубе крутых",
        "Я не придумал( Посмейся с этого, пожалуйста",
        "Я хочу пиццу...(",
        "Ровно посередине, как майонез в салате",
        "Золотая середина. Скучно, но стабильно",
        "Ни рыба ни мясо, зато не лох",
        "Крутость есть, но пока в режиме энергосбережения",
    ]),
    (72, [
        "А ты точно не читеришь?",
        "Лучший из худших.",
        "Добро пожаловать в клуб крутых",
        "Худший из лучших",
        "Охрана клуба крутых на тебя уже не пиздит",
        "Тебя начинают узнавать в лицо и даже здороваться",
        "Еще чуть-чуть, и можно требовать скидку в шаурмичной",
        "Аура пошла в рост, соседи заметили",
    ]),
    (84, [
        "Знатная аура",
        "Ты даже можешь выдавать титулы всем, кто не участвует в клубе",
        "Еблобот одобряет.",
        "Пройден порог крутости обычного человека, теперь ты воистину КРУТОЙ, поздравляю.",
        "Курьеры теперь обязаны кланяться принося тебе дары",
        "Твоя аура слепит",
        "Правая рука Якуба",
    ]),
    (96, [
        "Тебе доступна бесплатная раздача кириешек, не забудь зайти.",
        "🧌",
        "Огромный хуй большие яйца",
        "Осталось совсем немного. Тебе нужно больше тренироваться.",
        "Кабан лично пожал бы тебе копыто",
        "Выдать этому человеку гражданство Албании",
        "При тебе даже пердеть страшно",
        "Еблобот падает ниц",
    ]),
    (99, [
        "Еще совсем чуть чуть...",
        "Один шаг до титула Абсолютной Крутости, не подведи",
        "Крутометр уже плачет от счастья",
        "Стрелка упёрлась в край шкалы и дрожит",
    ]),
    (100, [
        "Поздравляю, достигнута абсолютная крутость!",
        "СТО ПРОЦЕНТОВ! Крутометр сломан, ты сломал систему",
        "Ты эталон крутости",
    ]),
]


# Блоки медиа: до какого результата (включительно) и как называется секция в media/krutometr_links.txt.
# Те же четыре блока предлагает команда /media, так что гифки из файла и из бота попадают в одни и те же диапазоны.
MEDIA_RANGES = [(30, "0-30"), (60, "31-60"), (90, "61-90"), (100, "91-100")]


def media_range(score: int) -> str:
    for high, name in MEDIA_RANGES:
        if score <= high:
            return name
    return MEDIA_RANGES[-1][1]


def find_band(score: int) -> int:
    for index, (high, _) in enumerate(BANDS):
        if score <= high:
            return index
    return len(BANDS) - 1


def load_media() -> dict[str, list[str]]:
    """Читает media/krutometr_links.txt: секции [диапазон], под ними по одной ссылке на строку.
    Пустой или отсутствующий файл — не ошибка: тогда бот отвечает просто текстом."""
    try:
        # utf-8-sig, чтобы не споткнуться о BOM, который добавляет Блокнот
        text = MEDIA_FILE.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.warning(f"Не удалось прочитать {MEDIA_FILE.name}: {e}")
        return {}

    known = {name for _, name in MEDIA_RANGES} | {"any"}
    media: dict[str, list[str]] = {}
    section = "any"  # ссылки выше первой секции считаются общими
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        header = re.fullmatch(r"\[(.+?)\]", line)
        if header:
            section = header.group(1).strip()
            if section not in known:
                logging.warning(f"{MEDIA_FILE.name}, строка {line_number}: неизвестный диапазон [{section}], его ссылки пропущены")
            continue

        if section not in known:
            continue
        if not media_kind(line):
            logging.warning(
                f"{MEDIA_FILE.name}, строка {line_number}: ссылка пропущена "
                f"(нужна прямая ссылка на .gif/.mp4/.jpg/.png): {line}"
            )
            continue
        media.setdefault(section, []).append(line)

    return {section: list(dict.fromkeys(urls)) for section, urls in media.items()}


MEDIA = load_media()


def roll(user_id: int, day: str) -> dict:
    """Результат зависит только от пользователя и даты: одно и то же в течение дня
    и после перезапуска бота, без хранения состояния."""
    rng = random.Random(f"krutometr:{user_id}:{day}")
    score = rng.randint(1, 100)
    index = find_band(score)
    phrase = rng.choice(BANDS[index][1])

    name = media_range(score)
    # ссылки из файла и то, что добавили через /media
    candidates = MEDIA.get(name, []) + media_store.stored(f"krutometr/{name}") + MEDIA.get("any", []) + media_store.stored("krutometr/any")
    media = rng.choice(candidates) if candidates and rng.random() < MEDIA_CHANCE else None
    return {"score": score, "phrase": phrase, "media": media}


def mock_phrase(user_id: int, day: str, score: int, name_html: str) -> str:
    rng = random.Random(f"krutometr-mock:{user_id}:{day}")
    pool = MOCK_SEVERE if score < MOCK_SEVERE_BELOW else MOCK_MILD
    return rng.choice(pool).format(name=name_html)


def render(header: str, score: int, body_html: str) -> str:
    filled = round(score / 100 * BAR_LENGTH)
    bar = "▰" * filled + "▱" * (BAR_LENGTH - filled)
    return "\n".join([f"{header}: <b>{score}%</b>", bar, body_html])


def format_result(name_html: str, score: int, phrase: str) -> str:
    return render(f"{name_html}, твой уровень крутости", score, html.escape(phrase))


def format_target_result(name_html: str, score: int, body_html: str) -> str:
    return render(f"{name_html}, твой уровень крутости", score, body_html)


def find_target(update: Update):
    """Автор сообщения, на которое ответили командой. None, если это не реплай или реплай на самого себя."""
    replied = update.message.reply_to_message
    # в форумах ответ «в никуда» приходит как реплай на служебное сообщение о создании темы
    if not replied or replied.forum_topic_created or not replied.from_user:
        return None
    if replied.from_user.id == update.effective_user.id:
        return None
    return replied.from_user


async def send_result(update: Update, text: str, media: str | None):
    if media:
        try:
            await send_media(update.message, media, caption=text, parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            # битая ссылка или слишком тяжёлый файл не должны оставлять без ответа
            logging.warning(f"Не удалось отправить медиа {media}: {e}")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def krutometr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(MSK).strftime("%Y-%m-%d")
    target = find_target(update)

    if not target:
        author = update.effective_user
        result = roll(author.id, today)
        text = format_result(mention_html(author), result["score"], result["phrase"])
        await send_result(update, text, result["media"])
        try:
            # запись нужна для топа недели, поэтому сбой хранилища не должен ломать сам ответ
            await record_roll(update, result["score"], today)
        except Exception:
            logging.exception("Не удалось записать результат крутометра")
        return

    if target.is_bot:
        await update.message.reply_text(
            f"{mention_html(update.effective_user)}, ботов крутометр не меряет: у них ни ауры, ни крутости, "
            "только запросы. А Еблобот вообще вне шкалы.",
            parse_mode=ParseMode.HTML,
        )
        return

    name = mention_html(target)
    result = roll(target.id, today)
    if result["score"] < MOCK_BELOW:
        body = mock_phrase(target.id, today, result["score"], name)
    else:
        body = html.escape(result["phrase"])
    await send_result(update, format_target_result(name, result["score"], body), result["media"])
    try:
        # результат цели тот же, что она получила бы сама, поэтому засчитываем его в топ недели за неё
        await record_roll(update, result["score"], today, user=target)
    except Exception:
        logging.exception("Не удалось записать результат крутометра")
