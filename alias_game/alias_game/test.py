from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
settings_path = BASE_DIR / 'alias_game/settings.py'

print(settings_path)  # Example usage to verify the path