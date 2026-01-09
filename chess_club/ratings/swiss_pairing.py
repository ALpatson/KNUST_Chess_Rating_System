from .models import TournamentStanding, Pairing
from .rating_calculator import RatingCalculator
import random


class SwissPairing:
    """FIDE Swiss tournament pairing system"""
    
    @staticmethod
    def generate_round_pairings(tournament, round_obj):
        """
        Generate pairings for a round using FIDE Swiss system
        """
        standings = list(TournamentStanding.objects.filter(
            tournament=tournament
        ).order_by('-total_score', '-wins'))
        
        if not standings:
            raise ValueError("No standings found. Add players to tournament first.")
        
        if round_obj.round_number == 1:
            pairings = SwissPairing._pair_first_round(standings, round_obj)
        else:
            pairings = SwissPairing._pair_fide_swiss(standings, round_obj)
        
        return pairings
    
    @staticmethod
    def _pair_first_round(standings, round_obj):
        """Pair first round randomly"""
        players = [s.player for s in standings]
        players = list(players)
        random.shuffle(players)
        pairings = []
        board_number = 1
        
        # Handle odd number of players (bye)
        if len(players) % 2 == 1:
            players.pop()  # Skip bye for now
        
        # Pair remaining players
        for i in range(0, len(players) - 1, 2):
            player_white = players[i]
            player_black = players[i + 1]
            
            pairing = Pairing.objects.create(
                round=round_obj,
                player_white=player_white,
                player_black=player_black,
                white_rating_before=player_white.rating,
                black_rating_before=player_black.rating,
                board_number=board_number,
            )
            pairings.append(pairing)
            board_number += 1
        
        return pairings
    
    @staticmethod
    def _pair_fide_swiss(standings, round_obj):
        """
        FIDE Swiss pairing:
        1. Group by score
        2. Pair within same score group (if they haven't played)
        3. If must pair with different score, use next lower group
        4. Never pair same opponents twice
        """
        pairings = []
        board_number = 1
        tournament = round_obj.tournament
        
        # Group by score
        score_groups = {}
        for standing in standings:
            score = standing.total_score
            if score not in score_groups:
                score_groups[score] = []
            score_groups[score].append(standing)
        
        # Sort scores descending
        sorted_scores = sorted(score_groups.keys(), reverse=True)
        
        paired_players = set()
        unpaired_standings = []
        
        # Process each score group
        for score in sorted_scores:
            group = [s for s in score_groups[score] if s.player.id not in paired_players]
            
            if len(group) == 0:
                continue
            
            # Try to pair within this score group
            group_unpaired = []
            i = 0
            while i < len(group):
                if i >= len(group) - 1:
                    # Odd one out from this group
                    group_unpaired.append(group[i])
                    i += 1
                    continue
                
                standing1 = group[i]
                standing2 = group[i + 1]
                
                # Check if they've played before
                if not SwissPairing._have_played(standing1.player, standing2.player, tournament):
                    # Valid pairing
                    pairing = Pairing.objects.create(
                        round=round_obj,
                        player_white=standing1.player,
                        player_black=standing2.player,
                        white_rating_before=standing1.player.rating,
                        black_rating_before=standing2.player.rating,
                        board_number=board_number,
                    )
                    pairings.append(pairing)
                    paired_players.add(standing1.player.id)
                    paired_players.add(standing2.player.id)
                    board_number += 1
                    i += 2
                else:
                    # They've played before - add to unpaired
                    group_unpaired.append(standing1)
                    i += 1
                    
                    # Also add standing2 if we're moving standing1
                    if i < len(group) and group[i] == standing2:
                        group_unpaired.append(standing2)
                        i += 1
            
            unpaired_standings.extend(group_unpaired)
        
        # Now handle unpaired standings - pair with next score group
        # Sort unpaired by original score (descending)
        unpaired_standings.sort(key=lambda s: s.total_score, reverse=True)
        
        i = 0
        while i < len(unpaired_standings):
            standing1 = unpaired_standings[i]
            
            if standing1.player.id in paired_players:
                i += 1
                continue
            
            # Find someone from lower score group they haven't played
            found = False
            for j in range(i + 1, len(unpaired_standings)):
                standing2 = unpaired_standings[j]
                
                if (standing2.player.id not in paired_players and
                    not SwissPairing._have_played(standing1.player, standing2.player, tournament)):
                    
                    pairing = Pairing.objects.create(
                        round=round_obj,
                        player_white=standing1.player,
                        player_black=standing2.player,
                        white_rating_before=standing1.player.rating,
                        black_rating_before=standing2.player.rating,
                        board_number=board_number,
                    )
                    pairings.append(pairing)
                    paired_players.add(standing1.player.id)
                    paired_players.add(standing2.player.id)
                    board_number += 1
                    found = True
                    break
            
            i += 1
        
        return pairings
    
    @staticmethod
    def _have_played(player1, player2, tournament):
        """Check if two players have already played in this tournament"""
        return Pairing.objects.filter(
            round__tournament=tournament,
            player_white__in=[player1, player2],
            player_black__in=[player1, player2],
        ).exclude(result='P').exists()


class TournamentResultsProcessor:
    """Process results and update ratings"""
    
    @staticmethod
    def process_pairing_result(pairing, result):
        """
        Process a pairing result and update ratings
        result: 'W', 'B', or 'D'
        """
        player_white = pairing.player_white
        player_black = pairing.player_black
        
        # Calculate rating changes
        white_change, black_change = RatingCalculator.process_match(
            player_white, player_black, result
        )
        
        # Get actual scores
        if result == 'W':
            white_score = 1.0
            black_score = 0.0
        elif result == 'B':
            white_score = 0.0
            black_score = 1.0
        else:  # Draw
            white_score = 0.5
            black_score = 0.5
        
        # Update pairing with results
        pairing.result = result
        pairing.white_rating_after = player_white.rating + white_change
        pairing.black_rating_after = player_black.rating + black_change
        pairing.white_rating_change = white_change
        pairing.black_rating_change = black_change
        pairing.save()
        
        # Update player ratings
        player_white.rating = pairing.white_rating_after
        player_black.rating = pairing.black_rating_after
        player_white.games_played += 1
        player_black.games_played += 1
        
        # Update peak ratings
        if player_white.rating > player_white.peak_rating:
            player_white.peak_rating = player_white.rating
        if player_black.rating > player_black.peak_rating:
            player_black.peak_rating = player_black.rating
        
        player_white.save()
        player_black.save()
        
        # Update tournament standings
        TournamentResultsProcessor._update_standing(
            pairing.round.tournament, player_white, white_score, white_change
        )
        TournamentResultsProcessor._update_standing(
            pairing.round.tournament, player_black, black_score, black_change
        )
        
        return pairing
    
    @staticmethod
    def _update_standing(tournament, player, score, rating_change):
        """Update a player's standing in the tournament"""
        standing = TournamentStanding.objects.get(
            tournament=tournament,
            player=player
        )
        
        standing.total_score += score
        standing.rating_change += rating_change
        standing.final_rating = player.rating
        
        if score == 1.0:
            standing.wins += 1
        elif score == 0.5:
            standing.draws += 1
        else:
            standing.losses += 1
        
        standing.save()
    
    @staticmethod
    def finalize_tournament(tournament):
        """Mark tournament as finished and finalize all ratings"""
        tournament.is_finished = True
        tournament.save()