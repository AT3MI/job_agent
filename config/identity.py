"""Личные данные письма: телефон, ссылка ВК, подпись.

В публичном репозитории здесь плейсхолдеры. Реальные значения храните в .env
(см. .env.example) — файл игнорируется git, значения попадают только в
сгенерированное письмо.
"""

import os

from config.paths import ENV_PATH
from dotenv import load_dotenv

load_dotenv(ENV_PATH)

PHONE = os.getenv("COVER_PHONE", "89990000000")
VK_URL = os.getenv("COVER_VK", "https://vk.ru/example")
FULL_NAME = os.getenv("COVER_NAME", "Иванов Иван")

CONTACTS_TEMPLATE = f"""Для связи прошу использовать мой личный номер
{PHONE} (Звонок или MAX)
Или сообщения в ВК
{VK_URL}

С уважением,
{FULL_NAME}"""
