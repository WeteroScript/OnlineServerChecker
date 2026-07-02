import os
import json
import html
import time
import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://api.blackhub.team/servers.json"
YOUTUBERS_API_URL = "https://api.blackrussia.online/client/listOfYoutubers.json"

# 📢 Канал: добавление / удаление (и переименование) серверов — и ТОЛЬКО ЭТО
SERVERS_CHANNEL_ID = int(os.getenv("SERVERS_CHANNEL_ID", "-1003990585623"))

# 📢 Канал: заход/выход игроков ТОЛЬКО сервера с ID 229 — и ТОЛЬКО ЭТО
PLAYERS_229_CHANNEL_ID = int(os.getenv("PLAYERS_229_CHANNEL_ID", "-1004400101443"))

# 📢 Канал: появление (и удаление) ников на YouTube-сервере — и ТОЛЬКО ЭТО
YOUTUBE_CHANNEL_ID = int(os.getenv("YOUTUBE_CHANNEL_ID", "-1004465586673"))

# 🔒 Канал, на который нужно быть подписанным, чтобы пользоваться ботом
SUBSCRIBE_CHANNEL_ID = int(os.getenv("SUBSCRIBE_CHANNEL_ID", "-1002623646036"))
# Ссылка-приглашение на канал подписки (укажите в переменных окружения реальную ссылку!)
SUBSCRIBE_CHANNEL_LINK = os.getenv("SUBSCRIBE_CHANNEL_LINK", "https://t.me/WeterochinaTest")

CHECK_INTERVAL = 15  # Секунд

# 👑 АДМИНЫ (можно перечислить несколько ID через запятую в переменной окружения ADMIN_IDS)
_admin_ids_env = os.getenv("ADMIN_IDS", "5877790074")
ADMIN_IDS = set()
for _part in _admin_ids_env.split(","):
    _part = _part.strip()
    if _part:
        try:
            ADMIN_IDS.add(int(_part))
        except ValueError:
            pass
if not ADMIN_IDS:
    ADMIN_IDS = {5877790074}
ADMIN_ID = next(iter(ADMIN_IDS))  # для обратной совместимости / логов

# 🎯 Единственный сервер, по которому шлём уведомления о заходе/выходе игроков
TRACKED_PLAYER_SERVER_ID = 229

# 🙈 Серверы, которые НЕ показываются в /status (тестовые серверы)
HIDDEN_FROM_STATUS = set(range(1, 92))  # ID с 1 по 91

# 🧪 Диапазон ID "тестовых" серверов для /getallip (когда-либо встречавшихся)
TEST_SERVER_RANGE = set(range(1, 92))  # ID с 1 по 91

# 🚫 Диапазон ID, исключаемый из /getactualip
ACTUAL_IP_EXCLUDE_RANGE = set(range(1, 91))  # ID с 1 по 90

# Файлы для хранения состояния
ALLOWED_USERS_FILE = "allowed_users.json"
MAX_ONLINE_FILE = "max_online.json"
ALL_USERS_FILE = "all_users.json"
TEST_SERVERS_FILE = "test_servers.json"

# Файл-выгрузка для /youtube
YOUTUBE_EXPORT_FILENAME = "youtubenickTestServerConnect.json"

# Кулдаун на команду /status В ГРУППОВЫХ ЧАТАХ (в секундах). Свой на каждый чат.
# В личных сообщениях кулдауна нет.
STATUS_COOLDOWN = 90


def load_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        logging.error(f"Ошибка загрузки {path}: {e}")
        return default


def save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения {path}: {e}")


def load_allowed_users():
    data = load_json_file(ALLOWED_USERS_FILE, None)
    if data is None:
        data = list(ADMIN_IDS)
        save_allowed_users(data)
    return data


def save_allowed_users(users):
    save_json_file(ALLOWED_USERS_FILE, users)


def load_max_online():
    data = load_json_file(MAX_ONLINE_FILE, {})
    return {int(k): int(v) for k, v in data.items()}


def save_max_online(data):
    save_json_file(MAX_ONLINE_FILE, {str(k): v for k, v in data.items()})


def load_all_users():
    return load_json_file(ALL_USERS_FILE, [])


def save_all_users(users):
    save_json_file(ALL_USERS_FILE, users)


def load_test_servers():
    data = load_json_file(TEST_SERVERS_FILE, {})
    return {int(k): v for k, v in data.items()}


def save_test_servers(data):
    save_json_file(TEST_SERVERS_FILE, {str(k): v for k, v in data.items()})


ALLOWED_USER_IDS: List[int] = load_allowed_users()
for _aid in ADMIN_IDS:
    if _aid not in ALLOWED_USER_IDS:
        ALLOWED_USER_IDS.append(_aid)
save_allowed_users(ALLOWED_USER_IDS)

MAX_ONLINE_STATE: Dict[int, int] = load_max_online()
ALL_USER_IDS: List[int] = load_all_users()
TEST_SERVERS_STATE: Dict[int, dict] = load_test_servers()
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
last_youtubers_data = []

# Кулдаун /status по чатам: {chat_id: last_call_timestamp}
status_cooldowns: Dict[int, float] = {}


# ============ КОМАНДЫ БОТА (описания) ============
DEFAULT_COMMANDS = [
    BotCommand(command="start", description="Информация о боте"),
    BotCommand(command="status", description="Онлайн серверов"),
    BotCommand(command="help", description="Помощь по командам"),
]

ACCESS_COMMANDS = DEFAULT_COMMANDS + [
    BotCommand(command="youtube", description="Ники YouTube (.json)"),
    BotCommand(command="getip", description="IP сервера по ID"),
    BotCommand(command="getallip", description="IP всех тестовых серверов (.json)"),
    BotCommand(command="getactualip", description="IP актуальных серверов (.json)"),
]

ADMIN_COMMANDS = ACCESS_COMMANDS + [
    BotCommand(command="refresh", description="Обновить состояние мониторинга"),
    BotCommand(command="access", description="Выдать доступ пользователю"),
    BotCommand(command="unaccess", description="Забрать доступ у пользователя"),
    BotCommand(command="users", description="Список пользователей с доступом"),
    BotCommand(command="mail", description="Рассылка всем пользователям бота"),
]


async def apply_commands_scope(user_id: int):
    """Выставить пользователю подходящий набор команд в меню Telegram."""
    try:
        if is_admin(user_id):
            commands = ADMIN_COMMANDS
        elif user_id in ALLOWED_USER_IDS:
            commands = ACCESS_COMMANDS
        else:
            commands = DEFAULT_COMMANDS
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
    except Exception as e:
        logger.debug(f"Не удалось выставить команды для {user_id}: {e}")


# ============ ОБЩИЕ УТИЛИТЫ ============
async def fetch_json(url, description="API"):
    """Универсальная функция для получения JSON данных."""
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
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
    return await fetch_json(API_URL, "Servers API")


async def fetch_youtubers():
    return await fetch_json(YOUTUBERS_API_URL, "YouTubers API")


def update_max_online(server_id, online):
    """Обновить максимальный зафиксированный онлайн сервера, если нужно."""
    global MAX_ONLINE_STATE
    old_max = MAX_ONLINE_STATE.get(server_id, 0)
    if online > old_max:
        MAX_ONLINE_STATE[server_id] = online
        save_max_online(MAX_ONLINE_STATE)


def update_test_server_store(server_id, info):
    """Запоминаем инфу о тестовом сервере (ID 1-91), чтобы /getallip
    мог отдать данные даже по серверам, которые уже удалены из API."""
    if server_id in TEST_SERVER_RANGE:
        TEST_SERVERS_STATE[server_id] = {
            "id": server_id,
            "name": info.get("name", "Без имени"),
            "ip": info.get("ip", "Нет данных"),
            "port": info.get("port", "Нет данных"),
            "url": info.get("url") or None,
        }
        save_test_servers(TEST_SERVERS_STATE)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_private(message: types.Message) -> bool:
    return message.chat.type == "private"


def track_user(user_id: int):
    """Запоминаем каждого, кто хоть раз написал боту — нужно для /mail."""
    global ALL_USER_IDS
    if user_id not in ALL_USER_IDS:
        ALL_USER_IDS.append(user_id)
        save_all_users(ALL_USER_IDS)


async def is_subscribed(user_id: int) -> bool:
    """Проверка подписки пользователя на обязательный канал."""
    try:
        member = await bot.get_chat_member(SUBSCRIBE_CHANNEL_ID, user_id)
        return member.status not in ("left", "kicked")
    except Exception as e:
        logger.warning(f"Не удалось проверить подписку {user_id}: {e}")
        # Если бот не может проверить (например не админ в канале) —
        # не блокируем пользователя наглухо, но логируем проблему.
        return False


def subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=SUBSCRIBE_CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
    ])


async def require_subscription(answer, user_id: int) -> bool:
    """Общая проверка подписки. answer — функция-ответчик (message.answer / callback.message.answer)."""
    if await is_subscribed(user_id):
        return True
    await answer(
        "🔒 Чтобы пользоваться ботом, подпишитесь на наш канал, "
        "а затем нажмите кнопку «Я подписался».",
        reply_markup=subscribe_keyboard()
    )
    return False


async def require_access(answer, user_id: int, chat_type: str) -> bool:
    """Проверка доступа (для /youtube, /getip, /getallip, /getactualip и т.п.)."""
    if is_admin(user_id) or user_id in ALLOWED_USER_IDS:
        return True
    if chat_type == "private":
        await answer("🚫 Эта команда доступна только пользователям с доступом.\nОбратитесь к администратору.")
    return False


def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 Статус", callback_data="menu_status")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu_help")],
    ]
    if is_admin(user_id) or user_id in ALLOWED_USER_IDS:
        rows.append([
            InlineKeyboardButton(text="🎬 YouTube ники", callback_data="menu_youtube"),
        ])
        rows.append([
            InlineKeyboardButton(text="🌐 GetAllIP", callback_data="menu_getallip"),
            InlineKeyboardButton(text="🗂 GetActualIP", callback_data="menu_getactualip"),
        ])
    if is_admin(user_id):
        rows.append([
            InlineKeyboardButton(text="👥 Пользователи", callback_data="menu_users"),
            InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_refresh"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_start_text(user_id: int) -> str:
    lines = [
        "🤖 *Бот мониторинга серверов*\n",
        "Добро пожаловать! Используйте команды или кнопки ниже.",
    ]
    return "\n".join(lines)


def build_help_text(user_id: int) -> str:
    lines = [
        "🤖 *Команды бота*\n",
        "👥 *Доступно всем:*",
        "/start — Информация о боте",
        "/status — Онлайн серверов (работает в любом чате)",
        "/help — Это сообщение",
    ]
    if is_admin(user_id) or user_id in ALLOWED_USER_IDS:
        lines += [
            "",
            "🔑 *Команды для пользователей с доступом:*",
            "/youtube — Выгрузить .json со всеми никами YouTubers",
            "/getip <id> — Название, IP, порт сервера по ID",
            "/getallip — .json IP всех тестовых серверов (когда-либо добавлялись)",
            "/getactualip — .json IP всех серверов, кроме ID 1–90",
        ]
    if is_admin(user_id):
        lines += [
            "",
            "👑 *Команды администратора (только в ЛС):*",
            "/refresh — Обновить состояние мониторинга",
            "/access @user/id — Выдать доступ",
            "/unaccess @user/id — Забрать доступ",
            "/users — Список пользователей с доступом",
            "/mail <текст> — Рассылка всем пользователям бота",
        ]
    return "\n".join(lines)


# ============ МОНИТОРИНГ: YOUTUBE ============
async def check_youtubers():
    """Проверка изменений в списке YouTubers. Всё уходит ТОЛЬКО в YOUTUBE_CHANNEL_ID."""
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
            await bot.send_message(YOUTUBE_CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🎬 Новый YouTuber: {nickname}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о YouTuber: {e}")

    for nickname in removed_youtubers:
        message = (
            f"❌ *YouTuber удален из списка*\n\n"
            f"👤 Никнейм: `{html.escape(str(nickname))}`"
        )

        try:
            await bot.send_message(YOUTUBE_CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"❌ Удален YouTuber: {nickname}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об удалении YouTuber: {e}")

    youtubers_state = current_youtubers


# ============ МОНИТОРИНГ: СЕРВЕРЫ ============
async def check_servers():
    """
    Проверка изменений по серверам.

    - Добавление / удаление / переименование серверов -> ТОЛЬКО SERVERS_CHANNEL_ID
    - Заход/выход игроков -> ТОЛЬКО для сервера TRACKED_PLAYER_SERVER_ID (229),
      уходит ТОЛЬКО в PLAYERS_229_CHANNEL_ID. Остальные сервера никуда не шлют
      уведомления о заходе/выходе игроков.
    """
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
                api_max_online = server.get("maxonline", None)
                if api_max_online is not None:
                    try:
                        api_max_online = int(api_max_online)
                    except (ValueError, TypeError):
                        api_max_online = None

                info = {
                    "name": server.get("name", "Без имени"),
                    "online": online_value,
                    "ip": server.get("ip", "Нет данных"),
                    "port": server.get("port", "Нет данных"),
                    "url": server.get("url"),
                    "maxonline": api_max_online,
                }
                current_state[server_id] = info

                update_max_online(server_id, online_value)
                if api_max_online is not None:
                    update_max_online(server_id, api_max_online)

                update_test_server_store(server_id, info)

    if not server_state:
        server_state = current_state
        logger.info(f"📊 Servers: начальное состояние ({len(server_state)} серверов)")
        return

    # --- Новые серверы ---
    for server_id, info in current_state.items():
        name = info["name"]
        current_online = info["online"]
        server_ip = info["ip"]
        server_port = info["port"]

        if server_id not in server_state:
            message = (
                f"🆕 *Новый сервер!*\n"
                f"📌 {html.escape(str(name))}\n"
                f"🆔 ID: `{server_id}`\n"
                f"🌐 IP: `{html.escape(str(server_ip))}`\n"
                f"🔌 Port: `{html.escape(str(server_port))}`"
            )
            try:
                await bot.send_message(SERVERS_CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"🆕 Новый сервер: {name} (ID: {server_id}) {server_ip}:{server_port}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о новом сервере: {e}")
            continue

        # --- Переименование ---
        old_name = server_state[server_id]["name"]
        if old_name != name:
            message = (
                f"✏️ *Переименован сервер!*\n"
                f"📌 {html.escape(str(old_name))} → {html.escape(str(name))}\n"
                f"🆔 ID: `{server_id}`"
            )
            try:
                await bot.send_message(SERVERS_CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"✏️ Переименован: {old_name} → {name} (ID: {server_id})")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о переименовании: {e}")

        # --- Заход/выход игроков: ТОЛЬКО отслеживаемый сервер ---
        if server_id != TRACKED_PLAYER_SERVER_ID:
            continue

        old_online = server_state[server_id]["online"]

        if current_online > old_online:
            diff = current_online - old_online
            message = (
                f"🟢 *{html.escape(str(name))}*\n"
                f"Зашел игрок! (+{diff})\n"
                f"Текущий онлайн: {current_online}"
            )
            try:
                await bot.send_message(PLAYERS_229_CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"🟢 {name}: {old_online} → {current_online}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления об онлайне: {e}")

        elif current_online < old_online:
            diff = old_online - current_online
            message = (
                f"🔴 *{html.escape(str(name))}*\n"
                f"Вышел игрок! (-{diff})\n"
                f"Текущий онлайн: {current_online}"
            )
            try:
                await bot.send_message(PLAYERS_229_CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"🔴 {name}: {old_online} → {current_online}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления об онлайне: {e}")

    # --- Удалённые серверы ---
    removed_servers = set(server_state.keys()) - set(current_state.keys())
    for server_id in removed_servers:
        old_info = server_state[server_id]
        name = old_info["name"]
        old_ip = old_info.get("ip", "Нет данных")
        old_port = old_info.get("port", "Нет данных")

        message = (
            f"🗑️ *Сервер удален!*\n"
            f"📌 {html.escape(str(name))}\n"
            f"🆔 ID: `{server_id}`\n"
            f"🌐 IP: `{html.escape(str(old_ip))}`\n"
            f"🔌 Port: `{html.escape(str(old_port))}`"
        )
        try:
            await bot.send_message(SERVERS_CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🗑️ Удален сервер: {name} (ID: {server_id}) {old_ip}:{old_port}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об удалении сервера: {e}")

    server_state = current_state


async def monitor_loop():
    """Фоновый цикл мониторинга."""
    logger.info(f"🔄 Мониторинг запущен (интервал: {CHECK_INTERVAL} сек)")

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


# ============ ОБЩАЯ ЛОГИКА КОМАНД (переиспользуется командами и кнопками) ============
async def send_status(answer, user_id: int, chat_id: int, chat_type: str):
    """
    /status работает в ЛЮБОМ чате.
    В ЛС кулдауна нет. В групповых чатах — свой кулдаун на каждый чат.
    """
    if not await require_subscription(answer, user_id):
        return

    is_priv = chat_type == "private"

    if not is_priv:
        now = time.time()
        last_call = status_cooldowns.get(chat_id, 0.0)
        elapsed = now - last_call
        if elapsed < STATUS_COOLDOWN:
            remaining = int(STATUS_COOLDOWN - elapsed)
            minutes = remaining // 60
            seconds = remaining % 60
            await answer(
                f"⏳ Команда на кулдауне в этом чате. Попробуйте через {minutes} мин {seconds} сек."
            )
            return

    data = await fetch_servers()

    if not data or not isinstance(data, list):
        await answer("Нет данных")
        return

    if not is_priv:
        status_cooldowns[chat_id] = time.time()

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

        api_max = server.get("maxonline", None)
        if api_max is not None:
            try:
                api_max = int(api_max)
            except (ValueError, TypeError):
                api_max = None

        update_max_online(server_id, online)
        if api_max is not None:
            update_max_online(server_id, api_max)

        local_max = MAX_ONLINE_STATE.get(server_id, online)
        if api_max is not None:
            max_online = max(api_max, local_max)
        else:
            max_online = local_max

        lines.append(f"{html.escape(str(name))}. {max_online}/{online}")

    if not lines:
        await answer("Нет данных для отображения")
        return

    body = "\n".join(lines)
    max_len = 3800

    if len(body) <= max_len:
        await answer(f"<blockquote>{body}</blockquote>", parse_mode="HTML")
    else:
        chunk = []
        chunk_len = 0
        for line in lines:
            if chunk_len + len(line) + 1 > max_len:
                await answer(f"<blockquote>{chr(10).join(chunk)}</blockquote>", parse_mode="HTML")
                chunk = []
                chunk_len = 0
            chunk.append(line)
            chunk_len += len(line) + 1
        if chunk:
            await answer(f"<blockquote>{chr(10).join(chunk)}</blockquote>", parse_mode="HTML")


def format_server_entry(name, ip, port, url) -> dict:
    return {
        "name": name if name not in (None, "") else "Без имени",
        "ip": ip if ip not in (None, "") else "Нет данных",
        "port": port if port not in (None, "") else "Нет данных",
        "url": url if url not in (None, "") else None,
    }


async def send_getallip(message: types.Message):
    entries = [
        format_server_entry(v.get("name"), v.get("ip"), v.get("port"), v.get("url"))
        for _id, v in sorted(TEST_SERVERS_STATE.items())
    ]
    payload = json.dumps(entries, ensure_ascii=False, indent=2)
    file = BufferedInputFile(payload.encode("utf-8"), filename="all_test_servers_ip.json")
    await message.answer_document(file, caption=f"🧪 Тестовых серверов в базе: {len(entries)}")


async def send_getactualip(message: types.Message):
    data = await fetch_servers()
    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных от API серверов")
        return

    entries = []
    for server in data:
        if not isinstance(server, dict):
            continue
        server_id = server.get("id")
        if server_id in ACTUAL_IP_EXCLUDE_RANGE:
            continue
        entries.append(format_server_entry(
            server.get("name"), server.get("ip"), server.get("port"), server.get("url")
        ))

    payload = json.dumps(entries, ensure_ascii=False, indent=2)
    file = BufferedInputFile(payload.encode("utf-8"), filename="actual_servers_ip.json")
    await message.answer_document(file, caption=f"🌐 Актуальных серверов: {len(entries)}")


# ============ КОМАНДЫ: СТАРТ / ПОМОЩЬ / СТАТУС ============
@dp.message(Command("start"))
async def start_command(message: types.Message):
    if not is_private(message):
        return

    track_user(message.from_user.id)

    if not await require_subscription(message.answer, message.from_user.id):
        return

    await apply_commands_scope(message.from_user.id)

    await message.answer(
        build_start_text(message.from_user.id),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    track_user(message.from_user.id)

    if not await require_subscription(message.answer, message.from_user.id):
        return

    await message.answer(build_help_text(message.from_user.id), parse_mode="Markdown")


@dp.message(Command("status"))
async def status_command(message: types.Message):
    track_user(message.from_user.id)
    await send_status(message.answer, message.from_user.id, message.chat.id, message.chat.type)


# ============ КОМАНДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ С ДОСТУПОМ ============
@dp.message(Command("youtube"))
async def youtube_command(message: types.Message):
    if not is_private(message):
        return

    track_user(message.from_user.id)

    if not await require_subscription(message.answer, message.from_user.id):
        return
    if not await require_access(message.answer, message.from_user.id, message.chat.type):
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

    await message.answer_document(file, caption=f"🎬 Всего ников: {len(nicknames)}")


@dp.message(Command("getip"))
async def getip_command(message: types.Message):
    if not is_private(message):
        return

    track_user(message.from_user.id)

    if not await require_subscription(message.answer, message.from_user.id):
        return
    if not await require_access(message.answer, message.from_user.id, message.chat.type):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Использование: `/getip <id_сервера>`", parse_mode="Markdown")
        return

    try:
        server_id = int(args[1].strip())
    except ValueError:
        await message.answer("❌ ID сервера должен быть числом")
        return

    data = await fetch_servers()
    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных от API серверов")
        return

    server = next(
        (s for s in data if isinstance(s, dict) and s.get("id") == server_id),
        None
    )
    if not server:
        await message.answer(f"❌ Сервер с ID {server_id} не найден")
        return

    entry = format_server_entry(server.get("name"), server.get("ip"), server.get("port"), server.get("url"))

    text = (
        f"📌 *Информация о сервере {server_id}*\n\n"
        f"1️⃣ Название: `{html.escape(str(entry['name']))}`\n"
        f"2️⃣ Айпи: `{html.escape(str(entry['ip']))}`\n"
        f"3️⃣ Порт: `{html.escape(str(entry['port']))}`\n"
        f"4️⃣ Url: `{html.escape(str(entry['url'] or '—'))}`"
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("getallip"))
async def getallip_command(message: types.Message):
    if not is_private(message):
        return

    track_user(message.from_user.id)

    if not await require_subscription(message.answer, message.from_user.id):
        return
    if not await require_access(message.answer, message.from_user.id, message.chat.type):
        return

    await send_getallip(message)


@dp.message(Command("getactualip"))
async def getactualip_command(message: types.Message):
    if not is_private(message):
        return

    track_user(message.from_user.id)

    if not await require_subscription(message.answer, message.from_user.id):
        return
    if not await require_access(message.answer, message.from_user.id, message.chat.type):
        return

    await send_getactualip(message)


@dp.message(Command("refresh"))
async def refresh_command(message: types.Message):
    if not is_private(message):
        return

    track_user(message.from_user.id)

    if not await require_subscription(message.answer, message.from_user.id):
        return
    if not await require_access(message.answer, message.from_user.id, message.chat.type):
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


# ============ КОМАНДЫ УПРАВЛЕНИЯ ДОСТУПОМ (ADMIN) ============
async def _resolve_target(message: types.Message, target: str):
    """Возвращает (user_id, display_name) или (None, None) при ошибке."""
    if target.startswith("@"):
        try:
            user = await bot.get_chat(target)
            return user.id, target
        except Exception:
            await message.answer(f"❌ Не найден пользователь {target}")
            return None, None
    else:
        try:
            user_id = int(target)
            return user_id, f"ID: {user_id}"
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте @username или ID")
            return None, None


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

    user_id, username = await _resolve_target(message, args[1])
    if user_id is None:
        return

    if is_admin(user_id):
        await message.answer("❌ Админ уже имеет доступ")
        return

    if user_id in ALLOWED_USER_IDS:
        await message.answer(f"ℹ️ Пользователь {username} уже имеет доступ")
        return

    ALLOWED_USER_IDS.append(user_id)
    save_allowed_users(ALLOWED_USER_IDS)
    await apply_commands_scope(user_id)

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

    user_id, username = await _resolve_target(message, args[1])
    if user_id is None:
        return

    if is_admin(user_id):
        await message.answer("❌ Нельзя забрать доступ у админа")
        return

    if user_id not in ALLOWED_USER_IDS:
        await message.answer(f"ℹ️ Пользователь {username} не имеет доступа")
        return

    ALLOWED_USER_IDS.remove(user_id)
    save_allowed_users(ALLOWED_USER_IDS)
    await apply_commands_scope(user_id)

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
            prefix = "👑" if is_admin(uid) else "•"

            if user.username:
                lines.append(f"{prefix} @{user.username} (`{uid}`)")
            else:
                lines.append(f"{prefix} {name} (`{uid}`)")
        except Exception:
            lines.append(f"• ID: `{uid}` (недоступен)")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@dp.message(Command("mail"))
async def mail_command(message: types.Message):
    if not is_private(message):
        return

    if not is_admin(message.from_user.id):
        await message.answer("❌ Только админ может делать рассылку")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Использование: /mail <текст сообщения>")
        return

    mail_text = parts[1]
    recipients = list(ALL_USER_IDS)

    if not recipients:
        await message.answer("📋 Пока нет ни одного пользователя для рассылки")
        return

    status_msg = await message.answer(f"📨 Рассылка запущена... 0/{len(recipients)}")

    sent, failed = 0, 0
    for uid in recipients:
        try:
            await bot.send_message(uid, mail_text)
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Не удалось отправить сообщение {uid}: {e}")
        await asyncio.sleep(0.05)

    try:
        await status_msg.edit_text(
            f"📨 Рассылка завершена!\n✅ Успешно: {sent}\n❌ Не удалось: {failed}"
        )
    except Exception:
        await message.answer(f"📨 Рассылка завершена!\n✅ Успешно: {sent}\n❌ Не удалось: {failed}")

    logger.info(f"📨 Рассылка от {message.from_user.id}: {sent} успешно, {failed} ошибок")


# ============ ОБРАБОТКА КНОПОК (INLINE) ============
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.answer("✅ Подписка подтверждена!", show_alert=True)
        await apply_commands_scope(callback.from_user.id)
        try:
            await callback.message.edit_text(
                build_start_text(callback.from_user.id),
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(callback.from_user.id),
            )
        except Exception:
            await callback.message.answer(
                build_start_text(callback.from_user.id),
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(callback.from_user.id),
            )
    else:
        await callback.answer("❌ Вы ещё не подписались на канал", show_alert=True)


@dp.callback_query(F.data == "menu_status")
async def menu_status_callback(callback: types.CallbackQuery):
    await callback.answer()
    await send_status(
        callback.message.answer,
        callback.from_user.id,
        callback.message.chat.id,
        callback.message.chat.type,
    )


@dp.callback_query(F.data == "menu_help")
async def menu_help_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not await require_subscription(callback.message.answer, callback.from_user.id):
        return
    await callback.message.answer(build_help_text(callback.from_user.id), parse_mode="Markdown")


@dp.callback_query(F.data == "menu_youtube")
async def menu_youtube_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not await require_subscription(callback.message.answer, callback.from_user.id):
        return
    if not await require_access(callback.message.answer, callback.from_user.id, "private"):
        return

    data = last_youtubers_data
    if not data:
        data = await fetch_youtubers()

    if not data or not isinstance(data, list):
        await callback.message.answer("❌ Нет данных от YouTubers API")
        return

    nicknames = [yt.get("nickname") for yt in data if isinstance(yt, dict) and yt.get("nickname")]
    payload = json.dumps(nicknames, ensure_ascii=False, indent=2)
    file = BufferedInputFile(payload.encode("utf-8"), filename=YOUTUBE_EXPORT_FILENAME)
    await callback.message.answer_document(file, caption=f"🎬 Всего ников: {len(nicknames)}")


@dp.callback_query(F.data == "menu_getallip")
async def menu_getallip_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not await require_subscription(callback.message.answer, callback.from_user.id):
        return
    if not await require_access(callback.message.answer, callback.from_user.id, "private"):
        return
    await send_getallip(callback.message)


@dp.callback_query(F.data == "menu_getactualip")
async def menu_getactualip_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not await require_subscription(callback.message.answer, callback.from_user.id):
        return
    if not await require_access(callback.message.answer, callback.from_user.id, "private"):
        return
    await send_getactualip(callback.message)


@dp.callback_query(F.data == "menu_users")
async def menu_users_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    await users_command(callback.message)  # доступно только для форматирования текста; ID проверок нет — только админ дошёл сюда


@dp.callback_query(F.data == "menu_refresh")
async def menu_refresh_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    global server_state, youtubers_state
    server_state = {}
    youtubers_state = set()
    await check_servers()
    await check_youtubers()
    await callback.message.answer(
        f"✅ Состояние обновлено!\n📊 Серверов: {len(server_state)}\n🎬 YouTubers: {len(youtubers_state)}"
    )


# ============ ОБРАБОТЧИК НЕИЗВЕСТНЫХ СООБЩЕНИЙ В ЛС ============
@dp.message()
async def private_message_handler(message: types.Message):
    if message.chat.type != "private":
        return

    track_user(message.from_user.id)

    if not await require_subscription(message.answer, message.from_user.id):
        return

    await message.answer(
        "❓ Неизвестная команда\nИспользуйте /help для списка команд",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )
# ============================================================


async def main():
    print("=" * 50)
    print("🤖 БОТ МОНИТОРИНГА СЕРВЕРОВ")
    print("=" * 50)
    print(f"👑 Админы: {ADMIN_IDS}")
    print(f"📢 Канал серверов (add/remove): {SERVERS_CHANNEL_ID}")
    print(f"📢 Канал игроков сервера {TRACKED_PLAYER_SERVER_ID}: {PLAYERS_229_CHANNEL_ID}")
    print(f"📢 Канал YouTube: {YOUTUBE_CHANNEL_ID}")
    print(f"🔒 Канал обязательной подписки: {SUBSCRIBE_CHANNEL_ID}")
    print(f"⏱️  Интервал мониторинга: {CHECK_INTERVAL} сек")
    print(f"🙈 Скрыто в /status: ID 1–91")
    print(f"👥 Пользователей с доступом: {len(ALLOWED_USER_IDS)}")
    print(f"🕐 Кулдаун /status (групповые чаты): {STATUS_COOLDOWN} сек, свой на чат")
    print("=" * 50)

    try:
        await bot.set_my_commands(DEFAULT_COMMANDS, scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning(f"Не удалось выставить команды по умолчанию: {e}")

    for uid in ALLOWED_USER_IDS:
        await apply_commands_scope(uid)

    asyncio.create_task(monitor_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
