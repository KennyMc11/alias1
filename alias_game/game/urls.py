# game/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('create-room/', views.create_room, name='create_room'),
    path('join-room/', views.join_room, name='join_room'),
    path('update-room-settings/', views.update_room_settings, name='update_room_settings'),
    path('join-team/', views.join_team, name='join_team'),
    path('update-team-name/', views.update_team_name, name='update_team_name'),
    path('start-game/', views.start_game, name='start_game'),
    path('room/<str:room_id>/', views.room_page, name='room_page'),
    path('game/<str:room_id>/', views.game_page, name='game_page'),
    path('api/room/<str:room_id>/state/', views.get_room_state, name='get_room_state'),
    path('api/start-explaining/', views.start_explaining, name='start_explaining'),
    path('api/word-guessed/', views.word_guessed, name='word_guessed'),
    path('api/word-skipped/', views.word_skipped, name='word_skipped'),
    path('api/end-turn/', views.end_turn, name='end_turn'),
]