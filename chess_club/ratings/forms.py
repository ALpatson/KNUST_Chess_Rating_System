from django import forms
from .models import Player, Match

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