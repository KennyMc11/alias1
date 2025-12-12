# game/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('create/', views.create_room, name='create_room'),
    path('create/post/', views.create_room_post, name='create_room_post'),
    path('join/', views.join_room, name='join_room'),
    path('join/post/', views.join_room_post, name='join_room_post'),
    path('set_identity/', views.set_web_identity, name='set_web_identity'),
    path('room/<uuid:room_id>/', views.room_detail, name='room_detail'),
    
    # AJAX API для игры
    path('room/<uuid:room_id>/state/', views.get_game_state, name='get_game_state'),
    path('room/<uuid:room_id>/update_team_name/', views.update_team_name, name='update_team_name'),
    path('room/<uuid:room_id>/select_team/', views.select_team, name='select_team'),
    path('room/<uuid:room_id>/start_game/', views.start_game, name='start_game'),
    path('room/<uuid:room_id>/start_round/', views.start_round, name='start_round'),
    path('room/<uuid:room_id>/guessed/', views.handle_word_action, {'action': 'guessed'}, name='guess_word'),
    path('room/<uuid:room_id>/skip/', views.handle_word_action, {'action': 'skip'}, name='skip_word'),
    path('room/<uuid:room_id>/end_round_timer/', views.end_round_timer, name='end_round_timer'),
    path('room/<uuid:room_id>/reset_game/', views.reset_game, name='reset_game'),
]
