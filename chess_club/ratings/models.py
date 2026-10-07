from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from datetime import timedelta

from .swiss import uses_round_robin


class Player(models.Model):
    name = models.CharField(max_length=100)
    rating = models.IntegerField(default=1500, validators=[MinValueValidator(0)])
    birth_date = models.DateField(null=True, blank=True)
    peak_rating = models.IntegerField(default=1500)
    games_played = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.rating})"

    class Meta:
        ordering = ['-rating']


class Match(models.Model):
    RESULT_CHOICES = [
        ('W', 'White Win'),
        ('B', 'Black Win'),
        ('D', 'Draw'),
    ]

    player_white = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='matches_white')
    player_black = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='matches_black')
    result = models.CharField(max_length=1, choices=RESULT_CHOICES)

    white_rating_before = models.IntegerField()
    black_rating_before = models.IntegerField()
    white_rating_after = models.IntegerField()
    black_rating_after = models.IntegerField()

    white_rating_change = models.IntegerField(default=0)
    black_rating_change = models.IntegerField(default=0)

    white_peak_before = models.IntegerField(default=1500)
    black_peak_before = models.IntegerField(default=1500)
    white_peak_after = models.IntegerField(default=1500)
    black_peak_after = models.IntegerField(default=1500)

    white_games_before = models.IntegerField(default=0)
    black_games_before = models.IntegerField(default=0)
    white_games_after = models.IntegerField(default=0)
    black_games_after = models.IntegerField(default=0)

    is_reverted = models.BooleanField(default=False)
    reverted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.player_white.name} vs {self.player_black.name} ({self.get_result_display()})"

    @property
    def is_expired(self):
        """Matches older than 30 days are kept but can no longer be reverted."""
        cutoff = timezone.now() - timedelta(days=30)
        return self.created_at < cutoff

    class Meta:
        ordering = ['-created_at']


class Tournament(models.Model):
    DRAFT = 'draft'
    ACTIVE = 'active'
    FINISHED = 'finished'
    STATUS_CHOICES = [
        (DRAFT, 'Not started'),
        (ACTIVE, 'In progress'),
        (FINISHED, 'Finished'),
    ]

    name = models.CharField(max_length=120)
    start_date = models.DateField(default=timezone.localdate)
    total_rounds = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(15)],
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    players = models.ManyToManyField(Player, related_name='tournaments', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def current_round(self):
        return self.rounds.order_by('-number').first()

    @property
    def is_round_robin(self):
        return uses_round_robin(self.players.count(), self.total_rounds)

    class Meta:
        ordering = ['-start_date', '-created_at']


class Round(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='rounds')
    number = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.tournament.name} - Round {self.number}'

    @property
    def is_complete(self):
        return not self.pairings.filter(result='').exists()

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(fields=['tournament', 'number'], name='unique_round_number'),
        ]


class Pairing(models.Model):
    """One board in a round. A pairing with no black player is a bye (worth 1 point)."""

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='pairings')
    board = models.PositiveSmallIntegerField()
    player_white = models.ForeignKey(Player, on_delete=models.PROTECT, related_name='+')
    player_black = models.ForeignKey(Player, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    result = models.CharField(max_length=1, choices=Match.RESULT_CHOICES, blank=True)
    match = models.OneToOneField(
        Match, on_delete=models.SET_NULL, null=True, blank=True, related_name='pairing',
    )

    @property
    def is_bye(self):
        return self.player_black_id is None

    def __str__(self):
        black = self.player_black.name if self.player_black else 'BYE'
        return f'Board {self.board}: {self.player_white.name} vs {black}'

    class Meta:
        ordering = ['board']
