# game/models.py

from django.db import models, transaction
from django.utils import timezone
import random
import string
import secrets
from django.db import connection
from contextlib import contextmanager

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

    id = models.CharField(primary_key=True, max_length=10, editable=False)
    creator_telegram_id = models.CharField(max_length=100)
    creator_telegram_username = models.CharField(max_length=255, null=True, blank=True)

    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    num_teams = models.IntegerField(default=2)
    winning_score = models.IntegerField(default=50)
    penalty_for_skip = models.BooleanField(default=True)

    status = models.CharField(max_length=10, choices=ROOM_STATUS_CHOICES, default='waiting')
    current_round = models.IntegerField(default=0)
    current_team_index = models.IntegerField(default=0)
    current_explainer_index_in_team = models.IntegerField(default=0)
    
    current_word = models.CharField(max_length=100, null=True, blank=True)
    round_start_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_activity = models.DateTimeField(default=timezone.now)
    words_in_round_guessed = models.JSONField(default=list)
    words_in_round_skipped = models.JSONField(default=list)
    
    is_ending_round = models.BooleanField(default=False)  # Флаг что раунд завершается
    last_timer_end = models.DateTimeField(null=True, blank=True)  # Время последнего завершения

    def __str__(self):
        return f"Room {self.id} (Status: {self.status})"

    def _generate_candidate_id(self):
        """Генерация ID комнаты с минимумом коллизий"""
        # Используем 8 символов для уменьшения вероятности коллизий
        return secrets.token_urlsafe(6)[:8].upper().replace('_', 'X').replace('-', 'Y')

    def save(self, *args, **kwargs):
        if not self.id:
            for _ in range(100):
                candidate = self._generate_candidate_id()
                if not Room.objects.filter(id=candidate).exists():
                    self.id = candidate
                    break
            else:
                # Fallback на timestamp-based ID
                import time
                self.id = f"R{int(time.time()) % 1000000:06d}"
        
        self.last_activity = timezone.now()
        super().save(*args, **kwargs)

    def get_current_team(self):
        """Безопасное получение текущей команды"""
        try:
            teams = list(self.team_set.all().order_by('index'))
            if teams and 0 <= self.current_team_index < len(teams):
                return teams[self.current_team_index]
        except (IndexError, Team.DoesNotExist):
            pass
        return None

    def get_current_explainer(self):
        """Безопасное получение текущего объясняющего"""
        try:
            current_team = self.get_current_team()
            if not current_team:
                return None
            
            players_in_team = list(current_team.player_set.all().order_by('id'))
            if not players_in_team:
                return None
            
            # Корректируем индекс если вышел за пределы
            if self.current_explainer_index_in_team >= len(players_in_team):
                self.current_explainer_index_in_team = 0
                self.save(update_fields=['current_explainer_index_in_team'])
            
            return players_in_team[self.current_explainer_index_in_team % len(players_in_team)]
        except Exception:
            return None
    
    def advance_turn(self):
        """Атомарное изменение хода с транзакцией"""
        with transaction.atomic():
            # Блокируем запись комнаты для предотвращения race conditions
            room = Room.objects.select_for_update().get(id=self.id)
            teams = list(room.team_set.all().order_by('index'))
            
            if room.is_ending_round:
                return  # Уже завершается
            
            room.is_ending_round = True
            room.save(update_fields=['is_ending_round'])
            
            if not teams:
                return
            
            current_team = teams[room.current_team_index] if 0 <= room.current_team_index < len(teams) else teams[0]
            players_in_team = list(current_team.player_set.all().order_by('id'))
            
            if players_in_team:
                room.current_explainer_index_in_team = (room.current_explainer_index_in_team + 1) % len(players_in_team)
            else:
                room.current_explainer_index_in_team = 0
            
            # Если вернулись к первому игроку в команде, переходим к следующей команде
            if room.current_explainer_index_in_team == 0:
                room.current_team_index = (room.current_team_index + 1) % len(teams)
                room.current_round += 1
            
            # Сброс состояния раунда
            room.words_in_round_guessed = []
            room.words_in_round_skipped = []
            room.current_word = None
            room.round_start_time = None
            room.last_activity = timezone.now()
            room.is_ending_round = False
            room.last_timer_end = timezone.now()
            room.save()
            
            # Обновляем self
            for field in ['current_team_index', 'current_explainer_index_in_team', 
                         'current_round', 'current_word', 'round_start_time',
                         'words_in_round_guessed', 'words_in_round_skipped']:
                setattr(self, field, getattr(room, field))

    def cleanup_inactive_players(self, hours=1):
        """Удаление неактивных игроков"""
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=hours)
        
        inactive_players = self.player_set.filter(
            room__last_activity__lt=cutoff
        )
        count = inactive_players.count()
        inactive_players.delete()
        return count
    
    def remove_disconnected_players(self, timeout_minutes=5):
        """Удаление игроков, которые не активны более timeout_minutes минут"""
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(minutes=timeout_minutes)
    
        inactive_players = self.player_set.filter(last_seen__lt=cutoff)
        count = inactive_players.count()
    
        if count > 0:
            # Перераспределяем игроков если нужно
            for player in inactive_players:
                if player.team:
                    # Если игрок был объясняющим, переходим к следующему
                    if (self.current_explainer_index_in_team is not None and 
                        player == self.get_current_explainer()):
                        self.current_explainer_index_in_team = (
                            self.current_explainer_index_in_team - 1) % max(1, player.team.player_set.count() - 1)
        
            inactive_players.delete()
            self.save(update_fields=['current_explainer_index_in_team'])
    
        return count


class Team(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    score = models.IntegerField(default=0)
    index = models.IntegerField()

    class Meta:
        unique_together = ('room', 'index')
        ordering = ['index']

    def __str__(self):
        return f"{self.room.id} - Team {self.name} (Score: {self.score})"

    def update_score(self, delta):
        """Атомарное обновление счета команды"""
        with transaction.atomic():
            team = Team.objects.select_for_update().get(id=self.id)
            team.score = max(0, team.score + delta)
            team.save()
            self.score = team.score
        return self.score


class Player(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    telegram_id = models.CharField(max_length=100)
    telegram_username = models.CharField(max_length=255, null=True, blank=True)
    joined_at = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('room', 'telegram_id')
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.telegram_username} ({self.telegram_id}) in Room {self.room.id}"

    def save(self, *args, **kwargs):
        self.last_seen = timezone.now()
        super().save(*args, **kwargs)

    def touch(self):
        """Обновить время последней активности"""
        self.last_seen = timezone.now()
        self.save(update_fields=['last_seen'])