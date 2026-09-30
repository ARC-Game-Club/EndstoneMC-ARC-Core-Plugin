# -*- coding: utf-8 -*-
"""NewbieBookStore 回归测试：书式新手引导的种子/迁移/规范化/原子保存。"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "endstone_arc_core"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# 直接按文件路径加载（绕开会导入 endstone 的包 __init__）
_spec = importlib.util.spec_from_file_location(
    "endstone_arc_core.newbie_book", _SRC / "newbie_book.py"
)
_newbie_book = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _newbie_book
assert _spec.loader is not None
_spec.loader.exec_module(_newbie_book)

NewbieBookStore = _newbie_book.NewbieBookStore
book_to_plain_text = _newbie_book.book_to_plain_text
default_book = _newbie_book.default_book
legacy_welcome_section = _newbie_book.legacy_welcome_section
load_book = _newbie_book.load_book
normalize_multiline_text = _newbie_book.normalize_multiline_text
normalize_single_line = _newbie_book.normalize_single_line
save_book = _newbie_book.save_book
seed_book = _newbie_book.seed_book


class NormalizeTest(unittest.TestCase):
    def test_multiline_literal_newlines(self):
        self.assertEqual(normalize_multiline_text("a\\nb"), "a\nb")
        self.assertEqual(normalize_multiline_text("a\r\nb\rc"), "a\nb\nc")
        self.assertEqual(normalize_multiline_text("  a \\n b  "), "a \n b")

    def test_multiline_truncate(self):
        self.assertEqual(normalize_multiline_text("x" * 50, max_len=10), "x" * 10)

    def test_single_line_collapses_newlines(self):
        self.assertEqual(normalize_single_line("a\\nb\nc", 32), "a b c")
        self.assertEqual(normalize_single_line("x" * 40, 32), "x" * 32)

    def test_none_safe(self):
        self.assertEqual(normalize_multiline_text(None), "")
        self.assertEqual(normalize_single_line(None, 16), "")


class LegacyMigrationTest(unittest.TestCase):
    def test_legacy_section_skipped_for_default_text(self):
        legacy = "欢迎来到我们的服务器！\n希望你在这里玩得愉快！\n如有疑问请联系管理员。"
        self.assertIsNone(legacy_welcome_section(legacy))

    def test_legacy_section_created_for_real_text(self):
        section = legacy_welcome_section("旧版第一行\n旧版第二行")
        self.assertIsNotNone(section)
        self.assertEqual(section["name"], "旧版教学")
        self.assertEqual(len(section["chapters"]), 1)
        self.assertIn("旧版第一行", section["chapters"][0]["content"])

    def test_seed_appends_legacy(self):
        book = seed_book("自定义旧文本")
        self.assertEqual(book["sections"][-1]["name"], "旧版教学")
        self.assertEqual(book["sections"][0]["name"], "插件")
        self.assertEqual(book["sections"][1]["name"], "模组")

    def test_seed_without_legacy(self):
        book = seed_book("")
        self.assertEqual([s["name"] for s in book["sections"]], ["插件", "模组"])


class StoreTest(unittest.TestCase):
    def test_missing_book_file_seeded_from_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            legacy = base / "newbie_welcome.txt"
            legacy.write_text("旧版教学全文", encoding="utf-8")
            store = NewbieBookStore(base, legacy_welcome_path=legacy)
            self.assertTrue((base / "newbie_book.json").exists())
            self.assertEqual(store.data["sections"][-1]["name"], "旧版教学")
            # 再次加载直接读 JSON，不再重复迁移
            again = NewbieBookStore(base, legacy_welcome_path=legacy)
            self.assertEqual(again.data["title"], store.data["title"])

    def test_corrupt_json_falls_back_to_existing_memory(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = NewbieBookStore(base)
            store.data["title"] = "手改标题"
            store.save()
            (base / "newbie_book.json").write_text("{broken", encoding="utf-8")
            store.reload()
            self.assertEqual(store.data["title"], "手改标题")

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = NewbieBookStore(base)
            store.data["title"] = "测试书"
            store.data["sections"].append(
                {"name": "规则", "intro": "规则介绍\\n第二行", "chapters": []}
            )
            store.save()
            loaded = load_book(base / "newbie_book.json")
            self.assertEqual(loaded["title"], "测试书")
            self.assertEqual(loaded["sections"][-1]["name"], "规则")
            self.assertEqual(loaded["sections"][-1]["intro"], "规则介绍\n第二行")

    def test_accessors_bounds(self):
        with tempfile.TemporaryDirectory() as td:
            store = NewbieBookStore(Path(td))
            self.assertEqual(store.count_sections(), 2)
            self.assertIsNone(store.get_section(9))
            self.assertIsNone(store.get_chapter(0, 9))
            self.assertEqual(store.get_chapter(0, 0)["title"], "示例：每日签到")

    def test_reset_to_default_restores_seed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = NewbieBookStore(base)
            store.data["sections"] = []
            store.save()
            store.reset_to_default(keep_legacy=True)
            self.assertGreaterEqual(len(store.data["sections"]), 2)


class PlainTextTest(unittest.TestCase):
    def test_book_to_plain_text(self):
        book = default_book()
        text = book_to_plain_text(book)
        self.assertIn("新手手册", text)
        self.assertIn("■ 插件", text)
        self.assertIn("· 示例：每日签到", text)

    def test_truncate_cap(self):
        book = default_book()
        book["intro"] = "很长的简介" * 1000
        self.assertLessEqual(len(book_to_plain_text(book, max_len=50)), 50)

    def test_empty_book(self):
        self.assertEqual(book_to_plain_text({}), "")


class JsonIoTest(unittest.TestCase):
    def test_save_creates_dirs_and_atomic_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sub" / "newbie_book.json"
            save_book(path, {"title": "x"})
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["title"], "x")
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_load_missing_returns_none(self):
        self.assertIsNone(load_book(Path("Z:/definitely/not/here.json")))


if __name__ == "__main__":
    unittest.main()
