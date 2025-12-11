# game/models.py
from django.db import models
import json
from django.utils import timezone

class GameRoom(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'Легкий'),
        ('medium', 'Средний'),
        ('hard', 'Сложный'),
    ]
    
    room_id = models.CharField(max_length=6, unique=True)
    created_by = models.CharField(max_length=100)  # Telegram user_id
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    current_round = models.IntegerField(default=1)
    current_team_index = models.IntegerField(default=0)
    current_explainer_index = models.IntegerField(default=0)
    is_game_started = models.BooleanField(default=False)
    
    # Настройки комнаты
    team_count = models.IntegerField(default=2)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    target_score = models.IntegerField(default=50)
    penalty_for_skip = models.BooleanField(default=False)
    
    # JSON поля для хранения состояния
    teams = models.TextField(default='[]')  # Список команд
    players = models.TextField(default='{}')  # Словарь игроков
    used_words = models.TextField(default='[]')  # Использованные слова
    current_words = models.TextField(default='[]')  # Текущие слова для объяснения
    scores = models.TextField(default='{}')  # Очки команд
    
    def get_teams(self):
        return json.loads(self.teams)
    
    def set_teams(self, teams_list):
        self.teams = json.dumps(teams_list)
    
    def get_players(self):
        return json.loads(self.players)
    
    def set_players(self, players_dict):
        self.players = json.dumps(players_dict)
    
    def get_used_words(self):
        return json.loads(self.used_words)
    
    def set_used_words(self, words_list):
        self.used_words = json.dumps(words_list)
    
    def get_current_words(self):
        return json.loads(self.current_words)
    
    def set_current_words(self, words_list):
        self.current_words = json.dumps(words_list)
    
    def get_scores(self):
        return json.loads(self.scores)
    
    def set_scores(self, scores_dict):
        self.scores = json.dumps(scores_dict)
    
    def __str__(self):
        return f"Комната {self.room_id} (создана {self.created_by})"


class Player(models.Model):
    user_id = models.CharField(max_length=100, unique=True)
    username = models.CharField(max_length=100, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    current_room = models.ForeignKey(GameRoom, on_delete=models.SET_NULL, null=True, blank=True, related_name='room_players')
    team_index = models.IntegerField(default=-1)  # -1 означает не в команде
    
    def __str__(self):
        return f"{self.first_name} (@{self.username})" if self.username else f"Игрок {self.user_id}"