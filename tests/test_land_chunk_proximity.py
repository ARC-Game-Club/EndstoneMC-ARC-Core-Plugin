# -*- coding: utf-8 -*-
"""api_has_land_nearby_chunk / has_any_land_nearby_chunk 的区块邻近查询。

领地按区块映射表登记（chunk_key = "cx_cz" → land_ids）；本用例用内存
stub 复刻该表，验证 3x3 半径判定与边界（相邻区块命中、两格外不命中）。
按仓库惯例（test_asset_totals）：importlib 直载模块，stub 掉包级
dimension_utils 依赖，不触发 endstone 导入。
"""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "endstone_arc_core"


def _prepare_stubs():
    pkg = types.ModuleType("endstone_arc_core")
    pkg.__path__ = []
    du = types.ModuleType("endstone_arc_core.dimension_utils")
    du.chunk_table_suffix = lambda dim: str(dim or "overworld").strip().lower()
    du.normalize_dimension_id = lambda dim: str(dim or "overworld").strip().lower()
    sys.modules.setdefault("endstone_arc_core", pkg)
    sys.modules["endstone_arc_core.dimension_utils"] = du


def _load_land_system():
    spec = importlib.util.spec_from_file_location(
        "land_system_under_test_chunk", _SRC / "LandSystem.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.LandSystem


def land_row(land_id, min_x, max_x, min_z, max_z):
    """一条能过 _parse_land_row 的完整 lands 行。"""
    return {
        "land_id": land_id, "land_name": f"L{land_id}", "dimension": "overworld",
        "min_x": min_x, "max_x": max_x, "min_z": min_z, "max_z": max_z,
        "tp_x": min_x, "tp_y": 64, "tp_z": min_z,
        "shared_users": "[]", "owner_xuid": "1234567890123456",
    }


class StubDB:
    """只实现查询路径上用到的三个方法。"""

    def __init__(self, chunk_map, lands):
        self._chunk_map = chunk_map     # {"cx_cz": [land_id, ...]}
        self._lands = lands             # {land_id: row}

    def table_exists(self, table):
        return True

    def create_table(self, *a, **k):
        return True

    def query_one(self, sql, params=()):
        if sql.startswith("SELECT land_ids FROM"):
            ids = self._chunk_map.get(params[0])
            return {"land_ids": json.dumps(ids)} if ids else None
        if sql.startswith("SELECT * FROM lands"):
            return self._lands.get(params[0])
        return None


class StubSettings:
    def GetSetting(self, key, default=None):
        return default if default is not None else "0"


class LandChunkProximityTests(unittest.TestCase):
    def _system(self, chunk_map, lands):
        _prepare_stubs()
        LandSystem = _load_land_system()
        return LandSystem(StubDB(chunk_map, lands), StubSettings())

    def test_land_in_center_chunk(self):
        ls = self._system(
            {"3_5": [10]},
            {10: land_row(10, 48, 60, 80, 90)})
        self.assertTrue(ls.has_any_land_nearby_chunk("overworld", 3, 5))

    def test_land_in_adjacent_chunk_inside_radius(self):
        # 领地登记在 (4,6)；查 (3,5) 的 3x3 邻域 → 相邻区块，应命中
        ls = self._system(
            {"4_6": [10]},
            {10: land_row(10, 64, 70, 96, 100)})
        self.assertTrue(ls.has_any_land_nearby_chunk("overworld", 3, 5, radius=1))
        # 半径收到 0 就只剩中心区块 → 不命中
        self.assertFalse(ls.has_any_land_nearby_chunk("overworld", 3, 5, radius=0))

    def test_land_two_chunks_away_outside_radius(self):
        ls = self._system(
            {"5_7": [10]},
            {10: land_row(10, 0, 9, 0, 9)})
        self.assertFalse(ls.has_any_land_nearby_chunk("overworld", 3, 5, radius=1))
        self.assertTrue(ls.has_any_land_nearby_chunk("overworld", 3, 5, radius=2))

    def test_wilderness_empty(self):
        ls = self._system({}, {})
        self.assertFalse(ls.has_any_land_nearby_chunk("overworld", 0, 0))


if __name__ == "__main__":
    unittest.main()
