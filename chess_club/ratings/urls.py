from django.urls import path
from . import views

urlpatterns = [
    path('', views.PlayerListView.as_view(), name='home'),
    # Players
    path('players/', views.PlayerListView.as_view(), name='player_list'),
    path('players/suggestions/', views.PlayerSearchSuggestionsView.as_view(), name='player_search_suggestions'),
    path('players/add/', views.PlayerCreateView.as_view(), name='player_create'),
    path('players/<int:pk>/', views.PlayerDetailView.as_view(), name='player_detail'),
    path('players/<int:pk>/edit/', views.PlayerUpdateView.as_view(), name='player_update'),
    path('players/<int:pk>/delete/', views.PlayerDeleteView.as_view(), name='player_delete'),
    # Matches and ranking
    path('matches/add/', views.MatchCreateView.as_view(), name='match_create'),
    path('players/ranking/', views.PlayerRankingView.as_view(), name='player_ranking'),
    path('players/ranking/pdf/', views.PlayerRankingPDFView.as_view(), name='player_ranking_pdf'),
    path('passcode/', views.PasscodeView.as_view(), name='passcode'),
    path('logout/', views.logout_view, name='logout'),
]