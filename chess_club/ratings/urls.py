from django.urls import path
from . import views

urlpatterns = [
    path('', views.PlayerListView.as_view(), name='home'),
    # Players
    path('players/', views.PlayerListView.as_view(), name='player_list'),
    path('players/add/', views.PlayerCreateView.as_view(), name='player_create'),
    # Matches and ranking
    path('matches/add/', views.MatchCreateView.as_view(), name='match_create'),
    path('players/ranking/', views.PlayerRankingView.as_view(), name='player_ranking'),
]