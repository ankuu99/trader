"""ISS-03: a partial scale-out on a scaled-in position must give the same
accounting whether or not the bot reboots in between (memory is pro-rata; the
DB lots must match)."""
from datetime import datetime

import pytest

from trader.data.store import Store
from trader.risk.manager import RiskManager

from tests.test_loss_reentry_block import _block
from tests.test_scale_in import _scale_in_config

INST = "NSE:TEST"
DAY1 = datetime(2026, 6, 1, 10, 0)
DAY2 = datetime(2026, 6, 2, 10, 0)


def _fresh_risk():
    r = RiskManager()
    r.on_order_filled(INST, 100.0, 100)
    r.on_order_filled(INST, 90.0, 50, addon=True)
    return r


def test_scaleout_then_reboot_matches_no_reboot(tmp_path):
    with _scale_in_config(), _block():
        # Path A: no reboot
        a = _fresh_risk()
        a.reduce_position(INST, 75, 105.0)

        # Path B: same fills/partial on a second RiskManager and the Store
        b = _fresh_risk()
        b.reduce_position(INST, 75, 105.0)
        store = Store(tmp_path / "t.db")
        store.upsert_open_position(INST, 100.0, 100, 0, DAY1)
        store.add_position_lot(INST, 90.0, 50, DAY2)
        store.consume_position_lots(INST, 75)
        pre_reboot_cum = b.cumulative_pnl

        pos = store.read_open_positions()[0]
        lots = pos["addon_lots"]
        assert all(l["qty"] >= 0 for l in lots)
        parent_qty = pos["quantity"] - sum(l["qty"] for l in lots)
        assert parent_qty >= 0
        c = RiskManager()
        c.seed_position(INST, parent_qty, pos["entry_price"], entry_ts=DAY1)
        c.seed_scale_in(INST, lots)
        c.seed_cumulative_pnl(pre_reboot_cum)

        qa, qc = a._open_positions[INST], c._open_positions[INST]
        assert qa == qc == 75
        assert a._position_values[INST] / qa == pytest.approx(
            c._position_values[INST] / qc, abs=0.01)
        assert abs(a.scale_in_deployed - c.scale_in_deployed) <= 90.0
        assert a.scale_in_deployed == pytest.approx(c.scale_in_deployed)

        a.close_position(INST, 95.0)
        c.close_position(INST, 95.0)
        assert a.cumulative_pnl == pytest.approx(c.cumulative_pnl, abs=1.0)
        assert INST in a.loss_reentry_state
        assert INST in c.loss_reentry_state
