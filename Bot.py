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
CHECK_INTERVAL = 15  # Секунд (15 секунд)

# 🔇 Серверы, которые НЕ нужно отслеживать (по ID)
IGNORED_SERVERS = [
    202, 203, 204, 205, 206, 207, 208, 209, 210,
    211, 212, 213, 214, 215, 216, 217, 218, 219,
    220, 221, 222, 223, 224, 225, 226
]

# ✅ Разрешенные ID чатов
ALLOWED_CHAT_IDS = [
    -1003909198412,  # ID твоего канала
]
# ================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Храним предыдущее состояние серверов
server_state = {}  # {server_id: {"name": name, "online": online}}

# ✅ Храним последнее отправленное уведомление для каждого сервера
last_notification = {}  # {server_id: {"online": число, "time": время}}


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
    global server_state, last_notification
    
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
    
    # === ПРОВЕРКА УДАЛЕННЫХ СЕРВЕРОВ ===
    for server_id, old_info in server_state.items():
        if server_id not in current_state:
            name = old_info.get("name", "Неизвестный сервер")
            message = f"🥀 *{name}*\nСервер удален"
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🥀 Сервер удален: {name} (ID: {server_id})")
            # Удаляем из последних уведомлений
            if server_id in last_notification:
                del last_notification[server_id]
    
    # === ПРОВЕРКА НОВЫХ СЕРВЕРОВ ===
    for server_id, info in current_state.items():
        if server_id not in server_state:
            name = info["name"]
            message = (
                f"🆕 *Новый сервер!*\n"
                f"📌 {name}\n"
                f"🌐 IP: {info.get('ip', 'Неизвестно')}\n"
                f"🔌 Port: {info.get('port', 'Неизвестно')}"
            )
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"🆕 Новый сервер: {name} (ID: {server_id})")
            # Запоминаем, что уведомление отправлено
            last_notification[server_id] = {"online": info["online"], "time": datetime.now()}
    
    # === ПРОВЕРКА ИЗМЕНЕНИЙ ОНЛАЙНА (только для НЕ игнорируемых) ===
    for server_id, info in current_state.items():
        name = info["name"]
        current_online = info["online"]
        is_ignored = server_id in IGNORED_SERVERS
        
        # Пропускаем игнорируемые
        if is_ignored:
            continue
        
        # Пропускаем, если сервер новый (уже обработали выше)
        if server_id not in server_state:
            continue
        
        old_online = server_state[server_id]["online"]
        
        # === ЕСЛИ ОНЛАЙН ИЗМЕНИЛСЯ ===
        if current_online != old_online:
            # ✅ Проверяем, не отправляли ли уже уведомление об этом изменении
            if server_id in last_notification:
                last = last_notification[server_id]
                # Если онлайн совпадает с последним отправленным — пропускаем
                if last["online"] == current_online:
                    continue
                # Если прошло меньше 2 минут с последнего уведомления — пропускаем
                if datetime.now() - last["time"] < timedelta(minutes=2):
                    continue
            
            # Отправляем уведомление
            if current_online > old_online:
                diff = current_online - old_online
                message = (
                    f"🟢 *{name}*\n"
                    f"Зашел игрок! (+{diff})\n"
                    f"Текущий онлайн: {current_online}"
                )
            else:
                diff = old_online - current_online
                message = (
                    f"🔴 *{name}*\n"
                    f"Вышел игрок! (-{diff})\n"
                    f"Текущий онлайн: {current_online}"
                )
            
            await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            logger.info(f"📢 Уведомление: {name} — {current_online} (было {old_online})")
            
            # Запоминаем, что уведомление отправлено
            last_notification[server_id] = {"online": current_online, "time": datetime.now()}
    
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
    if message.chat.id not in ALLOWED_CHAT_IDS:
        await message.answer("🚫 Доступ закрыт")
        return False
    return True


@dp.message(Command("start"))
async def start_command(message: types.Message):
    if not await check_access(message):
        return
    
    await message.answer(
        "🤖 *Бот мониторинга серверов*\n\n"
        f"📌 Интервал проверки: {CHECK_INTERVAL} секунд\n"
        f"🔇 Игнорируется серверов: {len(IGNORED_SERVERS)}",
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
    
    global server_state, last_notification
    
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
    last_notification = {}  # Очищаем историю уведомлений
    await message.answer(f"✅ Состояние обновлено ({len(server_state)} серверов)")


@dp.message(Command("sync"))
async def sync_command(message: types.Message):
    if not await check_access(message):
        return
    
    await message.answer("🔄 Выполняю полную синхронизацию...")
    
    global server_state, last_notification
    old_state = server_state.copy()
    server_state = {}
    last_notification = {}
    
    data = await fetch_servers()
    if not data or not isinstance(data, list):
        server_state = old_state
        await message.answer("❌ Ошибка: не удалось получить данные")
        return
    
    new_servers_found = 0
    for server in data:
        if isinstance(server, dict):
            server_id = server.get("id")
            if server_id:
                if server_id not in old_state:
                    new_servers_found += 1
                    name = server.get("name", "Без имени")
                    msg = (
                        f"🆕 *Новый сервер!*\n"
                        f"📌 {name}\n"
                        f"🌐 IP: {server.get('ip', 'Неизвестно')}\n"
                        f"🔌 Port: {server.get('port', 'Неизвестно')}"
                    )
                    await bot.send_message(CHANNEL_ID, msg, parse_mode="Markdown")
                
                server_state[server_id] = {
                    "name": server.get("name", "Без имени"),
                    "online": int(server.get("online", 0)),
                    "ip": server.get("ip", "Неизвестно"),
                    "port": server.get("port", "Неизвестно")
                }
    
    await message.answer(f"✅ Синхронизация завершена!\nНайдено новых серверов: {new_servers_found}")


@dp.message(Command("ignored"))
async def ignored_command(message: types.Message):
    if not await check_access(message):
        return
    
    if not IGNORED_SERVERS:
        await message.answer("🔇 Нет игнорируемых серверов")
        return
    
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
    if not await check_access(message):
        return
    
    await message.answer(
        "🤖 *Команды:*\n\n"
        "/start — Информация\n"
        "/status — Онлайн всех серверов\n"
        "/refresh — Обновить состояние\n"
        "/sync — Полная синхронизация\n"
        "/ignored — Список игнорируемых\n"
        "/help — Помощь",
        parse_mode="Markdown"
    )


@dp.message()
async def private_message_handler(message: types.Message):
    if message.chat.type == "private":
        await message.answer("🚫 Доступ закрыт")


async def main():
    print("=" * 50)
    print("🤖 БОТ МОНИТОРИНГА СЕРВЕРОВ")
    print("=" * 50)
    print(f"📢 Канал: {CHANNEL_ID}")
    print(f"⏱️  Интервал: {CHECK_INTERVAL} сек")
    print(f"🔇 Игнорируется: {len(IGNORED_SERVERS)} серверов")
    print("=" * 50)
    
    asyncio.create_task(monitor_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
