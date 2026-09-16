# -*- coding: utf-8 -*-
"""定期存款结算数学（Economy.compute_fixed_deposit_payout / 月利率解析）单测"""
import importlib.util
import unittest
from pathlib import Path

_ECONOMY_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "endstone_arc_core" / "Economy.py"
)
_spec = importlib.util.spec_from_file_location("economy_under_test", _ECONOMY_PATH)
economy_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(economy_mod)

Economy = economy_mod.Economy
MONTH = Economy.MONTH_SECONDS


class _FakeSettings:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def GetSetting(self, key):
        return self.data.get(key)


def _state(amount, term, rate, start, now):
    return Economy.compute_fixed_deposit_payout(amount, term, rate, start, now_ts=now)


class FixedDepositPayoutTests(unittest.TestCase):
    def test_zero_interest_before_first_month(self):
        st = _state(1000.0, 3, 5, 0.0, MONTH - 1)
        self.assertFalse(st["matured"])
        self.assertEqual(st["months_elapsed"], 0)
        self.assertEqual(st["payout"], 1000.0)
        self.assertEqual(st["interest"], 0.0)

    def test_partial_months_do_not_accrue(self):
        # 只满 1 个整月：不计息（未到期），剩余时间约为 2 个月
        st = _state(1000.0, 3, 5, 0.0, MONTH + 1)
        self.assertFalse(st["matured"])
        self.assertEqual(st["months_elapsed"], 1)
        self.assertEqual(st["payout"], 1000.0)
        self.assertEqual(st["remaining_seconds"], 2 * MONTH - 1)

    def test_matures_exactly_at_term_end(self):
        st = _state(1000.0, 12, 5, 0.0, 12 * MONTH)
        self.assertTrue(st["matured"])
        self.assertEqual(st["payout"], 1795.86)  # 1000 × 1.05^12 = 1795.8563…
        self.assertEqual(st["interest"], 795.86)

    def test_interest_capped_after_maturity(self):
        # 到期后利息封顶：存放再久支取金额不变（不自动续存）
        at_maturity = _state(1000.0, 1, 5, 0.0, MONTH)
        long_after = _state(1000.0, 1, 5, 0.0, 10 * MONTH)
        self.assertEqual(at_maturity["payout"], long_after["payout"])
        self.assertEqual(long_after["payout"], 1050.0)

    def test_early_withdraw_returns_principal_only(self):
        st = _state(888.88, 6, 5, 0.0, 5 * MONTH + 100)
        self.assertFalse(st["matured"])
        self.assertEqual(st["payout"], 888.88)
        self.assertEqual(st["interest"], 0.0)

    def test_zero_rate_never_grows(self):
        st = _state(1000.0, 12, 0, 0.0, 12 * MONTH)
        self.assertTrue(st["matured"])
        self.assertEqual(st["payout"], 1000.0)

    def test_negative_rate_clamped_to_zero(self):
        st = _state(1000.0, 1, -5, 0.0, MONTH)
        self.assertEqual(st["payout"], 1000.0)


class FixedDepositRateSettingTests(unittest.TestCase):
    def _economy(self, raw):
        return economy_mod.Economy(None, _FakeSettings({"FIXED_DEPOSIT_MONTHLY_RATE": raw}))

    def test_default_when_missing(self):
        self.assertEqual(
            economy_mod.Economy(None, _FakeSettings({})).get_fixed_deposit_monthly_rate(),
            Economy.DEFAULT_FIXED_DEPOSIT_MONTHLY_RATE,
        )

    def test_valid_percent_value(self):
        self.assertEqual(self._economy("5").get_fixed_deposit_monthly_rate(), 5.0)
        self.assertEqual(self._economy("2.5").get_fixed_deposit_monthly_rate(), 2.5)

    def test_invalid_falls_back_to_default(self):
        self.assertEqual(
            self._economy("abc").get_fixed_deposit_monthly_rate(),
            Economy.DEFAULT_FIXED_DEPOSIT_MONTHLY_RATE,
        )

    def test_negative_clamped_to_zero(self):
        self.assertEqual(self._economy("-3").get_fixed_deposit_monthly_rate(), 0.0)


class FixedDepositTermChoicesTests(unittest.TestCase):
    def test_term_choices(self):
        self.assertEqual(Economy.FIXED_DEPOSIT_TERM_CHOICES, (1, 3, 6, 12))

    def test_month_seconds_is_thirty_days(self):
        self.assertEqual(MONTH, 30 * 24 * 3600)


if __name__ == "__main__":
    unittest.main()
