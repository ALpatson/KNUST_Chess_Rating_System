import random
from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import swiss
from .models import Match, Pairing, Player, Tournament


@override_settings(PASSCODE='test-pass')
class PasscodeTests(TestCase):
    def test_requires_passcode(self):
        response = self.client.get(reverse('player_list'))
        self.assertRedirects(response, reverse('passcode'))

    def test_ajax_header_does_not_bypass_passcode(self):
        response = self.client.get(reverse('player_list'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertRedirects(response, reverse('passcode'))

    def test_correct_passcode_grants_access(self):
        self.client.post(reverse('passcode'), {'passcode': 'test-pass'})
        self.assertEqual(self.client.get(reverse('player_list')).status_code, 200)

    def test_wrong_passcode_is_rejected(self):
        response = self.client.post(reverse('passcode'), {'passcode': 'nope'})
        self.assertContains(response, 'Incorrect passcode')


@override_settings(PASSCODE='test-pass')
class AppTests(TestCase):
    def setUp(self):
        self.client.post(reverse('passcode'), {'passcode': 'test-pass'})
        self.a = Player.objects.create(name='Ama', rating=1600, peak_rating=1600)
        self.b = Player.objects.create(name='Kofi', rating=1500, peak_rating=1500)

    def record(self, white, black, result):
        return self.client.post(reverse('match_create'), {
            'player_white': white.pk, 'player_black': black.pk, 'result': result,
        })

    def test_record_and_revert_match(self):
        self.record(self.a, self.b, 'B')
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertLess(self.a.rating, 1600)
        self.assertGreater(self.b.rating, 1500)
        self.assertEqual(self.b.peak_rating, self.b.rating)

        match = Match.objects.get()
        self.client.post(reverse('match_revert', args=[match.pk]))
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual((self.a.rating, self.a.games_played), (1600, 0))
        self.assertEqual((self.b.rating, self.b.peak_rating), (1500, 1500))

    def test_old_matches_are_kept_but_not_revertible(self):
        self.record(self.a, self.b, 'W')
        match = Match.objects.get()
        Match.objects.filter(pk=match.pk).update(created_at=timezone.now() - timedelta(days=45))

        self.client.get(reverse('match_create'))
        self.client.get(reverse('match_history'))
        self.assertTrue(Match.objects.filter(pk=match.pk).exists())

        self.client.post(reverse('match_revert', args=[match.pk]))
        match.refresh_from_db()
        self.assertFalse(match.is_reverted)

    def test_bad_history_filters_do_not_crash(self):
        for params in ({'player': 'abc'}, {'date_from': 'garbage'}, {'date_to': '2026-13-45'}):
            self.assertEqual(self.client.get(reverse('match_history'), params).status_code, 200)

    def test_search_shows_overall_rank(self):
        response = self.client.get(reverse('player_list'), {'q': 'Kofi'})
        self.assertEqual([p.rank for p in response.context['players']], [2])

    def test_new_player_peak_matches_starting_rating(self):
        self.client.post(reverse('player_create'), {'name': 'Esi', 'rating': 1800})
        self.assertEqual(Player.objects.get(name='Esi').peak_rating, 1800)

    def test_editing_rating_above_peak_raises_peak(self):
        self.client.post(reverse('player_update', args=[self.b.pk]), {'name': 'Kofi', 'rating': 1700})
        self.b.refresh_from_db()
        self.assertEqual(self.b.peak_rating, 1700)

    def test_ranking_pdf(self):
        response = self.client.get(reverse('player_ranking_pdf'))
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_all_pages_render(self):
        Tournament.objects.create(name='Empty', total_rounds=1)
        self.record(self.a, self.b, 'D')
        for name, args in [
            ('player_list', []), ('player_detail', [self.a.pk]), ('player_create', []),
            ('player_update', [self.a.pk]), ('player_delete', [self.a.pk]), ('match_create', []),
            ('match_history', []), ('tournament_list', []), ('tournament_create', []),
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        self.assertRedirects(self.client.get(reverse('player_ranking')), reverse('player_list'))

    def test_player_profile_shows_games_and_record(self):
        self.record(self.a, self.b, 'W')
        self.record(self.b, self.a, 'D')
        response = self.client.get(reverse('player_detail', args=[self.a.pk]))
        self.assertEqual(response.context['record'], {'W': 1, 'D': 1, 'L': 0})
        self.assertEqual(len(response.context['chart_data']), 3)  # start + two games
        self.assertEqual(response.context['games'][0]['opponent'], self.b)


def fake_player(pid, rating):
    return SimpleNamespace(id=pid, name=f'P{pid}', rating=rating)


def fake_pairing(white, black, result):
    return SimpleNamespace(player_white_id=white, player_black_id=black, result=result)


class SwissEngineTests(SimpleTestCase):
    def test_round_one_is_top_half_vs_bottom_half(self):
        players = [fake_player(i, 2000 - i * 10) for i in range(1, 9)]
        entries = swiss.build_entries(players, [])
        pairs = swiss.make_pairings(list(entries.values()))
        boards = [tuple(sorted(p)) for p in pairs]
        self.assertEqual(boards, [(1, 5), (2, 6), (3, 7), (4, 8)])
        # Colours alternate down the boards.
        self.assertEqual(pairs[0][0], 1)
        self.assertEqual(pairs[1][1], 2)

    def test_odd_players_lowest_gets_bye_once(self):
        players = [fake_player(i, 2000 - i * 10) for i in range(1, 6)]
        entries = swiss.build_entries(players, [])
        pairs = swiss.make_pairings(list(entries.values()))
        self.assertEqual(pairs[-1], (5, None))

        entries = swiss.build_entries(players, [fake_pairing(5, None, 'W')])
        pairs = swiss.make_pairings(list(entries.values()))
        self.assertNotEqual(pairs[-1][0], 5)
        self.assertIsNone(pairs[-1][1])

    def test_simulated_tournaments_never_repeat_games_or_byes(self):
        """Every player count from 2-16 and every possible round count, Swiss or round robin."""
        rng = random.Random(7)
        for n_players in range(2, 17):
            for total_rounds in range(1, swiss.max_rounds(n_players) + 1):
                for _ in range(5):
                    players = [fake_player(i, rng.randint(1200, 2100)) for i in range(1, n_players + 1)]
                    round_robin = swiss.uses_round_robin(n_players, total_rounds)
                    history = []
                    for round_index in range(total_rounds):
                        entries = swiss.build_entries(players, history)
                        pairs = swiss.next_round(entries, round_index, round_robin)
                        seated = sorted(pid for pair in pairs for pid in pair if pid is not None)
                        self.assertEqual(seated, [p.id for p in players])
                        for white, black in pairs:
                            history.append(fake_pairing(white, black, 'W' if black is None else rng.choice('WBD')))

                    label = f'{n_players} players, {total_rounds} rounds'
                    games = [frozenset((p.player_white_id, p.player_black_id)) for p in history if p.player_black_id]
                    self.assertEqual(len(games), len(set(games)), f'repeat game: {label}')
                    byes = [p.player_white_id for p in history if p.player_black_id is None]
                    self.assertEqual(len(byes), len(set(byes)), f'second bye: {label}')
                    for entry in swiss.build_entries(players, history).values():
                        self.assertLessEqual(abs(entry.color_balance), 3, label)

    def test_round_robin_threshold(self):
        self.assertFalse(swiss.uses_round_robin(16, 5))
        self.assertTrue(swiss.uses_round_robin(6, 4))   # max is 5
        self.assertTrue(swiss.uses_round_robin(7, 6))   # max is 7

    def test_standings_tiebreaks(self):
        players = [fake_player(i, 1500) for i in range(1, 5)]
        history = [
            fake_pairing(1, 2, 'W'), fake_pairing(3, 4, 'W'),
            fake_pairing(1, 3, 'D'), fake_pairing(2, 4, 'W'),
        ]
        table = swiss.standings(players, history)
        self.assertEqual([e.player_id for e in table][:2], [1, 3])
        self.assertEqual(table[0].points, 1.5)
        # Player 1's opponents (2 and 3) scored 1 + 1.5.
        self.assertEqual(table[0].buchholz, 2.5)


@override_settings(PASSCODE='test-pass')
class TournamentFlowTests(TestCase):
    def setUp(self):
        self.client.post(reverse('passcode'), {'passcode': 'test-pass'})
        self.players = [
            Player.objects.create(name=f'Player {i}', rating=1800 - i * 20, peak_rating=1800 - i * 20)
            for i in range(5)
        ]

    def create(self, rounds=3):
        self.client.post(reverse('tournament_create'), {
            'name': 'Club Open', 'start_date': '2026-10-10', 'total_rounds': rounds,
            'players': [p.pk for p in self.players],
        })
        return Tournament.objects.get(name='Club Open')

    def play_round(self, t, result='W'):
        for p in Pairing.objects.filter(round__tournament=t, result=''):
            self.client.post(reverse('pairing_result', args=[t.pk, p.pk]), {'result': result})

    def test_form_rejects_too_many_rounds(self):
        response = self.client.post(reverse('tournament_create'), {
            'name': 'Too long', 'start_date': '2026-10-10', 'total_rounds': 9,
            'players': [p.pk for p in self.players],
        })
        self.assertFalse(Tournament.objects.filter(name='Too long').exists())
        self.assertIn('total_rounds', response.context['form'].errors)

    def test_full_tournament(self):
        t = self.create()
        self.assertEqual(t.status, Tournament.DRAFT)

        self.client.post(reverse('tournament_pair', args=[t.pk]))
        t.refresh_from_db()
        self.assertEqual(t.status, Tournament.ACTIVE)
        round1 = list(Pairing.objects.filter(round__number=1))
        self.assertEqual(len(round1), 3)  # 2 games + 1 bye
        self.assertEqual(sum(p.is_bye for p in round1), 1)

        # Round 2 can't be paired before the results are in.
        self.client.post(reverse('tournament_pair', args=[t.pk]))
        self.assertEqual(t.rounds.count(), 1)

        self.play_round(t)
        self.assertEqual(Match.objects.count(), 2)
        game = next(p for p in round1 if not p.is_bye)
        game.refresh_from_db()
        self.assertIsNotNone(game.match_id)
        game.player_white.refresh_from_db()
        self.assertGreater(game.player_white.rating, game.match.white_rating_before)

        # A second result for the same board is rejected.
        self.client.post(reverse('pairing_result', args=[t.pk, game.pk]), {'result': 'B'})
        self.assertEqual(Match.objects.count(), 2)

        for _ in range(2):
            self.client.post(reverse('tournament_pair', args=[t.pk]))
            self.play_round(t, 'D')
        self.assertEqual(t.rounds.count(), 3)

        self.client.post(reverse('tournament_pair', args=[t.pk]))  # beyond the last round
        self.assertEqual(t.rounds.count(), 3)

        self.client.post(reverse('tournament_finish', args=[t.pk]))
        t.refresh_from_db()
        self.assertEqual(t.status, Tournament.FINISHED)

        response = self.client.get(reverse('tournament_detail', args=[t.pk]))
        self.assertEqual(response.status_code, 200)
        # 3 rounds x (2 games worth 1 point each + 1 bye worth 1 point)
        self.assertEqual(sum(e.points for e in response.context['standings']), 9)

        for url in (reverse('tournament_standings_pdf', args=[t.pk]), reverse('tournament_round_pdf', args=[t.pk, 1])):
            self.assertEqual(self.client.get(url)['Content-Type'], 'application/pdf')

        # Players with tournament games are protected, and so is the tournament itself.
        self.client.post(reverse('player_delete', args=[game.player_white_id]))
        self.assertTrue(Player.objects.filter(pk=game.player_white_id).exists())
        self.client.post(reverse('tournament_delete', args=[t.pk]))
        self.assertTrue(Tournament.objects.filter(pk=t.pk).exists())

    def test_undo_restores_ratings_and_board(self):
        t = self.create()
        self.client.post(reverse('tournament_pair', args=[t.pk]))
        game = Pairing.objects.filter(round__tournament=t, player_black__isnull=False).first()
        before = (game.player_white.rating, game.player_black.rating)

        self.client.post(reverse('pairing_result', args=[t.pk, game.pk]), {'result': 'B'})
        self.client.post(reverse('pairing_undo', args=[t.pk, game.pk]))

        game.refresh_from_db()
        game.player_white.refresh_from_db()
        game.player_black.refresh_from_db()
        self.assertEqual(game.result, '')
        self.assertIsNone(game.match_id)
        self.assertEqual((game.player_white.rating, game.player_black.rating), before)

    def test_revert_from_history_reopens_board(self):
        t = self.create()
        self.client.post(reverse('tournament_pair', args=[t.pk]))
        game = Pairing.objects.filter(round__tournament=t, player_black__isnull=False).first()
        self.client.post(reverse('pairing_result', args=[t.pk, game.pk]), {'result': 'W'})
        game.refresh_from_db()
        self.client.post(reverse('match_revert', args=[game.match_id]))
        game.refresh_from_db()
        self.assertEqual(game.result, '')

    def test_draft_tournament_can_be_edited_and_deleted(self):
        t = self.create()
        self.client.post(reverse('tournament_update', args=[t.pk]), {
            'name': 'Renamed', 'start_date': '2026-10-11', 'total_rounds': 2,
            'players': [p.pk for p in self.players[:3]],
        })
        t.refresh_from_db()
        self.assertEqual((t.name, t.players.count()), ('Renamed', 3))
        self.client.post(reverse('tournament_delete', args=[t.pk]))
        self.assertFalse(Tournament.objects.filter(pk=t.pk).exists())
