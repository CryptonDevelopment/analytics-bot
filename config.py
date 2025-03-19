import os

# Токен Telegram-бота (рекомендуется задавать через переменную окружения)
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")

# Строка подключения к PostgreSQL (формат: postgresql://user:password@host:port/dbname)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/dbname")

# Разрешенные Telegram ID (через переменную окружения, например: "123456789,987654321")
ALLOWED_TELEGRAM_IDS = os.getenv("ALLOWED_TELEGRAM_IDS", "123456789").split(',')
ALLOWED_TELEGRAM_IDS = [int(x.strip()) for x in ALLOWED_TELEGRAM_IDS if x.strip().isdigit()]
