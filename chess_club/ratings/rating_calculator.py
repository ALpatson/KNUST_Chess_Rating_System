from datetime import date


class RatingCalculator:
    """Simplified FIDE-based rating calculator using provided rules.

    Rules implemented (based on user-supplied summary):
    - K = 40 for players new to the rating list until they have completed at least 30 games.
    - K = 40 for players under 18 while their rating remains under 2300 (if birthdate provided).
    - K = 20 as long as a player's rating remains under 2400.
    - K = 10 once a player's rating has reached 2400 (simple threshold-based implementation).
    """

    @staticmethod
    def get_k_factor(player):
        # player is a Player instance (may have attributes: rating, games_played, birth_date)
        rating = getattr(player, 'rating', 0)
        games = getattr(player, 'games_played', 0)
        birth = getattr(player, 'birth_date', None)

        # Age rule: under 18 and rating < 2300 -> K=40
        if birth:
            try:
                today = date.today()
                age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
                if age < 18 and rating < 2300:
                    return 40
            except Exception:
                pass

        # New player rule: fewer than 30 games -> K=40
        if games < 30:
            return 40

        # High rating rule
        if rating >= 2400:
            return 10

        # Default intermediate K
        return 20
    
    @staticmethod
    def calculate_expected_score(player_rating, opponent_rating):
        """Calculate expected score using Elo formula."""
        rating_diff = opponent_rating - player_rating
        expected = 1 / (1 + 10 ** (rating_diff / 400))
        return expected
    
    @staticmethod
    def calculate_rating_change(player, opponent_rating, actual_score):
        """
        Calculate rating change. `player` is a Player instance used to derive K.
        actual_score: 1 for win, 0.5 for draw, 0 for loss
        """
        k_factor = RatingCalculator.get_k_factor(player)
        expected_score = RatingCalculator.calculate_expected_score(
            player.rating,
            opponent_rating,
        )
        rating_change = k_factor * (actual_score - expected_score)
        return round(rating_change)
    
    @staticmethod
    def process_match(player_white, player_black, result):
        """Process a match between two Player instances, return (white_change, black_change).

        Note: this function does not persist player objects; caller should save updates.
        """
        white_score = 1.0 if result == 'W' else (0.5 if result == 'D' else 0.0)
        black_score = 1.0 if result == 'B' else (0.5 if result == 'D' else 0.0)

        white_change = RatingCalculator.calculate_rating_change(
            player_white,
            player_black.rating,
            white_score,
        )
        black_change = RatingCalculator.calculate_rating_change(
            player_black,
            player_white.rating,
            black_score,
        )

        return white_change, black_change