import logging
import os
import time
import sys
from http import HTTPStatus

import requests
from telebot import TeleBot
from dotenv import load_dotenv

from exceptions import HTTPRequestError

load_dotenv()

MISSING_ENV_VARS = ('Отсутствие необходимых переменных окружения:'
                    '{missing_tokens}')
MESSAGE_SENT_SUCCESS = 'Сообщение успешно отправлено: {message}'
MESSAGE_SEND_ERROR = ('Произошёл сбой: {error}. При отправке сообщения:'
                      '{message}')
REQUEST_ERROR = ('Ошибка выполнения запроса {req_error} URL: {url},'
                 'Headers: {headers}, Params: {params}')
RESPONSE_STATUS_ERROR = ('Неверный статус ответа: {status_code}. URL: {url},'
                         'Headers: {headers}, Params: {params}')
API_RESPONSE_ERROR = 'Ошибка в ответе API: {error_message}, ключ:{error_key}'
INVALID_API_RESPONSE_TYPE = ('Ответ API не является словарем, получен тип:'
                             '{response_type}')
MISSING_HOMEWORKS_KEY = 'Отсутствие ключа "homeworks" в ответе API'
INVALID_HOMEWORKS_TYPE = ('Тип данных homeworks в ответе API не является'
                          'списком, получен тип: {homeworks_type}')
MISSING_HOMEWORK_KEYS = ('Отсутствие ожидаемых ключей в ответе API:'
                         '{missing_keys}')
UNKNOWN_HOMEWORK_STATUS = 'Неизвестный статус домашней работы: {status}'
STATUS_CHANGED_MESSAGE = ('Изменился статус проверки работы "{homework_name}".'
                          '{verdict}')
NO_STATUS_CHANGE = 'Отсутствие изменения статуса: список домашних работ пуст'
PROGRAM_FAILURE = 'Сбой в работе программы: {error}'


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

TOKEN_NAMES = {'PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID'}


def check_tokens():
    """Проверка доступности необходимых переменных окружения."""
    missing_tokens = [name for name in TOKEN_NAMES if not globals().get(name)]
    if missing_tokens:
        logger.critical(
            MISSING_ENV_VARS.format(missing_tokens=missing_tokens))
        return False
    return True


def send_message(bot, message):
    """Отправка сообщения в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(MESSAGE_SENT_SUCCESS.format(message=message))
    except Exception as error:
        logger.error(MESSAGE_SEND_ERROR.format(error=error, message=message))


def get_api_answer(timestamp):
    """Делает запрос к API и возвращает ответ."""
    params = {'from_date': timestamp}
    try:
        response: requests.Response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params=params,
        )
    except requests.RequestException as req_error:
        raise RuntimeError(REQUEST_ERROR.format(
            req_error=req_error, url=ENDPOINT, headers=HEADERS, params=params))
    if response.status_code != HTTPStatus.OK:
        raise HTTPRequestError(RESPONSE_STATUS_ERROR.format(
            status_code=response.status_code, url=ENDPOINT, headers=HEADERS,
            params=params))
    response_json = response.json()
    if 'code' in response_json or 'error' in response_json:
        error_key = 'error' if 'error' in response_json else 'code'
        error_message = response_json[error_key]
        raise HTTPRequestError(API_RESPONSE_ERROR.format(
            error_message=error_message, error_key=error_key))
    return response_json


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(INVALID_API_RESPONSE_TYPE.format(
            response_type=type(response)))
    if 'homeworks' not in response:
        raise KeyError(MISSING_HOMEWORKS_KEY)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            INVALID_HOMEWORKS_TYPE.format(homeworks_type=type(homeworks)))
    return homeworks


def parse_status(homework):
    """Извлечение статуса домашней работы."""
    required_keys = ['homework_name', 'status']
    missing_keys = [key for key in required_keys if key not in homework]
    if missing_keys:
        raise KeyError(MISSING_HOMEWORK_KEYS.format(missing_keys=missing_keys))
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(UNKNOWN_HOMEWORK_STATUS.format(status=status))
    verdict = HOMEWORK_VERDICTS[status]
    return STATUS_CHANGED_MESSAGE.format(homework_name=homework_name,
                                         verdict=verdict)


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        return

    # Создаем объект класса бота
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    timestamp = response.get('current_date', timestamp)
            else:
                logger.debug(
                    NO_STATUS_CHANGE)
        except Exception as error:
            message = PROGRAM_FAILURE.format(error=error)
            logger.error(message)
            if message != last_error_message:
                if send_message(bot, message):
                    last_error_message = message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    def setup_logging():
        """Установка logging конфигурации."""
        home_dir = os.path.expanduser('~')
        log_file = os.path.join(home_dir, 'practicum_bot.log')

        logging.basicConfig(
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.DEBUG,
            handlers=[
                logging.FileHandler(log_file, mode='w'),
                logging.StreamHandler(sys.stdout)
            ]
        )

        return logging.getLogger(__name__)

    logger = setup_logging()
    main()
