import os
import json
import html
import time
import aiohttp
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://api.blackhub.team/servers.json"
YOUTUBERS_API_URL = "https://api.blackrussia.online/client/listOfYoutubers.json"
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1003909198412")
CHECK_INTERVAL = 15  # Секунд

# 👑 АДМИН
ADMIN_ID = 5877790074

# 🔇 Серверы, изменения онлайна которых НЕ присылаем в канал
IGNORED_SERVERS = [
    202, 203, 204, 205, 206, 207, 208, 209, 210,
    211, 212, 213, 214, 215, 216, 217, 218, 219,
    220, 221, 222, 223, 224, 225, 226, 229
]

# 🙈 Серверы, которые НЕ показываются в /status (но изменения по ним уходят в канал)
HIDDEN_FROM_STATUS = set(range(1, 92))  # ID с 1 по 91

# Файл для хранения разрешенных пользователей
ALLOWED_USERS_FILE = "allowed_users.json"

# Файл для хранения максимального онлайна по серверам
MAX_ONLINE_FILE = "max_online.json"

# Файл-выгрузка для /youtube
YOUTUBE_EXPORT_FILENAME = "youtubenickTestServerConnect.json"

# Кулдаун на команду /status (в секундах) — общий для всех пользователей
STATUS_COOLDOWN = 90


def load_allowed_users():
    """Загрузить список разрешенных пользователей из файла."""
    try:
        with open(ALLOWED_USERS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        default_users = [ADMIN_ID]
        save_allowed_users(default_users)
        return default_users
    except Exception as e:
        logging.error(f"Ошибка загрузки allowed_users: {e}")
        return [ADMIN_ID]


def save_allowed_users(users):
    """Сохранить список разрешенных пользователей в файл."""
    try:
        with open(ALLOWED_USERS_FILE, "w") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения allowed_users: {e}")


def load_max_online():
    """Загрузить сохраненные максимальные онлайны серверов."""
    try:
        with open(MAX_ONLINE_FILE, "r") as f:
            data = json.load(f)
            return {int(k): int(v) for k, v in data.items()}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Ошибка загрузки max_online: {e}")
        return {}


def save_max_online(data):
    """Сохранить максимальные онлайны серверов в файл."""
    try:
        with open(MAX_ONLINE_FILE, "w") as f:
            json.dump({str(k): v for k, v in data.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения max_online: {e}")


ALLOWED_USER_IDS = load_allowed_users()

if ADMIN_ID not in ALLOWED_USER_IDS:
    ALLOWED_USER_IDS.append(ADMIN_ID)
    save_allowed_users(ALLOWED_USER_IDS)

MAX_ONLINE_STATE = load_max_online()
# ================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Храним предыдущее состояние серверов и YouTubers
server_state = {}
youtubers_state = set()
# Сохраняем последние данные YouTubers (для /youtube), чтобы не делать лишний запрос
last_youtubers_data = []

# Время последнего успешного вызова /status (общий кулдаун для всех)
last_status_call = 0.0


async def fetch_json(url, description="API"):
    """Универсальная функция для получения JSON данных."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"{description}: HTTP {response.status}")
                    return None
    except asyncio.TimeoutError:
        logger.error(f"{description}: Timeout")
        return None
    except Exception as e:
        logger.error(f"{description}: {e}")
        return None


async def fetch_servers():
    """Получение данных серверов из API."""
    return await fetch_json(API_URL, "Servers API")


async def fetch_youtubers():
    """Получение списка YouTubers из API."""
    return await fetch_json(YOUTUBERS_API_URL, "YouTubers API")


def update_max_online(server_id, online):
    """Обновить максимальный зафиксированный онлайн сервера, если нужно."""
    global MAX_ONLINE_STATE

    old_max = MAX_ONLINE_STATE.get(server_id, 0)
    if online > old_max:
        MAX_ONLINE_STATE[server_id] = online
        save_max_online(MAX_ONLINE_STATE)


async def check_youtubers():
    """Проверка изменений в списке YouTubers."""
    global youtubers_state, last_youtubers_data

    data = await fetch_youtubers()

    if not data or not isinstance(data, list):
        logger.warning("YouTubers API: нет данных или неверный формат")
        return

    last_youtubers_data = data

    current_youtubers = set()
    youtubers_dict = {}

    for yt in data:
        if isinstance(yt, dict):
            nickname = yt.get("nickname")
            if nickname:
                current_youtubers.add(nickname)
                youtubers_dict[nickname] = yt

    if not youtubers_state:
        youtubers_state = current_youtubers
        logger.info(f"📹 YouTubers: начальное состояние ({len(youtubers_state)} человек)")
        return

    new_youtubers = current_youtubers - youtubers_state
    removed_youtubers = youtubers_state - current_youtubers

    for nickname in new_youtubers:
        yt_info = youtubers_dict.get(nickname, {})
        youtube_link = yt_info.get("youtube", "Нет ссылки")

        message = (
            f"🎬 *Новый YouTuber добавлен!*\n\n"
            f"👤 Никнейм: `{html.escape(str(nickname))}`\n"
            f"🔗 YouTube: {html.escape(str(youtube_link))}"
        )

        try:
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🎬 Новый YouTuber: {nickname}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о YouTuber: {e}")

    for nickname in removed_youtubers:
        message = (
            f"❌ *YouTuber удален из списка*\n\n"
            f"👤 Никнейм: `{html.escape(str(nickname))}`"
        )

        try:
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"❌ Удален YouTuber: {nickname}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об удалении YouTuber: {e}")

    youtubers_state = current_youtubers


async def check_servers():
    """Проверка изменений в онлайне серверов (без IP/портов)."""
    global server_state

    data = await fetch_servers()

    if not data or not isinstance(data, list):
        logger.warning("Servers API: нет данных")
        return

    current_state = {}
    for server in data:
        if isinstance(server, dict):
            server_id = server.get("id")
            if server_id:
                online_value = int(server.get("online", 0))
                current_state[server_id] = {
                    "name": server.get("name", "Без имени"),
                    "online": online_value,
                }
                update_max_online(server_id, online_value)

    if not server_state:
        server_state = current_state
        logger.info(f"📊 Servers: начальное состояние ({len(server_state)} серверов)")
        return

    for server_id, info in current_state.items():
        name = info["name"]
        current_online = info["online"]
        is_ignored = server_id in IGNORED_SERVERS

        if server_id not in server_state:
            message = (
                f"🆕 *Новый сервер!*\n"
                f"📌 {name}\n"
                f"🆔 ID: `{server_id}`"
            )
            try:
                await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"🆕 Новый сервер: {name} (ID: {server_id})")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о новом сервере: {e}")
            continue

        old_name = server_state[server_id]["name"]
        if old_name != name:
            message = (
                f"✏️ *Переименован сервер!*\n"
                f"📌 {old_name} → {name}\n"
                f"🆔 ID: `{server_id}`"
            )
            try:
                await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"✏️ Переименован: {old_name} → {name} (ID: {server_id})")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о переименовании: {e}")

        if is_ignored:
            continue

        old_online = server_state[server_id]["online"]

        if current_online > old_online:
            diff = current_online - old_online
            message = (
                f"🟢 *{name}*\n"
                f"Зашел игрок! (+{diff})\n"
                f"Текущий онлайн: {current_online}"
            )
            try:
                await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"🟢 {name}: {old_online} → {current_online}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления об онлайне: {e}")

        elif current_online < old_online:
            diff = old_online - current_online
            message = (
                f"🔴 *{name}*\n"
                f"Вышел игрок! (-{diff})\n"
                f"Текущий онлайн: {current_online}"
            )
            try:
                await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"🔴 {name}: {old_online} → {current_online}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления об онлайне: {e}")

    removed_servers = set(server_state.keys()) - set(current_state.keys())
    for server_id in removed_servers:
        name = server_state[server_id]["name"]
        message = (
            f"🗑️ *Сервер удален!*\n"
            f"📌 {name}\n"
            f"🆔 ID: `{server_id}`"
        )
        try:
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🗑️ Удален сервер: {name} (ID: {server_id})")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об удалении сервера: {e}")

    server_state = current_state


async def monitor_loop():
    """Фоновый цикл мониторинга."""
    logger.info(f"🔄 Мониторинг запущен (интервал: {CHECK_INTERVAL} сек)")
    logger.info(f"🔇 Игнорируемых для нотификаций серверов: {len(IGNORED_SERVERS)}")

    try:
        await check_servers()
        await check_youtubers()
    except Exception as e:
        logger.error(f"Ошибка инициализации мониторинга: {e}", exc_info=True)

    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            await check_servers()
            await check_youtubers()
        except Exception as e:
            logger.error(f"Ошибка в мониторинге: {e}", exc_info=True)


# ============ ПРОВЕРКА ДОСТУПА ============
async def check_access(message: types.Message) -> bool:
    """Проверяет, есть ли у пользователя доступ к боту."""
    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        return True

    if user_id in ALLOWED_USER_IDS:
        return True

    if message.chat.type == "private":
        await message.answer("🚫 У вас нет доступа к этому боту")

    return False


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def is_private(message: types.Message) -> bool:
    """В группах/каналах бот реагирует только на /status. Все остальные
    команды работают только в личных сообщениях."""
    return message.chat.type == "private"
# ============================================================


# ============ КОМАНДЫ УПРАВЛЕНИЯ ДОСТУПОМ ============
@dp.message(Command("access"))
async def access_command(message: types.Message):
    if not is_private(message):
        return

    if not is_admin(message.from_user.id):
        await message.answer("❌ Только админ может выдавать доступ")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Использование:\n"
            "/access @username — выдать доступ по юзернейму\n"
            "/access 123456789 — выдать доступ по ID"
        )
        return

    target = args[1]
    user_id = None

    if target.startswith("@"):
        try:
            user = await bot.get_chat(target)
            user_id = user.id
            username = target
        except Exception:
            await message.answer(f"❌ Не найден пользователь {target}")
            return
    else:
        try:
            user_id = int(target)
            username = f"ID: {user_id}"
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте @username или ID")
            return

    if user_id == ADMIN_ID:
        await message.answer("❌ Админ уже имеет доступ")
        return

    if user_id in ALLOWED_USER_IDS:
        await message.answer(f"i️ Пользователь {username} уже имеет доступ")
        return

    ALLOWED_USER_IDS.append(user_id)
    save_allowed_users(ALLOWED_USER_IDS)

    await message.answer(f"✅ Пользователь {username} получил доступ к боту")
    logger.info(f"✅ Доступ выдан: {username}")


@dp.message(Command("unaccess"))
async def unaccess_command(message: types.Message):
    if not is_private(message):
        return

    if not is_admin(message.from_user.id):
        await message.answer("❌ Только админ может забирать доступ")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ Использование:\n"
            "/unaccess @username — забрать доступ по юзернейму\n"
            "/unaccess 123456789 — забрать доступ по ID"
        )
        return

    target = args[1]
    user_id = None

    if target.startswith("@"):
        try:
            user = await bot.get_chat(target)
            user_id = user.id
            username = target
        except Exception:
            await message.answer(f"❌ Не найден пользователь {target}")
            return
    else:
        try:
            user_id = int(target)
            username = f"ID: {user_id}"
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте @username или ID")
            return

    if user_id == ADMIN_ID:
        await message.answer("❌ Нельзя забрать доступ у админа")
        return

    if user_id not in ALLOWED_USER_IDS:
        await message.answer(f"i️ Пользователь {username} не имеет доступа")
        return

    ALLOWED_USER_IDS.remove(user_id)
    save_allowed_users(ALLOWED_USER_IDS)

    await message.answer(f"✅ У пользователя {username} забран доступ к боту")
    logger.info(f"❌ Доступ забран: {username}")


@dp.message(Command("users"))
async def users_command(message: types.Message):
    if not is_private(message):
        return

    if not is_admin(message.from_user.id):
        await message.answer("❌ Только админ может просматривать список")
        return

    if not ALLOWED_USER_IDS:
        await message.answer("📋 Список пользователей с доступом пуст")
        return

    lines = ["📋 *Пользователи с доступом:*\n"]

    for uid in ALLOWED_USER_IDS:
        try:
            user = await bot.get_chat(uid)
            name = user.full_name or user.username or str(uid)
            prefix = "👑" if uid == ADMIN_ID else "•"

            if user.username:
                lines.append(f"{prefix} @{user.username} (`{uid}`)")
            else:
                lines.append(f"{prefix} {name} (`{uid}`)")
        except Exception:
            lines.append(f"• ID: `{uid}` (недоступен)")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ============ КОМАНДА /youtube ============
@dp.message(Command("youtube"))
async def youtube_command(message: types.Message):
    """Выгрузить всех YouTubers в JSON-файл."""
    if not is_private(message):
        return

    if not await check_access(message):
        return

    data = last_youtubers_data
    if not data:
        data = await fetch_youtubers()

    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных от YouTubers API")
        return

    nicknames = []
    for yt in data:
        if isinstance(yt, dict):
            nickname = yt.get("nickname")
            if nickname:
                nicknames.append(nickname)

    payload = json.dumps(nicknames, ensure_ascii=False, indent=2)
    file = BufferedInputFile(payload.encode("utf-8"), filename=YOUTUBE_EXPORT_FILENAME)

    await message.answer_document(
        file,
        caption=f"🎬 Всего ников: {len(nicknames)}"
    )


# ============ КОМАНДЫ БОТА ============
def build_full_commands_text() -> str:
    """Полный список команд — показывается всем, и обычным пользователям, и админам."""
    lines = [
        "🤖 *Бот мониторинга серверов*\n",
        "👥 *Команды пользователя:*",
        "/start — Информация о боте",
        "/status — Онлайн серверов (работает в любом чате)",
        "/refresh — Обновить состояние",
        "/youtube — Выгрузить файл со всеми никами YouTubers",
        "",
        "👑 *Команды администратора (только в ЛС):*",
        "/access @user/id — Выдать доступ",
        "/unaccess @user/id — Забрать доступ",
        "/users — Список пользователей с доступом",
    ]
    return "\n".join(lines)


@dp.message(Command("start"))
async def start_command(message: types.Message):
    if not is_private(message):
        return

    if not await check_access(message):
        return

    await message.answer(build_full_commands_text(), parse_mode="Markdown")


@dp.message(Command("status"))
async def status_command(message: types.Message):
    """
    /status работает в ЛЮБОМ чате, даже без доступа.
    Общий кулдаун STATUS_COOLDOWN секунд на всех пользователей.
    Формат строки: Название сервера. Максимальный онлайн/текущий онлайн.
    Серверы с ID 1–91 не показываются.
    """
    global last_status_call

    now = time.time()
    elapsed = now - last_status_call

    if elapsed < STATUS_COOLDOWN:
        remaining = int(STATUS_COOLDOWN - elapsed)
        minutes = remaining // 60
        seconds = remaining % 60
        await message.answer(
            f"⏳ Команда на кулдауне. Попробуйте через {minutes} мин {seconds} сек."
        )
        return

    data = await fetch_servers()

    if not data or not isinstance(data, list):
        await message.answer("Нет данных")
        return

    # Кулдаун засчитывается только при успешном выполнении команды
    last_status_call = now

    sorted_servers = sorted(
        data,
        key=lambda x: x.get("id", 0) if isinstance(x, dict) else 0
    )

    lines = []
    for server in sorted_servers:
        if not isinstance(server, dict):
            continue

        server_id = server.get("id", 0)
        if server_id in HIDDEN_FROM_STATUS:
            continue

        name = server.get("name", "???")
        online = int(server.get("online", 0))

        update_max_online(server_id, online)
        max_online = MAX_ONLINE_STATE.get(server_id, online)

        lines.append(f"{html.escape(str(name))}. {max_online}/{online}")

    if not lines:
        await message.answer("Нет данных для отображения")
        return

    body = "\n".join(lines)

    # Telegram ограничивает длину сообщения — при необходимости разбиваем,
    # каждую часть всё равно оформляем цитированием
    max_len = 3800
    if len(body) <= max_len:
        await message.answer(f"<blockquote>{body}</blockquote>", parse_mode="HTML")
    else:
        chunk = []
        chunk_len = 0
        for line in lines:
            if chunk_len + len(line) + 1 > max_len:
                await message.answer(
                    f"<blockquote>{chr(10).join(chunk)}</blockquote>",
                    parse_mode="HTML"
                )
                chunk = []
                chunk_len = 0
            chunk.append(line)
            chunk_len += len(line) + 1
        if chunk:
            await message.answer(
                f"<blockquote>{chr(10).join(chunk)}</blockquote>",
                parse_mode="HTML"
            )


@dp.message(Command("refresh"))
async def refresh_command(message: types.Message):
    if not is_private(message):
        return

    if not await check_access(message):
        return

    global server_state, youtubers_state

    server_state = {}
    youtubers_state = set()

    await check_servers()
    await check_youtubers()

    await message.answer(
        f"✅ Состояние обновлено!\n"
        f"📊 Серверов: {len(server_state)}\n"
        f"🎬 YouTubers: {len(youtubers_state)}"
    )


# ============ ОБРАБОТЧИК ДЛЯ ЛИЧНЫХ СООБЩЕНИЙ ============
@dp.message()
async def private_message_handler(message: types.Message):
    if message.chat.type != "private":
        return

    if not await check_access(message):
        return

    await message.answer(
        "❓ Неизвестная команда\n"
        "Используйте /start для списка команд"
    )
# ============================================================


async def main():
    """Запуск бота."""
    print("=" * 50)
    print("🤖 БОТ МОНИТОРИНГА СЕРВЕРОВ")
    print("=" * 50)
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"📢 Канал: {CHANNEL_ID}")
    print(f"⏱️  Интервал: {CHECK_INTERVAL} сек")
    print(f"🔇 Игнорируется (нотификации): {len(IGNORED_SERVERS)}")
    print(f"🙈 Скрыто в /status: ID 1–91")
    print(f"👥 Пользователей с доступом: {len(ALLOWED_USER_IDS)}")
    print(f"🕐 Кулдаун /status: {STATUS_COOLDOWN} сек")
    print("=" * 50)

    asyncio.create_task(monitor_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
