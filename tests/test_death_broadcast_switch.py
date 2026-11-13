# -*- coding: utf-8 -*-
"""游戏内死亡播报开关（ENABLE_DEATH_BROADCAST）回归测试。

背景：该设置早就进了 setting_catalog 与 core_setting.yml，但主插件从来没读过它，
所以「游戏内死亡播报」在 OP 面板里关不掉 —— 全服聊天栏照样刷屏（枪战服最吵）。

本用例不复制粘贴逻辑，而是用 AST 从 arc_core_plugin.py 里摘出**真实方法体**来跑：
- 删掉 / 改名 _is_death_broadcast_enabled → 用例直接失败；
- 把发送循环改回无脑全服广播 → 用例直接失败。
"""
import ast
import types
import unittest
from pathlib import Path

_PLUGIN_PATH = Path(__file__).resolve().parents[1] / "src" / "endstone_arc_core" / "arc_core_plugin.py"
_SOURCE = _PLUGIN_PATH.read_text(encoding="utf-8")


def _extract_method(class_name: str, method_name: str):
    """从插件源码 AST 里摘出某个方法的函数对象（测的是真实代码，不是副本）。"""
    tree = ast.parse(_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    src = ast.get_source_segment(_SOURCE, item)
                    assert src, f"无法提取 {class_name}.{method_name} 源码"
                    namespace = {
                        # 方法签名里的注解在 def 时求值，必须给个占位
                        "PlayerDeathEvent": type("PlayerDeathEvent", (), {}),
                        "get_dimension_id": lambda dim: "overworld",
                    }
                    exec(compile(src, str(_PLUGIN_PATH), "exec"), namespace)
                    return namespace[method_name]
    raise AssertionError(f"源码里找不到方法 {class_name}.{method_name}")


class _FakeSettingManager:
    def __init__(self, values):
        self._values = values

    def GetSetting(self, key):
        return self._values.get(key)


class _FakePlayer:
    def __init__(self, name="Steve"):
        self.name = name
        self.xuid = "1234567890"
        self.location = _FakeLocation()
        self.messages = []

    def send_message(self, message):
        self.messages.append(message)


class _FakeLocation:
    dimension = "overworld"
    x = 10.0
    y = 64.0
    z = -20.0


class _FakeEvent:
    def __init__(self, player):
        self.player = player


class _FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, msg):
        self.errors.append(str(msg))

    def warning(self, msg):
        pass


class _FakeLanguageManager:
    def GetText(self, key):
        # 不带占位符：各分支 .format(...) 后仍是同一串文本，测试只关心「有没有发、发给了谁」
        return f"text:{key}"


class _StubPlugin:
    """够 _send_death_broadcast 跑起来的最小桩。"""

    def __init__(self, settings=None, qq_enabled=False, online_count=2):
        self.setting_manager = _FakeSettingManager(settings or {})
        self.language_manager = _FakeLanguageManager()
        self.logger = _FakeLogger()
        self.server = types.SimpleNamespace(
            online_players=[_FakePlayer(f"P{i}") for i in range(online_count)]
        )
        self._qq_enabled = qq_enabled
        self.qq_events = []
        self.title_system = types.SimpleNamespace(get_equipped_title=lambda p: "")
        self._is_death_broadcast_enabled = types.MethodType(
            _extract_method("ARCCorePlugin", "_is_death_broadcast_enabled"), self
        )

    # --- 被测方法依赖的桩 ---
    def format_player_display_label_with_guild(self, raw_name, title, xuid):
        return raw_name

    def _format_death_broadcast_player_display(self, player):
        return player.name

    def _translate_dimension_name(self, raw):
        return "主世界"

    def _get_death_cause(self, event):
        return "player_attack"

    def _translate_death_cause(self, cause):
        return "玩家攻击"

    def _get_entity_name_from_damage_source(self, event):
        return "对手"

    def _is_entity_attack_death_cause(self, cause):
        return True

    def _pick_entity_kill_message_keys(self, cause):
        return ("DEATH_BROADCAST_BY_ENTITY", "DEATH_QQ_BY_ENTITY")

    def _should_send_qq_death_broadcast(self, event):
        return self._qq_enabled

    def _notify_qqsync(self, kind, display_name, raw_name, message):
        self.qq_events.append((kind, message))


class DeathBroadcastSwitchTest(unittest.TestCase):
    def setUp(self):
        self._send = _extract_method("ARCCorePlugin", "_send_death_broadcast")

    def _run(self, settings, qq_enabled=False):
        plugin = _StubPlugin(settings=settings, qq_enabled=qq_enabled)
        event = _FakeEvent(_FakePlayer("死者"))
        self._send(plugin, event)
        return plugin

    # ---------- 开关取值 ----------

    def test_default_on_when_key_missing(self):
        plugin = self._run({})
        self.assertTrue(plugin._is_death_broadcast_enabled())
        for p in plugin.server.online_players:
            self.assertEqual(len(p.messages), 1, "键缺失时应保持默认播报")

    def test_default_on_when_value_empty(self):
        plugin = self._run({"ENABLE_DEATH_BROADCAST": ""})
        self.assertTrue(plugin._is_death_broadcast_enabled())

    def test_explicit_true_enables(self):
        plugin = self._run({"ENABLE_DEATH_BROADCAST": "True"})
        self.assertTrue(plugin._is_death_broadcast_enabled())

    def test_explicit_false_disables(self):
        plugin = self._run({"ENABLE_DEATH_BROADCAST": "False"})
        self.assertFalse(plugin._is_death_broadcast_enabled())

    def test_falsy_aliases_disable(self):
        for raw in ("false", "FALSE", "0", "no", "off", "否", "关闭"):
            with self.subTest(raw=raw):
                plugin = self._run({"ENABLE_DEATH_BROADCAST": raw})
                self.assertFalse(plugin._is_death_broadcast_enabled())

    def test_truthy_aliases_enable(self):
        for raw in ("True", "true", "1", "yes", "on", "是"):
            with self.subTest(raw=raw):
                plugin = self._run({"ENABLE_DEATH_BROADCAST": raw})
                self.assertTrue(plugin._is_death_broadcast_enabled())

    # ---------- 真正的行为：关掉后聊天栏不再刷屏 ----------

    def test_disabled_no_in_game_message(self):
        plugin = self._run({"ENABLE_DEATH_BROADCAST": "False"})
        self.assertEqual(plugin.logger.errors, [], "不应有异常被静默吞掉")
        for p in plugin.server.online_players:
            self.assertEqual(p.messages, [], "关闭后不应有任何在线玩家收到死亡播报")

    def test_enabled_sends_to_all_online_players(self):
        plugin = self._run({"ENABLE_DEATH_BROADCAST": "True"})
        self.assertEqual(plugin.logger.errors, [])
        for p in plugin.server.online_players:
            self.assertEqual(len(p.messages), 1, "开启时应给每个在线玩家发一条")

    def test_qq_broadcast_independent_from_in_game_switch(self):
        """游戏内开关只管聊天栏；群聊播报仍由 QQ_DEATH_BROADCAST_MODE 单独控制。"""
        plugin = self._run({"ENABLE_DEATH_BROADCAST": "False"}, qq_enabled=True)
        self.assertEqual(plugin.qq_events and len(plugin.qq_events), 1)
        for p in plugin.server.online_players:
            self.assertEqual(p.messages, [])

    def test_qq_off_while_in_game_on(self):
        plugin = self._run({"ENABLE_DEATH_BROADCAST": "True"}, qq_enabled=False)
        self.assertEqual(plugin.qq_events, [])
        for p in plugin.server.online_players:
            self.assertEqual(len(p.messages), 1)


if __name__ == "__main__":
    unittest.main()
