from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta


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

    @classmethod
    def cleanup_expired_records(cls):
        cutoff = timezone.now() - timedelta(days=30)
        cls.objects.filter(created_at__lt=cutoff).delete()

    @property
    def is_expired(self):
        cutoff = timezone.now() - timedelta(days=30)
        return self.created_at < cutoff

    class Meta:
        ordering = ['-created_at']
