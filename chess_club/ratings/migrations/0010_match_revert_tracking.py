from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ratings', '0009_player_default_rating_1500'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='black_games_after',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='match',
            name='black_games_before',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='match',
            name='black_peak_after',
            field=models.IntegerField(default=1500),
        ),
        migrations.AddField(
            model_name='match',
            name='black_peak_before',
            field=models.IntegerField(default=1500),
        ),
        migrations.AddField(
            model_name='match',
            name='is_reverted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='match',
            name='reverted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='match',
            name='white_games_after',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='match',
            name='white_games_before',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='match',
            name='white_peak_after',
            field=models.IntegerField(default=1500),
        ),
        migrations.AddField(
            model_name='match',
            name='white_peak_before',
            field=models.IntegerField(default=1500),
        ),
    ]
