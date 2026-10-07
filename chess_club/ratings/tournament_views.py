from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from .forms import TournamentForm
from .models import Pairing, Round, Tournament
from .pdf import table_pdf_response
from .services import MatchError, record_match, revert_match
from . import swiss


def tournament_pairings(tournament):
    return Pairing.objects.filter(round__tournament=tournament)


def tournament_standings(tournament):
    return swiss.standings(tournament.players.all(), tournament_pairings(tournament))


def format_points(value):
    return f'{value:g}'


class TournamentListView(ListView):
    model = Tournament
    template_name = 'ratings/tournament_list.html'
    context_object_name = 'tournaments'

    def get_queryset(self):
        return Tournament.objects.prefetch_related('players', 'rounds')


class TournamentCreateView(CreateView):
    model = Tournament
    form_class = TournamentForm
    template_name = 'ratings/tournament_form.html'

    def get_initial(self):
        return {'total_rounds': 5}

    def get_success_url(self):
        return reverse('tournament_detail', args=[self.object.pk])

    def form_valid(self, form):
        messages.success(self.request, 'Tournament created. Check the players, then start round 1.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'New Tournament'
        context['submit_text'] = 'Create Tournament'
        return context


class TournamentUpdateView(UpdateView):
    model = Tournament
    form_class = TournamentForm
    template_name = 'ratings/tournament_form.html'

    def dispatch(self, request, *args, **kwargs):
        tournament = self.get_object()
        if tournament.status != Tournament.DRAFT:
            messages.error(request, 'Players and rounds can only be changed before the tournament starts.')
            return redirect('tournament_detail', pk=tournament.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('tournament_detail', args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object.name}'
        context['submit_text'] = 'Save Changes'
        return context


class TournamentDetailView(DetailView):
    model = Tournament
    template_name = 'ratings/tournament_detail.html'
    context_object_name = 'tournament'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tournament = self.object

        rounds = list(
            tournament.rounds.prefetch_related('pairings__player_white', 'pairings__player_black')
        )
        current = rounds[-1] if rounds else None
        all_pairings = [p for r in rounds for p in r.pairings.all()]
        current_complete = current is not None and all(p.result for p in current.pairings.all())

        context['rounds'] = rounds
        context['past_rounds'] = list(reversed(rounds[:-1]))
        context['current_round'] = current
        context['current_complete'] = current_complete
        context['incomplete_count'] = sum(1 for p in all_pairings if not p.result)
        context['standings'] = swiss.standings(tournament.players.all(), all_pairings)
        context['is_last_round'] = current is not None and current.number >= tournament.total_rounds
        context['has_results'] = any(p.match_id for p in all_pairings)
        context['players'] = tournament.players.order_by('-rating', 'name')
        return context


class TournamentPairNextRoundView(View):
    """Start the tournament (round 1) or pair the next round."""

    def post(self, request, pk):
        with transaction.atomic():
            tournament = get_object_or_404(Tournament.objects.select_for_update(), pk=pk)

            if tournament.status == Tournament.FINISHED:
                messages.error(request, 'This tournament has already finished.')
                return redirect('tournament_detail', pk=pk)

            current = tournament.current_round
            if current is not None and not current.is_complete:
                messages.error(request, f'Enter all results for round {current.number} first.')
                return redirect('tournament_detail', pk=pk)
            if tournament_pairings(tournament).filter(result='').exists():
                messages.error(request, 'Some earlier boards are missing results. Enter them first.')
                return redirect('tournament_detail', pk=pk)

            next_number = (current.number + 1) if current else 1
            if next_number > tournament.total_rounds:
                messages.error(request, 'All rounds have been played. Finish the tournament instead.')
                return redirect('tournament_detail', pk=pk)

            entries = swiss.build_entries(tournament.players.all(), tournament_pairings(tournament))
            try:
                pairs = swiss.next_round(entries, next_number - 1, tournament.is_round_robin)
            except swiss.PairingError as exc:
                messages.error(request, str(exc))
                return redirect('tournament_detail', pk=pk)

            round_obj = Round.objects.create(tournament=tournament, number=next_number)
            Pairing.objects.bulk_create([
                Pairing(
                    round=round_obj,
                    board=board,
                    player_white_id=white_id,
                    player_black_id=black_id,
                    # A bye is an automatic win for the player who gets it.
                    result='W' if black_id is None else '',
                )
                for board, (white_id, black_id) in enumerate(pairs, 1)
            ])

            if tournament.status == Tournament.DRAFT:
                tournament.status = Tournament.ACTIVE
                tournament.save(update_fields=['status'])

        messages.success(request, f'Round {next_number} has been paired.')
        return redirect('tournament_detail', pk=pk)


class PairingResultView(View):
    """Enter a result for one board; this records a rated match."""

    def post(self, request, pk, pairing_pk):
        result = request.POST.get('result', '')
        if result not in ('W', 'B', 'D'):
            messages.error(request, 'Choose a valid result.')
            return redirect('tournament_detail', pk=pk)

        try:
            with transaction.atomic():
                pairing = get_object_or_404(
                    Pairing.objects.select_for_update().select_related('round__tournament'),
                    pk=pairing_pk, round__tournament_id=pk,
                )
                if pairing.round.tournament.status != Tournament.ACTIVE:
                    raise MatchError('Results can only be entered while the tournament is in progress.')
                if pairing.is_bye:
                    raise MatchError('A bye does not need a result.')
                if pairing.result:
                    raise MatchError('This board already has a result. Undo it first to change it.')

                match = record_match(pairing.player_white_id, pairing.player_black_id, result)
                pairing.result = result
                pairing.match = match
                pairing.save(update_fields=['result', 'match'])
        except MatchError as exc:
            messages.error(request, str(exc))
        return redirect(reverse('tournament_detail', args=[pk]) + '#current-round')


class PairingUndoView(View):
    """Undo a board's result by reverting its rated match."""

    def post(self, request, pk, pairing_pk):
        pairing = get_object_or_404(
            Pairing.objects.select_related('round__tournament'), pk=pairing_pk, round__tournament_id=pk,
        )
        if pairing.round.tournament.status != Tournament.ACTIVE or not pairing.match_id:
            messages.error(request, 'This result cannot be undone.')
            return redirect('tournament_detail', pk=pk)

        try:
            revert_match(pairing.match_id)
        except MatchError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Result on board {pairing.board} was undone and ratings restored.')
        return redirect(reverse('tournament_detail', args=[pk]) + '#current-round')


class TournamentFinishView(View):
    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        if tournament.status != Tournament.ACTIVE:
            messages.error(request, 'Only a tournament in progress can be finished.')
        elif tournament_pairings(tournament).filter(result='').exists():
            messages.error(request, 'Enter all results before finishing the tournament.')
        else:
            tournament.status = Tournament.FINISHED
            tournament.save(update_fields=['status'])
            winner = tournament_standings(tournament)[0]
            messages.success(request, f'Tournament finished. Congratulations to {winner.name}!')
        return redirect('tournament_detail', pk=pk)


class TournamentDeleteView(DeleteView):
    model = Tournament
    template_name = 'ratings/tournament_confirm_delete.html'
    success_url = reverse_lazy('tournament_list')
    context_object_name = 'tournament'

    def dispatch(self, request, *args, **kwargs):
        # Once rated games exist, keep the tournament as the record of where they came from.
        tournament = self.get_object()
        if tournament_pairings(tournament).filter(match__isnull=False).exists():
            messages.error(request, 'This tournament has rated games, so it can\'t be deleted. Undo its results first.')
            return redirect('tournament_detail', pk=tournament.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, f'{self.object.name} was deleted.')
        return super().form_valid(form)


class TournamentStandingsPDFView(View):
    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        rows = [
            [
                str(e.rank), e.name, str(e.rating), format_points(e.points),
                format_points(e.buchholz), format_points(e.sonneborn_berger), f'{e.wins}/{e.draws}/{e.losses}',
            ]
            for e in tournament_standings(tournament)
        ]
        played = tournament.rounds.count()
        return table_pdf_response(
            filename=f'{slugify(tournament.name) or "tournament"}-standings.pdf',
            title=tournament.name.upper(),
            subtitle=f'Standings after round {played} of {tournament.total_rounds}',
            header=['#', 'Player', 'Rating', 'Pts', 'Buch.', 'S-B', 'W/D/L'],
            rows=rows,
            col_widths=[0.5 * 72, 2.6 * 72, 0.8 * 72, 0.6 * 72, 0.7 * 72, 0.7 * 72, 0.9 * 72],
        )


class TournamentRoundPDFView(View):
    def get(self, request, pk, number):
        tournament = get_object_or_404(Tournament, pk=pk)
        round_obj = get_object_or_404(Round, tournament=tournament, number=number)
        result_text = {'W': '1 - 0', 'B': '0 - 1', 'D': '½ - ½', '': ''}
        rows = []
        for p in round_obj.pairings.select_related('player_white', 'player_black'):
            if p.is_bye:
                rows.append([str(p.board), f'{p.player_white.name} ({p.player_white.rating})', 'BYE', '1'])
            else:
                rows.append([
                    str(p.board),
                    f'{p.player_white.name} ({p.player_white.rating})',
                    f'{p.player_black.name} ({p.player_black.rating})',
                    result_text.get(p.result, ''),
                ])
        return table_pdf_response(
            filename=f'{slugify(tournament.name) or "tournament"}-round-{number}.pdf',
            title=tournament.name.upper(),
            subtitle=f'Round {number} of {tournament.total_rounds} pairings',
            header=['Board', 'White', 'Black', 'Result'],
            rows=rows,
            col_widths=[0.7 * 72, 2.7 * 72, 2.7 * 72, 0.9 * 72],
            align_left_cols=(1, 2),
        )
