import os
import logging
import asyncio
import asyncpg
import io

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from openpyxl import Workbook

# ----------------------------
# Конфигурация и настройки
# ----------------------------

# Токен Telegram-бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")

# Парсинг разрешённых пользователей с указанием отдела.
# Формат переменной ALLOWED_USERS: "123456789:marketing,987654321:analytics,111111111:admin"
allowed_users_env = os.getenv("ALLOWED_USERS", "123456789:marketing")
ALLOWED_USERS = {}
for entry in allowed_users_env.split(","):
    parts = entry.split(":")
    if len(parts) == 2:
        try:
            uid = int(parts[0].strip())
            dept = parts[1].strip().lower()
            ALLOWED_USERS[uid] = dept
        except ValueError:
            pass

# Адреса баз данных для каждого сервиса.
# Для каждого сервиса своя БД.
DATABASE_URLS = {
    "marketing": os.getenv("MARKETING_DB_URL", "postgresql://user:password@localhost:5432/marketing_db"),
    "analytics": os.getenv("ANALYTICS_DB_URL", "postgresql://user:password@localhost:5432/analytics_db")
}

# Определяем запросы для каждого сервиса.
# Каждая запись содержит: название кнопки, идентификатор (для callback), SQL-запрос и требуемый отдел.
SERVICE_QUERIES = {
    "marketing": [
        {
            "name": "Выгрузить всех пользователей",
            "callback": "export_users",
            "sql": "SELECT * FROM users_marketing;",
            "dept": "marketing"
        },
        # Можно добавить другие запросы для маркетинга
    ],
    "analytics": [
        {
            "name": "Выгрузить всех пользователей",
            "callback": "export_users",
            "sql": "SELECT * FROM users_analytics;",
            "dept": "analytics"
        },
        # Можно добавить другие запросы для аналитики
    ]
}

# Глобальная переменная для отслеживания активности пользователей.
# Структура: { user_id: {"count": int, "total_length": int} }
ACTIVITY_STATS = {}

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------
# Функции для работы с БД и генерации Excel
# ----------------------------

async def fetch_data(query: str, db_url: str):
    """Асинхронное выполнение SQL-запроса с использованием asyncpg."""
    conn = await asyncpg.connect(db_url)
    try:
        data = await conn.fetch(query)
    finally:
        await conn.close()
    return data

def generate_excel(data) -> io.BytesIO:
    """Генерация Excel-файла из списка записей с помощью openpyxl."""
    wb = Workbook()
    ws = wb.active

    if data:
        headers = list(data[0].keys())
        ws.append(headers)
        for record in data:
            ws.append([record.get(header) for header in headers])
    else:
        ws.append(["Нет данных для отображения"])

    excel_io = io.BytesIO()
    wb.save(excel_io)
    excel_io.seek(0)
    return excel_io

# ----------------------------
# Инициализация бота и диспетчера
# ----------------------------

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

def get_user_department(user_id: int):
    """Возвращает отдел пользователя, если он разрешён."""
    return ALLOWED_USERS.get(user_id)

# ----------------------------
# Хэндлеры команд и сообщений
# ----------------------------

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """
    Команда /start.
    Если пользователь разрешён, предлагает выбрать сервис.
    """
    user_id = message.from_user.id
    if user_id not in ALLOWED_USERS:
        await message.answer("У вас нет доступа к этому боту.")
        logger.warning("Попытка доступа неавторизованного пользователя: %s", user_id)
        return

    # Предлагаем выбор сервиса (например, маркетинг или аналитика)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Маркетинг", callback_data="service:marketing")],
        [InlineKeyboardButton(text="Аналитика", callback_data="service:analytics")]
    ])
    await message.answer("Выберите сервис:", reply_markup=keyboard)
    logger.info("Пользователь %s запустил бота", user_id)

@dp.callback_query(lambda c: c.data.startswith("service:"))
async def service_selection_handler(callback: types.CallbackQuery):
    """
    Обработка выбора сервиса.
    После выбора сервиса выводятся кнопки с запросами, доступными для данного отдела.
    """
    user_id = callback.from_user.id
    if user_id not in ALLOWED_USERS:
        await callback.answer("У вас нет доступа к этому боту.", show_alert=True)
        logger.warning("Попытка доступа неавторизованного пользователя: %s", user_id)
        return

    # Извлекаем выбранный сервис из callback data
    service = callback.data.split(":", 1)[1]
    user_dept = get_user_department(user_id)
    queries = SERVICE_QUERIES.get(service, [])

    # Формируем инлайн-клавиатуру с запросами, доступными для данного отдела (или admin)
    keyboard_buttons = []
    for query in queries:
        if user_dept == "admin" or user_dept == query["dept"]:
            # Код callback: <service>:<query_callback>
            callback_data = f"{service}:{query['callback']}"
            keyboard_buttons.append([InlineKeyboardButton(text=query["name"], callback_data=callback_data)])

    if not keyboard_buttons:
        await callback.message.answer("Нет доступных запросов для выбранного сервиса.")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.answer(f"Сервис «{service}». Выберите запрос:", reply_markup=keyboard)
    await callback.answer()
    logger.info("Пользователь %s выбрал сервис %s", user_id, service)

@dp.callback_query(lambda c: ":" in c.data and not c.data.startswith("service:"))
async def query_handler(callback: types.CallbackQuery):
    """
    Обработка нажатия на кнопку запроса.
    Проверяется доступ, выбирается нужная база данных, выполняется SQL-запрос,
    генерируется Excel и отправляется пользователю.
    """
    user_id = callback.from_user.id
    if user_id not in ALLOWED_USERS:
        await callback.answer("У вас нет доступа к этому боту.", show_alert=True)
        logger.warning("Попытка доступа неавторизованного пользователя (query handler): %s", user_id)
        return

    try:
        # Callback data имеет формат: <service>:<query_callback>
        service, query_key = callback.data.split(":", 1)
    except ValueError:
        await callback.answer("Неверные данные запроса.")
        return

    # Поиск конфигурации запроса для выбранного сервиса
    queries = SERVICE_QUERIES.get(service, [])
    query_config = None
    for q in queries:
        if q["callback"] == query_key:
            query_config = q
            break

    if not query_config:
        await callback.answer("Запрос не найден.")
        logger.warning("Запрос не найден для callback data: %s", callback.data)
        return

    # Проверяем, имеет ли пользователь доступ к данному запросу
    user_dept = get_user_department(user_id)
    if not (user_dept == "admin" or user_dept == query_config["dept"]):
        await callback.answer("У вас нет доступа к этому запросу.", show_alert=True)
        logger.warning("Пользователь %s с отделом %s попытался выполнить запрос %s (требуется %s)",
                       user_id, user_dept, query_config["name"], query_config["dept"])
        return

    await callback.answer("Обработка запроса...")

    # Получаем адрес базы данных для выбранного сервиса
    db_url = DATABASE_URLS.get(service)
    if not db_url:
        await bot.send_message(user_id, "Нет настроенной базы данных для выбранного сервиса.")
        logger.error("Не задан адрес базы данных для сервиса: %s", service)
        return

    # Выполнение SQL-запроса
    try:
        data = await fetch_data(query_config["sql"], db_url)
        logger.info("Данные успешно получены для пользователя %s, сервис %s, запрос %s",
                    user_id, service, query_config["name"])
    except Exception as e:
        logger.error("Ошибка при выполнении запроса к базе данных: %s", e)
        await bot.send_message(user_id, "Ошибка при выполнении запроса к базе данных.")
        return

    # Генерация Excel-файла
    try:
        excel_file = generate_excel(data)
        logger.info("Excel-файл успешно сгенерирован для пользователя %s, сервис %s, запрос %s",
                    user_id, service, query_config["name"])
    except Exception as e:
        logger.error("Ошибка при генерации Excel-файла: %s", e)
        await bot.send_message(user_id, "Ошибка при генерации Excel файла.")
        return

    # Отправка Excel-файла пользователю
    try:
        await bot.send_document(
            chat_id=user_id,
            document=excel_file,
            filename=f"{service}_{query_key}.xlsx",
            caption=f"Отчет: {query_config['name']}"
        )
        logger.info("Excel-файл отправлен пользователю %s", user_id)
    except Exception as e:
        logger.error("Ошибка при отправке Excel-файла: %s", e)
        await bot.send_message(user_id, "Ошибка при отправке файла.")

@dp.message()
async def track_activity(message: types.Message):
    """
    Отслеживание активности пользователей в чатах.
    Каждое сообщение учитывается: увеличивается счётчик и суммарная длина текста.
    Бот не отвечает на эти сообщения.
    """
    if not message.from_user:
        return
    user_id = message.from_user.id
    text = message.text or ""
    msg_length = len(text)
    stats = ACTIVITY_STATS.get(user_id, {"count": 0, "total_length": 0})
    stats["count"] += 1
    stats["total_length"] += msg_length
    ACTIVITY_STATS[user_id] = stats

@dp.message(Command("my_stats"))
async def my_stats_handler(message: types.Message):
    """
    Команда для получения статистики активности конкретного пользователя.
    Выводит количество отправленных сообщений и среднюю длину.
    """
    user_id = message.from_user.id
    stats = ACTIVITY_STATS.get(user_id, {"count": 0, "total_length": 0})
    count = stats["count"]
    avg_length = stats["total_length"] / count if count > 0 else 0
    await message.answer(f"Ваша активность:\nСообщений: {count}\nСредняя длина: {avg_length:.2f} символов")

@dp.message(Command("all_stats"))
async def all_stats_handler(message: types.Message):
    """
    Команда для получения сводной статистики по всем пользователям.
    Доступна только для admin.
    """
    user_id = message.from_user.id
    user_dept = get_user_department(user_id)
    if user_dept != "admin":
        await message.answer("У вас нет доступа к этой команде.")
        return

    if not ACTIVITY_STATS:
        await message.answer("Нет данных по активности.")
        return

    stats_lines = []
    for uid, stats in ACTIVITY_STATS.items():
        count = stats["count"]
        avg_length = stats["total_length"] / count if count > 0 else 0
        stats_lines.append(f"User {uid}: сообщений: {count}, средняя длина: {avg_length:.2f}")
    await message.answer("\n".join(stats_lines))

# ----------------------------
# Основной цикл запуска бота
# ----------------------------

async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
