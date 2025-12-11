import os
import sys
import logging

# Добавляем путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'alias_game.settings')
import django
django.setup()

from django.conf import settings
import telebot
from telebot import types

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = settings.TELEGRAM_BOT_TOKEN
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user = message.from_user

    welcome_text = f"""
👋 Привет, {user.first_name}!

🎮 Добро пожаловать в игру Alias!

✨ Чтобы начать игру, нажмите кнопку ниже:
"""

    keyboard = types.InlineKeyboardMarkup()
    web_app = types.WebAppInfo(url=f"https://{settings.ALLOWED_HOSTS[0]}/")
    keyboard.add(types.InlineKeyboardButton(
        text="🎮 Играть в Alias",
        web_app=web_app
    ))

    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=keyboard
    )

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == '/play':
        send_welcome(message)
    else:
        bot.send_message(message.chat.id, "Нажмите /start чтобы начать игру")

@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    data = message.web_app_data.data
    logger.info(f"Данные из Web App: {data}")

def run_bot():
    logger.info("Запуск Telegram бота...")
    try:
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Ошибка бота: {e}")
        import time
        time.sleep(5)
        run_bot()

if __name__ == '__main__':
    run_bot()