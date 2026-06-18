import os
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://api.blackhub.team/servers.json"
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1003909198412")
CHECK_INTERVAL = 15  # Секунд (1:30 минуты)

# 🔇 Серверы, которые НЕ нужно отслеживать (по ID)
IGNORED_SERVERS = [
    202, 203, 204, 205, 206, 207, 208, 209, 210,
    211, 212, 213, 214, 215, 216, 217, 218, 219,
    220, 221, 222, 223, 224, 225, 226
]

# ✅ Разрешенные ID чатов (только эти каналы могут использовать бота)
ALLOWED_CHAT_IDS = [
    -1003909198412,  # ID твоего канала (замени на свой)
    # Можешь добавить другие каналы через запятую
]
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


# ============ ПРОВЕРКА ДОСТУПА (для всех команд) ============
async def check_access(message: types.Message) -> bool:
    """Проверяет, разрешен ли чат для использования бота."""
    if message.chat.id not in ALLOWED_CHAT_IDS:
        await message.answer("🚫 Доступ закрыт")
        return False
    return True
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
    
    await message.answer(
        "🤖 *Доступные команды:*\n\n"
        "/start — Информация о боте\n"
        "/status — Онлайн всех серверов\n"
        "/refresh — Обновить состояние\n"
        "/ignored — Список игнорируемых серверов\n"
        "/help — Список команд",
        parse_mode="Markdown"
    )


# ============ ОБРАБОТЧИК ДЛЯ ЛИЧНЫХ СООБЩЕНИЙ ============
@dp.message()
async def private_message_handler(message: types.Message):
    """Обработка любых сообщений в личке."""
    # Если это личный чат (не канал и не группа)
    if message.chat.type == "private":
        await message.answer("🚫 Доступ закрыт")
# ============================================================


async def main():
    """Запуск бота."""
    print("=" * 50)
    print("🤖 БОТ МОНИТОРИНГА СЕРВЕРОВ")
    print("=" * 50)
    print(f"📢 Канал: {CHANNEL_ID}")
    print(f"⏱️  Интервал: {CHECK_INTERVAL} сек")
    print(f"🔇 Игнорируется: {len(IGNORED_SERVERS)} серверов")
    print(f"✅ Разрешено каналов: {len(ALLOWED_CHAT_IDS)}")
    print("=" * 50)
    
    # Запускаем мониторинг в фоне
    asyncio.create_task(monitor_loop())
    
    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
