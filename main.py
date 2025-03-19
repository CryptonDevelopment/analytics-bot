import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN, ALLOWED_TELEGRAM_IDS
from database import fetch_data
from excel_generator import generate_excel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_TELEGRAM_IDS

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if not is_allowed(message.from_user.id):
        await message.answer("У вас нет доступа к этому боту.")
        logger.warning(f"Попытка доступа неавторизованного пользователя: {message.from_user.id}")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выгрузить всех пользователей", callback_data="export_users")]
    ])
    await message.answer("Выберите действие:", reply_markup=keyboard)
    logger.info(f"Пользователь {message.from_user.id} начал работу с ботом.")

@dp.callback_query()
async def button_handler(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id):
        await callback.answer("У вас нет доступа к этому боту.")
        logger.warning(f"Попытка вызова callback неавторизованным пользователем: {callback.from_user.id}")
        return

    if callback.data == "export_users":
        query = "SELECT * FROM users;"  # Запрос для выгрузки всех пользователей
    else:
        await callback.answer("Неизвестный запрос!")
        logger.warning(f"Неизвестный callback_data: {callback.data} от пользователя {callback.from_user.id}")
        return

    await callback.answer("Обработка запроса...")

    # Выполнение запроса к базе данных
    try:
        data = await fetch_data(query)
        logger.info(f"Данные успешно получены для запроса {callback.data}")
    except Exception as e:
        logger.error(f"Ошибка при выполнении запроса к БД: {e}")
        await bot.send_message(callback.from_user.id, "Ошибка при выполнении запроса к базе данных.")
        return

    # Генерация Excel-файла на основе полученных данных
    try:
        excel_file = generate_excel(data)
        logger.info("Excel файл успешно сгенерирован")
    except Exception as e:
        logger.error(f"Ошибка при генерации Excel файла: {e}")
        await bot.send_message(callback.from_user.id, "Ошибка при генерации Excel файла.")
        return

    # Отправка Excel файла пользователю
    try:
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=excel_file,
            filename="users_export.xlsx",
            caption="Выгрузка всех пользователей"
        )
        logger.info(f"Excel файл отправлен пользователю {callback.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке файла: {e}")
        await bot.send_message(callback.from_user.id, "Ошибка при отправке файла.")

async def main():
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
