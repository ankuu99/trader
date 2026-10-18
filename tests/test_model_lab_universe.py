from research.model_lab import paths, universe


def test_is_series_variant():
    for ts in ("ABC-BE", "ABC-SG", "ABC-N1", "BAJAJ-AUTO-BE"):
        assert universe._is_series_variant(ts)
    for ts in ("BAJAJ-AUTO", "NAM-INDIA", "HCL-INSYS", "RELIANCE"):
        assert not universe._is_series_variant(ts)


def test_snapshot_keeps_hyphenated_stocks(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "UNIVERSE_DIR", tmp_path)

    def row(ts, name, typ="EQ"):
        return {"tradingsymbol": ts, "name": name, "segment": "NSE", "instrument_type": typ,
                "instrument_token": 1, "lot_size": 1, "tick_size": 0.05}

    class FakeKite:
        def instruments(self, ex):
            return [row("RELIANCE", "RELIANCE INDUSTRIES"), row("BAJAJ-AUTO", "BAJAJ AUTO"),
                    row("BAJAJ-AUTO-BE", "BAJAJ AUTO"), row("ABC-SG", "ABC GOLD BOND"),
                    row("NIFTYBEES", "NIPPON NIFTY BEES"), row("FOO", "FOO", typ="BE")]

    df = universe.snapshot_instruments(FakeKite())
    assert list(df["symbol"]) == ["NSE:RELIANCE", "NSE:BAJAJ-AUTO"]
