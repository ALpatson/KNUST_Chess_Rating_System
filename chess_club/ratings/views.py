from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, View
from django.urls import reverse_lazy
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.utils.http import urlencode
from django.contrib.auth import logout
from .models import Player, Match
from .forms import PlayerForm, MatchForm
from .rating_calculator import RatingCalculator
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from django.shortcuts import render
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class PlayerListView(ListView):
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add New Player'
        context['submit_text'] = 'Add Player'
        return context


class PlayerDetailView(DetailView):
    model = Player
    template_name = 'ratings/player_detail.html'
    context_object_name = 'player'


class PlayerUpdateView(UpdateView):
    model = Player
    form_class = PlayerForm
    template_name = 'ratings/player_form.html'
    success_url = reverse_lazy('player_list')

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


class MatchCreateView(CreateView):
    model = Match
    form_class = MatchForm
    template_name = 'ratings/match_form.html'
    success_url = reverse_lazy('match_create')

    def dispatch(self, request, *args, **kwargs):
        Match.cleanup_expired_records()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        history_player_query = self.request.GET.get('history_player', '').strip()
        recent_matches = Match.objects.select_related('player_white', 'player_black')

        if history_player_query:
            recent_matches = recent_matches.filter(
                Q(player_white__name__icontains=history_player_query)
                | Q(player_black__name__icontains=history_player_query)
            )
        else:
            recent_matches = recent_matches[:12]

        context['recent_matches'] = recent_matches
        context['history_player_query'] = history_player_query
        return context

    def form_valid(self, form):
        match = form.save(commit=False)

        with transaction.atomic():
            white = Player.objects.select_for_update().get(pk=match.player_white.pk)
            black = Player.objects.select_for_update().get(pk=match.player_black.pk)

            match.player_white = white
            match.player_black = black

            # snapshot stats before this match
            match.white_rating_before = white.rating
            match.black_rating_before = black.rating
            match.white_peak_before = white.peak_rating
            match.black_peak_before = black.peak_rating
            match.white_games_before = white.games_played or 0
            match.black_games_before = black.games_played or 0

            # calculate rating changes
            w_change, b_change = RatingCalculator.process_match(white, black, match.result)
            match.white_rating_change = w_change
            match.black_rating_change = b_change

            # apply player updates
            white.rating = white.rating + w_change
            black.rating = black.rating + b_change
            white.games_played = (white.games_played or 0) + 1
            black.games_played = (black.games_played or 0) + 1

            if white.rating > white.peak_rating:
                white.peak_rating = white.rating
            if black.rating > black.peak_rating:
                black.peak_rating = black.rating

            # snapshot stats after this match
            match.white_rating_after = white.rating
            match.black_rating_after = black.rating
            match.white_peak_after = white.peak_rating
            match.black_peak_after = black.peak_rating
            match.white_games_after = white.games_played
            match.black_games_after = black.games_played

            white.save(update_fields=['rating', 'peak_rating', 'games_played'])
            black.save(update_fields=['rating', 'peak_rating', 'games_played'])
            match.save()

        messages.success(self.request, 'Match recorded. You can revert this result within 30 days if needed.')
        self.object = match
        return redirect(self.get_success_url())


class MatchRevertView(View):
    def post(self, request, pk):
        Match.cleanup_expired_records()
        history_player_query = request.POST.get('history_player', '').strip()

        with transaction.atomic():
            match = get_object_or_404(
                Match.objects.select_related('player_white', 'player_black').select_for_update(),
                pk=pk,
            )

            if match.is_reverted:
                messages.info(request, 'This match has already been reverted.')
                url = reverse('match_create')
                if history_player_query:
                    url = f"{url}?{urlencode({'history_player': history_player_query})}"
                return redirect(url)

            if match.is_expired:
                messages.error(request, 'This match is older than 30 days and can no longer be reverted.')
                url = reverse('match_create')
                if history_player_query:
                    url = f"{url}?{urlencode({'history_player': history_player_query})}"
                return redirect(url)

            white_has_later_matches = Match.objects.filter(
                Q(player_white=match.player_white) | Q(player_black=match.player_white),
                is_reverted=False,
                created_at__gt=match.created_at,
            ).exists()

            black_has_later_matches = Match.objects.filter(
                Q(player_white=match.player_black) | Q(player_black=match.player_black),
                is_reverted=False,
                created_at__gt=match.created_at,
            ).exists()

            if white_has_later_matches or black_has_later_matches:
                messages.error(
                    request,
                    'Cannot revert this match because one of the players has newer recorded matches. Revert the newest matches first.',
                )
                url = reverse('match_create')
                if history_player_query:
                    url = f"{url}?{urlencode({'history_player': history_player_query})}"
                return redirect(url)

            white = match.player_white
            black = match.player_black

            # Restore the exact snapshots from before this match.
            white.rating = match.white_rating_before
            white.peak_rating = match.white_peak_before
            white.games_played = max(match.white_games_before, 0)

            black.rating = match.black_rating_before
            black.peak_rating = match.black_peak_before
            black.games_played = max(match.black_games_before, 0)

            white.save(update_fields=['rating', 'peak_rating', 'games_played'])
            black.save(update_fields=['rating', 'peak_rating', 'games_played'])

            match.is_reverted = True
            match.reverted_at = timezone.now()
            match.save(update_fields=['is_reverted', 'reverted_at'])

        messages.success(request, 'Match reverted successfully. Player ratings, peak ratings, and games played were restored.')
        url = reverse('match_create')
        if history_player_query:
            url = f"{url}?{urlencode({'history_player': history_player_query})}"
        return redirect(url)


class MatchHistoryView(ListView):
    model = Match
    template_name = 'ratings/match_history.html'
    context_object_name = 'matches'
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        Match.cleanup_expired_records()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Match.objects.select_related('player_white', 'player_black')

        self.player_id = self.request.GET.get('player', '').strip()
        self.date_from = self.request.GET.get('date_from', '').strip()
        self.date_to = self.request.GET.get('date_to', '').strip()

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


class PlayerRankingView(ListView):
    model = Player
    template_name = 'ratings/player_ranking.html'
    context_object_name = 'players'
    
    def get_queryset(self):
        return Player.objects.all().order_by('-rating')

    
class PlayerRankingPDFView(View):
    def get(self, request):
        # Get all players ordered by rating
        players = Player.objects.all().order_by('-rating')
        
        # Create PDF response
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="KNUST_Rankings_{timezone.now().strftime("%Y%m%d")}.pdf"'
        
        # Create PDF document
        doc = SimpleDocTemplate(response, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []
        
        # Title
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#b58863'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        title = Paragraph("KNUST CHESS CLUB RANKINGS", title_style)
        elements.append(title)
        
        # Date
        date_style = ParagraphStyle(
            'Date',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.grey,
            spaceAfter=20,
            alignment=TA_CENTER
        )
        date_text = Paragraph(f"Generated on {timezone.now().strftime('%B %d, %Y')}", date_style)
        elements.append(date_text)
        
        elements.append(Spacer(1, 0.2*inch))
        
        # Create table data
        table_data = [['Rank', 'Player Name', 'Current Rating', 'Peak Rating']]
        
        for idx, player in enumerate(players, 1):
            table_data.append([
                str(idx),
                player.name,
                str(player.rating),
                str(player.peak_rating)
            ])
        
        # Create table
        table = Table(table_data, colWidths=[0.8*inch, 2.5*inch, 1.3*inch, 1.3*inch])
        
        # Style the table
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#262421')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#f0d9b5')),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            
            # Data rows styling
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
            ('PADDING', (0, 1), (-1, -1), 10),
            
            # Alternate row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
            
            # Rank column styling
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor('#b58863')),
            ('FONTSIZE', (0, 1), (0, -1), 12),
            
            # Rating columns styling
            ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#4CAF50')),
            ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (3, 1), (3, -1), colors.black),
            ('FONTNAME', (3, 1), (3, -1), 'Helvetica-Bold'),
        ]))
        
        elements.append(table)
        
        # Build PDF
        doc.build(elements)
        return response


class PasscodeView(View):
    template_name = 'ratings/passcode.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        code = request.POST.get('passcode', '')
        if code and code == getattr(settings, 'PASSCODE', ''):
            request.session['access_granted'] = True
            # store grant time (epoch seconds) so middleware can enforce expiry
            request.session['access_granted_at'] = timezone.now().timestamp()
            # redirect to home
            return redirect(reverse('home'))
        # fall back with an error
        return render(request, self.template_name, {'error': 'Incorrect passcode'})


def logout_view(request):
    """Clear passcode session keys, log out any authenticated user, and redirect to passcode."""
    # remove the passcode session flags so the user must re-enter the passcode
    request.session.pop('access_granted', None)
    request.session.pop('access_granted_at', None)
    # also log out any django-authenticated user if present
    logout(request)
    return redirect(reverse('passcode'))