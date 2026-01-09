from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from .models import Player, Match
from .forms import PlayerForm, MatchForm
from .rating_calculator import RatingCalculator


class PlayerListView(ListView):
    model = Player
    template_name = 'ratings/player_list.html'
    context_object_name = 'players'


class PlayerCreateView(CreateView):
    model = Player
    form_class = PlayerForm
    template_name = 'ratings/player_form.html'
    success_url = reverse_lazy('player_list')


class MatchCreateView(CreateView):
    model = Match
    form_class = MatchForm
    template_name = 'ratings/match_form.html'
    success_url = reverse_lazy('player_ranking')

    def form_valid(self, form):
        match = form.save(commit=False)

        # snapshot ratings before
        match.white_rating_before = match.player_white.rating
        match.black_rating_before = match.player_black.rating

        # calculate rating changes
        w_change, b_change = RatingCalculator.process_match(
            match.player_white, match.player_black, match.result
        )

        match.white_rating_change = w_change
        match.black_rating_change = b_change


        # apply changes to players and update peak ratings
        match.player_white.rating = match.player_white.rating + w_change
        if match.player_white.rating > match.player_white.peak_rating:
            match.player_white.peak_rating = match.player_white.rating

        match.player_black.rating = match.player_black.rating + b_change
        if match.player_black.rating > match.player_black.peak_rating:
            match.player_black.peak_rating = match.player_black.rating

        # increment games played
        match.player_white.games_played = (match.player_white.games_played or 0) + 1
        match.player_black.games_played = (match.player_black.games_played or 0) + 1

        # after ratings
        match.white_rating_after = match.player_white.rating
        match.black_rating_after = match.player_black.rating

        # save players and match
        match.player_white.save()
        match.player_black.save()
        match.save()

        return super().form_valid(form)


class PlayerRankingView(ListView):
    model = Player
    template_name = 'ratings/player_ranking.html'
    context_object_name = 'players'
    queryset = Player.objects.all().order_by('-rating')