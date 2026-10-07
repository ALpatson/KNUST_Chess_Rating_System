"""Swiss-system standings and pairings.

Pairing follows the Dutch system in simplified form:
- players are ranked by score, then rating;
- within a score group, the top half plays the bottom half (1 vs 5, 2 vs 6, ...);
- nobody meets the same opponent twice (unless it's impossible, e.g. more
  rounds than opponents);
- with an odd number of players, the lowest-ranked player who hasn't had a
  bye yet gets one (worth 1 point);
- colours are balanced: whoever has had white less often gets white.
"""
from dataclasses import dataclass, field

BYE_POINTS = 1.0
SCORES = {'W': (1.0, 0.0), 'B': (0.0, 1.0), 'D': (0.5, 0.5)}


@dataclass
class Entry:
    player_id: int
    name: str
    rating: int
    points: float = 0.0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    had_bye: bool = False
    opponents: list = field(default_factory=list)       # opponent ids, in order
    results: dict = field(default_factory=dict)         # opponent id -> points scored against them
    colors: list = field(default_factory=list)          # 'W' / 'B' per game played
    buchholz: float = 0.0
    sonneborn_berger: float = 0.0
    rank: int = 0

    @property
    def color_balance(self):
        return self.colors.count('W') - self.colors.count('B')

    @property
    def games(self):
        return self.wins + self.draws + self.losses


def build_entries(players, pairings):
    """Tally scores from finished pairings.

    `players` is an iterable of Player-like objects (id, name, rating).
    `pairings` is an iterable of objects with player_white_id, player_black_id, result.
    """
    entries = {p.id: Entry(player_id=p.id, name=p.name, rating=p.rating) for p in players}

    for pairing in pairings:
        white = entries.get(pairing.player_white_id)
        if white is None:
            continue
        if pairing.player_black_id is None:
            white.had_bye = True
            white.points += BYE_POINTS
            continue
        black = entries.get(pairing.player_black_id)
        if black is None:
            continue

        # Colours and opponents count as soon as the pairing exists.
        white.opponents.append(black.player_id)
        black.opponents.append(white.player_id)
        white.colors.append('W')
        black.colors.append('B')

        if pairing.result not in SCORES:
            continue
        w_pts, b_pts = SCORES[pairing.result]
        white.points += w_pts
        black.points += b_pts
        white.results[black.player_id] = white.results.get(black.player_id, 0) + w_pts
        black.results[white.player_id] = black.results.get(white.player_id, 0) + b_pts
        for entry, pts in ((white, w_pts), (black, b_pts)):
            if pts == 1:
                entry.wins += 1
            elif pts == 0.5:
                entry.draws += 1
            else:
                entry.losses += 1

    return entries


def standings(players, pairings):
    """Return entries sorted by points, Buchholz, Sonneborn-Berger, wins, rating."""
    entries = build_entries(players, pairings)
    for entry in entries.values():
        entry.buchholz = sum(entries[o].points for o in entry.opponents if o in entries)
        entry.sonneborn_berger = sum(
            entries[o].points * pts for o, pts in entry.results.items() if o in entries
        )

    ordered = sorted(
        entries.values(),
        key=lambda e: (-e.points, -e.buchholz, -e.sonneborn_berger, -e.wins, -e.rating, e.name.lower()),
    )
    for idx, entry in enumerate(ordered, 1):
        entry.rank = idx
    return ordered


class PairingError(Exception):
    pass


def max_rounds(player_count):
    """Rounds in a full round robin: the most possible without repeat games."""
    return player_count if player_count % 2 else player_count - 1


def uses_round_robin(player_count, total_rounds):
    """Swiss pairing can paint itself into a corner in the last rounds before
    everyone has met everyone, so those tournaments use a round-robin schedule."""
    return player_count >= 2 and total_rounds >= max_rounds(player_count) - 1


def round_robin_opponents(player_ids, round_index):
    """Who meets whom in one round of a round robin (circle method).

    `player_ids` must be in the same order every round; `round_index` is
    0-based. Returns (unordered pairs, bye player id or None).
    """
    ids = list(player_ids)
    if len(ids) % 2:
        ids.append(None)  # whoever is paired with None has the bye
    n = len(ids)
    fixed, others = ids[-1], ids[:-1]
    shift = round_index % (n - 1)
    rotated = others[shift:] + others[:shift]
    seats = [fixed] + rotated

    pairs, bye = [], None
    for board in range(n // 2):
        a, b = seats[board], seats[n - 1 - board]
        if a is None or b is None:
            bye = a if b is None else b
        else:
            pairs.append((a, b))
    return pairs, bye


def next_round(entries, round_index, round_robin):
    """Pairings for the next round as (white_id, black_id) tuples, best boards first, bye last."""
    if not round_robin:
        return make_pairings(list(entries.values()))

    pairs, bye = round_robin_opponents(sorted(entries), round_index)
    rank = {e.player_id: i for i, e in enumerate(
        sorted(entries.values(), key=lambda e: (-e.points, -e.rating, e.name.lower())))}
    # Put the higher-ranked player first so colours and board order follow the standings.
    pairs = sorted(
        (tuple(sorted(pair, key=rank.get)) for pair in pairs),
        key=lambda pair: rank[pair[0]],
    )
    result = [_assign_colors(entries[a], entries[b], board) for board, (a, b) in enumerate(pairs)]
    if bye is not None:
        result.append((bye, None))
    return result


def make_pairings(entries):
    """Pair the next round.

    Returns a list of (white_id, black_id) tuples, best boards first; a bye is
    returned last as (player_id, None).
    """
    ordered = sorted(entries, key=lambda e: (-e.points, -e.rating, e.name.lower()))
    if len(ordered) < 2:
        raise PairingError('At least two players are needed to make pairings.')

    if len(ordered) % 2:
        # Lowest-ranked players first. A second bye is only used if no one else can take it.
        from_bottom = list(reversed(ordered))
        fresh = [e for e in from_bottom if not e.had_bye]
        repeat_bye = [e for e in from_bottom if e.had_bye]
    else:
        fresh, repeat_bye = [None], []

    # Most important first: no repeat games, then no second byes.
    attempts = [(False, fresh), (False, repeat_bye), (True, fresh or repeat_bye)]
    for allow_repeats, bye_candidates in attempts:
        for bye in bye_candidates:
            pool = [e for e in ordered if e is not bye]
            pairs = _pair(pool, allow_repeats, budget=[100000])
            if pairs is not None:
                result = [_assign_colors(a, b, board) for board, (a, b) in enumerate(pairs)]
                if bye is not None:
                    result.append((bye.player_id, None))
                return result

    raise PairingError('Could not generate pairings.')


def _candidate_order(player, rest):
    """Opponents to try for `player` (the top-ranked unpaired player), best first."""
    group = [e for e in rest if e.points == player.points]
    lower = [e for e in rest if e.points != player.points]
    # Group size including `player`; Dutch system pairs index 0 with index size // 2.
    half = (len(group) + 1) // 2
    preferred = group[half - 1:] + list(reversed(group[:half - 1]))
    return preferred + lower


def _pair(pool, allow_repeats, budget):
    if not pool:
        return []
    player, rest = pool[0], pool[1:]
    for opponent in _candidate_order(player, rest):
        if not allow_repeats and opponent.player_id in player.opponents:
            continue
        budget[0] -= 1
        if budget[0] < 0:
            return None
        remaining = [e for e in rest if e is not opponent]
        sub = _pair(remaining, allow_repeats, budget)
        if sub is not None:
            return [(player, opponent)] + sub
    return None


def _assign_colors(a, b, board_index):
    """`a` is the higher-ranked player. Returns (white_id, black_id)."""
    if a.color_balance != b.color_balance:
        white_is_a = a.color_balance < b.color_balance
    elif a.colors and b.colors and a.colors[-1] != b.colors[-1]:
        white_is_a = a.colors[-1] == 'B'
    else:
        # Alternate by board so top seeds don't all get the same colour.
        white_is_a = board_index % 2 == 0
    return (a.player_id, b.player_id) if white_is_a else (b.player_id, a.player_id)
