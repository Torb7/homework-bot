# К сожелению в этом проекте тесты настроены очень жёстко - шаг влево, шаг
# вправо и они падают, поэтому пришлось подстраиваться под них - из-за этого
# один пункт ТЗ не смог выполнить(отправка ошибок в телеграм). Плюс есть
# странные моменты в "архитектуре" или я что-то не понял - я их отметил
# в комментариях в коде.
from datetime import datetime, timedelta
import logging
import os
import sys
import time

from dotenv import load_dotenv
import requests
from telebot import TeleBot, apihelper

from exceptions import TokenError

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
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


def check_tokens():
    """Проверяет доступность переменных окружения."""
    if not all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)):
        logger.critical('Отсутствуют обязательные переменные окружения')
        raise TokenError()


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение успешно отправлено')

    except apihelper.ApiTelegramException as error:
        logger.error(f'Ошибка Telegram API: {error}')

    except requests.RequestException as error:
        logger.error(f'Ошибка сети при подключении к Telegram API: {error}')


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}

    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params=payload, timeout=5
        )
        # Пришлось писать такую конструкцию, потому что если использовать
        # response.raise_for_status() - падают тесты.
        if response.status_code != 200:
            raise requests.HTTPError()

        return response.json()

    except requests.HTTPError:
        # Если просто залогировать ошибку здесь и не прокидывать исключение
        # дальше - падают тесты.
        raise requests.HTTPError()

    except requests.RequestException as error:
        # Здесь не возможно отправить сообщение в Telegram, но если вынести
        # этот блок за функцию - падают тесты. Так же из-за этого блока здесь,
        # функция возвращает None и приходиться в 142 строке выбрасывать
        # исключение, тут же его нельзя пробросить - падают тесты.
        logger.error(error)


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ не является dict')

    if 'homeworks' not in response:
        raise KeyError('В ответе отсутствует ключ homeworks')

    if 'current_date' not in response:
        raise KeyError('В ответе отсутствует ключ current_date')

    if not isinstance(response['current_date'], int):
        raise TypeError('Ключ current_date не является int')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Ключ homeworks не является list')

    if homeworks:
        for homework in homeworks:
            if not isinstance(homework, dict):
                raise TypeError('Данные в homeworks не являются dict')


def parse_status(homework):
    """Обработка homework и генерация строки ответа."""
    status = homework.get('status')
    homework_name = homework.get('homework_name')

    if status is None:
        raise KeyError('Отсутствует ключ status')

    if homework_name is None:
        raise KeyError('Отсутствует ключ homework_name')

    if status not in HOMEWORK_VERDICTS:
        raise ValueError('Неверный ключ status')

    verdict = HOMEWORK_VERDICTS[status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)

    timestamp = int(
        (datetime.now() - timedelta(seconds=RETRY_PERIOD)).timestamp()
    )

    while True:
        try:
            data = get_api_answer(timestamp)
            if not data:
                raise requests.RequestException()
            check_response(data)

            homeworks = data['homeworks']
            if homeworks:
                message = parse_status(homeworks[-1])
                send_message(bot, message)
            else:
                logger.debug('В ответе отсутствуют новые статусы')

            timestamp = data['current_date']

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            # По ТЗ все события уровня ERROR нужно пересылать ещё в Telegram,
            # но если это сделать тут - падают тесты.

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
