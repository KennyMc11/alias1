# game/admin.py
from django.contrib import admin
from .models import GameRoom, Player

class GameRoomAdmin(admin.ModelAdmin):
    list_display = ('room_id', 'created_by', 'created_at', 'is_active', 'is_game_started')
    list_filter = ('is_active', 'is_game_started', 'difficulty', 'created_at')
    search_fields = ('room_id', 'created_by')
    readonly_fields = ('room_id', 'created_at')
    
    # Добавляем методы для отображения в админке
    def get_teams_display(self, obj):
        teams = obj.get_teams()
        return ', '.join(teams) if teams else 'Нет команд'
    get_teams_display.short_description = 'Команды'
    
    def get_scores_display(self, obj):
        scores = obj.get_scores()
        return str(scores)
    get_scores_display.short_description = 'Очки'
    
    def get_players_count(self, obj):
        players = obj.get_players()
        return len(players)
    get_players_count.short_description = 'Игроков'
    
    # Изменяем list_display для показа дополнительной информации
    list_display = ('room_id', 'created_by', 'get_players_count', 'current_round', 
                   'is_active', 'is_game_started', 'created_at')
    
    # Группировка полей в форме редактирования
    fieldsets = (
        ('Основная информация', {
            'fields': ('room_id', 'created_by', 'created_at', 'is_active')
        }),
        ('Игровой процесс', {
            'fields': ('is_game_started', 'current_round', 'current_team_index', 
                      'current_explainer_index')
        }),
        ('Настройки игры', {
            'fields': ('team_count', 'difficulty', 'target_score', 'penalty_for_skip')
        }),
        ('Состояние игры (JSON)', {
            'fields': ('teams', 'players', 'scores', 'used_words', 'current_words'),
            'classes': ('collapse',)  # Сворачиваемый блок
        }),
    )

class PlayerAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'username', 'first_name', 'get_current_room', 
                   'get_team_index', 'get_joined_time')
    list_filter = ('current_room',)
    search_fields = ('user_id', 'username', 'first_name', 'last_name')
    
    # Методы для отображения дополнительной информации
    def get_current_room(self, obj):
        return obj.current_room.room_id if obj.current_room else 'Нет'
    get_current_room.short_description = 'Комната'
    get_current_room.admin_order_field = 'current_room__room_id'
    
    def get_team_index(self, obj):
        if obj.current_room and obj.team_index >= 0:
            teams = obj.current_room.get_teams()
            if obj.team_index < len(teams):
                return f"{teams[obj.team_index]} ({obj.team_index})"
        return 'Не в команде' if obj.team_index == -1 else f'Команда {obj.team_index}'
    get_team_index.short_description = 'Команда'
    
    def get_joined_time(self, obj):
        # Ищем когда игрок присоединился к комнате
        if obj.current_room:
            players = obj.current_room.get_players()
            # Можно добавить логику для отслеживания времени присоединения
            return 'Неизвестно'
        return 'Не в комнате'
    get_joined_time.short_description = 'Присоединился'
    
    # Группировка полей
    fieldsets = (
        ('Информация о пользователе', {
            'fields': ('user_id', 'username', 'first_name', 'last_name')
        }),
        ('Игровая информация', {
            'fields': ('current_room', 'team_index')
        }),
    )

admin.site.register(GameRoom, GameRoomAdmin)
admin.site.register(Player, PlayerAdmin)