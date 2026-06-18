import os
import aiohttp
import asyncio
import logging
import json
import socket
import subprocess
import platform
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://api.blackhub.team/servers.json"
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1003909198412")
CHECK_INTERVAL = 15  # Секунд (1:30 минуты)

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
            json.dump(users, f)
    except Exception as e:
        logging.error(f"Ошибка сохранения allowed_users: {e}")

# Загружаем разрешенных пользователей
ALLOWED_USER_IDS = load_allowed_users()

# Гарантируем, что админ есть в списке
if ADMIN_ID not in ALLOWED_USER_IDS:
    ALLOWED_USER_IDS.append(ADMIN_ID)
    save_allowed_users(ALLOWED_USER_IDS)
# ================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Храним предыдущее состояние серверов
server_state = {}


async def fetch_servers():
    """Получение данных из API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                return None
    except Exception as e:
        logger.error(f"Ошибка API: {e}")
        return None


async def check_and_notify():
    """Проверка изменений онлайна и отправка уведомлений."""
    global server_state
    
    data = await fetch_servers()
    
    if not data or not isinstance(data, list):
        logger.warning("Нет данных от API")
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
    
    for server_id, info in current_state.items():
        name = info["name"]
        current_online = info["online"]
        is_ignored = server_id in IGNORED_SERVERS
        
        if server_id not in server_state:
            message = (
                f"🆕 *Новый сервер!*\n"
                f"📌 {name}\n"
                f"🌐 IP: {info.get('ip', 'Неизвестно')}\n"
                f"🔌 Port: {info.get('port', 'Неизвестно')}"
            )
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🆕 Новый сервер: {name} (ID: {server_id})")
            continue
        
        old_name = server_state[server_id]["name"]
        if old_name != name:
            message = (
                f"✏️ *Переименован сервер!*\n"
                f"📌 {old_name} → {name}"
            )
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"✏️ Переименован сервер: {old_name} → {name} (ID: {server_id})")
        
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
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
        elif current_online < old_online:
            diff = old_online - current_online
            message = (
                f"🔴 *{name}*\n"
                f"Вышел игрок! (-{diff})\n"
                f"Текущий онлайн: {current_online}"
            )
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
    
    server_state = current_state


async def monitor_loop():
    """Фоновый цикл мониторинга."""
    logger.info(f"🔄 Мониторинг запущен (интервал: {CHECK_INTERVAL} сек)")
    logger.info(f"🔇 Игнорируемых серверов: {len(IGNORED_SERVERS)}")
    
    data = await fetch_servers()
    if data and isinstance(data, list):
        for server in data:
            if isinstance(server, dict):
                server_id = server.get("id")
                if server_id:
                    server_state[server_id] = {
                        "name": server.get("name", "Без имени"),
                        "online": int(server.get("online", 0)),
                        "ip": server.get("ip", "Неизвестно"),
                        "port": server.get("port", "Неизвестно")
                    }
        logger.info(f"📊 Начальное состояние: {len(server_state)} серверов")
    
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            await check_and_notify()
        except Exception as e:
            logger.error(f"Ошибка в мониторинге: {e}")


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
    else:
        await message.answer("🚫 Доступ закрыт")
    
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
        for server in servers:
            builder.button(
                text=f"🖥️ {server['name']}",
                callback_data=f"ping_{server['name']}"
            )
        builder.button(text="─" * 20, callback_data="separator")
    
    builder.button(text="🔄 Обновить", callback_data="refresh_ping")
    builder.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1)
    
    return builder.as_markup()


# ============ ТВОЙ КОД ПИНГА (ТОЛЬКО ПИНГ, БЕЗ ПОРТА) ============
def ping_server(ip, count=2):
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
            timeout=10
        )
        
        return result.returncode == 0, result.stdout
    except subprocess.TimeoutExpired:
        return False, "Таймаут"
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
        await message.answer("❌ Нельзя выдать доступ админу")
        return
    
    if user_id in ALLOWED_USER_IDS:
        await message.answer(f"ℹ️ Пользователь {username} уже имеет доступ")
        return
    
    ALLOWED_USER_IDS.append(user_id)
    save_allowed_users(ALLOWED_USER_IDS)
    
    await message.answer(f"✅ Пользователь {username} получил доступ к боту")


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
    lines.append(f"👑 Админ: `{ADMIN_ID}`")
    
    for uid in ALLOWED_USER_IDS:
        if uid == ADMIN_ID:
            continue
        try:
            user = await bot.get_chat(uid)
            name = user.full_name or user.username or str(uid)
            if user.username:
                lines.append(f"• @{user.username} (`{uid}`)")
            else:
                lines.append(f"• {name} (`{uid}`)")
        except:
            lines.append(f"• ID: `{uid}`")
    
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
    
    if ip != "Неизвестно" and port != "Неизвестно":
        response = (
            f"🖥️ *{name}*\n"
            f"🆔 ID: `{server_id}`\n"
            f"🌐 IP: `{ip}`\n"
            f"🔌 Port: `{port}`\n\n"
            f"📌 `{ip}:{port}`"
        )
    else:
        response = (
            f"🖥️ *{name}*\n"
            f"🆔 ID: `{server_id}`\n"
            f"❌ Данные отсутствуют"
        )
    
    await message.answer(response, parse_mode="Markdown")


# ============ КОМАНДЫ БОТА ============
@dp.message(Command("start"))
async def start_command(message: types.Message):
    if not await check_access(message):
        return
    
    await message.answer(
        "🤖 *Бот мониторинга серверов*\n\n"
        "Бот отслеживает изменения онлайна и отправляет уведомления в канал.\n\n"
        f"📌 Интервал проверки: {CHECK_INTERVAL} секунд\n"
        f"📢 Уведомления приходят в этот канал\n\n"
        "📡 /ping — Пинг серверов\n"
        "🔍 /ip <ID> — Получить IP и порт сервера",
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
    
    lines = ["📊 *Текущий онлайн:*\n"]
    for server in sorted_servers:
        if isinstance(server, dict):
            name = server.get("name", "???")
            online = server.get("online", "0")
            server_id = server.get("id", "?")
            
            if server_id in IGNORED_SERVERS:
                lines.append(f"🔇 {name} — {online} (игнорируется)")
            else:
                lines.append(f"{name} — {online}")
    
    text = "\n".join(lines)
    
    if len(text) > 4096:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(f"```\n{part}\n```", parse_mode="Markdown")
    else:
        await message.answer(f"```\n{text}\n```", parse_mode="Markdown")


@dp.message(Command("refresh"))
async def refresh_command(message: types.Message):
    if not await check_access(message):
        return
    
    global server_state
    
    data = await fetch_servers()
    
    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных")
        return
    
    new_state = {}
    for server in data:
        if isinstance(server, dict):
            server_id = server.get("id")
            if server_id:
                new_state[server_id] = {
                    "name": server.get("name", "Без имени"),
                    "online": int(server.get("online", 0)),
                    "ip": server.get("ip", "Неизвестно"),
                    "port": server.get("port", "Неизвестно")
                }
    
    server_state = new_state
    await message.answer(f"✅ Состояние обновлено ({len(server_state)} серверов)")


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
        "/ip <ID> — Получить IP и порт сервера",
        "/help — Список команд"
    ]
    
    if is_admin_user:
        commands.extend([
            "",
            "👑 *Команды администратора (только в ЛС):*",
            "/access @username/id — Выдать доступ к боту",
            "/unaccess @username/id — Забрать доступ к боту",
            "/users — Список пользователей с доступом"
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
        await callback.message.edit_text(
            "📡 *Выберите сервер для пинга:*\n\n"
            "Нажмите на кнопку с названием сервера",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await callback.answer("🔄 Обновлено")
        return
    
    if data.startswith("ping_"):
        server_name = data.replace("ping_", "")
        server_info = await get_server_info(server_name)
        
        if not server_info:
            await callback.answer("❌ Сервер не найден")
            return
        
        ip = server_info["ip"]
        
        # Отправляем статус "пингуем..."
        await callback.answer(f"🔍 Пингую {server_name}...")
        
        status_msg = await callback.message.answer(
            f"🔍 *Пингую {server_name}...*\n"
            f"🌐 {ip}",
            parse_mode="Markdown"
        )
        
        # ===== ТВОЙ КОД ПИНГА (ТОЛЬКО ПИНГ, БЕЗ ПОРТА) =====
        ping_success, ping_output = ping_server(ip, count=2)
        
        # Формируем результат
        if ping_success:
            ping_status = "✅ ДОСТУПЕН"
        else:
            ping_status = "❌ НЕДОСТУПЕН"
        
        result_text = (
            f"📡 *Результат пинга*\n\n"
            f"🖥️ *{server_name}*\n"
            f"🌐 {ip}\n\n"
            f"📶 {ping_status}"
        )
        
        await status_msg.edit_text(result_text, parse_mode="Markdown")
        await callback.answer("✅ Готово!")


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
    print("=" * 50)
    
    asyncio.create_task(monitor_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
