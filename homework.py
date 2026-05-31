import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Any

import requests
from dotenv import load_dotenv
from telebot import TeleBot, apihelper

from exceptions import TokenError, PracticumAPIError

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s %(levelname)s %(funcName)s %(message)s'
)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def check_tokens() -> None:
    """Проверяет доступность переменных окружения."""
    tokens = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')
    missing_tokens = [token for token in tokens if not globals()[token]]

    if missing_tokens:
        message = f'Отсутствуют переменные окружения: {missing_tokens}'
        logger.critical(message)
        raise TokenError(message)


def send_message(bot: TeleBot, message: str) -> None:
    """Отправляет сообщение в Telegram-чат."""
    logger.debug('Начало выполнения отправки сообщения')

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

    logger.debug('Сообщение успешно отправлено')


def get_api_answer(timestamp: int) -> dict[str, Any]:
    """Делает запрос к эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}

    logger.debug(
        f'Начало выполнения запроса к {ENDPOINT} с параметрами: {payload}'
    )

    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params=payload, timeout=5
        )

    except requests.RequestException as error:
        raise PracticumAPIError(error) from error

    if response.status_code != HTTPStatus.OK:
        raise PracticumAPIError(
            f'Неверный статус-код Practicum API: {response.status_code}'
        )

    logger.debug(
        f'Успешное завершение запроса к {ENDPOINT} с параметрами: {payload}'
    )

    return response.json()


def check_response(response: dict[str, Any]) -> None:
    """Проверяет ответ API на соответствие документации."""
    logger.debug('Начало выполнения функции check_response')

    if not isinstance(response, dict):
        raise TypeError(f'Тип данных ответа: {response} - не является dict')

    if 'homeworks' not in response:
        raise KeyError('В ответе отсутствует ключ homeworks')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Тип данных ключа homeworks: {homeworks} - не является list'
        )

    logger.debug('Успешное завершение функции check_response')


def parse_status(homework: dict[str, Any]) -> str:
    """Обработка homework и генерация строки ответа."""
    logger.debug('Начало выполнения функции parse_status')

    if not isinstance(homework, dict):
        raise TypeError(f'Тип данных homework: {homework} - не является dict')

    keys = ('status', 'homework_name')
    missing_keys = [key for key in keys if key not in homework]
    if missing_keys:
        raise KeyError(f'В homework отсутствует ключи: {missing_keys}')

    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестное значение ключа status: {status}')

    homework_name = homework['homework_name']
    verdict = HOMEWORK_VERDICTS[status]

    logger.debug('Успешное завершение функции parse_status')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)

    prev_message = ''
    timestamp = int(time.time()) - RETRY_PERIOD

    while True:
        try:
            data = get_api_answer(timestamp)
            check_response(data)

            homeworks = data['homeworks']
            if not homeworks:
                logger.debug('В ответе отсутствуют новые статусы')
                continue

            message = parse_status(homeworks[-1])
            if prev_message != message:
                send_message(bot, message)
                prev_message = message

            timestamp += RETRY_PERIOD

        except (
            apihelper.ApiTelegramException,
            requests.RequestException,
        ) as error:
            logger.exception(f'Ошибка Telegram API: {error}')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.exception(message)

            if prev_message != message:
                send_message(bot, message)
                prev_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
