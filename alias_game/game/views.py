# game/views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import random
import string
import time
from django.views.decorators.http import require_http_methods
from .models import GameRoom, Player
from . import words


@csrf_exempt
def index(request):
    return render(request, 'game/index.html')

@csrf_exempt
def create_room(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user_id = data.get('user_id')
        username = data.get('username', '')
        first_name = data.get('first_name', '')
        
        # Создаем или получаем игрока
        player, created = Player.objects.get_or_create(
            user_id=user_id,
            defaults={
                'username': username,
                'first_name': first_name
            }
        )
        
        # Генерируем уникальный ID комнаты
        room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        while GameRoom.objects.filter(room_id=room_id).exists():
            room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Создаем комнату
        room = GameRoom.objects.create(
            room_id=room_id,
            created_by=user_id
        )
        
        # Добавляем создателя в комнату
        player.current_room = room
        player.team_index = 0
        player.save()
        
        # Инициализируем команды
        teams = [f'Команда {i+1}' for i in range(room.team_count)]
        room.set_teams(teams)
        
        # Инициализируем игроков
        players_data = {}
        players_data[user_id] = {
            'username': username,
            'first_name': first_name,
            'team_index': 0
        }
        room.set_players(players_data)
        
        # Инициализируем очки
        scores = {str(i): 0 for i in range(room.team_count)}
        room.set_scores(scores)
        
        room.save()
        
        return JsonResponse({
            'room_id': room_id,
            'is_host': True
        })
    
    return render(request, 'game/create_room.html')

@csrf_exempt
def join_room(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        user_id = data.get('user_id')
        username = data.get('username', '')
        first_name = data.get('first_name', '')
        
        try:
            room = GameRoom.objects.get(room_id=room_id, is_active=True)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        # Создаем или получаем игрока
        player, created = Player.objects.get_or_create(
            user_id=user_id,
            defaults={
                'username': username,
                'first_name': first_name
            }
        )
        
        # Добавляем игрока в комнату
        player.current_room = room
        player.save()
        
        # Добавляем игрока в данные комнаты
        players_data = room.get_players()
        players_data[user_id] = {
            'username': username,
            'first_name': first_name,
            'team_index': -1  # Пока не выбрал команду
        }
        room.set_players(players_data)
        room.save()
        
        return JsonResponse({
            'room_id': room_id,
            'teams': room.get_teams(),
            'players': players_data
        })
    
    return render(request, 'game/join_room.html')

@csrf_exempt
def update_room_settings(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        
        try:
            room = GameRoom.objects.get(room_id=room_id)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        # Обновляем настройки
        room.team_count = data.get('team_count', 2)
        room.difficulty = data.get('difficulty', 'medium')
        room.target_score = data.get('target_score', 50)
        room.penalty_for_skip = data.get('penalty_for_skip', False)
        
        # Обновляем команды
        teams = room.get_teams()
        if len(teams) != room.team_count:
            teams = [f'Команда {i+1}' for i in range(room.team_count)]
            room.set_teams(teams)
            
            # Сбрасываем очки
            scores = {str(i): 0 for i in range(room.team_count)}
            room.set_scores(scores)
        
        room.save()
        
        return JsonResponse({
            'success': True,
            'teams': teams,
            'settings': {
                'team_count': room.team_count,
                'difficulty': room.difficulty,
                'target_score': room.target_score,
                'penalty_for_skip': room.penalty_for_skip
            }
        })

@csrf_exempt
def join_team(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        user_id = data.get('user_id')
        team_index = data.get('team_index')
        
        try:
            room = GameRoom.objects.get(room_id=room_id)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        # Обновляем данные игрока
        player = Player.objects.get(user_id=user_id)
        player.team_index = team_index
        player.save()
        
        # Обновляем данные в комнате
        players_data = room.get_players()
        if user_id in players_data:
            players_data[user_id]['team_index'] = team_index
            room.set_players(players_data)
            room.save()
        
        return JsonResponse({'success': True})

@csrf_exempt
def update_team_name(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        team_index = data.get('team_index')
        team_name = data.get('team_name')
        
        try:
            room = GameRoom.objects.get(room_id=room_id)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        teams = room.get_teams()
        if 0 <= team_index < len(teams):
            teams[team_index] = team_name
            room.set_teams(teams)
            room.save()
        
        return JsonResponse({'success': True, 'teams': teams})

@csrf_exempt
def start_game(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        
        try:
            room = GameRoom.objects.get(room_id=room_id)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        room.is_game_started = True
        room.current_round = 1
        room.current_team_index = 0
        room.current_explainer_index = 0
        
        # Генерируем первые слова
        generate_words_for_round(room)
        
        room.save()
        
        return JsonResponse({
            'success': True,
            'game_state': get_game_state(room)
        })

@csrf_exempt
def get_room_state(request, room_id):
    try:
        room = GameRoom.objects.get(room_id=room_id)
    except GameRoom.DoesNotExist:
        return JsonResponse({'error': 'Комната не найдена'}, status=404)
    
    if room.is_game_started:
        return JsonResponse(get_game_state(room))
    else:
        return JsonResponse({
            'is_game_started': False,
            'teams': room.get_teams(),
            'players': room.get_players(),
            'settings': {
                'team_count': room.team_count,
                'difficulty': room.difficulty,
                'target_score': room.target_score,
                'penalty_for_skip': room.penalty_for_skip
            }
        })

@csrf_exempt
def start_explaining(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        
        try:
            room = GameRoom.objects.get(room_id=room_id)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        # Возвращаем текущие слова
        current_words = room.get_current_words()
        
        return JsonResponse({
            'success': True,
            'words': current_words,
            'time_limit': 60  # 60 секунд на раунд
        })

@csrf_exempt
def word_guessed(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        word_index = data.get('word_index')
        
        try:
            room = GameRoom.objects.get(room_id=room_id)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        # Обновляем очки
        scores = room.get_scores()
        team_key = str(room.current_team_index)
        scores[team_key] = scores.get(team_key, 0) + 1
        room.set_scores(scores)
        
        # Удаляем слово из текущих
        current_words = room.get_current_words()
        if word_index < len(current_words):
            current_words.pop(word_index)
        room.set_current_words(current_words)
        
        room.save()
        
        return JsonResponse({
            'success': True,
            'scores': scores,
            'words_left': len(current_words)
        })

@csrf_exempt
def word_skipped(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        word_index = data.get('word_index')
        
        try:
            room = GameRoom.objects.get(room_id=room_id)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        # Если включен штраф за пропуск
        if room.penalty_for_skip:
            scores = room.get_scores()
            team_key = str(room.current_team_index)
            scores[team_key] = scores.get(team_key, 0) - 1
            room.set_scores(scores)
        
        # Удаляем слово из текущих
        current_words = room.get_current_words()
        if word_index < len(current_words):
            current_words.pop(word_index)
        room.set_current_words(current_words)
        
        room.save()
        
        return JsonResponse({
            'success': True,
            'scores': room.get_scores(),
            'words_left': len(current_words)
        })

@csrf_exempt
def end_turn(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        room_id = data.get('room_id')
        
        try:
            room = GameRoom.objects.get(room_id=room_id)
        except GameRoom.DoesNotExist:
            return JsonResponse({'error': 'Комната не найдена'}, status=404)
        
        # Проверяем, не достигнута ли победа
        scores = room.get_scores()
        target_score = room.target_score
        winning_team = None
        
        for team_index, score in scores.items():
            if score >= target_score:
                winning_team = int(team_index)
                break
        
        if winning_team is not None:
            # Игра окончена
            teams = room.get_teams()
            return JsonResponse({
                'game_over': True,
                'winning_team': winning_team,
                'winning_team_name': teams[winning_team],
                'scores': scores
            })
        
        # Передаем ход следующей команде
        room.current_team_index = (room.current_team_index + 1) % room.team_count
        
        # Если это начало нового круга, меняем объясняющего
        if room.current_team_index == 0:
            room.current_explainer_index += 1
            room.current_round += 1
        
        # Генерируем новые слова
        generate_words_for_round(room)
        
        room.save()
        
        return JsonResponse(get_game_state(room))

def generate_words_for_round(room):
    """Генерирует слова для текущего раунда"""
    difficulty = room.difficulty
    word_list = words.get_words_by_difficulty(difficulty)
    
    # Исключаем уже использованные слова
    used_words = set(room.get_used_words())
    available_words = [w for w in word_list if w not in used_words]
    
    # Выбираем 10 случайных слов
    if len(available_words) < 10:
        # Если слов мало, сбрасываем использованные
        available_words = word_list
        used_words = []
    
    selected_words = random.sample(available_words, min(10, len(available_words)))
    
    # Обновляем использованные слова
    new_used_words = list(used_words) + selected_words
    room.set_used_words(new_used_words)
    room.set_current_words(selected_words)

def get_game_state(room):
    """Возвращает состояние игры для комнаты"""
    teams = room.get_teams()
    players = room.get_players()
    scores = room.get_scores()
    
    # Находим объясняющего
    current_team_players = [
        player_id for player_id, data in players.items() 
        if data.get('team_index') == room.current_team_index
    ]
    
    if current_team_players:
        explainer_index = room.current_explainer_index % len(current_team_players)
        explainer_id = current_team_players[explainer_index]
        explainer_name = players.get(explainer_id, {}).get('first_name', 'Игрок')
    else:
        explainer_name = 'Игрок'
    
    return {
        'is_game_started': True,
        'current_round': room.current_round,
        'current_team_index': room.current_team_index,
        'current_team_name': teams[room.current_team_index],
        'explainer_name': explainer_name,
        'scores': scores,
        'teams': teams,
        'players': players,
        'target_score': room.target_score
    }

@csrf_exempt
@require_http_methods(["GET"])
def room_page(request, room_id):
    try:
        room = GameRoom.objects.get(room_id=room_id)
        return render(request, 'game/room.html', {'room_id': room_id})
    except GameRoom.DoesNotExist:
        return redirect('/')

@csrf_exempt
@require_http_methods(["GET"])
def game_page(request, room_id):
    try:
        room = GameRoom.objects.get(room_id=room_id, is_game_started=True)
        return render(request, 'game/game.html', {'room_id': room_id})
    except GameRoom.DoesNotExist:
        return redirect(f'/room/{room_id}/')