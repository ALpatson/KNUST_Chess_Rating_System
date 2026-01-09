from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, CreateView, View
from django.urls import reverse_lazy
from django.http import HttpResponse
from django.utils import timezone
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