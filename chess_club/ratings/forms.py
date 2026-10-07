from django import forms
from . import swiss
from .models import Player, Match, Tournament


class TournamentForm(forms.ModelForm):
    players = forms.ModelMultipleChoiceField(
        queryset=Player.objects.order_by('-rating', 'name'),
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Tournament
        fields = ['name', 'start_date', 'total_rounds', 'players']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. October Rapid Open'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'total_rounds': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 15}),
        }
        labels = {'total_rounds': 'Number of rounds'}

    def clean(self):
        cleaned = super().clean()
        players = cleaned.get('players')
        rounds = cleaned.get('total_rounds')
        if players is not None and len(players) < 2:
            self.add_error('players', 'Select at least two players.')
        elif players is not None and rounds:
            # A full round robin is the most rounds possible without repeat games.
            max_rounds = swiss.max_rounds(len(players))
            if rounds > max_rounds:
                self.add_error(
                    'total_rounds',
                    f'With {len(players)} players, at most {max_rounds} rounds can be played without repeat games.',
                )
        return cleaned

class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['name', 'rating']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'rating': forms.NumberInput(attrs={'class': 'form-control'}),
        }





class MatchForm(forms.ModelForm):
    player_white = forms.ModelChoiceField(
        queryset=Player.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    player_black = forms.ModelChoiceField(
        queryset=Player.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Match
        fields = ['player_white', 'player_black', 'result']
        widgets = {
            'result': forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['result'].choices = [('W', '1-0 White won'), ('D', '½-½ Draw'), ('B', '0-1 Black won')]

        # If the form is bound, exclude the selected white player from black choices
        try:
            if self.data.get('player_white'):
                pw = int(self.data.get('player_white'))
                self.fields['player_black'].queryset = Player.objects.exclude(pk=pw)
            elif self.initial.get('player_white'):
                init_pw = self.initial.get('player_white')
                if hasattr(init_pw, 'pk'):
                    self.fields['player_black'].queryset = Player.objects.exclude(pk=init_pw.pk)
        except Exception:
            # fallback: leave full queryset
            pass

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get('player_white')
        pb = cleaned.get('player_black')
        if pw and pb and pw == pb:
            raise forms.ValidationError('A player cannot play themselves')
        return cleaned