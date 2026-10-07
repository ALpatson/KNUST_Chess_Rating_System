import hmac

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from .forms import MatchForm, PlayerForm
from .models import Match, Player
from .pdf import table_pdf_response
from .services import MatchError, record_match, revert_match


def parse_date_safe(value):
    try:
        return parse_date(value) if value else None
    except ValueError:
        return None


def safe_next_url(request, fallback):
    """Return the POSTed `next` URL if it points back into this site."""
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return fallback


class PlayerListView(ListView):
    """Club rankings: every player ordered by rating, with search."""
    model = Player
    template_name = 'ratings/player_list.html'
    context_object_name = 'players'

    def get_queryset(self):
        queryset = Player.objects.all().order_by('-rating', 'name')
        self.search_query = self.request.GET.get('q', '').strip()

        if self.search_query:
            queryset = queryset.filter(name__icontains=self.search_query)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = getattr(self, 'search_query', '')
        # Overall rank, so a filtered search still shows each player's true position.
        ordered_ids = Player.objects.order_by('-rating', 'name').values_list('pk', flat=True)
        rank_by_id = {pk: idx for idx, pk in enumerate(ordered_ids, 1)}
        for player in context['players']:
            player.rank = rank_by_id.get(player.pk)
        context['total_players'] = len(rank_by_id)
        return context


class PlayerSearchSuggestionsView(View):
    def get(self, request):
        query = request.GET.get('q', '').strip()
        if not query:
            return JsonResponse({'results': []})

        suggestions = list(
            Player.objects.filter(name__icontains=query)
            .order_by('name')
            .values('id', 'name', 'rating')[:8]
        )
        return JsonResponse({'results': suggestions})


class PlayerCreateView(CreateView):
    model = Player
    form_class = PlayerForm
    template_name = 'ratings/player_form.html'
    success_url = reverse_lazy('player_list')

    def form_valid(self, form):
        form.instance.peak_rating = form.instance.rating
        messages.success(self.request, f'{form.instance.name} was added.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add New Player'
        context['submit_text'] = 'Add Player'
        return context


class PlayerDetailView(DetailView):
    model = Player
    template_name = 'ratings/player_detail.html'
    context_object_name = 'player'
    recent_limit = 30

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        player = self.object

        matches = list(
            Match.objects.filter(Q(player_white=player) | Q(player_black=player), is_reverted=False)
            .select_related('player_white', 'player_black', 'pairing__round__tournament')
            .order_by('created_at')
        )

        games = []
        for match in matches:
            is_white = match.player_white_id == player.pk
            if match.result == 'D':
                outcome = 'D'
            elif (match.result == 'W') == is_white:
                outcome = 'W'
            else:
                outcome = 'L'
            pairing = getattr(match, 'pairing', None)
            games.append({
                'match': match,
                'color': 'White' if is_white else 'Black',
                'opponent': match.player_black if is_white else match.player_white,
                'opponent_rating': match.black_rating_before if is_white else match.white_rating_before,
                'outcome': outcome,
                'change': match.white_rating_change if is_white else match.black_rating_change,
                'rating_after': match.white_rating_after if is_white else match.black_rating_after,
                'rating_before': match.white_rating_before if is_white else match.black_rating_before,
                'tournament': pairing.round.tournament if pairing else None,
            })

        chart = []
        if games:
            first = games[0]
            chart.append({'label': 'Start', 'rating': first['rating_before']})
            for game in games:
                chart.append({
                    'label': timezone.localtime(game['match'].created_at).strftime('%b %d'),
                    'rating': game['rating_after'],
                })

        context['games'] = list(reversed(games))[:self.recent_limit]
        context['total_games_listed'] = len(games)
        context['record'] = {
            'W': sum(g['outcome'] == 'W' for g in games),
            'D': sum(g['outcome'] == 'D' for g in games),
            'L': sum(g['outcome'] == 'L' for g in games),
        }
        context['chart_data'] = chart
        rank_ids = list(Player.objects.order_by('-rating', 'name').values_list('pk', flat=True))
        context['rank'] = rank_ids.index(player.pk) + 1
        context['tournaments'] = player.tournaments.order_by('-start_date')[:10]
        return context


class PlayerUpdateView(UpdateView):
    model = Player
    form_class = PlayerForm
    template_name = 'ratings/player_form.html'

    def get_success_url(self):
        return reverse('player_detail', args=[self.object.pk])

    def form_valid(self, form):
        if form.instance.rating > form.instance.peak_rating:
            form.instance.peak_rating = form.instance.rating
        messages.success(self.request, 'Player updated.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object.name}'
        context['submit_text'] = 'Save Changes'
        return context


class PlayerDeleteView(DeleteView):
    model = Player
    template_name = 'ratings/player_confirm_delete.html'
    success_url = reverse_lazy('player_list')
    context_object_name = 'player'

    def form_valid(self, form):
        name = self.object.name
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f'{name} has played in a tournament, so they can\'t be deleted. Delete the tournament first.',
            )
            return redirect('player_detail', pk=self.object.pk)
        messages.success(self.request, f'{name} was deleted.')
        return response


class MatchCreateView(CreateView):
    model = Match
    form_class = MatchForm
    template_name = 'ratings/match_form.html'
    success_url = reverse_lazy('match_create')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        history_player_query = self.request.GET.get('history_player', '').strip()
        recent_matches = Match.objects.select_related('player_white', 'player_black')

        if history_player_query:
            recent_matches = recent_matches.filter(
                Q(player_white__name__icontains=history_player_query)
                | Q(player_black__name__icontains=history_player_query)
            )[:50]
        else:
            recent_matches = recent_matches[:12]

        context['recent_matches'] = recent_matches
        context['history_player_query'] = history_player_query
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = record_match(
                    form.cleaned_data['player_white'].pk,
                    form.cleaned_data['player_black'].pk,
                    form.cleaned_data['result'],
                )
        except MatchError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        messages.success(self.request, 'Match recorded. You can revert this result within 30 days if needed.')
        return redirect(self.get_success_url())


class MatchRevertView(View):
    def post(self, request, pk):
        history_player_query = request.POST.get('history_player', '').strip()
        fallback = reverse('match_create')
        if history_player_query:
            fallback = f"{fallback}?{urlencode({'history_player': history_player_query})}"
        next_url = safe_next_url(request, fallback)

        get_object_or_404(Match, pk=pk)
        try:
            revert_match(pk)
        except MatchError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                'Match reverted successfully. Player ratings, peak ratings, and games played were restored.',
            )
        return redirect(next_url)


class MatchHistoryView(ListView):
    model = Match
    template_name = 'ratings/match_history.html'
    context_object_name = 'matches'
    paginate_by = 25

    def get_queryset(self):
        queryset = Match.objects.select_related('player_white', 'player_black')

        self.player_id = self.request.GET.get('player', '').strip()
        self.date_from = self.request.GET.get('date_from', '').strip()
        self.date_to = self.request.GET.get('date_to', '').strip()

        # Ignore malformed filters instead of crashing with a server error.
        if not self.player_id.isdigit():
            self.player_id = ''
        if not parse_date_safe(self.date_from):
            self.date_from = ''
        if not parse_date_safe(self.date_to):
            self.date_to = ''

        if self.player_id:
            queryset = queryset.filter(
                Q(player_white_id=self.player_id) | Q(player_black_id=self.player_id)
            )

        if self.date_from:
            queryset = queryset.filter(created_at__date__gte=self.date_from)

        if self.date_to:
            queryset = queryset.filter(created_at__date__lte=self.date_to)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['players'] = Player.objects.order_by('name')
        context['selected_player'] = self.player_id
        context['date_from'] = self.date_from
        context['date_to'] = self.date_to
        context['query_string'] = self._query_string_without_page()
        return context

    def _query_string_without_page(self):
        params = self.request.GET.copy()
        params.pop('page', None)
        encoded = params.urlencode()
        return f'&{encoded}' if encoded else ''


class PlayerRankingPDFView(View):
    def get(self, request):
        players = Player.objects.all().order_by('-rating', 'name')
        rows = [
            [str(idx), player.name, str(player.rating), str(player.peak_rating), str(player.games_played)]
            for idx, player in enumerate(players, 1)
        ]
        return table_pdf_response(
            filename=f'KNUST_Rankings_{timezone.localdate().strftime("%Y%m%d")}.pdf',
            title='KNUST CHESS CLUB RANKINGS',
            subtitle=f'{len(rows)} rated players',
            header=['Rank', 'Player', 'Rating', 'Peak', 'Games'],
            rows=rows,
            col_widths=[0.7 * 72, 3.0 * 72, 1.0 * 72, 1.0 * 72, 0.9 * 72],
        )


class PasscodeView(View):
    template_name = 'ratings/passcode.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        code = request.POST.get('passcode', '')
        expected = getattr(settings, 'PASSCODE', '')
        if code and expected and hmac.compare_digest(code.encode(), expected.encode()):
            request.session['access_granted'] = True
            # store grant time (epoch seconds) so middleware can enforce expiry
            request.session['access_granted_at'] = timezone.now().timestamp()
            return redirect(reverse('home'))
        return render(request, self.template_name, {'error': 'Incorrect passcode'})


def logout_view(request):
    """Clear passcode session keys, log out any authenticated user, and redirect to passcode."""
    request.session.pop('access_granted', None)
    request.session.pop('access_granted_at', None)
    logout(request)
    return redirect(reverse('passcode'))
