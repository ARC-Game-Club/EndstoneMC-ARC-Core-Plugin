# -*- coding: utf-8 -*-
"""邮件系统逻辑：个人/全服邮件、附件（物品+金币）、已读与领取状态、过期清理。

跨服说明：mail_id 用 uuid（而非自增 id），任意服发件经同步中心 REPLACE 落库都
不会撞号；全服邮件的已读/领取状态在 player_mail_claim 按 (mail_id, xuid) 记录。
本模块只负责数据与状态，不含 UI 与物品发放（由插件层分发）。
"""
import json
import math
import time
import uuid
from typing import Any, Dict, List, Optional


class MailSystem:
    """邮件系统：player_mail / player_mail_claim 两表的数据逻辑。"""

    MAIL_TABLE = "player_mail"
    MAIL_CLAIM_TABLE = "player_mail_claim"
    # receiver_xuid 为空串表示全服邮件
    GLOBAL_XUID = ""
    # 单封邮件附件物品条数上限（背包发放按条 give，防刷屏）
    MAX_ATTACHMENT_ITEMS = 12
    DEFAULT_EXPIRE_DAYS = 30.0

    def __init__(self, database_manager, setting_manager, logger=None):
        self.db = database_manager
        self.setting_manager = setting_manager
        self.logger = logger

    def _log(self, level: str, message: str):
        if self.logger:
            getattr(self.logger, level, self.logger.info)(message)
        else:
            print(f"[{level.upper()}] {message}")

    # ------------------------------------------------------------------ 建表

    def init_mail_tables(self) -> bool:
        ok = self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.MAIL_TABLE} (
                mail_id TEXT PRIMARY KEY,
                receiver_xuid TEXT NOT NULL DEFAULT '',
                receiver_name TEXT NOT NULL DEFAULT '',
                sender_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                items_json TEXT NOT NULL DEFAULT '[]',
                money REAL NOT NULL DEFAULT 0,
                is_global INTEGER NOT NULL DEFAULT 0,
                claimed INTEGER NOT NULL DEFAULT 0,
                claimed_at REAL NOT NULL DEFAULT 0,
                read_flag INTEGER NOT NULL DEFAULT 0,
                send_time REAL NOT NULL DEFAULT 0,
                expire_time REAL NOT NULL DEFAULT 0
            )
            """
        )
        ok = self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.MAIL_CLAIM_TABLE} (
                mail_id TEXT NOT NULL,
                xuid TEXT NOT NULL,
                read_flag INTEGER NOT NULL DEFAULT 0,
                claimed INTEGER NOT NULL DEFAULT 0,
                claimed_at REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (mail_id, xuid)
            )
            """
        ) and ok
        # 高频查询：按收件人查个人邮件 / 按玩家查全服邮件领取状态
        self.db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_player_mail_receiver "  # nosec B608
            f"ON {self.MAIL_TABLE} (receiver_xuid, send_time)"
        )
        self.db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_player_mail_claim_xuid "  # nosec B608
            f"ON {self.MAIL_CLAIM_TABLE} (xuid)"
        )
        return ok

    # ------------------------------------------------------------------ 配置

    def get_expire_days(self) -> float:
        """MAIL_EXPIRE_DAYS：>0 为附件/邮件保留天数；<=0 表示永不过期。"""
        try:
            days = float(self.setting_manager.GetSetting("MAIL_EXPIRE_DAYS"))
        except (TypeError, ValueError):
            return self.DEFAULT_EXPIRE_DAYS
        if days != days:  # NaN
            return self.DEFAULT_EXPIRE_DAYS
        return days

    # ------------------------------------------------------------------ 发件

    @staticmethod
    def normalize_items(items: Optional[List]) -> List[Dict[str, Any]]:
        """校验并规整附件物品：[{"item_name"/"type"/"id", "count"}] → 有效条目列表。

        兼容 arc_inventory 的富物品条目：若带 nbt_b64 / enchants / lore / name /
        data 字段则原样保留，发放时可经 arc_inventory 还原完整 NBT（潜影盒内容物、
        附魔、Lore 不丢失）；普通 item_name+count 条目行为不变。
        """
        out: List[Dict[str, Any]] = []
        if not isinstance(items, list):
            return out
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("item_name") or it.get("type") or it.get("id") or "").strip()
            try:
                count = int(it.get("count", 1))
            except (TypeError, ValueError):
                continue
            if not name or count <= 0:
                continue
            entry: Dict[str, Any] = {"item_name": name, "count": count}
            nbt = str(it.get("nbt_b64") or "").strip()
            if nbt:
                entry["nbt_b64"] = nbt
            enchants = it.get("enchants")
            if isinstance(enchants, dict) and enchants:
                entry["enchants"] = {str(k): v for k, v in enchants.items()}
            lore = it.get("lore")
            if isinstance(lore, list) and lore:
                entry["lore"] = [str(x) for x in lore]
            display = str(it.get("name") or "").strip()
            if display:
                entry["name"] = display
            try:
                data = int(it.get("data") or 0)
            except (TypeError, ValueError):
                data = 0
            if data:
                entry["data"] = data
            out.append(entry)
            if len(out) >= MailSystem.MAX_ATTACHMENT_ITEMS:
                break
        return out

    def _expire_time_for(self, expire_days: Optional[float]) -> float:
        if expire_days is None:
            expire_days = self.get_expire_days()
        try:
            days = float(expire_days)
        except (TypeError, ValueError):
            days = self.DEFAULT_EXPIRE_DAYS
        if days <= 0:
            return 0.0
        return time.time() + days * 86400.0

    def send_mail(
        self,
        receiver_xuid: str,
        receiver_name: str = "",
        sender_name: str = "",
        title: str = "",
        content: str = "",
        items: Optional[List] = None,
        money: float = 0.0,
        expire_days: Optional[float] = None,
    ) -> str:
        """发一封个人邮件。返回 mail_id；参数无效返回空串。"""
        receiver_xuid = str(receiver_xuid or "").strip()
        if not receiver_xuid:
            return ""
        return self._insert_mail(
            receiver_xuid=receiver_xuid,
            receiver_name=str(receiver_name or "").strip(),
            sender_name=sender_name,
            title=title,
            content=content,
            items=items,
            money=money,
            expire_days=expire_days,
        )

    def send_global_mail(
        self,
        sender_name: str = "",
        title: str = "",
        content: str = "",
        items: Optional[List] = None,
        money: float = 0.0,
        expire_days: Optional[float] = None,
    ) -> str:
        """发一封全服邮件（所有玩家各自领取附件）。返回 mail_id。"""
        return self._insert_mail(
            receiver_xuid=self.GLOBAL_XUID,
            receiver_name="",
            sender_name=sender_name,
            title=title,
            content=content,
            items=items,
            money=money,
            expire_days=expire_days,
        )

    def _insert_mail(
        self,
        receiver_xuid: str,
        receiver_name: str,
        sender_name: str,
        title: str,
        content: str,
        items: Optional[List],
        money: float,
        expire_days: Optional[float],
    ) -> str:
        norm_items = self.normalize_items(items)
        try:
            money_val = max(0.0, round(float(money or 0), 2))
        except (TypeError, ValueError):
            money_val = 0.0
        mail_id = uuid.uuid4().hex
        row = {
            "mail_id": mail_id,
            "receiver_xuid": receiver_xuid,
            "receiver_name": receiver_name,
            "sender_name": str(sender_name or "").strip(),
            "title": str(title or "").strip(),
            "content": str(content or ""),
            "items_json": json.dumps(norm_items, ensure_ascii=False),
            "money": money_val,
            "is_global": 1 if receiver_xuid == self.GLOBAL_XUID else 0,
            "claimed": 0,
            "claimed_at": 0,
            "read_flag": 0,
            "send_time": time.time(),
            "expire_time": self._expire_time_for(expire_days),
        }
        if not self.db.insert(self.MAIL_TABLE, row):
            return ""
        return mail_id

    # ------------------------------------------------------------------ 查询

    def get_mail(self, mail_id: str) -> Optional[Dict[str, Any]]:
        mail_id = str(mail_id or "").strip()
        if not mail_id:
            return None
        return self.db.query_one(
            f"SELECT * FROM {self.MAIL_TABLE} WHERE mail_id = ?",  # nosec B608
            (mail_id,),
        )

    def list_mails_for_xuid(self, xuid: str, limit: int = 100) -> List[Dict[str, Any]]:
        """玩家邮箱视图：个人邮件 + 全服邮件合并，新邮件在前。

        每封附带视图字段：unread / claimed / has_attachment / is_global。
        """
        xuid = str(xuid or "").strip()
        if not xuid:
            return []
        try:
            lim = max(1, min(500, int(limit)))
        except (TypeError, ValueError):
            lim = 100
        personal = self.db.query_all(
            f"SELECT * FROM {self.MAIL_TABLE} "  # nosec B608
            f"WHERE receiver_xuid = ? ORDER BY send_time DESC LIMIT {lim}",
            (xuid,),
        )
        global_rows = self.db.query_all(
            f"SELECT * FROM {self.MAIL_TABLE} "  # nosec B608
            f"WHERE is_global = 1 ORDER BY send_time DESC LIMIT {lim}"
        )
        merged = list(personal) + list(global_rows)
        merged.sort(key=lambda r: float(r.get("send_time") or 0), reverse=True)
        now = time.time()
        views = []
        for row in merged[:lim]:
            if self._is_expired_row(row, now):
                continue
            views.append(self.build_view(row, xuid))
        return views

    def _is_expired_row(self, row: Dict[str, Any], now: Optional[float] = None) -> bool:
        expire = float(row.get("expire_time") or 0)
        if expire <= 0:
            return False
        if now is None:
            now = time.time()
        return now >= expire

    def build_view(self, row: Dict[str, Any], xuid: str) -> Dict[str, Any]:
        """行数据 → 玩家视角视图：补充已读/领取/附件信息。"""
        view = dict(row)
        try:
            items = json.loads(str(view.get("items_json") or "[]"))
        except (TypeError, ValueError):
            items = []
        view["items"] = items if isinstance(items, list) else []
        view["is_global"] = int(view.get("is_global") or 0)
        if view["is_global"]:
            state = self.db.query_one(
                f"SELECT read_flag, claimed FROM {self.MAIL_CLAIM_TABLE} "  # nosec B608
                f"WHERE mail_id = ? AND xuid = ?",
                (str(view.get("mail_id")), str(xuid)),
            ) or {}
            view["read_flag"] = int(state.get("read_flag") or 0)
            view["claimed"] = int(state.get("claimed") or 0)
        else:
            view["read_flag"] = int(view.get("read_flag") or 0)
            view["claimed"] = int(view.get("claimed") or 0)
        try:
            money = float(view.get("money") or 0)
        except (TypeError, ValueError):
            money = 0.0
        view["money"] = money
        view["has_attachment"] = bool(view["items"]) or money > 0
        view["unread"] = view["read_flag"] == 0
        view["unclaimed"] = view["has_attachment"] and view["claimed"] == 0
        expire = float(view.get("expire_time") or 0)
        view["remaining_days"] = (
            None if expire <= 0
            else max(0, math.ceil((expire - time.time()) / 86400.0))
        )
        return view

    def count_unread(self, xuid: str) -> int:
        xuid = str(xuid or "").strip()
        if not xuid:
            return 0
        return sum(1 for view in self.list_mails_for_xuid(xuid) if view["unread"])

    def count_unclaimed(self, xuid: str) -> int:
        """有附件且未领取的邮件数（供列表页/进服提示）。"""
        count = 0
        for view in self.list_mails_for_xuid(xuid):
            if view["unclaimed"]:
                count += 1
        return count

    # ------------------------------------------------------------------ 已读 / 领取状态

    def mark_read(self, mail_id: str, xuid: str) -> bool:
        mail_id = str(mail_id or "").strip()
        xuid = str(xuid or "").strip()
        if not mail_id or not xuid:
            return False
        row = self.get_mail(mail_id)
        if not row:
            return False
        if int(row.get("is_global") or 0):
            return self._upsert_claim_state(mail_id, xuid, read_flag=1)
        return self.db.execute(
            f"UPDATE {self.MAIL_TABLE} SET read_flag = 1 WHERE mail_id = ? AND read_flag = 0",  # nosec B608
            (mail_id,),
        )

    def try_mark_claimed(self, mail_id: str, xuid: str) -> bool:
        """把附件标记为已领取；返回 False 表示邮件不存在或已被领取。

        用条件 UPDATE（claimed=0 → 1）保证同一封邮件不会重复发放。
        """
        mail_id = str(mail_id or "").strip()
        xuid = str(xuid or "").strip()
        if not mail_id or not xuid:
            return False
        row = self.get_mail(mail_id)
        if not row:
            return False
        now = time.time()
        if int(row.get("is_global") or 0):
            # 先确保状态行存在（可能已因“已读”写入过），再条件置为已领取
            self._upsert_claim_state(mail_id, xuid, read_flag=1)
            updated = self.db.execute_and_get_rowcount(
                f"UPDATE {self.MAIL_CLAIM_TABLE} SET claimed = 1, claimed_at = ?, read_flag = 1 "  # nosec B608
                f"WHERE mail_id = ? AND xuid = ? AND claimed = 0",
                (now, mail_id, xuid),
            )
            return updated == 1
        updated = self.db.execute_and_get_rowcount(
            f"UPDATE {self.MAIL_TABLE} SET claimed = 1, claimed_at = ?, read_flag = 1 "  # nosec B608
            f"WHERE mail_id = ? AND claimed = 0",
            (now, mail_id),
        )
        return updated == 1

    def _upsert_claim_state(self, mail_id: str, xuid: str, read_flag: int = 0, claimed: int = 0) -> bool:
        """全服邮件的个人状态行：无则插入，有则按位补写。"""
        existing = self.db.query_one(
            f"SELECT mail_id FROM {self.MAIL_CLAIM_TABLE} WHERE mail_id = ? AND xuid = ?",  # nosec B608
            (mail_id, xuid),
        )
        if existing is None:
            return self.db.insert(
                self.MAIL_CLAIM_TABLE,
                {"mail_id": mail_id, "xuid": xuid,
                 "read_flag": int(read_flag), "claimed": int(claimed),
                 "claimed_at": time.time() if claimed else 0},
            )
        return self.db.execute(
            f"UPDATE {self.MAIL_CLAIM_TABLE} SET read_flag = MAX(read_flag, ?), "  # nosec B608
            f"claimed = MAX(claimed, ?) WHERE mail_id = ? AND xuid = ?",
            (int(read_flag), int(claimed), mail_id, xuid),
        )

    # ------------------------------------------------------------------ 清理 / 删除

    def purge_expired(self, now: Optional[float] = None) -> int:
        """删除过期邮件（附件随之作废）并清掉孤儿领取状态行。返回删除邮件数。"""
        if now is None:
            now = time.time()
        removed = 0
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM player_mail WHERE expire_time > 0 AND expire_time <= ?",
            (now,),
        )
        if row:
            removed = int(row.get("n") or 0)
        self.db.execute(
            f"DELETE FROM {self.MAIL_TABLE} WHERE expire_time > 0 AND expire_time <= ?",  # nosec B608
            (now,),
        )
        self.db.execute(
            f"DELETE FROM {self.MAIL_CLAIM_TABLE} WHERE mail_id NOT IN "  # nosec B608
            f"(SELECT mail_id FROM {self.MAIL_TABLE})",
        )
        return removed

    def delete_mail(self, mail_id: str) -> bool:
        """OP 删除指定邮件（含其全部领取状态行）。"""
        mail_id = str(mail_id or "").strip()
        if not mail_id:
            return False
        ok = self.db.execute(
            f"DELETE FROM {self.MAIL_TABLE} WHERE mail_id = ?",  # nosec B608
            (mail_id,),
        )
        self.db.execute(
            f"DELETE FROM {self.MAIL_CLAIM_TABLE} WHERE mail_id = ?",  # nosec B608
            (mail_id,),
        )
        return ok

    def list_recent_mails(self, limit: int = 30) -> List[Dict[str, Any]]:
        """OP 管理视图：最近的全部邮件（含个人/全服）。"""
        try:
            lim = max(1, min(200, int(limit)))
        except (TypeError, ValueError):
            lim = 30
        rows = self.db.query_all(
            f"SELECT * FROM {self.MAIL_TABLE} ORDER BY send_time DESC LIMIT {lim}",  # nosec B608
            (),
        )
        for row in rows:
            try:
                items = json.loads(str(row.get("items_json") or "[]"))
            except (TypeError, ValueError):
                items = []
            row["items"] = items if isinstance(items, list) else []
            row["is_global"] = int(row.get("is_global") or 0)
        return rows
