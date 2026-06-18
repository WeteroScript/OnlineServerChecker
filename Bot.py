import os
import aiohttp
import asyncio
import logging
import json
import socket
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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

# Файл для хранения разрешенных пользователей
ALLOWED_USERS_FILE = "allowed_users.json"

# Загружаем разрешенных пользователей
def load_allowed_users():
    """Загрузить список разрешенных пользователей из файла."""
    try:
        with open(ALLOWED_USERS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # Если файла нет, создаем с админом по умолчанию
        default_users = [ADMIN_ID]
        save_allowed_users(default_users)
        return default_users
    except Exception as e:
        logger.error(f"Ошибка загрузки allowed_users: {e}")
        return [ADMIN_ID]

def save_allowed_users(users):
    """Сохранить список разрешенных пользователей в файл."""
    try:
        with open(ALLOWED_USERS_FILE, "w") as f:
            json.dump(users, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения allowed_users: {e}")

# Загружаем разрешенных пользователей
ALLOWED_USER_IDS = load_allowed_users()
# ================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Храним предыдущее состояние серверов
server_state = {}  # {server_id: {"name": name, "online": online, "ip": ip, "port": port}}


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
    
    # Получаем текущее состояние
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
    
    # Проверяем новые серверы, изменения и переименования
    for server_id, info in current_state.items():
        name = info["name"]
        current_online = info["online"]
        is_ignored = server_id in IGNORED_SERVERS
        
        # === НОВЫЙ СЕРВЕР (если его не было в прошлом состоянии) ===
        if server_id not in server_state:
            # Отправляем уведомление о новом сервере (даже если он в игноре)
            message = (
                f"🆕 *Новый сервер!*\n"
                f"📌 {name}\n"
                f"🌐 IP: {info.get('ip', 'Неизвестно')}\n"
                f"🔌 Port: {info.get('port', 'Неизвестно')}"
            )
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🆕 Новый сервер: {name} (ID: {server_id})")
            continue  # Пропускаем уведомления о заходе/выходе для нового сервера
        
        # === ПРОВЕРКА ПЕРЕИМЕНОВАНИЯ (для всех серверов, даже игнорируемых) ===
        old_name = server_state[server_id]["name"]
        if old_name != name:
            message = (
                f"✏️ *Переименован сервер!*\n"
                f"📌 {old_name} → {name}"
            )
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"✏️ Переименован сервер: {old_name} → {name} (ID: {server_id})")
        
        # === ИГНОРИРУЕМЫЙ СЕРВЕР - пропускаем уведомления об онлайне ===
        if is_ignored:
            continue
        
        # === ИЗМЕНЕНИЕ ОНЛАЙНА (только для НЕ игнорируемых) ===
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
    
    # Обновляем состояние
    server_state = current_state


async def monitor_loop():
    """Фоновый цикл мониторинга."""
    logger.info(f"🔄 Мониторинг запущен (интервал: {CHECK_INTERVAL} сек)")
    logger.info(f"🔇 Игнорируемых серверов: {len(IGNORED_SERVERS)}")
    
    # Первый запуск - просто сохраняем состояние
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
    
    # Админ имеет доступ всегда
    if user_id == ADMIN_ID:
        return True
    
    # Проверяем в списке разрешенных
    if user_id in ALLOWED_USER_IDS:
        return True
    
    await message.answer("🚫 У вас нет доступа к этому боту")
    return False

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом."""
    return user_id == ADMIN_ID
# ============================================================


# ============ КОМАНДЫ УПРАВЛЕНИЯ ДОСТУПОМ ============
@dp.message(Command("access"))
async def access_command(message: types.Message):
    """Выдать доступ пользователю. Только в ЛС. /access @username или /access 123456789"""
    # Проверяем, что это ЛС
    if message.chat.type != "private":
        await message.answer("❌ Эта команда работает только в личных сообщениях")
        return
    
    # Проверяем, что админ
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
    
    # Пробуем получить ID
    if target.startswith("@"):
        # По юзернейму
        try:
            user = await bot.get_chat(target)
            user_id = user.id
            username = target
        except Exception as e:
            await message.answer(f"❌ Не найден пользователь {target}")
            return
    else:
        # По ID
        try:
            user_id = int(target)
            username = f"ID: {user_id}"
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте @username или ID")
            return
    
    # Проверяем, что не админ
    if user_id == ADMIN_ID:
        await message.answer("❌ Нельзя выдать доступ админу (он и так имеет доступ)")
        return
    
    # Проверяем, есть ли уже доступ
    if user_id in ALLOWED_USER_IDS:
        await message.answer(f"ℹ️ Пользователь {username} уже имеет доступ")
        return
    
    # Добавляем доступ
    ALLOWED_USER_IDS.append(user_id)
    save_allowed_users(ALLOWED_USER_IDS)
    
    await message.answer(f"✅ Пользователь {username} получил доступ к боту")
    logger.info(f"Админ {message.from_user.id} выдал доступ {username}")


@dp.message(Command("unaccess"))
async def unaccess_command(message: types.Message):
    """Забрать доступ у пользователя. Только в ЛС. /unaccess @username или /unaccess 123456789"""
    # Проверяем, что это ЛС
    if message.chat.type != "private":
        await message.answer("❌ Эта команда работает только в личных сообщениях")
        return
    
    # Проверяем, что админ
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
    
    # Пробуем получить ID
    if target.startswith("@"):
        try:
            user = await bot.get_chat(target)
            user_id = user.id
            username = target
        except Exception as e:
            await message.answer(f"❌ Не найден пользователь {target}")
            return
    else:
        try:
            user_id = int(target)
            username = f"ID: {user_id}"
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте @username или ID")
            return
    
    # Проверяем, что не админ
    if user_id == ADMIN_ID:
        await message.answer("❌ Нельзя забрать доступ у админа")
        return
    
    # Проверяем, есть ли доступ
    if user_id not in ALLOWED_USER_IDS:
        await message.answer(f"ℹ️ Пользователь {username} не имеет доступа")
        return
    
    # Убираем доступ
    ALLOWED_USER_IDS.remove(user_id)
    save_allowed_users(ALLOWED_USER_IDS)
    
    await message.answer(f"✅ У пользователя {username} забран доступ к боту")
    logger.info(f"Админ {message.from_user.id} забрал доступ у {username}")


@dp.message(Command("users"))
async def users_command(message: types.Message):
    """Показать список пользователей с доступом. Только в ЛС."""
    # Проверяем, что это ЛС
    if message.chat.type != "private":
        await message.answer("❌ Эта команда работает только в личных сообщениях")
        return
    
    # Проверяем, что админ
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
# ============================================================


@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Команда /start для личного чата."""
    if not await check_access(message):
        return
    
    await message.answer(
        "🤖 *Бот мониторинга серверов*\n\n"
        "Бот отслеживает изменения онлайна и отправляет уведомления в канал.\n\n"
        f"📌 Интервал проверки: {CHECK_INTERVAL} секунд\n"
        f"🔇 Игнорируется серверов: {len(IGNORED_SERVERS)}\n"
        f"📢 Уведомления приходят в этот канал",
        parse_mode="Markdown"
    )


@dp.message(Command("status"))
async def status_command(message: types.Message):
    """Показать текущий статус серверов."""
    if not await check_access(message):
        return
    
    data = await fetch_servers()
    
    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных")
        return
    
    # Сортируем по ID
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
            
            # Отмечаем игнорируемые серверы
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
    """Принудительное обновление состояния."""
    if not await check_access(message):
        return
    
    global server_state
    
    data = await fetch_servers()
    
    if not data or not isinstance(data, list):
        await message.answer("❌ Нет данных")
        return
    
    # Обновляем состояние
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


@dp.message(Command("ignored"))
async def ignored_command(message: types.Message):
    """Показать список игнорируемых серверов."""
    if not await check_access(message):
        return
    
    if not IGNORED_SERVERS:
        await message.answer("🔇 Нет игнорируемых серверов")
        return
    
    # Получаем данные, чтобы показать названия
    data = await fetch_servers()
    
    lines = ["🔇 *Игнорируемые серверы:*\n"]
    
    if data and isinstance(data, list):
        server_names = {}
        for server in data:
            if isinstance(server, dict):
                server_id = server.get("id")
                if server_id in IGNORED_SERVERS:
                    server_names[server_id] = server.get("name", "Без имени")
        
        for server_id in sorted(IGNORED_SERVERS):
            name = server_names.get(server_id, "Неизвестно")
            lines.append(f"• ID: `{server_id}` — {name}")
    else:
        for server_id in sorted(IGNORED_SERVERS):
            lines.append(f"• ID: `{server_id}`")
    
    await message.answer("\n".join(lines), parse_mode="Markdown")


@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Список команд."""
    if not await check_access(message):
        return
    
    is_admin_user = is_admin(message.from_user.id)
    
    commands = [
        "🤖 *Доступные команды:*\n",
        "/start — Информация о боте",
        "/status — Онлайн всех серверов",
        "/refresh — Обновить состояние",
        "/ignored — Список игнорируемых серверов",
        "/help — Список команд"
    ]
    
    # Админские команды (только в ЛС)
    if is_admin_user:
        commands.extend([
            "",
            "👑 *Команды администратора (только в ЛС):*",
            "/access @username/id — Выдать доступ к боту",
            "/unaccess @username/id — Забрать доступ к боту",
            "/users — Список пользователей с доступом"
        ])
    
    await message.answer("\n".join(commands), parse_mode="Markdown")


@dp.message(Command("ping"))
async def ping_command(message: types.Message):
    """Проверить доступность сервера: /ping 123"""
    if not await check_access(message):
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /ping <ID_сервера>")
        return
    
    try:
        server_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    
    # Ищем сервер
    data = await fetch_servers()
    if not data:
        await message.answer("❌ Нет данных от API")
        return
    
    server = next((s for s in data if s.get("id") == server_id), None)
    if not server:
        await message.answer(f"❌ Сервер с ID {server_id} не найден")
        return
    
    name = server.get("name", "Без имени")
    ip = server.get("ip")
    port = server.get("port")
    
    if not ip:
        await message.answer(f"❌ У сервера {name} нет IP")
        return
    
    # Проверяем
    status_msg = await message.answer(f"🔍 Пингую {name}...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((ip, port if port else 80))
        sock.close()
        
        if result == 0:
            status = "✅ ДОСТУПЕН"
        else:
            status = "❌ НЕДОСТУПЕН"
    except Exception:
        status = "❌ ОШИБКА"
    
    response = (
        f"📡 *Результат пинга*\n"
        f"📌 {name}\n"
        f"🌐 {ip}"
    )
    if port:
        response += f":{port}"
    response += f"\n\n{status}"
    
    await status_msg.edit_text(response, parse_mode="Markdown")


# ============ ОБРАБОТЧИК ДЛЯ ЛИЧНЫХ СООБЩЕНИЙ ============
@dp.message()
async def private_message_handler(message: types.Message):
    """Обработка любых сообщений в личке."""
    if message.chat.type == "private":
        # Если у пользователя нет доступа
        if not await check_access(message):
            return
        # Если есть доступ, но команда не распознана
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
    print("=" * 50)
    
    # Запускаем мониторинг в фоне
    asyncio.create_task(monitor_loop())
    
    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
