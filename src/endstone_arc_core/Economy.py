# -*- coding: utf-8 -*-
"""经济系统逻辑：金钱存储、增减、排行等（基于 XUID，精确到分）"""
import time
from typing import Any, Callable, Dict, List, Optional


class Economy:
    """经济系统：负责 player_economy 表及金钱相关数据逻辑，不包含 UI 与通知。"""

    # 定期存款：30 天记 1 个月，按月复利；到期前支取仅返还本金，到期后利息封顶（不自动续存）
    FIXED_DEPOSIT_TABLE = "player_fixed_deposit"
    MONTH_SECONDS = 30 * 24 * 3600
    FIXED_DEPOSIT_TERM_CHOICES = (1, 3, 6, 12)
    DEFAULT_FIXED_DEPOSIT_MONTHLY_RATE = 5.0

    def __init__(self, database_manager, setting_manager, logger=None):
        self.db = database_manager
        self.setting_manager = setting_manager
        self.logger = logger
        self._persistent_error_cb: Optional[Callable[[str, str, Optional[BaseException]], None]] = None
        self._balance_changed_cb: Optional[Callable[[str], None]] = None

    def set_persistent_error_callback(
        self, callback: Optional[Callable[[str, str, Optional[BaseException]], None]]
    ) -> None:
        """由插件注册：仅写入 error_log / 控制台，不向玩家发消息。"""
        self._persistent_error_cb = callback

    def set_balance_changed_callback(
        self, callback: Optional[Callable[[str], None]]
    ) -> None:
        """余额写入成功后回调（参数为 xuid），供侧边栏等订阅。"""
        self._balance_changed_cb = callback

    def _emit_persistent_error(
        self, error_code: str, detail: str, exc: Optional[BaseException] = None
    ) -> None:
        if self._persistent_error_cb:
            try:
                self._persistent_error_cb(error_code, detail, exc)
            except Exception as cb_err:
                self._log("warning", f"persistent error callback failed: {cb_err}")

    def set_logger(self, logger):
        """设置日志记录器（插件 on_enable 后调用）"""
        self.logger = logger

    def _log(self, level: str, message: str):
        if self.logger:
            if level == "error":
                self.logger.error(message)
            elif level == "warning":
                self.logger.warning(message)
            else:
                self.logger.info(message)
        else:
            print(f"[{level.upper()}] {message}")

    @staticmethod
    def round_money(value: float) -> float:
        """将金额四舍五入到分（两位小数）"""
        return round(float(value), 2)

    def format_money_display(self, value: float) -> str:
        """格式化金额用于界面显示（始终两位小数）"""
        return "%.2f" % self.round_money(value)

    def init_economy_table(self) -> bool:
        """初始化经济系统表格（money 使用 REAL，支持小数到分）"""
        fields = {
            "xuid": "TEXT PRIMARY KEY",
            "money": "REAL NOT NULL DEFAULT 0",
        }
        return self.db.create_table("player_economy", fields)

    def upgrade_player_economy_table_to_float(self) -> bool:
        """若 player_economy 表中 money 列为 INTEGER，则迁移为 REAL（仅执行一次）"""
        try:
            if not self.db.table_exists("player_economy"):
                return True
            columns_info = self.db.query_all("PRAGMA table_info(player_economy)")
            money_type = None
            for col in columns_info:
                if col.get("name") == "money":
                    money_type = str(col.get("type", "")).upper()
                    break
            if money_type != "INTEGER":
                return True
            ok = self.db.rebuild_table_copy(
                logical_table="player_economy",
                temp_table="player_economy_new",
                create_sql=(
                    "CREATE TABLE player_economy_new "
                    "(xuid TEXT PRIMARY KEY, money REAL NOT NULL DEFAULT 0)"
                ),
                copy_columns=["xuid", "money"],
                select_sql="SELECT xuid, CAST(money AS REAL) FROM player_economy",
            )
            if ok:
                print("[ARC Core]Upgraded player_economy money column to REAL (float).")
            return ok
        except Exception as e:
            print(f"[ARC Core]Upgrade player_economy to float error: {str(e)}")
            self._emit_persistent_error(
                "BANK09", f"upgrade_player_economy_table_to_float: {e}", e
            )
            return False

    def _get_init_money(self) -> float:
        """从配置读取初始金钱"""
        raw = self.setting_manager.GetSetting("PLAYER_INIT_MONEY_NUM")
        try:
            return self.round_money(float(raw))
        except (ValueError, TypeError):
            return 0.0

    def get_player_money_by_xuid(self, xuid: str) -> float:
        """
        按 XUID 获取玩家金钱；若记录不存在则创建并返回初始金钱。
        :return: 金钱数量（精确到分）
        """
        try:
            result = self.db.query_one(
                "SELECT money FROM player_economy WHERE xuid = ?", (xuid,)
            )
            if result is None:
                init_money = self._get_init_money()
                self.db.insert("player_economy", {"xuid": xuid, "money": init_money})
                return init_money
            return self.round_money(result["money"])
        except Exception as e:
            self._log("error", f"[ARC Core]Get player money error: {str(e)}")
            self._emit_persistent_error(
                "BANK01", f"get_player_money_by_xuid xuid={xuid!r}: {e}", e
            )
            return 0.0

    def set_player_money_by_xuid(self, xuid: str, amount: float) -> bool:
        """按 XUID 设置玩家金钱（仅数据，不通知）"""
        try:
            amount = self.round_money(amount)
            ok = self.db.update(
                table="player_economy",
                data={"money": amount},
                where="xuid = ?",
                params=(xuid,),
            )
            if not ok:
                self._log(
                    "error",
                    f"[ARC Core]Set player money failed (db returned False) xuid={xuid}",
                )
                self._emit_persistent_error(
                    "BANK02",
                    f"set_player_money_by_xuid xuid={xuid!r} amount={amount} db update returned False",
                    None,
                )
            elif self._balance_changed_cb is not None:
                try:
                    self._balance_changed_cb(str(xuid))
                except Exception as cb_err:
                    self._log(
                        "warning",
                        f"[ARC Core]balance changed callback failed: {cb_err}",
                    )
            return ok
        except Exception as e:
            self._log("error", f"[ARC Core]Set player money error: {str(e)}")
            self._emit_persistent_error(
                "BANK02", f"set_player_money_by_xuid xuid={xuid!r}: {e}", e
            )
            return False

    def increase_player_money_by_xuid(self, xuid: str, amount: float) -> bool:
        """按 XUID 增加玩家金钱（仅数据，不通知）"""
        amount = abs(self.round_money(amount))
        if amount <= 0:
            return True
        current = self.get_player_money_by_xuid(xuid)
        new_money = self.round_money(current + amount)
        return self.set_player_money_by_xuid(xuid, new_money)

    def decrease_player_money_by_xuid(self, xuid: str, amount: float) -> bool:
        """按 XUID 减少玩家金钱（仅数据，不通知）"""
        amount = abs(self.round_money(amount))
        if amount <= 0:
            return True
        current = self.get_player_money_by_xuid(xuid)
        new_money = self.round_money(current - amount)
        return self.set_player_money_by_xuid(xuid, new_money)

    def change_player_money_by_xuid(
        self, xuid: str, money_to_change: float
    ) -> bool:
        """按 XUID 改变玩家金钱（正增负减，仅数据）"""
        m = self.round_money(money_to_change)
        if m == 0:
            return True
        if m > 0:
            return self.increase_player_money_by_xuid(xuid, m)
        return self.decrease_player_money_by_xuid(xuid, abs(m))

    def judge_if_player_has_enough_money_by_xuid(
        self, xuid: str, amount: float
    ) -> bool:
        """按 XUID 判断玩家是否有足够金钱"""
        return self.get_player_money_by_xuid(xuid) >= abs(
            self.round_money(amount)
        )

    def get_top_richest_xuids(self, top_count: int) -> List[Dict[str, Any]]:
        """获取金钱最多的玩家列表，每项为 {'xuid': str, 'money': float}"""
        try:
            return self.db.query_all(
                "SELECT xuid, money FROM player_economy ORDER BY money DESC LIMIT ?",
                (top_count,),
            )
        except Exception as e:
            self._log("error", f"[ARC Core]Get top richest players error: {str(e)}")
            self._emit_persistent_error("BANK03", f"get_top_richest_xuids: {e}", e)
            return []

    def get_player_money_rank_by_xuid(self, xuid: str) -> Optional[int]:
        """按 XUID 获取玩家金钱排名（从 1 开始）"""
        try:
            result = self.db.query_one(
                """
                WITH RankedPlayers AS (
                    SELECT xuid, money,
                    ROW_NUMBER() OVER (ORDER BY money DESC) as rank
                    FROM player_economy
                )
                SELECT rank FROM RankedPlayers WHERE xuid = ?
                """,
                (xuid,),
            )
            return result["rank"] if result else None
        except Exception as e:
            self._log(
                "error", f"[ARC Core]Get player money rank error: {str(e)}"
            )
            self._emit_persistent_error(
                "BANK04", f"get_player_money_rank_by_xuid xuid={xuid!r}: {e}", e
            )
            return None

    def init_player_economy_by_xuid(self, xuid: str) -> bool:
        """按 XUID 初始化玩家经济记录（若已存在则跳过）"""
        try:
            existing = self.db.query_one(
                "SELECT xuid FROM player_economy WHERE xuid = ?", (xuid,)
            )
            if existing:
                return True
            init_money = self._get_init_money()
            return self.db.insert(
                "player_economy", {"xuid": xuid, "money": init_money}
            )
        except Exception as e:
            self._log(
                "error",
                f"[ARC Core]Init player economy info error: {str(e)}",
            )
            self._emit_persistent_error(
                "BANK05", f"init_player_economy_by_xuid xuid={xuid!r}: {e}", e
            )
            return False

    def get_richest_one(self) -> Optional[Dict[str, Any]]:
        """获取最富有的一名玩家，返回 {'xuid': str, 'money': float} 或 None"""
        try:
            return self.db.query_one(
                "SELECT xuid, money FROM player_economy ORDER BY money DESC LIMIT 1"
            )
        except Exception as e:
            self._log(
                "error", f"[ARC Core]Get richest player error: {str(e)}"
            )
            self._emit_persistent_error("BANK06", f"get_richest_one: {e}", e)
            return None

    def get_poorest_one(self) -> Optional[Dict[str, Any]]:
        """获取最贫穷的一名玩家，返回 {'xuid': str, 'money': float} 或 None"""
        try:
            return self.db.query_one(
                "SELECT xuid, money FROM player_economy ORDER BY money ASC LIMIT 1"
            )
        except Exception as e:
            self._log(
                "error", f"[ARC Core]Get poorest player error: {str(e)}"
            )
            self._emit_persistent_error("BANK07", f"get_poorest_one: {e}", e)
            return None

    def get_all_money_raw(self) -> List[Dict[str, Any]]:
        """获取所有玩家的金钱原始数据 [{'xuid': str, 'money': float}, ...]"""
        try:
            return self.db.query_all(
                "SELECT xuid, money FROM player_economy"
            )
        except Exception as e:
            self._log("error", f"[ARC Core]Get all money data error: {str(e)}")
            self._emit_persistent_error("BANK08", f"get_all_money_raw: {e}", e)
            return []

    # ------------------------------------------------------------------
    # 定期存款
    # ------------------------------------------------------------------

    def init_fixed_deposit_table(self) -> bool:
        """初始化定期存款表：每张存单一行，支取即删行，存在即视为存单生效中"""
        fields = {
            "deposit_id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "xuid": "TEXT NOT NULL",
            "amount": "REAL NOT NULL",
            "start_ts": "REAL NOT NULL",
            "term_months": "INTEGER NOT NULL",
        }
        return self.db.create_table(self.FIXED_DEPOSIT_TABLE, fields)

    def get_fixed_deposit_monthly_rate(self) -> float:
        """读取定期存款月利率（百分比数值，如 5 = 5%）；缺省/非法回退默认值"""
        raw = self.setting_manager.GetSetting("FIXED_DEPOSIT_MONTHLY_RATE")
        try:
            rate = float(raw)
        except (ValueError, TypeError):
            return self.DEFAULT_FIXED_DEPOSIT_MONTHLY_RATE
        return max(0.0, rate)

    @staticmethod
    def compute_fixed_deposit_payout(
        amount: float,
        term_months: int,
        monthly_rate: float,
        start_ts: float,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """按月复利计算存单状态与当前可支取金额（纯计算，无 IO）。

        - 30 天记 1 个月，只按完整月计息，不足整月部分不计息；
        - 利息封顶于存期结束（到期后不自动续存，金额保持到支取）；
        - 未到期支取仅返还本金（payout = amount，interest = 0）；
        - monthly_rate 为百分比数值（5 = 5%），负值按 0 处理。
        """
        now_ts = time.time() if now_ts is None else float(now_ts)
        amount = max(0.0, float(amount))
        term_months = max(1, int(term_months))
        rate = max(0.0, float(monthly_rate)) / 100.0
        start_ts = float(start_ts)

        elapsed = now_ts - start_ts
        months_elapsed = max(0, int(elapsed // Economy.MONTH_SECONDS))
        matured = months_elapsed >= term_months
        if matured:
            payout = amount * ((1.0 + rate) ** term_months)
            months_counted = term_months
        else:
            payout = amount
            months_counted = months_elapsed
        remaining_seconds = max(0, int(term_months * Economy.MONTH_SECONDS - elapsed))
        return {
            "matured": matured,
            "months_elapsed": months_elapsed,
            "months_counted": months_counted,
            "payout": Economy.round_money(payout),
            "interest": Economy.round_money(payout - amount),
            "remaining_seconds": remaining_seconds,
        }

    def create_fixed_deposit(self, xuid: str, amount: float, term_months: int) -> bool:
        """新建一张定期存单（调用方需先自行扣减余额）"""
        try:
            return self.db.insert(
                self.FIXED_DEPOSIT_TABLE,
                {
                    "xuid": str(xuid),
                    "amount": self.round_money(amount),
                    "start_ts": float(time.time()),
                    "term_months": int(term_months),
                },
            )
        except Exception as e:
            self._log("error", f"[ARC Core]Create fixed deposit error: {str(e)}")
            self._emit_persistent_error(
                "BANK18",
                f"create_fixed_deposit xuid={xuid!r} amount={amount} term={term_months}: {e}",
                e,
            )
            return False

    def restore_fixed_deposit(
        self, xuid: str, amount: float, start_ts: float, term_months: int
    ) -> bool:
        """按原存入时间回插一张存单（仅用于支取入账失败后的回滚）"""
        try:
            return self.db.insert(
                self.FIXED_DEPOSIT_TABLE,
                {
                    "xuid": str(xuid),
                    "amount": self.round_money(amount),
                    "start_ts": float(start_ts),
                    "term_months": int(term_months),
                },
            )
        except Exception as e:
            self._log("error", f"[ARC Core]Restore fixed deposit error: {str(e)}")
            self._emit_persistent_error(
                "BANK19",
                f"restore_fixed_deposit xuid={xuid!r} amount={amount} start_ts={start_ts}: {e}",
                e,
            )
            return False

    def list_fixed_deposits_by_xuid(self, xuid: str) -> List[Dict[str, Any]]:
        """列出玩家全部生效中的存单（按存入时间升序）"""
        try:
            return self.db.query_all(
                f"SELECT * FROM {self.FIXED_DEPOSIT_TABLE} WHERE xuid = ? ORDER BY start_ts ASC",
                (str(xuid),),
            )
        except Exception as e:
            self._log("error", f"[ARC Core]List fixed deposits error: {str(e)}")
            self._emit_persistent_error(
                "BANK20", f"list_fixed_deposits_by_xuid xuid={xuid!r}: {e}", e
            )
            return []

    def take_fixed_deposit(self, deposit_id: int, xuid: str) -> Optional[Dict[str, Any]]:
        """删除并返回一张属于该玩家的存单；不存在 / 不属于该玩家 / 删除失败返回 None"""
        try:
            row = self.db.query_one(
                f"SELECT * FROM {self.FIXED_DEPOSIT_TABLE} WHERE deposit_id = ? AND xuid = ?",
                (int(deposit_id), str(xuid)),
            )
            if row is None:
                return None
            ok = self.db.delete(
                self.FIXED_DEPOSIT_TABLE, "deposit_id = ?", (int(deposit_id),)
            )
            return row if ok else None
        except Exception as e:
            self._log("error", f"[ARC Core]Take fixed deposit error: {str(e)}")
            self._emit_persistent_error(
                "BANK21",
                f"take_fixed_deposit deposit_id={deposit_id!r} xuid={xuid!r}: {e}",
                e,
            )
            return None

    def count_matured_fixed_deposits_by_xuid(self, xuid: str) -> int:
        """统计玩家已到期、尚未支取的存单数量（进服提醒用）"""
        rate = self.get_fixed_deposit_monthly_rate()
        now_ts = time.time()
        count = 0
        for row in self.list_fixed_deposits_by_xuid(xuid):
            state = self.compute_fixed_deposit_payout(
                row.get("amount", 0.0),
                row.get("term_months", 1),
                rate,
                row.get("start_ts", now_ts),
                now_ts=now_ts,
            )
            if state["matured"]:
                count += 1
        return count
