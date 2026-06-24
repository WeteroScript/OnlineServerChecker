import os
import aiohttp
import asyncio
import logging
import json
import subprocess
import platform
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://api.blackhub.team/servers.json"
YOUTUBERS_API_URL = "https://api.blackrussia.online/client/listOfYoutubers.json"
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1003909198412")
CHECK_INTERVAL = 90  # Секунд (1:30 минуты)

# 👑 АДМИН
ADMIN_ID = 5877790074

# 🔇 Серверы, которые НЕ нужно отслеживать (по ID)
IGNORED_SERVERS = [
    202, 203, 204, 205, 206, 207, 208, 209, 210,
    211, 212, 213, 214, 215, 216, 217, 218, 219,
    220, 221, 222, 223, 224, 225, 226
]

# 📋 Список серверов для пинга
PING_SERVERS = {
    "Dev Test Server": [
        {"name": "D2", "ip": "5.188.118.53"},
        {"name": "D1", "ip": "5.188.118.53"},
        {"name": "HARD-2", "ip": "5.188.118.53"},
        {"name": "HARD-1", "ip": "5.188.118.53"},
        {"name": "BURY-2", "ip": "5.188.118.53"},
        {"name": "BURY-1", "ip": "5.188.118.53"},
        {"name": "MAZER-2", "ip": "5.188.118.53"},
        {"name": "MAZER-1", "ip": "5.188.118.53"},
        {"name": "ihn1fi-2", "ip": "5.188.118.53"},
        {"name": "ihn1fi-1", "ip": "5.188.118.53"},
        {"name": "Baton-2", "ip": "5.188.118.53"},
        {"name": "Baton-1", "ip": "5.188.118.53"},
        {"name": "Tokie-2", "ip": "5.188.118.53"},
        {"name": "Tokie-1", "ip": "5.188.118.53"},
        {"name": "estranossa-2", "ip": "5.188.118.53"},
        {"name": "estranossa-1", "ip": "5.188.118.53"},
        {"name": "Test Server Core", "ip": "51.159.125.199"},
        {"name": "like2bemike-2", "ip": "5.188.118.53"},
        {"name": "like2bemike-1", "ip": "5.188.118.53"},
        {"name": "slaughter-1", "ip": "5.188.118.53"},
        {"name": "slaughter-2", "ip": "5.188.118.53"},
        {"name": "donbeton-1", "ip": "5.188.118.53"},
        {"name": "donbeton-2", "ip": "5.188.118.53"},
    ],
    "Work Test Server": [
        {"name": "P1", "ip": "80.66.82.19"},
        {"name": "P2", "ip": "80.66.82.19"},
        {"name": "P3", "ip": "80.66.82.19"},
        {"name": "P4", "ip": "80.66.82.19"},
        {"name": "YouTube", "ip": "80.66.82.19"},
        {"name": "stage-229", "ip": "80.66.82.150"},
        {"name": "CBT-PR", "ip": "185.169.134.21"},
        {"name": "CBT2-PR", "ip": "185.169.134.20"},
    ],
    "Local Test Server": [
        {"name": "feature-update-wp2", "ip": "10.211.0.195"},
        {"name": "feature-add-k8s-deploy", "ip": "10.211.3.89"},
        {"name": "feature-season4-main", "ip": "10.211.3.160"},
        {"name": "feature-notfix-sounds", "ip": "10.211.0.29"},
        {"name": "feature-season3-main", "ip": "10.211.2.178"},
        {"name": "office_perf", "ip": "10.3.0.132"},
        {"name": "test-k8s-2", "ip": "10.211.2.178"},
        {"name": "test-k8s-1", "ip": "10.211.0.81"},
    ]
}

# Файл для хранения разрешенных пользователей
ALLOWED_USERS_FILE = "allowed_users.json"

# Загружаем разрешенных пользователей
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

# Загружаем разрешенных пользователей
ALLOWED_USER_IDS = load_allowed_users()

# Гарантируем, что админ есть в списке
if ADMIN_ID not in ALLOWED_USER_IDS:
    ALLOWED_USER_IDS.append(ADMIN_ID)
    save_allowed_users(ALLOWED_USER_IDS)
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


async def check_youtubers():
    """Проверка изменений в списке YouTubers."""
    global youtubers_state
    
    data = await fetch_youtubers()
    
    if not data or not isinstance(data, list):
        logger.warning("YouTubers API: нет данных или неверный формат")
        return
    
    # Создаем множество текущих YouTubers (по никнейму)
    current_youtubers = set()
    youtubers_dict = {}
    
    for yt in data:
        if isinstance(yt, dict):
            nickname = yt.get("nickname")
            if nickname:
                current_youtubers.add(nickname)
                youtubers_dict[nickname] = yt
    
    # Если это первый запуск - просто сохраняем состояние
    if not youtubers_state:
        youtubers_state = current_youtubers
        logger.info(f"📹 YouTubers: начальное состояние ({len(youtubers_state)} человек)")
        return
    
    # Проверяем новых YouTubers
    new_youtubers = current_youtubers - youtubers_state
    removed_youtubers = youtubers_state - current_youtubers
    
    # Уведомляем о новых YouTubers
    for nickname in new_youtubers:
        yt_info = youtubers_dict.get(nickname, {})
        youtube_link = yt_info.get("youtube", "Нет ссылки")
        
        message = (
            f"🎬 *Новый YouTuber добавлен!*\n\n"
            f"👤 Никнейм: `{nickname}`\n"
            f"🔗 YouTube: {youtube_link}"
        )
        
        try:
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🎬 Новый YouTuber: {nickname}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о YouTuber: {e}")
    
    # Уведомляем об удаленных YouTubers
    for nickname in removed_youtubers:
        message = (
            f"❌ *YouTuber удален из списка*\n\n"
            f"👤 Никнейм: `{nickname}`"
        )
        
        try:
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"❌ Удален YouTuber: {nickname}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об удалении YouTuber: {e}")
    
    # Обновляем состояние
    youtubers_state = current_youtubers


async def check_servers():
    """Проверка изменений в онлайне серверов."""
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
                current_state[server_id] = {
                    "name": server.get("name", "Без имени"),
                    "online": int(server.get("online", 0)),
                    "ip": server.get("ip", "Неизвестно"),
                    "port": server.get("port", "Неизвестно")
                }
    
    # Если это первый запуск
    if not server_state:
        server_state = current_state
        logger.info(f"📊 Servers: начальное состояние ({len(server_state)} серверов)")
        return
    
    # Проверяем новые серверы
    for server_id, info in current_state.items():
        name = info["name"]
        current_online = info["online"]
        is_ignored = server_id in IGNORED_SERVERS
        
        # Новый сервер
        if server_id not in server_state:
            message = (
                f"🆕 *Новый сервер!*\n"
                f"📌 {name}\n"
                f"🆔 ID: `{server_id}`\n"
                f"🌐 IP: `{info['ip']}`\n"
                f"🔌 Port: `{info['port']}`"
            )
            try:
                await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
                logger.info(f"🆕 Новый сервер: {name} (ID: {server_id})")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о новом сервере: {e}")
            continue
        
        # Переименование сервера
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
        
        # Игнорируем изменения онлайна для игнорируемых серверов
        if is_ignored:
            continue
        
        old_online = server_state[server_id]["online"]
        
        # Увеличение онлайна
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
        
        # Уменьшение онлайна
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
    
    # Проверяем удаленные серверы
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
    
    # Обновляем состояние
    server_state = current_state


async def monitor_loop():
    """Фоновый цикл мониторинга."""
    logger.info(f"🔄 Мониторинг запущен (интервал: {CHECK_INTERVAL} сек)")
    logger.info(f"🔇 Игнорируемых серверов: {len(IGNORED_SERVERS)}")
    
    # Инициализация начального состояния
    await check_servers()
    await check_youtubers()
    
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
    
    # Админ имеет доступ ВСЕГДА
    if user_id == ADMIN_ID:
        return True
    
    if user_id in ALLOWED_USER_IDS:
        return True
    
    if message.chat.type == "private":
        await message.answer("🚫 У вас нет доступа к этому боту")
    
    return False

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID
# ============================================================


async def get_server_info(server_name):
    """Найти сервер по имени."""
    for category, servers in PING_SERVERS.items():
        for server in servers:
            if server["name"] == server_name:
                return server
    return None


def get_ping_keyboard():
    """Создать клавиатуру с серверами по категориям."""
    builder = InlineKeyboardBuilder()
    
    for category, servers in PING_SERVERS.items():
        # Добавляем заголовок категории
        builder.button(text=f"━━ {category} ━━", callback_data="separator")
        
        # Добавляем серверы
        for server in servers:
            builder.button(
                text=f"🖥️ {server['name']}",
                callback_data=f"ping_{server['name']}"
            )
    
    builder.button(text="🔄 Обновить", callback_data="refresh_ping")
    builder.adjust(1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 1, 2, 2, 2, 1)
    
    return builder.as_markup()


def ping_server(ip, count=4):
    """ICMP пинг через системную команду."""
    try:
        if platform.system().lower() == 'windows':
            param = '-n'
        else:
            param = '-c'
        
        result = subprocess.run(
            ["ping", param, str(count), ip],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        return result.returncode == 0, result.stdout
    except subprocess.TimeoutExpired:
        return False, "Timeout (15s)"
    except Exception as e:
        return False, str(e)


# ============ КОМАНДЫ УПРАВЛЕНИЯ ДОСТУПОМ ============
@dp.message(Command("access"))
async def access_command(message: types.Message):
    """Выдать доступ пользователю. Только в ЛС."""
    if message.chat.type != "private":
        await message.answer("❌ Эта команда работает только в личных сообщениях")
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
        await message.answer(f"ℹ️ Пользователь {username} уже имеет доступ")
        return
    
    ALLOWED_USER_IDS.append(user_id)
    save_allowed_users(ALLOWED_USER_IDS)
    
    await message.answer(f"✅ Пользователь {username} получил доступ к боту")
    logger.info(f"✅ Доступ выдан: {username}")


@dp.message(Command("unaccess"))
async def unaccess_command(message: types.Message):
    """Забрать доступ у пользователя. Только в ЛС."""
    if message.chat.type != "private":
        await message.answer("❌ Эта команда работает только в личных сообщениях")
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
        await message.answer(f"ℹ️ Пользователь {username} не имеет доступа")
        return
    
    ALLOWED_USER_IDS.remove(user_id)
    save_allowed_users(ALLOWED_USER_IDS)
    
    await message.answer(f"✅ У пользователя {username} забран доступ к боту")
    logger.info(f"❌ Доступ забран: {username}")


@dp.message(Command("users"))
async def users_command(message: types.Message):
    """Показать список пользователей с доступом. Только в ЛС."""
    if message.chat.type != "private":
        await message.answer("❌ Эта команда работает только в личных сообщениях")
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
            if uid == ADMIN_ID:
                prefix = "👑"
            else:
                prefix = "•"
            
            if user.username:
                lines.append(f"{prefix} @{user.username} (`{uid}`)")
            else:
                lines.append(f"{prefix} {name} (`{uid}`)")
        except Exception as e:
            lines.append(f"• ID: `{uid}` (недоступен)")
    
    await message.answer("\n".join(lines), parse_mode="Markdown")


# ============ КОМАНДА /ip ============
@dp.message(Command("ip"))
async def ip_command(message: types.Message):
    """Получить IP и порт сервера по ID: /ip 205"""
    if not await check_access(message):
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /ip <ID_сервера>\nПример: /ip 205")
        return
    
    try:
        server_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    
    data = await fetch_servers()
    
    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных от API")
        return
    
    server = None
    for s in data:
        if isinstance(s, dict) and s.get("id") == server_id:
            server = s
            break
    
    if not server:
        await message.answer(f"❌ Сервер с ID {server_id} не найден")
        return
    
    name = server.get("name", "Без имени")
    ip = server.get("ip", "Неизвестно")
    port = server.get("port", "Неизвестно")
    online = server.get("online", "0")
    
    if ip != "Неизвестно" and port != "Неизвестно":
        response = (
            f"🖥️ *{name}*\n"
            f"🆔 ID: `{server_id}`\n"
            f"🌐 IP: `{ip}`\n"
            f"🔌 Port: `{port}`\n"
            f"👥 Онлайн: {online}\n\n"
            f"📌 `{ip}:{port}`"
        )
    else:
        response = (
            f"🖥️ *{name}*\n"
            f"🆔 ID: `{server_id}`\n"
            f"❌ Данные отсутствуют"
        )
    
    await message.answer(response, parse_mode="Markdown")


# ============ КОМАНДА /youtubers ============
@dp.message(Command("youtubers"))
async def youtubers_command(message: types.Message):
    """Показать список всех YouTubers."""
    if not await check_access(message):
        return
    
    data = await fetch_youtubers()
    
    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных от YouTubers API")
        return
    
    lines = [f"🎬 *Список YouTubers ({len(data)}):*\n"]
    
    for yt in data:
        if isinstance(yt, dict):
            nickname = yt.get("nickname", "Неизвестно")
            youtube = yt.get("youtube", "Нет ссылки")
            lines.append(f"👤 `{nickname}`\n🔗 {youtube}\n")
    
    text = "\n".join(lines)
    
    # Разбиваем на части, если текст слишком длинный
    if len(text) > 4096:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")


# ============ КОМАНДЫ БОТА ============
@dp.message(Command("start"))
async def start_command(message: types.Message):
    if not await check_access(message):
        return
    
    await message.answer(
        "🤖 *Бот мониторинга серверов*\n\n"
        "Бот отслеживает:\n"
        "• Изменения онлайна серверов\n"
        "• Новые/удаленные серверы\n"
        "• Новые/удаленные YouTubers\n\n"
        f"📌 Интервал проверки: {CHECK_INTERVAL} секунд\n"
        f"📢 Уведомления в канал\n\n"
        "📡 /ping — Пинг серверов\n"
        "🔍 /ip <ID> — IP и порт сервера\n"
        "🎬 /youtubers — Список YouTubers\n"
        "❓ /help — Все команды",
        parse_mode="Markdown"
    )


@dp.message(Command("status"))
async def status_command(message: types.Message):
    if not await check_access(message):
        return
    
    data = await fetch_servers()
    
    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных")
        return
    
    sorted_servers = sorted(
        data,
        key=lambda x: x.get("id", 0) if isinstance(x, dict) else 0
    )
    
    lines = ["📊 *Текущий онлайн серверов:*\n"]
    total_online = 0
    
    for server in sorted_servers:
        if isinstance(server, dict):
            name = server.get("name", "???")
            online = int(server.get("online", 0))
            server_id = server.get("id", "?")
            total_online += online
            
            if server_id in IGNORED_SERVERS:
                lines.append(f"🔇 {name} — {online}")
            else:
                lines.append(f"🟢 {name} — {online}")
    
    lines.append(f"\n📈 *Всего онлайн: {total_online}*")
    
    text = "\n".join(lines)
    
    if len(text) > 4096:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")


@dp.message(Command("refresh"))
async def refresh_command(message: types.Message):
    if not await check_access(message):
        return
    
    global server_state, youtubers_state
    
    # Сбрасываем состояние
    server_state = {}
    youtubers_state = set()
    
    # Загружаем новое состояние
    await check_servers()
    await check_youtubers()
    
    await message.answer(
        f"✅ Состояние обновлено!\n"
        f"📊 Серверов: {len(server_state)}\n"
        f"🎬 YouTubers: {len(youtubers_state)}"
    )


@dp.message(Command("ping"))
async def ping_menu_command(message: types.Message):
    """Показать меню с серверами для пинга."""
    if not await check_access(message):
        return
    
    keyboard = get_ping_keyboard()
    await message.answer(
        "📡 *Выберите сервер для пинга:*\n\n"
        "Нажмите на кнопку с названием сервера",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    if not await check_access(message):
        return
    
    is_admin_user = is_admin(message.from_user.id)
    
    commands = [
        "🤖 *Доступные команды:*\n",
        "/start — Информация о боте",
        "/status — Онлайн всех серверов",
        "/refresh — Обновить состояние",
        "/ping — Пинг серверов",
        "/ip <ID> — IP и порт сервера",
        "/youtubers — Список YouTubers",
        "/help — Список команд"
    ]
    
    if is_admin_user:
        commands.extend([
            "",
            "👑 *Команды администратора (только в ЛС):*",
            "/access @user/id — Выдать доступ",
            "/unaccess @user/id — Забрать доступ",
            "/users — Список пользователей"
        ])
    
    await message.answer("\n".join(commands), parse_mode="Markdown")


# ============ ОБРАБОТЧИК КНОПОК ============
@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    """Обработка нажатий на кнопки."""
    data = callback.data
    
    if data == "separator":
        await callback.answer()
        return
    
    if data == "refresh_ping":
        keyboard = get_ping_keyboard()
        try:
            await callback.message.edit_text(
                "📡 *Выберите сервер для пинга:*\n\n"
                "Нажмите на кнопку с названием сервера",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            await callback.answer("🔄 Обновлено")
        except Exception as e:
            await callback.answer("Уже обновлено")
        return
    
    if data.startswith("ping_"):
        server_name = data.replace("ping_", "")
        server_info = await get_server_info(server_name)
        
        if not server_info:
            await callback.answer("❌ Сервер не найден")
            return
        
        ip = server_info["ip"]
        
        await callback.answer(f"🔍 Пингую {server_name}...")
        
        status_msg = await callback.message.answer(
            f"🔍 *Пингую {server_name}...*\n"
            f"🌐 {ip}",
            parse_mode="Markdown"
        )
        
        # Выполняем пинг
        ping_success, ping_output = ping_server(ip, count=4)
        
        if ping_success:
            ping_status = "✅ ДОСТУПЕН"
        else:
            ping_status = "❌ НЕДОСТУПЕН"
        
        result_text = (
            f"📡 *Результат пинга*\n\n"
            f"🖥️ *{server_name}*\n"
            f"🌐 `{ip}`\n\n"
            f"📶 {ping_status}"
        )
        
        try:
            await status_msg.edit_text(result_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")


# ============ ОБРАБОТЧИК ДЛЯ ЛИЧНЫХ СООБЩЕНИЙ ============
@dp.message()
async def private_message_handler(message: types.Message):
    if message.chat.type == "private":
        if not await check_access(message):
            return
        await message.answer(
            "❓ Неизвестная команда\n"
            "Используйте /help для списка команд"
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
    print(f"🔇 Игнорируется: {len(IGNORED_SERVERS)} серверов")
    print(f"👥 Пользователей с доступом: {len(ALLOWED_USER_IDS)}")
    print(f"📡 Серверов для пинга: {sum(len(s) for s in PING_SERVERS.values())}")
    print(f"🎬 Мониторинг YouTubers: включен")
    print("=" * 50)
    
    asyncio.create_task(monitor_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
