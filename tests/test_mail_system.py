# -*- coding: utf-8 -*-
"""邮件系统（MailSystem）单测：建表/发件/已读领取状态/过期清理 + 跨服白名单接线"""
import importlib.util
import sys
import tempfile
import time
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = _ROOT / "src" / "endstone_arc_core" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.stdout.flush()
    spec.loader.exec_module(mod)
    return mod


DatabaseManager = _load("DatabaseManager").DatabaseManager
MailSystem = _load("MailSystem").MailSystem
sync_write = _load("sync_write")
sync_config = _load("sync_config")
sync_protocol = _load("sync_protocol")


class _FakeSettings:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def GetSetting(self, key):
        return self.data.get(key)


def _make_mail(data_dir, settings=None):
    db = DatabaseManager(str(Path(data_dir) / "test.db"))
    mail = MailSystem(db, _FakeSettings(settings))
    mail.init_mail_tables()
    return mail


class MailTestBase(unittest.TestCase):
    """Windows 下 sqlite 线程本地连接需显式关闭，否则临时目录清理报文件占用。"""

    def setUp(self):
        self._dbs = []
        self._tds = []

    def tearDown(self):
        for db in self._dbs:
            db.close()
        self._dbs.clear()
        for td in self._tds:
            try:
                td.cleanup()
            except OSError:
                pass
        self._tds.clear()

    def make_mail(self, settings=None):
        td = tempfile.TemporaryDirectory()
        self._tds.append(td)
        db = DatabaseManager(str(Path(td.name) / "test.db"))
        self._dbs.append(db)
        mail = MailSystem(db, _FakeSettings(settings))
        mail.init_mail_tables()
        return mail


class MailSendListTests(MailTestBase):
    def test_send_and_list_personal(self):
        mail = self.make_mail()
        mid = mail.send_mail(
            "xuid_a", "玩家A", "系统", "活动奖励", "感谢参与",
            items=[{"item_name": "minecraft:diamond", "count": 3}],
            money=12.5,
        )
        self.assertTrue(mid)
        views = mail.list_mails_for_xuid("xuid_a")
        self.assertEqual(len(views), 1)
        v = views[0]
        self.assertEqual(v["title"], "活动奖励")
        self.assertTrue(v["unread"])
        self.assertTrue(v["unclaimed"])
        self.assertFalse(v["is_global"])
        self.assertEqual(v["items"][0]["item_name"], "minecraft:diamond")
        self.assertEqual(v["money"], 12.5)
        # 其他玩家看不到
        self.assertEqual(mail.list_mails_for_xuid("xuid_b"), [])
        self.assertEqual(mail.count_unread("xuid_a"), 1)
        self.assertEqual(mail.count_unread("xuid_b"), 0)

    def test_global_mail_visible_to_all_with_per_player_claim(self):
        mail = self.make_mail()
        mid = mail.send_global_mail(
            "系统", "全服福利", "人人有份",
            items=[{"item_name": "minecraft:bread", "count": 8}],
        )
        self.assertTrue(mid)
        for xuid in ("xuid_a", "xuid_b"):
            views = mail.list_mails_for_xuid(xuid)
            self.assertEqual(len(views), 1)
            self.assertTrue(views[0]["is_global"])
            self.assertTrue(views[0]["unclaimed"])
        # A 领取后：A 不可再领，B 仍可领
        self.assertTrue(mail.try_mark_claimed(mid, "xuid_a"))
        self.assertFalse(mail.try_mark_claimed(mid, "xuid_a"))
        va = mail.build_view(mail.get_mail(mid), "xuid_a")
        vb = mail.build_view(mail.get_mail(mid), "xuid_b")
        self.assertTrue(va["claimed"])
        self.assertFalse(vb["claimed"])

    def test_claim_after_read_still_works(self):
        """先读后领：claim 行已存在（read_flag=1）时领取仍应成功。"""
        mail = self.make_mail()
        mid = mail.send_global_mail("系统", "g", "")
        self.assertTrue(mail.mark_read(mid, "xuid_a"))
        self.assertTrue(mail.try_mark_claimed(mid, "xuid_a"))
        self.assertFalse(mail.try_mark_claimed(mid, "xuid_a"))

    def test_personal_claim_once_only(self):
        mail = self.make_mail()
        mid = mail.send_mail("xuid_a", "A", "系统", "t", "c", money=1)
        self.assertTrue(mail.try_mark_claimed(mid, "xuid_a"))
        self.assertFalse(mail.try_mark_claimed(mid, "xuid_a"))
        v = mail.build_view(mail.get_mail(mid), "xuid_a")
        self.assertTrue(v["claimed"])
        self.assertFalse(v["unclaimed"])
        # 已读同时置位
        self.assertEqual(mail.count_unread("xuid_a"), 0)

    def test_mark_read_personal_and_global(self):
        mail = self.make_mail()
        mid_p = mail.send_mail("xuid_a", "A", "系统", "p", "")
        mid_g = mail.send_global_mail("系统", "g", "")
        self.assertTrue(mail.mark_read(mid_p, "xuid_a"))
        self.assertTrue(mail.mark_read(mid_g, "xuid_a"))
        self.assertEqual(mail.count_unread("xuid_a"), 0)
        # B 的全服邮件仍是未读
        self.assertEqual(mail.count_unread("xuid_b"), 1)

    def test_list_newest_first_and_empty_receiver(self):
        mail = self.make_mail()
        first = mail.send_mail("x", "", "s", "old", "")
        time.sleep(0.01)
        second = mail.send_mail("x", "", "s", "new", "")
        views = mail.list_mails_for_xuid("x")
        self.assertEqual([v["mail_id"] for v in views], [second, first])
        self.assertEqual(mail.list_mails_for_xuid(""), [])


class MailExpiryTests(MailTestBase):
    def test_purge_expired_and_orphan_claims(self):
        mail = self.make_mail()
        mid_old = mail.send_global_mail("系统", "old", "", money=5, expire_days=0.0000005)
        mid_keep = mail.send_mail("xuid_a", "A", "系统", "keep", "")
        time.sleep(0.3)
        self.assertEqual(mail.purge_expired(), 1)
        self.assertIsNone(mail.get_mail(mid_old))
        self.assertIsNotNone(mail.get_mail(mid_keep))
        views = mail.list_mails_for_xuid("xuid_a")
        self.assertEqual([v["title"] for v in views], ["keep"])

    def test_zero_expire_days_means_never(self):
        mail = self.make_mail({"MAIL_EXPIRE_DAYS": "0"})
        mid = mail.send_mail("x", "", "s", "forever", "")
        row = mail.get_mail(mid)
        self.assertEqual(float(row["expire_time"]), 0.0)
        self.assertFalse(mail._is_expired_row(row))
        self.assertEqual(mail.purge_expired(), 0)

    def test_default_expire_days(self):
        mail = self.make_mail()
        self.assertEqual(mail.get_expire_days(), MailSystem.DEFAULT_EXPIRE_DAYS)
        mail2 = self.make_mail({"MAIL_EXPIRE_DAYS": "7"})
        self.assertEqual(mail2.get_expire_days(), 7.0)

    def test_expired_rows_hidden_from_list_and_count(self):
        mail = self.make_mail()
        mail.send_mail("x", "", "s", "gone", "", expire_days=0.0000005)
        time.sleep(0.3)
        self.assertEqual(mail.list_mails_for_xuid("x"), [])
        self.assertEqual(mail.count_unread("x"), 0)


class MailItemNormalizationTests(MailTestBase):
    def test_normalize_items(self):
        out = MailSystem.normalize_items(
            [
                {"item_name": "minecraft:diamond", "count": 2},
                {"id": "minecraft:apple"},
                {"item_name": "minecraft:rot", "count": 0},
                {"item_name": "", "count": 3},
                "junk",
                {"item_name": "minecraft:bread", "count": "x"},
            ]
        )
        self.assertEqual(
            out,
            [
                {"item_name": "minecraft:diamond", "count": 2},
                {"item_name": "minecraft:apple", "count": 1},
            ],
        )

    def test_attachment_cap(self):
        items = [{"item_name": f"minecraft:i{n}", "count": 1} for n in range(30)]
        out = MailSystem.normalize_items(items)
        self.assertEqual(len(out), MailSystem.MAX_ATTACHMENT_ITEMS)

    def test_no_attachment_mail_not_claimable_view(self):
        mail = self.make_mail()
        mid = mail.send_mail("x", "", "s", "plain", "hello")
        v = mail.build_view(mail.get_mail(mid), "x")
        self.assertFalse(v["has_attachment"])
        self.assertFalse(v["unclaimed"])


class MailDeleteTests(MailTestBase):
    def test_delete_mail_removes_claims(self):
        mail = self.make_mail()
        mid = mail.send_global_mail("系统", "bye", "")
        mail.mark_read(mid, "xuid_a")
        self.assertTrue(mail.delete_mail(mid))
        self.assertIsNone(mail.get_mail(mid))
        # 孤儿领取行也应被清掉
        leftover = mail.db.query_all(
            "SELECT * FROM player_mail_claim WHERE mail_id = ?", (mid,)
        )
        self.assertEqual(leftover, [])

    def test_recent_list_for_op(self):
        mail = self.make_mail()
        mail.send_mail("x", "甲", "s", "t1", "")
        mail.send_global_mail("s", "t2", "")
        rows = mail.list_recent_mails(10)
        self.assertEqual(len(rows), 2)
        flags = sorted(int(r["is_global"]) for r in rows)
        self.assertEqual(flags, [0, 1])


class MailSyncWiringTests(MailTestBase):
    """邮件两表必须在跨服同步三处白名单里（协议枚举/类别映射/镜像主键）。"""

    def test_protocol_enum_mapping(self):
        self.assertEqual(
            sync_protocol.TABLE_TO_ENUM.get("player_mail"),
            sync_protocol.SyncTable.PLAYER_MAIL,
        )
        self.assertEqual(
            sync_protocol.TABLE_TO_ENUM.get("player_mail_claim"),
            sync_protocol.SyncTable.PLAYER_MAIL_CLAIM,
        )

    def test_category_tables(self):
        self.assertEqual(
            sync_config.SYNC_CATEGORY_TABLES.get("mail"),
            ["player_mail", "player_mail_claim"],
        )
        self.assertIn(
            "SYNC_CLIENT_SYNC_MAIL", sync_config.SYNC_CATEGORY_SETTING_KEYS
        )
        self.assertIn(
            "MAIL_EXPIRE_DAYS", sync_config.SYNC_CATEGORY_SHARED_SETTINGS["mail"]
        )

    def test_mirror_primary_keys(self):
        self.assertEqual(
            sync_write.SYNC_TABLE_PRIMARY_KEYS.get("player_mail"), ("mail_id",)
        )
        self.assertEqual(
            sync_write.SYNC_TABLE_PRIMARY_KEYS.get("player_mail_claim"),
            ("mail_id", "xuid"),
        )

    def test_mail_ids_are_uuid_unique(self):
        mail = self.make_mail()
        ids = {mail.send_mail(f"x{n}", "", "s", "t", "") for n in range(20)}
        self.assertEqual(len(ids), 20)
        self.assertEqual(max(len(i) for i in ids), 32)


if __name__ == "__main__":
    unittest.main()
