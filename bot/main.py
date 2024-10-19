from flask import Flask, request, jsonify
import requests
import hashlib
import hmac
import time
import openai
import logging
import os
from tonclient import TonClient
import json
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import config

ASK_NAME, ASK_PHOTO, ASK_SPECIALIZATION, ASK_SKILL = range(4)

openai.api_key = os.getenv('OPENAI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN or not openai.api_key:
    raise EnvironmentError("Токены Telegram и OpenAI должны быть заданы в переменных окружения.")

TELEGRAM_API_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'
ton_client = TonClient(config={"network": {"server_address": "net.ton.dev"}})

app = Flask(__name__)

# Tg бот
def start(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [['Да', 'Нет']]
    update.message.reply_text(
        "Предлагаю составить вам резюме. (да/нет)",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return ASK_NAME if update.message.text.lower() == 'да' else ConversationHandler.END

def askName(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Напишите ваше ФИО.')
    return ASK_PHOTO

def askPhoto(update: Update, context: CallbackContext) -> int:
    context.user_data['full_name'] = update.message.text
    update.message.reply_text('Отправьте своё фото.')
    return ASK_SPECIALIZATION

def askSpecialization(update: Update, context: CallbackContext) -> int:
    photo_file = update.message.photo[-1].get_file()
    photo_file.download(f"user_photos/{update.message.chat_id}.jpg")
    update.message.reply_text('Ваша специальность:')
    return ASK_SKILL

def askSkills(update: Update, context: CallbackContext) -> int:
    context.user_data['specialization'] = update.message.text
    update.message.reply_text('Теперь напишите о себе и о Ваших ключевых навыках:')
    return ConversationHandler.END

def geneResume(update: Update, context: CallbackContext) -> None:
    user_data = context.user_data
    user_data['about'] = update.message.text

    resume_data = {
        "full_name": user_data['full_name'],
        "specialization": user_data['specialization'],
        "about": user_data['about']
    }

    prompt = f"Улучшите резюме на основе этих данных:\nФИО: {resume_data['full_name']}\nСпециальность: {resume_data['specialization']}\nО себе: {resume_data['about']}"

    try:
        response = openai.Completion.create(
            engine="gpt-4",
            prompt=prompt,
            max_tokens=150
        )
        improved_text = response.choices[0].text.strip()
        update.message.reply_text(f"Улучшенное резюме:\n{improved_text}")
    except Exception as e:
        update.message.reply_text(f"Ошибка при запросе к GPT: {e}")

def cancel(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Операция отменена.')
    return ConversationHandler.END

def main() -> None:
    updater = Updater(TELEGRAM_BOT_TOKEN)
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_NAME: [MessageHandler(Filters.text & ~Filters.command, askName)],
            ASK_PHOTO: [MessageHandler(Filters.photo, askPhoto)],
            ASK_SPECIALIZATION: [MessageHandler(Filters.text & ~Filters.command, askSpecialization)],
            ASK_SKILL: [MessageHandler(Filters.text & ~Filters.command, askSkills)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dispatcher.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()

# мини Приложение
@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if 'message' in update and 'location' in update['message']:
        user_id = update['message']['from']['id']
        location = update['message']['location']
        latitude = location['latitude']
        longitude = location['longitude']
        logging.info(f"Получена геолокация от пользователя {user_id}: ({latitude}, {longitude})")
        return jsonify({'status': 'success', 'message': 'Геолокация получена!'}), 200
    return jsonify({'status': 'error', 'message': 'Нет геолокации в сообщении.'}), 400

@app.route('/auth', methods=['GET'])
def auth():
    telegram_data = request.args.to_dict()
    if check_telegram_auth(telegram_data):
        user_id = telegram_data['id']
        first_name = telegram_data.get('first_name', 'User')
        logging.info(f"Успешная авторизация для пользователя: {first_name} (ID: {user_id})")
        return jsonify({'status': 'success', 'message': f'Добро пожаловать, {first_name}!', 'user_id': user_id})
    else:
        logging.warning("Ошибка авторизации: данные не прошли проверку.")
        return jsonify({'status': 'error', 'message': 'Ошибка авторизации!'}), 401

@app.route('/send_notification', methods=['POST'])
def send_notification():
    data = request.json
    if 'chat_id' not in data or 'message' not in data:
        return jsonify({'status': 'error', 'message': 'Отсутствуют обязательные параметры chat_id или message.'}), 400

    chat_id = data['chat_id']
    message = data['message']

    try:
        response = requests.post(f'{TELEGRAM_API_URL}/sendMessage', json={'chat_id': chat_id, 'text': message})
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при отправке уведомления: {e}")
        return jsonify({'status': 'error', 'message': 'Ошибка отправки уведомления!'}), 500

    logging.info(f"Уведомление успешно отправлено пользователю {chat_id}.")
    return jsonify({'status': 'success', 'message': 'Уведомление отправлено!'})

@app.route('/get_recommendation', methods=['POST'])
def get_recommendation():
    data = request.json
    prompt = data.get('prompt', 'Дай рекомендации по вакансиям.')
    if not prompt:
        return jsonify({'status': 'error', 'message': 'Prompt отсутствует.'}), 400

    try:
        response = openai.Completion.create(
            engine="gpt-4",
            prompt=prompt,
            max_tokens=150
        )
        recommendation = response['choices'][0]['text'].strip()
        logging.info("Рекомендация успешно получена от GPT.")
    except Exception as e:
        logging.error(f"Ошибка при запросе к OpenAI API: {e}")
        return jsonify({'status': 'error', 'message': 'Ошибка при запросе к OpenAI API.'}), 500

    return jsonify({'status': 'success', 'response': recommendation})

@app.route('/ton_balance', methods=['POST'])
def get_ton_balance():
    data = request.json
    address = data.get('address')
    if not address:
        return jsonify({'status': 'error', 'message': 'Адрес не указан.'}), 400
    try:
        balance = ton_client.get_balance(address)
        logging.info(f"Баланс TON для адреса {address}: {balance}")
        return jsonify({'status': 'success', 'balance': balance})
    except Exception as e:
        logging.error(f"Ошибка при получении баланса TON: {e}")
        return jsonify({'status': 'error', 'message': 'Ошибка получения баланса TON.'}), 500

@app.route('/connect_wallet', methods=['POST'])
def connect_wallet():
    data = request.json
    wallet_address = data.get('wallet_address')
    if not wallet_address:
        return jsonify({'status': 'error', 'message': 'Адрес кошелька не указан.'}), 400
    try:
        balance = ton_client.get_balance(wallet_address)
        logging.info(f"Подключен кошелек: {wallet_address}, баланс: {balance}")
        return jsonify({'status': 'success', 'wallet_address': wallet_address, 'balance': balance})
    except Exception as e:
        logging.error(f"Ошибка при подключении кошелька: {e}")
        return jsonify({'status': 'error', 'message': 'Ошибка подключения кошелька.'}), 500

@app.route('/execute_contract', methods=['POST'])
def execute_contract():
    data = request.json
    contract_address = data.get('contract_address')
    function_name = data.get('function_name')
    params = data.get('params', {})
    sender_address = data.get('sender_address')
    sender_key = data.get('sender_key')

    if not contract_address or not function_name or not sender_address or not sender_key:
        return jsonify({'status': 'error', 'message': 'Не указаны адрес контракта, функция или адрес отправителя.'}), 400

    try:
        result = ton_client.call_contract_function(
            contract_address=contract_address,
            function_name=function_name,
            params=params,
            sender_address=sender_address,
            sender_key=sender_key
        )
        logging.info(f"Контракт выполнен успешно: {result}")
        return jsonify({'status': 'success', 'result': result})
    except Exception as e:
        logging.error(f"Ошибка выполнения контракта: {e}")
        return jsonify({'status': 'error', 'message': 'Ошибка выполнения контракта.'}), 500


# Это поиск -- его надо доработать вам пупсики
# @app.route('/search' , methods=['GET'])
# def search():
#     query = request.args.get('query')
#     if not query:
#         return jsonify({'status': 'error', 'message': 'ошибка.'}), 400
#
#     results = [
#         {'title': 'тест 1', 'url': 'http://example.com/result1'},
#         {'title': 'тест 2', 'url': 'http://example.com/result2'},
#         {'title': 'тест 3', 'url': 'http://example.com/result3'}
#     ]
#     logging.info(f"Поиск выполнен для запроса: {query}")
#     return jsonify({'status': 'success', 'results': results})



def check_telegram_auth(data):
    token_sha256 = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
    check_string = "\n".join([f"{k}={v}" for k, v in sorted(data.items()) if k != 'hash'])
    secret_key = hmac.new(token_sha256, check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(secret_key, data['hash'])

# тут настройка портов и запуск с дебагом
if __name__ == '__main__':
    main()
    app.run(port=5050, debug=True)
