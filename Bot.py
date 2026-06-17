import os
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://api.blackhub.team/servers.json"
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1003909198412")  # Значение по умолчанию
CHECK_INTERVAL = 90  # Секунд (1:30 минуты)
# =====================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Храним предыдущее состояние серверов
server_state = {}  # {server_id: {"name": name, "online": online}}


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
                    "online": int(server.get("online", 0))
                }
    
    # Сравниваем с предыдущим состоянием
    for server_id, info in current_state.items():
        name = info["name"]
        current_online = info["online"]
        
        if server_id in server_state:
            old_online = server_state[server_id]["online"]
            
            # Игрок зашел
            if current_online > old_online:
                diff = current_online - old_online
                message = (
                    f"🟢 *{name}*\n"
                    f"Зашел игрок! (+{diff})\n"
                    f"Текущий онлайн: {current_online}"
                )
                await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
            
            # Игрок вышел
            elif current_online < old_online:
                diff = old_online - current_online
                message = (
                    f"🔴 *{name}*\n"
                    f"Вышел игрок! (-{diff})\n"
                    f"Текущий онлайн: {current_online}"
                )
                await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
        else:
            # Новый сервер
            if current_online > 0:
                message = (
                    f"🆕 *{name}*\n"
                    f"Сервер появился!\n"
                    f"Онлайн: {current_online}"
                )
                await bot.send_message(CHANNEL_ID, message, parse_mode="Markdown")
    
    # Обновляем состояние
    server_state = current_state


async def monitor_loop():
    """Фоновый цикл мониторинга."""
    logger.info(f"🔄 Мониторинг запущен (интервал: {CHECK_INTERVAL} сек)")
    
    # Первый запуск - просто сохраняем состояние
    data = await fetch_servers()
    if data and isinstance(data, list):
        for server in data:
            if isinstance(server, dict):
                server_id = server.get("id")
                if server_id:
                    server_state[server_id] = {
                        "name": server.get("name", "Без имени"),
                        "online": int(server.get("online", 0))
                    }
        logger.info(f"📊 Начальное состояние: {len(server_state)} серверов")
    
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            await check_and_notify()
        except Exception as e:
            logger.error(f"Ошибка в мониторинге: {e}")


@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Команда /start для личного чата."""
    await message.answer(
        "🤖 *Бот мониторинга серверов*\n\n"
        "Бот отслеживает изменения онлайна и отправляет уведомления в канал.\n\n"
        f"📌 Интервал проверки: {CHECK_INTERVAL} секунд\n"
        f"📢 Уведомления приходят в канал: {CHANNEL_ID}",
        parse_mode="Markdown"
    )


@dp.message(Command("status"))
async def status_command(message: types.Message):
    """Показать текущий статус серверов."""
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
                    "online": int(server.get("online", 0))
                }
    
    server_state = new_state
    await message.answer(f"✅ Состояние обновлено ({len(server_state)} серверов)")


async def main():
    """Запуск бота."""
    print("=" * 50)
    print("🤖 БОТ МОНИТОРИНГА СЕРВЕРОВ")
    print("=" * 50)
    print(f"📢 Канал: {CHANNEL_ID}")
    print(f"⏱️  Интервал: {CHECK_INTERVAL} сек")
    print("=" * 50)
    
    # Запускаем мониторинг в фоне
    asyncio.create_task(monitor_loop())
    
    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
