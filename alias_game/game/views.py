# game/views.py

import json
import uuid
import re
import urllib.parse
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.conf import settings
from django.db import transaction, DatabaseError
from django.views.decorators.csrf import csrf_exempt
import random
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

from .models import Room, Team, Player
from .words import WORDS

# --- Helper function for getting Telegram User Info ---
def get_telegram_user_info(request):
    """Попытаться извлечь информацию о пользователе Telegram или веб-пользователя из запроса."""
    user_id = None
    username = None
    
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
                logger.warning(f"Failed to decode cookie username: {cookie_username}")

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
        except Exception as e:
            logger.error(f"Error parsing JSON body: {e}")

    # 4) initData string
    if (not user_id or not username) and (request.POST.get('initData') or request.GET.get('initData')):
        init_data = request.POST.get('initData') or request.GET.get('initData')
        try:
            decoded = json.loads(init_data)
            user_data = decoded.get('user') if isinstance(decoded, dict) else None
            if user_data:
                user_id = user_id or user_data.get('id')
                username = username or user_data.get('username') or user_data.get('first_name')
        except Exception as e:
            logger.error(f"Error parsing initData: {e}")

    # Normalize types
    if user_id is not None:
        try:
            user_id = str(user_id)
        except Exception:
            user_id = None
            logger.error(f"Failed to convert user_id to string: {user_id}")

    if username is None and user_id is not None:
        username = f"Игрок_{user_id[-4:]}" if len(user_id) >= 4 else f"Игрок_{user_id}"

    return {'id': user_id, 'username': username}


def fetch_room_by_str(room_id_str):
    """Попытаться найти `Room` по строковому идентификатору."""
    if not room_id_str:
        return None

    room_id_str = str(room_id_str).strip()
    
    # Ищем по точному совпадению ID
    try:
        return Room.objects.filter(id=room_id_str).first()
    except (Room.DoesNotExist, ValueError):
        return None


# --- Основные страницы ---

@require_GET
def index(request):
    telegram_user_info = get_telegram_user_info(request)
    return render(request, 'game/index.html', {'telegram_user_info': telegram_user_info})


@require_GET
def create_room(request):
    telegram_user_info = get_telegram_user_info(request)
    return render(request, 'game/create_room.html', {'telegram_user_info': telegram_user_info})


@require_POST
def create_room_post(request):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)

    try:
        num_teams = int(request.POST.get('num_teams', 2))
        winning_score = int(request.POST.get('winning_score', 50))
        difficulty = request.POST.get('difficulty', 'medium')
        penalty_for_skip = request.POST.get('penalty_for_skip') == 'on'

        if not (2 <= num_teams <= 4):
            return JsonResponse({'status': 'error', 'message': 'Количество команд должно быть от 2 до 4.'}, status=400)
        if winning_score < 10 or winning_score > 1000:
            return JsonResponse({'status': 'error', 'message': 'Очки для победы должны быть от 10 до 1000.'}, status=400)
        if difficulty not in dict(Room.DIFFICULTY_CHOICES):
            return JsonResponse({'status': 'error', 'message': 'Недопустимый уровень сложности.'}, status=400)

        with transaction.atomic():
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
                Team.objects.create(room=room, name=f"Команда {i+1}", index=i)
            
            # Создатель комнаты автоматически присоединяется
            player = Player.objects.create(
                room=room,
                telegram_id=telegram_user_info['id'],
                telegram_username=telegram_user_info['username']
            )
            
            logger.info(f"Room {room.id} created by {telegram_user_info['username']}")

        return JsonResponse({'status': 'success', 'room_id': str(room.id)})
    
    except DatabaseError as e:
        logger.error(f"Database error creating room: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка базы данных при создании комнаты.'}, status=500)
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)


@require_GET
def join_room(request):
    telegram_user_info = get_telegram_user_info(request)
    return render(request, 'game/join_room.html', {'telegram_user_info': telegram_user_info})


@require_POST
def join_room_post(request):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)

    room_id = request.POST.get('room_id')
    if not room_id:
        return JsonResponse({'status': 'error', 'message': 'Не указан ID комнаты.'}, status=400)

    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    if room.status == 'finished':
        return JsonResponse({'status': 'error', 'message': 'Игра в этой комнате уже завершена.'}, status=400)
    
    if room.player_set.count() >= 20:  # Максимум 20 игроков в комнате
        return JsonResponse({'status': 'error', 'message': 'В комнате достигнут лимит игроков.'}, status=400)

    try:
        with transaction.atomic():
            player, created = Player.objects.get_or_create(
                room=room,
                telegram_id=telegram_user_info['id'],
                defaults={
                    'telegram_username': telegram_user_info['username']
                }
            )
            
            if not created:
                # Обновляем имя и активность существующего игрока
                player.telegram_username = telegram_user_info['username']
                player.touch()
                player.save()
            
            # Обновляем активность комнаты
            room.last_activity = timezone.now()
            room.save(update_fields=['last_activity'])
            
            logger.info(f"Player {telegram_user_info['username']} joined room {room.id}")

        return JsonResponse({'status': 'success', 'room_id': str(room.id)})
    except DatabaseError as e:
        logger.error(f"Database error joining room: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка базы данных при присоединении к комнате.'}, status=500)
    except Exception as e:
        logger.error(f"Error joining room: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)


@require_GET
def room_detail(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return redirect('index')

    room = fetch_room_by_str(room_id)
    if not room:
        return render(request, 'game/room_not_found.html', {'room_id': room_id})
    
    # Проверяем, что игрок находится в комнате
    try:
        player = Player.objects.get(room=room, telegram_id=telegram_user_info['id'])
        player.touch()  # Обновляем активность игрока
    except Player.DoesNotExist:
        # Если игрок не в комнате, перенаправляем на страницу присоединения
        return redirect(f'/join/?room_id={room_id}&tg_user_id={telegram_user_info["id"]}&tg_username={telegram_user_info["username"]}')

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
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)
    
    # Кэшируем состояние на 1 секунду
    cache_key = f'room_state_{room_id}_{telegram_user_info["id"]}'
    cached_state = cache.get(cache_key)
    
    if cached_state and not request.GET.get('force', False):
        # Проверяем, не изменилось ли состояние
        room = fetch_room_by_str(room_id)
        if room and room.last_activity and cached_state.get('last_activity'):
            if room.last_activity.isoformat() == cached_state['last_activity']:
                return JsonResponse(cached_state)

    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    try:
        player = Player.objects.get(room=room, telegram_id=telegram_user_info['id'])
        player.touch()  # Обновляем активность игрока
    except Player.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Вы не находитесь в этой комнате.'}, status=403)

    # Очищаем неактивных игроков (старше 2 часов)
    room.cleanup_inactive_players(hours=2)

    teams_data = []
    for team in room.team_set.all().order_by('index'):
        players_in_team = [{'id': p.id, 'telegram_username': p.telegram_username} 
                          for p in team.player_set.all().order_by('id')]
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
        # Отладочная информация
        logger.debug(f"Room {room.id}: elapsed={elapsed_time:.1f}s, remaining={time_remaining}s")

    game_finished = False
    winning_team_name = None
    if room.status == 'playing':
        for team in room.team_set.all():
            if team.score >= room.winning_score:
                with transaction.atomic():
                    room = Room.objects.select_for_update().get(id=room.id)
                    room.status = 'finished'
                    room.save()
                game_finished = True
                winning_team_name = team.name
                break
    elif room.status == 'finished':
        game_finished = True
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
        'players_in_room_count': room.player_set.count(),
        'server_time': timezone.now().isoformat(),# Для синхронизации времени
        'player_has_team': bool(player.team),  # True если у игрока есть команда
        'player_team_name': player.team.name if player.team else None
    }
    
    # Кэшируем результат
    cache.set(cache_key, response_data, timeout=1)
    
    return JsonResponse(response_data)


@require_POST
def update_team_name(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)
    
    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    # Только создатель комнаты может менять названия команд
    if room.creator_telegram_id != telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Только создатель комнаты может изменять названия команд.'}, status=403)

    team_id = request.POST.get('team_id')
    new_name = request.POST.get('new_name', '').strip()

    if not team_id:
        return JsonResponse({'status': 'error', 'message': 'Не указан ID команды.'}, status=400)
    
    if not new_name or len(new_name) < 2 or len(new_name) > 50:
        return JsonResponse({'status': 'error', 'message': 'Название команды должно быть от 2 до 50 символов.'}, status=400)

    try:
        with transaction.atomic():
            team = get_object_or_404(Team, room=room, id=team_id)
            team.name = new_name
            team.save()
            
            logger.info(f"Team {team_id} renamed to '{new_name}' in room {room.id}")
            
        return JsonResponse({'status': 'success', 'new_name': new_name})
    except Team.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Команда не найдена.'}, status=404)
    except DatabaseError as e:
        logger.error(f"Database error updating team name: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка базы данных при обновлении названия команды.'}, status=500)
    except Exception as e:
        logger.error(f"Error updating team name: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)


@require_POST
def select_team(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)

    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    try:
        player = Player.objects.get(room=room, telegram_id=telegram_user_info['id'])
    except Player.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Вы не находитесь в этой комнате.'}, status=403)

    if room.status != 'waiting':
        return JsonResponse({'status': 'error', 'message': 'Нельзя менять команду после начала игры.'}, status=400)

    team_id = request.POST.get('team_id')
    if not team_id:
        return JsonResponse({'status': 'error', 'message': 'Не указан ID команды.'}, status=400)

    try:
        with transaction.atomic():
            team = get_object_or_404(Team, room=room, id=team_id)
            player.team = team
            player.touch()
            player.save()
            
            logger.info(f"Player {telegram_user_info['username']} joined team '{team.name}' in room {room.id}")
            
        return JsonResponse({'status': 'success', 'team_name': team.name})
    except Team.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Команда не найдена.'}, status=404)
    except DatabaseError as e:
        logger.error(f"Database error selecting team: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка базы данных при выборе команды.'}, status=500)
    except Exception as e:
        logger.error(f"Error selecting team: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)


@require_POST
def set_web_identity(request):
    """Установить идентичность веб-пользователя."""
    username = request.POST.get('web_username', '').strip()
    next_url = request.POST.get('next') or request.POST.get('redirect_to') or request.META.get('HTTP_REFERER') or '/'

    if not username:
        return JsonResponse({'status': 'error', 'message': 'Имя пользователя не может быть пустым.'}, status=400)
    
    if len(username) < 2 or len(username) > 50:
        return JsonResponse({'status': 'error', 'message': 'Имя пользователя должно быть от 2 до 50 символов.'}, status=400)

    new_id = str(uuid.uuid4())
    response = redirect(next_url)
    
    # Сохраняем на 30 дней
    max_age = 60 * 60 * 24 * 30
    response.set_cookie('alias_web_user_id', new_id, max_age=max_age, httponly=True, samesite='Lax')
    
    try:
        cookie_username = urllib.parse.quote(username, safe='')
    except Exception:
        cookie_username = username
    
    response.set_cookie('alias_web_username', cookie_username, max_age=max_age, samesite='Lax')
    
    logger.info(f"Web identity set: {username} ({new_id})")
    return response


@require_POST
def start_game(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)

    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    # Только создатель может начать игру
    if room.creator_telegram_id != telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Только создатель комнаты может начать игру.'}, status=403)
    
    if room.status != 'waiting':
        return JsonResponse({'status': 'error', 'message': 'Игра уже началась или завершена.'}, status=400)
    
    # Проверка, что во всех командах есть хотя бы 1 игрок
    teams_with_players = sum(1 for team in room.team_set.all() if team.player_set.count() > 0)
    if teams_with_players < room.num_teams:
        return JsonResponse({'status': 'error', 'message': 'Во всех командах должен быть хотя бы один игрок.'}, status=400)
    
    # Проверка минимального количества игроков
    total_players = room.player_set.count()
    if total_players < 2:
        return JsonResponse({'status': 'error', 'message': 'Для начала игры нужно минимум 2 игрока.'}, status=400)
    
    players_without_team = room.player_set.filter(team__isnull=True)
    if players_without_team.exists():
        player_names = [p.telegram_username for p in players_without_team]
        return JsonResponse({
            'status': 'error', 
            'message': f'Некоторые игроки не выбрали команду: {", ".join(player_names)}'
        }, status=400)
        
    errors = []
    for player in room.player_set.all():
        error = validate_player_has_team(room, player)
        if error:
            errors.append(error)

    if errors:
        return JsonResponse({
            'status': 'error', 
            'message': 'Нельзя начать игру пока все игроки не выберут команду:\n' + '\n'.join(errors)
        }, status=400)

    try:
        with transaction.atomic():
            room = Room.objects.select_for_update().get(id=room.id)
            room.status = 'playing'
            room.current_round = 1
            room.current_team_index = 0
            room.current_explainer_index_in_team = 0
            room.save()
            
            logger.info(f"Game started in room {room.id}")
            
        return JsonResponse({'status': 'success'})
    except DatabaseError as e:
        logger.error(f"Database error starting game: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка базы данных при начале игры.'}, status=500)
    except Exception as e:
        logger.error(f"Error starting game: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)


@require_POST
def start_round(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)

    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    try:
        player = Player.objects.get(room=room, telegram_id=telegram_user_info['id'])
        player.touch()
    except Player.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Вы не находитесь в этой комнате.'}, status=403)

    current_explainer = room.get_current_explainer()
    if not current_explainer or current_explainer.id != player.id:
        return JsonResponse({'status': 'error', 'message': 'Сейчас не ваш ход объяснять.'}, status=403)

    if room.status != 'playing':
        return JsonResponse({'status': 'error', 'message': 'Игра не в активном состоянии.'}, status=400)

    # Если слово уже есть, значит раунд уже стартовал
    if room.current_word and room.round_start_time:
         return JsonResponse({'status': 'error', 'message': 'Раунд уже начался.'}, status=400)

    try:
        with transaction.atomic():
            room = Room.objects.select_for_update().get(id=room.id)
            
            # Выбираем случайное слово
            available_words = [w for w in WORDS[room.difficulty] 
                             if w not in room.words_in_round_guessed + room.words_in_round_skipped]
            
            if not available_words:
                # Если слова закончились, очищаем списки и берем из общего
                room.words_in_round_guessed = []
                room.words_in_round_skipped = []
                available_words = WORDS[room.difficulty]
            
            if not available_words:
                return JsonResponse({'status': 'error', 'message': 'Нет доступных слов для игры.'}, status=500)
            
            new_word = random.choice(available_words)
            room.current_word = new_word
            room.round_start_time = timezone.now()
            room.last_activity = timezone.now()
            room.save()
            
            logger.info(f"Round started in room {room.id}, word: {new_word}")
            
        return JsonResponse({'status': 'success', 'word': new_word})
    except DatabaseError as e:
        logger.error(f"Database error starting round: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка базы данных при начале раунда.'}, status=500)
    except Exception as e:
        logger.error(f"Error starting round: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)


@require_POST
def handle_word_action(request, room_id, action):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)

    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    try:
        player = Player.objects.get(room=room, telegram_id=telegram_user_info['id'])
        player.touch()
    except Player.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Вы не находитесь в этой комнате.'}, status=403)

    current_explainer = room.get_current_explainer()
    if not current_explainer or current_explainer.id != player.id:
        return JsonResponse({'status': 'error', 'message': 'Сейчас не ваш ход объяснять.'}, status=403)
    
    if room.status != 'playing' or not room.current_word:
        return JsonResponse({'status': 'error', 'message': 'Нет активного слова для обработки.'}, status=400)
    
    try:
        with transaction.atomic():
            room = Room.objects.select_for_update().get(id=room.id)
            current_team = room.get_current_team()
            
            if not current_team:
                return JsonResponse({'status': 'error', 'message': 'Текущая команда не найдена.'}, status=500)
            
            if action == 'guessed':
                current_team.update_score(1)
                room.words_in_round_guessed.append(room.current_word)
                logger.info(f"Word guessed: {room.current_word} in room {room.id}")
            elif action == 'skip':
                if room.penalty_for_skip:
                    current_team.update_score(-1)
                room.words_in_round_skipped.append(room.current_word)
                logger.info(f"Word skipped: {room.current_word} in room {room.id}")
            else:
                return JsonResponse({'status': 'error', 'message': 'Неизвестное действие.'}, status=400)
            
            room.current_word = None
            room.last_activity = timezone.now()
            room.save()
            
            # Проверка на победу
            if current_team.score >= room.winning_score:
                room.status = 'finished'
                room.save()
                return JsonResponse({
                    'status': 'success', 
                    'game_over': True, 
                    'winning_team': current_team.name,
                    'winning_score': current_team.score
                })
            
            # Выбираем новое слово
            available_words = [w for w in WORDS[room.difficulty] 
                             if w not in room.words_in_round_guessed + room.words_in_round_skipped]
            
            if not available_words:
                # Если слова закончились, переходим к следующему ходу
                room.advance_turn()
                return JsonResponse({'status': 'success', 'next_turn': True})
            
            new_word = random.choice(available_words)
            room.current_word = new_word
            room.save()
            
        return JsonResponse({'status': 'success', 'word': new_word})
    except DatabaseError as e:
        logger.error(f"Database error handling word action: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка базы данных при обработке слова.'}, status=500)
    except Exception as e:
        logger.error(f"Error handling word action: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)


@require_POST
def end_round_timer(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)

    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    # Проверяем, что игрок в комнате
    try:
        player = Player.objects.get(room=room, telegram_id=telegram_user_info['id'])
        player.touch()
    except Player.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Вы не находитесь в этой комнате.'}, status=403)

    if room.status != 'playing':
        return JsonResponse({'status': 'error', 'message': 'Игра не в активном состоянии.'}, status=400)

    # Проверяем, что это текущий объясняющий
    current_explainer = room.get_current_explainer()
    if not current_explainer or current_explainer.id != player.id:
        return JsonResponse({
            'status': 'error', 
            'message': 'Только текущий объясняющий может завершить раунд.'
        }, status=403)
    
    # Проверяем, что таймер действительно истек
    if room.round_start_time:
        elapsed_time = (timezone.now() - room.round_start_time).total_seconds()
        # Разрешаем завершить если осталось меньше 5 секунд или уже истекло
        if elapsed_time < settings.ROUND_DURATION_SECONDS - 5:
            return JsonResponse({
                'status': 'error', 
                'message': f'Таймер еще не истек. Осталось: {int(settings.ROUND_DURATION_SECONDS - elapsed_time)}с'
            }, status=400)
    
    try:
        with transaction.atomic():
            # Блокируем комнату для атомарной операции
            room = Room.objects.select_for_update().get(id=room.id)
            
            # Дополнительная проверка на случай race condition
            if room.status != 'playing':
                return JsonResponse({'status': 'error', 'message': 'Игра уже завершена.'}, status=400)
                
            # Завершаем раунд
            room.advance_turn()
            room.last_activity = timezone.now()
            room.save()
            
            logger.info(f"Round ended by timer in room {room.id} by {telegram_user_info['username']}")
            
        return JsonResponse({'status': 'success', 'message': 'Раунд завершен по таймеру.'})
    except DatabaseError as e:
        logger.error(f"Database error ending round: {e}")
        return JsonResponse({
            'status': 'error', 
            'message': 'Ошибка базы данных. Попробуйте еще раз.'
        }, status=500)
    except Exception as e:
        logger.error(f"Error ending round: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка: {str(e)}'}, status=500)


@require_POST
def reset_game(request, room_id):
    telegram_user_info = get_telegram_user_info(request)
    if not telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Необходимо указать идентификатор пользователя.'}, status=400)

    room = fetch_room_by_str(room_id)
    if not room:
        return JsonResponse({'status': 'error', 'message': 'Комната не найдена.'}, status=404)
    
    # Только создатель комнаты может сбросить игру
    if room.creator_telegram_id != telegram_user_info['id']:
        return JsonResponse({'status': 'error', 'message': 'Только создатель комнаты может сбросить игру.'}, status=403)
    
    try:
        with transaction.atomic():
            room = Room.objects.select_for_update().get(id=room.id)
            
            # Сброс состояния комнаты
            room.status = 'waiting'
            room.current_round = 0
            room.current_team_index = 0
            room.current_explainer_index_in_team = 0
            room.current_word = None
            room.round_start_time = None
            room.words_in_round_guessed = []
            room.words_in_round_skipped = []
            room.last_activity = timezone.now()
            room.save()
            
            # Сброс очков команд
            for team in room.team_set.all():
                team.score = 0
                team.save()
            
            logger.info(f"Game reset in room {room.id}")
            
        return JsonResponse({'status': 'success', 'message': 'Игра успешно сброшена.'})
    except DatabaseError as e:
        logger.error(f"Database error resetting game: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка базы данных при сбросе игры.'}, status=500)
    except Exception as e:
        logger.error(f"Error resetting game: {e}")
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)
    
def validate_player_has_team(room, player):
    """Проверяет, что у игрока есть команда, и возвращает сообщение об ошибке если нет."""
    if not player.team:
        return f"Игрок {player.telegram_username} не выбрал команду"
    return None