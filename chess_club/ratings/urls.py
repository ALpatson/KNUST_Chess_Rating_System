from django.urls import path
from django.views.generic import RedirectView

from . import tournament_views, views

urlpatterns = [
    path('', views.PlayerListView.as_view(), name='home'),
    # Players (the player list is the club rankings)
    path('players/', views.PlayerListView.as_view(), name='player_list'),
    path('players/suggestions/', views.PlayerSearchSuggestionsView.as_view(), name='player_search_suggestions'),
    path('players/add/', views.PlayerCreateView.as_view(), name='player_create'),
    path('players/<int:pk>/', views.PlayerDetailView.as_view(), name='player_detail'),
    path('players/<int:pk>/edit/', views.PlayerUpdateView.as_view(), name='player_update'),
    path('players/<int:pk>/delete/', views.PlayerDeleteView.as_view(), name='player_delete'),
    path('players/ranking/', RedirectView.as_view(pattern_name='player_list', permanent=False), name='player_ranking'),
    path('players/ranking/pdf/', views.PlayerRankingPDFView.as_view(), name='player_ranking_pdf'),
    # Matches
    path('matches/add/', views.MatchCreateView.as_view(), name='match_create'),
    path('matches/history/', views.MatchHistoryView.as_view(), name='match_history'),
    path('matches/<int:pk>/revert/', views.MatchRevertView.as_view(), name='match_revert'),
    # Tournaments
    path('tournaments/', tournament_views.TournamentListView.as_view(), name='tournament_list'),
    path('tournaments/new/', tournament_views.TournamentCreateView.as_view(), name='tournament_create'),
    path('tournaments/<int:pk>/', tournament_views.TournamentDetailView.as_view(), name='tournament_detail'),
    path('tournaments/<int:pk>/edit/', tournament_views.TournamentUpdateView.as_view(), name='tournament_update'),
    path('tournaments/<int:pk>/delete/', tournament_views.TournamentDeleteView.as_view(), name='tournament_delete'),
    path('tournaments/<int:pk>/pair/', tournament_views.TournamentPairNextRoundView.as_view(), name='tournament_pair'),
    path('tournaments/<int:pk>/finish/', tournament_views.TournamentFinishView.as_view(), name='tournament_finish'),
    path('tournaments/<int:pk>/boards/<int:pairing_pk>/result/', tournament_views.PairingResultView.as_view(), name='pairing_result'),
    path('tournaments/<int:pk>/boards/<int:pairing_pk>/undo/', tournament_views.PairingUndoView.as_view(), name='pairing_undo'),
    path('tournaments/<int:pk>/standings.pdf', tournament_views.TournamentStandingsPDFView.as_view(), name='tournament_standings_pdf'),
    path('tournaments/<int:pk>/rounds/<int:number>.pdf', tournament_views.TournamentRoundPDFView.as_view(), name='tournament_round_pdf'),
    # Access
    path('passcode/', views.PasscodeView.as_view(), name='passcode'),
    path('logout/', views.logout_view, name='logout'),
]
