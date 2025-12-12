from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
settings_path = BASE_DIR / 'alias_game/settings.py'

if __name__ == '__main__':
	# Example usage to verify the path
	print(settings_path)