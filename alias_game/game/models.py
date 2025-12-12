# game/models.py

import uuid
from django.db import models
from django.utils import timezone
import random

class Room(models.Model):
    ROOM_STATUS_CHOICES = [
        ('waiting', 'Waiting for players'),
        ('playing', 'Playing'),
        ('finished', 'Finished'),
    ]
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator_telegram_id = models.CharField(max_length=100) # ID создателя из Telegram
    creator_telegram_username = models.CharField(max_length=255, null=True, blank=True)

    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    num_teams = models.IntegerField(default=2)
    winning_score = models.IntegerField(default=50)
    penalty_for_skip = models.BooleanField(default=True)

    status = models.CharField(max_length=10, choices=ROOM_STATUS_CHOICES, default='waiting')
    current_round = models.IntegerField(default=0) # Номер раунда
    current_team_index = models.IntegerField(default=0) # Индекс текущей команды в списке teams
    current_explainer_index_in_team = models.IntegerField(default=0) # Индекс объясняющего в текущей команде
    
    current_word = models.CharField(max_length=100, null=True, blank=True)
    round_start_time = models.DateTimeField(null=True, blank=True) # Время начала текущего раунда
    created_at = models.DateTimeField(default=timezone.now)
    words_in_round_guessed = models.JSONField(default=list) # Слова, отгаданные в текущем раунде
    words_in_round_skipped = models.JSONField(default=list) # Слова, пропущенные в текущем раунде

    def __str__(self):
        return f"Room {self.id} (Status: {self.status})"

    def get_current_team(self):
        teams = list(self.team_set.all().order_by('index'))
        if teams:
            return teams[self.current_team_index % len(teams)]
        return None

    def get_current_explainer(self):
        current_team = self.get_current_team()
        if not current_team:
            return None
        
        players_in_team = list(current_team.player_set.all().order_by('id')) # Сортируем для стабильного порядка
        if not players_in_team:
            return None
        
        # Обновляем explainer_index, если он вышел за пределы списка игроков
        if self.current_explainer_index_in_team >= len(players_in_team):
             self.current_explainer_index_in_team = 0
             self.save()
        return players_in_team[self.current_explainer_index_in_team % len(players_in_team)]
    
    def advance_turn(self):
        teams = list(self.team_set.all().order_by('index'))
        if not teams:
            return

        # Сначала меняем объясняющего в текущей команде
        current_team = teams[self.current_team_index]
        players_in_team = list(current_team.player_set.all().order_by('id'))
        
        if players_in_team:
            self.current_explainer_index_in_team = (self.current_explainer_index_in_team + 1) % len(players_in_team)
        else: # Если в команде нет игроков, просто переходим к следующей команде
            self.current_explainer_index_in_team = 0 # Сбрасываем для новой команды

        # Если explainer_index_in_team обнулился (прошли всех в команде), переходим к следующей команде
        if self.current_explainer_index_in_team == 0:
            self.current_team_index = (self.current_team_index + 1) % len(teams)
            self.current_round += 1 # Увеличиваем номер раунда при смене команды (цикл команд)

        # Сброс слов раунда
        self.words_in_round_guessed = []
        self.words_in_round_skipped = []
        self.current_word = None
        self.round_start_time = None
        self.save()


class Team(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    score = models.IntegerField(default=0)
    index = models.IntegerField() # Для определения порядка хода

    class Meta:
        unique_together = ('room', 'index') # Каждая команда в комнате имеет уникальный индекс

    def __str__(self):
        return f"{self.room.id} - Team {self.name} (Score: {self.score})"

class Player(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    telegram_id = models.CharField(max_length=100, unique=False) # ID пользователя Telegram
    telegram_username = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.telegram_username} ({self.telegram_id}) in Room {self.room.id}"

    class Meta:
        unique_together = ('room', 'telegram_id') # Пользователь может быть только один раз в одной комнате
