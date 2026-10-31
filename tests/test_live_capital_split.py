from trader.risk.manager import live_capital_split

B, CAP = 600_000, 60_000


def test_zero_pnl_matches_previous_behaviour():
    assert live_capital_split(494_000, B, 0, CAP) == (494_000, 0)
    assert live_capital_split(630_000, B, 0, CAP) == (600_000, 30_000)
    assert live_capital_split(700_000, B, 0, CAP) == (600_000, 60_000)


def test_profits_grow_sleeve_before_pool():
    assert live_capital_split(650_000, B, 50_000, CAP) == (600_000, 0)
    assert live_capital_split(680_000, B, 50_000, CAP) == (600_000, 30_000)
    assert live_capital_split(730_000, B, 50_000, CAP) == (600_000, 60_000)


def test_account_below_sleeve_no_double_count():
    eff, pool = live_capital_split(550_000, B, 50_000, CAP)
    assert eff == 500_000 and eff + 50_000 == 550_000 and pool == 0


def test_losses_shrink_sleeve():
    assert live_capital_split(550_000, B, -50_000, CAP) == (600_000, 0)
    assert live_capital_split(600_000, B, -50_000, CAP) == (600_000, 50_000)


def test_invariants():
    for eq in range(300_000, 900_000, 10_000):
        for cum in (-100_000, 0, 50_000, 150_000):
            if eq < cum:
                continue
            eff, pool = live_capital_split(eq, B, cum, CAP)
            assert eff + cum <= eq + 1e-6
            assert eff + cum + pool <= eq + 1e-6
            assert pool <= CAP
            assert eff >= 0


def test_floor_zero():
    assert live_capital_split(10_000, B, 50_000, CAP)[0] == 0.0
