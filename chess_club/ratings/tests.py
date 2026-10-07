from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Player, Match


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
