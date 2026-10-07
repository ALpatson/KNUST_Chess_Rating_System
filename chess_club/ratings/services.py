"""Recording and reverting rated matches.

Used by both casual match entry and tournament result entry so that ratings,
peak ratings and games played are always updated the same way.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Match, Player
from .rating_calculator import RatingCalculator


class MatchError(Exception):
    """A match could not be recorded or reverted; the message is user-facing."""


def record_match(white_id, black_id, result):
    """Record a rated game between two players and update both players' stats.

    Must be called inside a transaction (it locks both player rows).
    """
    if white_id == black_id:
        raise MatchError('A player cannot play themselves.')

    white = Player.objects.select_for_update().get(pk=white_id)
    black = Player.objects.select_for_update().get(pk=black_id)

    match = Match(
        player_white=white,
        player_black=black,
        result=result,
        white_rating_before=white.rating,
        black_rating_before=black.rating,
        white_peak_before=white.peak_rating,
        black_peak_before=black.peak_rating,
        white_games_before=white.games_played or 0,
        black_games_before=black.games_played or 0,
    )

    w_change, b_change = RatingCalculator.process_match(white, black, result)
    match.white_rating_change = w_change
    match.black_rating_change = b_change

    for player, change in ((white, w_change), (black, b_change)):
        player.rating += change
        player.games_played = (player.games_played or 0) + 1
        player.peak_rating = max(player.peak_rating, player.rating)
        player.save(update_fields=['rating', 'peak_rating', 'games_played'])

    match.white_rating_after = white.rating
    match.black_rating_after = black.rating
    match.white_peak_after = white.peak_rating
    match.black_peak_after = black.peak_rating
    match.white_games_after = white.games_played
    match.black_games_after = black.games_played
    match.save()
    return match


def revert_match(match_id):
    """Undo a match, restoring both players' exact stats from before it.

    Only allowed within 30 days, and only if neither player has played a newer
    match (otherwise the later rating changes would be wrong).
    """
    with transaction.atomic():
        match = (
            Match.objects.select_related('player_white', 'player_black')
            .select_for_update()
            .get(pk=match_id)
        )

        if match.is_reverted:
            raise MatchError('This match has already been reverted.')
        if match.is_expired:
            raise MatchError('This match is older than 30 days and can no longer be reverted.')

        for player in (match.player_white, match.player_black):
            has_newer = Match.objects.filter(
                Q(player_white=player) | Q(player_black=player),
                is_reverted=False,
                created_at__gt=match.created_at,
            ).exists()
            if has_newer:
                raise MatchError(
                    f'Cannot revert this match because {player.name} has newer recorded matches. '
                    'Revert the newest matches first.'
                )

        white, black = match.player_white, match.player_black
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

        # A reverted tournament game goes back to "no result" on its board.
        pairing = getattr(match, 'pairing', None)
        if pairing is not None:
            pairing.result = ''
            pairing.match = None
            pairing.save(update_fields=['result', 'match'])

    return match
