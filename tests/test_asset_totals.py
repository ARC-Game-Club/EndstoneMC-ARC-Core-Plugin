# -*- coding: utf-8 -*-
"""资产评估合计（Economy.get_fixed_deposits_total_by_xuid /
LandSystem.get_player_lands_total_value）单测：拍卖验资等场景的数据源"""
import importlib.util
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "endstone_arc_core"


def _load(py_name, mod_name):
    _spec = importlib.util.spec_from_file_location(mod_name, _SRC / py_name)
    mod = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(mod)
    return mod


class FixedDepositsTotalTests(unittest.TestCase):
    def _economy(self, deposits):
        economy_mod = _load("Economy.py", "economy_under_test_totals")
        Economy = economy_mod.Economy

        class _Stub(Economy):
            def __init__(self, rows):
                self._rows = rows

            def list_fixed_deposits_by_xuid(self, xuid):
                return list(self._rows)

        return _Stub(deposits)

    def test_empty_is_zero(self):
        self.assertEqual(self._economy([]).get_fixed_deposits_total_by_xuid("x1"), 0.0)

    def test_sums_principal(self):
        rows = [{"amount": 1000.0}, {"amount": 250.5}, {"amount": 49.5}]
        self.assertEqual(self._economy(rows).get_fixed_deposits_total_by_xuid("x1"), 1300.0)

    def test_ignores_bad_amounts(self):
        rows = [{"amount": 100.0}, {"amount": None}, {"amount": "abc"}, {}]
        self.assertEqual(self._economy(rows).get_fixed_deposits_total_by_xuid("x1"), 100.0)

    def test_rounded_to_cents(self):
        rows = [{"amount": 0.1}, {"amount": 0.2}]
        self.assertEqual(
            self._economy(rows).get_fixed_deposits_total_by_xuid("x1"), 0.3)


class PlayerLandsTotalValueTests(unittest.TestCase):
    def _land_system(self, lands):
        land_mod = _load("LandSystem.py", "land_system_under_test_totals")
        LandSystem = land_mod.LandSystem

        class _Stub(LandSystem):
            def __init__(self, data):
                self._data = data

            def get_player_lands(self, xuid):
                return dict(self._data)

        return _Stub(lands)

    def test_no_lands_is_zero(self):
        self.assertEqual(self._land_system({}).get_player_lands_total_value("x1"), 0.0)

    def test_sums_owner_paid_money(self):
        lands = {
            1: {"owner_paid_money": 2500.0, "land_name": "a"},
            2: {"owner_paid_money": 117.5, "land_name": "b"},
        }
        self.assertEqual(self._land_system(lands).get_player_lands_total_value("x1"), 2617.5)

    def test_treats_missing_value_as_zero(self):
        lands = {1: {"owner_paid_money": 0}, 2: {"land_name": "未付钱"}}
        self.assertEqual(self._land_system(lands).get_player_lands_total_value("x1"), 0.0)

    def test_rounded_to_cents(self):
        lands = {
            1: {"owner_paid_money": 0.1},
            2: {"owner_paid_money": 0.2},
        }
        self.assertEqual(self._land_system(lands).get_player_lands_total_value("x1"), 0.3)


if __name__ == "__main__":
    unittest.main()
