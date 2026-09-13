# -*- coding: utf-8 -*-
"""SettingManager 回归测试：配置文件缺失/为空时播种 DATABASE_PATH，不再让主插件初始化崩溃。"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _load_fresh():
    """每次用全新的类字典加载 SettingManager（类变量跨用例共享，需隔离）。"""
    for name in list(sys.modules):
        if name.startswith("endstone_arc_core.SettingManager"):
            del sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        "endstone_arc_core.SettingManager", _SRC / "endstone_arc_core" / "SettingManager.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class SettingManagerSeedTest(unittest.TestCase):
    def test_missing_file_seeded(self):
        with tempfile.TemporaryDirectory() as td:
            mod = _load_fresh()
            orig = mod.MAIN_PATH
            try:
                mod.MAIN_PATH = td
                sm = mod.SettingManager()
                self.assertEqual(sm.GetSetting("DATABASE_PATH"), "ARCCore.db")
                self.assertIn("DATABASE_PATH=ARCCore.db", (Path(td) / "core_setting.yml").read_text(encoding="utf-8"))
            finally:
                mod.MAIN_PATH = orig

    def test_empty_file_seeded(self):
        with tempfile.TemporaryDirectory() as td:
            mod = _load_fresh()
            (Path(td) / "core_setting.yml").write_text("", encoding="utf-8")
            orig = mod.MAIN_PATH
            try:
                mod.MAIN_PATH = td
                sm = mod.SettingManager()
                self.assertEqual(sm.GetSetting("DATABASE_PATH"), "ARCCore.db")
            finally:
                mod.MAIN_PATH = orig

    def test_existing_file_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            mod = _load_fresh()
            (Path(td) / "core_setting.yml").write_text("DATABASE_PATH=my.db\nOTHER=1\n", encoding="utf-8")
            orig = mod.MAIN_PATH
            try:
                mod.MAIN_PATH = td
                sm = mod.SettingManager()
                self.assertEqual(sm.GetSetting("DATABASE_PATH"), "my.db")
            finally:
                mod.MAIN_PATH = orig

    def test_blank_key_value_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            mod = _load_fresh()
            (Path(td) / "core_setting.yml").write_text("DATABASE_PATH=\n", encoding="utf-8")
            orig = mod.MAIN_PATH
            try:
                mod.MAIN_PATH = td
                sm = mod.SettingManager()
                # 已存在但为空的键不播种（保留用户显式配置），由调用方兜底
                self.assertIsNone(sm.GetSetting("DATABASE_PATH"))
            finally:
                mod.MAIN_PATH = orig


if __name__ == "__main__":
    unittest.main()
