import json
import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler

# Состояния диалога
FIO, ACTION = range(2)

# Путь к файлу базы данных
DATA_FILE = 'user_data.json'

# Инициализация базы данных, если файл не существует
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump([], f)

# Команда /start
async def start(update: Update, context) -> int:
    await update.message.reply_text(
        "Привет! Пожалуйста, отправьте ваше ФИО."
    )
    return FIO

# Получение ФИО и предложение действий
async def get_fio(update: Update, context) -> int:
    user_data = {
        'user_id': update.message.from_user.id,
        'fio': update.message.text
    }

    # Записываем данные пользователя в контекст
    context.user_data['user_info'] = user_data

    # Создаем клавиатуру с опциями
    reply_keyboard = [['Резюме', 'Фото', 'Описание', 'Info']]

    await update.message.reply_text(
        f"{user_data['fio']}, выберите одно из действий, чтобы отредактировать профиль:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )

    return ACTION

# Обработчик действий пользователя
async def handle_action(update: Update, context) -> int:
    user_choice = update.message.text

    if user_choice == 'Резюме':
        await update.message.reply_text('Пожалуйста, отправьте ваше резюме.')
        return ConversationHandler.END  # Здесь можно продолжить процесс загрузки резюме

    elif user_choice == 'Фото':
        await update.message.reply_text('Пожалуйста, отправьте ваше фото.')
        return ConversationHandler.END  # Можно добавить обработку фото

    elif user_choice == 'Описание':
        await update.message.reply_text('Пожалуйста, отправьте описание вашего профиля.')
        return ConversationHandler.END  # Обработка описания

    elif user_choice == 'Info':
        await update.message.reply_text('Тут будет инфа.')
        return ACTION  # Оставляем пользователя в текущем состоянии выбора действий

# Команда для отмены процесса
async def cancel(update: Update, context) -> int:
    await update.message.reply_text('Процесс отменен.', reply_markup=ReplyKeyboardMarkup([[]]))
    return ConversationHandler.END

def main():
    # Вставьте свой токен бота здесь
    TOKEN = '8078020916:AAFgQ_K8tWhx79jPPWTTfT3DXoTUsaYo7Ls'
    
    # Инициализация Application
    application = Application.builder().token(TOKEN).build()

    # Определяем ConversationHandler для управления диалогом
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fio)],
            ACTION: [MessageHandler(filters.TEXT, handle_action)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
