import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Путь к корню проекта
project_home = str(BASE_DIR)
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Путь к директории с настройками
settings_path = BASE_DIR / 'alias_game/settings.py'
if settings_path not in sys.path:
    sys.path.insert(0, settings_path)

# Установите переменные окружения
os.environ['DJANGO_SETTINGS_MODULE'] = 'alias_game.settings'

# Загрузите Django приложение
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()