
# game/views.py

import json
import uuid
import urllib.parse
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.conf import settings
import random

from .models import Room, Team, Player
from .words import WORDS # Импортируем слова

# --- Helper function for getting Telegram User Info ---
# Сначала пытаемся получить информацию из Telegram Mini App (GET/POST/Headers),
# затем из cookies для веб-режима, затем из JSON тела или initData при наличии.
# В продакшене Telegram initData нужно валидировать через токен бота.
def get_telegram_user_info(request):
    """Попытаться извлечь информацию о пользователе Telegram или веб-пользователя из запроса.

    Источники (по убыванию приоритета):
    - GET / POST параметры `tg_user_id` и `tg_username` (используется в UI-формах);
    - Заголовки `X-Telegram-User-Id` и `X-Telegram-Username`;
    - Cookies: `alias_web_user_id` и `alias_web_username` для веб-пользователей;
    - JSON-тело (например, initData или `{ "user": {...} }`).

    Возвращает словарь {'id': str|None, 'username': str|None}.
    """
    # 1) GET / POST / HEADERS
    user_id = (
        request.POST.get('tg_user_id')
        or request.GET.get('tg_user_id')
        or request.headers.get('X-Telegram-User-Id')
    )
    username = (
        request.POST.get('tg_username')
        or request.GET.get('tg_username')
        or request.headers.get('X-Telegram-Username')
    )

    # 2) Cookie (веб)
    if not user_id:
        user_id = request.COOKIES.get('alias_web_user_id')
    if not username:
        cookie_username = request.COOKIES.get('alias_web_username')
        if cookie_username:
            try:
                username = urllib.parse.unquote(cookie_username)
            except Exception:
                username = cookie_username

    # 3) JSON body
    if (not user_id or not username) and request.content_type and 'application/json' in request.content_type:
        try:
            body = request.body
            if body:
                data = json.loads(body)
                user_data = data.get('user') if isinstance(data, dict) else None
                if isinstance(user_data, dict):
                    user_id = user_id or user_data.get('id')
                    username = username or user_data.get('username') or user_data.get('first_name')
                else:
                    user_id = user_id or data.get('tg_user_id') or data.get('user_id')
                    username = username or data.get('tg_username') or data.get('username') or data.get('first_name')
        except Exception:
            pass

    # 4) initData string
    if (not user_id or not username) and (request.POST.get('initData') or request.GET.get('initData')):
        init_data = request.POST.get('initData') or request.GET.get('initData')
        try:
            decoded = json.loads(init_data)
            user_data = decoded.get('user') if isinstance(decoded, dict) else None
            if user_data:
                user_id = user_id or user_data.get('id')
                username = username or user_data.get('username') or user_data.get('first_name')
        except Exception:
            pass

    # Normalize types
    if user_id is not None:
        try:
            user_id = str(user_id)
        except Exception:
            user_id = None

    if username is None and user_id is not None:
        username = f"TG_{user_id}"

    return {'id': user_id, 'username': username}


# --- Основные страницы ---

@require_GET
def index(request):
    telegram_user_info = get_telegram_user_info(request)
    return render(request, 'game/index.html', {'telegram_user_info': telegram_user_info})

@require_GET
def create_room(request):
    telegram_user_info = get_telegram_user_info(request)
    # Если пользователь не из Telegram — покажем форму для ввода имени (в псевдо-веб режиме)
    return render(request, 'game/create_room.html', {'telegram_user_info': telegram_user_info})

@require_POST
def create_room_post(request):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    try:
        num_teams = int(request.POST.get('num_teams', 2))
        winning_score = int(request.POST.get('winning_score', 50))
        difficulty = request.POST.get('difficulty', 'medium')
        penalty_for_skip = request.POST.get('penalty_for_skip') == 'on'

        if not (2 <= num_teams <= 4): # Ограничиваем количество команд
            return JsonResponse({'status': 'error', 'message': 'Number of teams must be between 2 and 4.'}, status=400)
        if winning_score < 10:
            return JsonResponse({'status': 'error', 'message': 'Winning score must be at least 10.'}, status=400)
        if difficulty not in dict(Room.DIFFICULTY_CHOICES):
            return JsonResponse({'status': 'error', 'message': 'Invalid difficulty.'}, status=400)

        room = Room.objects.create(
            creator_telegram_id=telegram_user_info['id'],
            creator_telegram_username=telegram_user_info['username'],
            num_teams=num_teams,
            winning_score=winning_score,
            difficulty=difficulty,
            penalty_for_skip=penalty_for_skip,
            status='waiting'
        )

        for i in range(num_teams):
            Team.objects.create(room=room, name=f"Team {i+1}", index=i)
        
        # Создатель комнаты автоматически присоединяется
        Player.objects.create(
            room=room,
            telegram_id=telegram_user_info['id'],
            telegram_username=telegram_user_info['username'],
            team=room.team_set.first() # Присоединяем к первой команде по умолчанию
        )

        return JsonResponse({'status': 'success', 'room_id': str(room.id)})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_GET
def join_room(request):
    telegram_user_info = get_telegram_user_info(request)
    # Если пользователь не из Telegram — покажем форму для ввода имени (в псевдо-веб режиме)
    return render(request, 'game/join_room.html', {'telegram_user_info': telegram_user_info})

@require_POST
def join_room_post(request):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    room_id = request.POST.get('room_id')
    try:
        room = get_object_or_404(Room, id=room_id)
        
        player, created = Player.objects.get_or_create(
            room=room,
            telegram_id=telegram_user_info['id'],
            defaults={
                'telegram_username': telegram_user_info['username'],
                'team': room.team_set.first() # Присоединяем к первой команде по умолчанию
            }
        )
        if not created:
            player.telegram_username = telegram_user_info['username'] # Обновляем имя, если оно изменилось
            player.save()

        return JsonResponse({'status': 'success', 'room_id': str(room.id)})
    except Room.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Room not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_GET
def room_detail(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return redirect('index')

    room = get_object_or_404(Room, id=room_id)
    player = get_object_or_404(Player, room=room, telegram_id=telegram_user_info['id'])

    is_creator = (player.telegram_id == room.creator_telegram_id)
    
    context = {
        'room': room,
        'player': player,
        'is_creator': is_creator,
        'telegram_user_info': telegram_user_info,
        'ROUND_DURATION_SECONDS': settings.ROUND_DURATION_SECONDS
    }
    return render(request, 'game/room.html', context)

# --- AJAX API для игры ---

@require_GET
def get_game_state(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    room = get_object_or_404(Room, id=room_id)
    player = get_object_or_404(Player, room=room, telegram_id=telegram_user_info['id'])

    teams_data = []
    for team in room.team_set.all().order_by('index'):
        players_in_team = [{'id': p.id, 'telegram_username': p.telegram_username} for p in team.player_set.all().order_by('id')]
        teams_data.append({
            'id': str(team.id),
            'name': team.name,
            'score': team.score,
            'players': players_in_team
        })
    
    current_team = room.get_current_team()
    current_explainer = room.get_current_explainer()

    is_current_explainer = (current_explainer and current_explainer.id == player.id)
    
    time_remaining = 0
    if room.status == 'playing' and room.round_start_time:
        elapsed_time = (timezone.now() - room.round_start_time).total_seconds()
        time_remaining = max(0, settings.ROUND_DURATION_SECONDS - int(elapsed_time))
        if time_remaining == 0:
            # Время вышло, автоматически завершаем раунд
            room.advance_turn()
            room.status = 'playing' # Игра продолжается
            room.save()
            # Пересчитаем состояние после смены хода
            current_team = room.get_current_team()
            current_explainer = room.get_current_explainer()
            is_current_explainer = (current_explainer and current_explainer.id == player.id)
            room.current_word = None # Сброс слова для нового объясняющего
            time_remaining = settings.ROUND_DURATION_SECONDS # Новый раунд, полный таймер

    game_finished = False
    winning_team_name = None
    if room.status == 'playing':
        for team in room.team_set.all():
            if team.score >= room.winning_score:
                room.status = 'finished'
                room.save()
                game_finished = True
                winning_team_name = team.name
                break
    elif room.status == 'finished':
        game_finished = True
        # Найти победителя (первая команда, набравшая очки)
        winning_team = room.team_set.filter(score__gte=room.winning_score).first()
        if winning_team:
            winning_team_name = winning_team.name


    response_data = {
        'status': room.status,
        'game_finished': game_finished,
        'winning_team_name': winning_team_name,
        'room_id': str(room.id),
        'creator_username': room.creator_telegram_username,
        'difficulty': room.get_difficulty_display(),
        'num_teams': room.num_teams,
        'winning_score': room.winning_score,
        'penalty_for_skip': room.penalty_for_skip,
        'current_round': room.current_round,
        'current_team_name': current_team.name if current_team else 'N/A',
        'current_explainer_username': current_explainer.telegram_username if current_explainer else 'N/A',
        'is_current_explainer': is_current_explainer,
        'current_word': room.current_word,
        'time_remaining': time_remaining,
        'teams': teams_data,
        'my_player_id': player.id,
        'my_team_id': str(player.team.id) if player.team else None,
        'players_in_room_count': room.player_set.count()
    }
    return JsonResponse(response_data)

@require_POST
def update_team_name(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)
    
    room = get_object_or_404(Room, id=room_id)
    # Только создатель комнаты или участник команды может менять название своей команды
    if room.creator_telegram_id != telegram_user_info['id']:
         return JsonResponse({'status': 'error', 'message': 'Only the room creator can update team names.'}, status=403)

    team_id = request.POST.get('team_id')
    new_name = request.POST.get('new_name')

    if not new_name or len(new_name) < 2 or len(new_name) > 50:
        return JsonResponse({'status': 'error', 'message': 'Team name must be between 2 and 50 characters.'}, status=400)

    try:
        team = get_object_or_404(Team, room=room, id=team_id)
        team.name = new_name
        team.save()
        return JsonResponse({'status': 'success'})
    except Team.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Team not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
def select_team(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    room = get_object_or_404(Room, id=room_id)
    player = get_object_or_404(Player, room=room, telegram_id=telegram_user_info['id'])

    team_id = request.POST.get('team_id')
    try:
        team = get_object_or_404(Team, room=room, id=team_id)
        player.team = team
        player.save()
        return JsonResponse({'status': 'success'})
    except Team.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Team not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
def set_web_identity(request):
    """Установить идентичность веб-пользователя (когда Telegram недоступен).

    Принимает `web_username` и опциональный `next` — URL для перенаправления.
    Сохраняет `alias_web_user_id` и `alias_web_username` в cookies.
    """
    username = request.POST.get('web_username', '').strip()
    next_url = request.POST.get('next') or request.POST.get('redirect_to') or request.META.get('HTTP_REFERER') or '/'

    if not username:
        # Нельзя создать пустое имя — вернемся обратно с ошибкой (простое поведение)
        response = redirect(next_url)
        return response

    new_id = str(uuid.uuid4())
    response = redirect(next_url)
    # Сохраняем на год
    response.set_cookie('alias_web_user_id', new_id, max_age=60 * 60 * 24 * 365, httponly=True)
    # URL-encode username to ensure header-safe cookie value
    try:
        cookie_username = urllib.parse.quote(username, safe='')
    except Exception:
        cookie_username = username
    response.set_cookie('alias_web_username', cookie_username, max_age=60 * 60 * 24 * 365)
    return response


@require_POST
def start_game(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    room = get_object_or_404(Room, id=room_id)
    # Только создатель может начать игру
    if room.creator_telegram_id != telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Only the room creator can start the game.'}, status=403)
    
    if room.status != 'waiting':
        return JsonResponse({'status': 'error', 'message': 'Game has already started or finished.'}, status=400)
    
    # Проверка, что во всех командах есть хотя бы 1 игрок
    teams_with_players = sum(1 for team in room.team_set.all() if team.player_set.count() > 0)
    if teams_with_players < room.num_teams:
        return JsonResponse({'status': 'error', 'message': 'All teams must have at least one player to start the game.'}, status=400)

    room.status = 'playing'
    room.current_round = 1
    room.current_team_index = 0
    room.current_explainer_index_in_team = 0
    room.save()

    return JsonResponse({'status': 'success'})


@require_POST
def start_round(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    room = get_object_or_404(Room, id=room_id)
    player = get_object_or_404(Player, room=room, telegram_id=telegram_user_info['id'])

    current_explainer = room.get_current_explainer()
    if not current_explainer or current_explainer.id != player.id:
        return JsonResponse({'status': 'error', 'message': 'You are not the current explainer.'}, status=403)

    if room.status != 'playing':
        return JsonResponse({'status': 'error', 'message': 'Game is not in playing state.'}, status=400)

    # Если слово уже есть, значит раунд уже стартовал
    if room.current_word and room.round_start_time:
         return JsonResponse({'status': 'error', 'message': 'Round already started.'}, status=400)

    # Выбираем случайное слово
    available_words = [w for w in WORDS[room.difficulty] if w not in room.words_in_round_guessed + room.words_in_round_skipped]
    if not available_words:
        # Если слова закончились, можно перезагрузить список или закончить игру
        # Для простоты, пока просто возьмем из общего списка снова, но это может привести к повторам
        available_words = WORDS[room.difficulty]
        room.words_in_round_guessed = []
        room.words_in_round_skipped = []
        room.save() # Сохраним очистку списков

    new_word = random.choice(available_words)
    room.current_word = new_word
    room.round_start_time = timezone.now()
    room.save()

    return JsonResponse({'status': 'success', 'word': new_word})

@require_POST
def handle_word_action(request, room_id, action): # 'guessed' or 'skip'
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    room = get_object_or_404(Room, id=room_id)
    player = get_object_or_404(Player, room=room, telegram_id=telegram_user_info['id'])

    current_explainer = room.get_current_explainer()
    if not current_explainer or current_explainer.id != player.id:
        return JsonResponse({'status': 'error', 'message': 'You are not the current explainer.'}, status=403)
    
    if room.status != 'playing' or not room.current_word:
        return JsonResponse({'status': 'error', 'message': 'No active word to ' + action}, status=400)
    
    current_team = room.get_current_team()

    if action == 'guessed':
        current_team.score += 1
        room.words_in_round_guessed.append(room.current_word)
        current_team.save()
    elif action == 'skip':
        if room.penalty_for_skip:
            current_team.score = max(0, current_team.score - 1) # Не уходим в минус
            current_team.save()
        room.words_in_round_skipped.append(room.current_word)
    
    room.current_word = None # Сбрасываем текущее слово
    room.save()

    # Проверка на победу
    if current_team.score >= room.winning_score:
        room.status = 'finished'
        room.save()
        return JsonResponse({'status': 'success', 'game_over': True, 'winning_team': current_team.name})

    # Выбираем новое слово
    available_words = [w for w in WORDS[room.difficulty] if w not in room.words_in_round_guessed + room.words_in_round_skipped]
    if not available_words:
        # Если слова закончились в текущем раунде, переходим к следующему ходу/раунду
        # В этом случае, слова обнулятся при advance_turn()
        room.advance_turn()
        return JsonResponse({'status': 'success', 'message': 'Words exhausted, next turn.', 'next_turn': True})

    new_word = random.choice(available_words)
    room.current_word = new_word
    room.save()

    return JsonResponse({'status': 'success', 'word': new_word})

# Функция для завершения раунда по таймеру
@require_POST
def end_round_timer(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    room = get_object_or_404(Room, id=room_id)
    # Только текущий объясняющий может запросить завершение раунда по таймеру
    # (но логика таймера в get_game_state должна быть основной)
    player = get_object_or_404(Player, room=room, telegram_id=telegram_user_info['id'])
    current_explainer = room.get_current_explainer()

    if current_explainer and current_explainer.id != player.id: # Если не текущий объясняющий
        # Разрешим это делать любому игроку, если таймер уже истек, чтобы синхронизировать
        if room.round_start_time and (timezone.now() - room.round_start_time).total_seconds() < settings.ROUND_DURATION_SECONDS:
            return JsonResponse({'status': 'error', 'message': 'Timer has not expired yet.'}, status=400)
    
    if room.status != 'playing':
        return JsonResponse({'status': 'error', 'message': 'Game is not in playing state.'}, status=400)

    room.advance_turn()
    room.save()

    return JsonResponse({'status': 'success', 'message': 'Round ended by timer.'})

@require_POST
def reset_game(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Telegram user ID is missing.'}, status=400)

    room = get_object_or_404(Room, id=room_id)
    # Только создатель комнаты может сбросить игру
    if room.creator_telegram_id != telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Only the room creator can reset the game.'}, status=403)
    
    # Сброс состояния комнаты
    room.status = 'waiting'
    room.current_round = 0
    room.current_team_index = 0
    room.current_explainer_index_in_team = 0
    room.current_word = None
    room.round_start_time = None
    room.words_in_round_guessed = []
    room.words_in_round_skipped = []
    room.save()

    # Сброс очков команд
    for team in room.team_set.all():
        team.score = 0
        team.save()
    
    return JsonResponse({'status': 'success', 'message': 'Game reset successfully.'})

