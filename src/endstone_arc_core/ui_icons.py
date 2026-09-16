# -*- coding: utf-8 -*-
"""表单按钮图标路径常量，供 ActionForm.add_button(icon=...) 使用。

约定（自定义 RP 贴图）：路径必须带 .png，贴图需存在于客户端已加载的资源包
（弧光核心RP，textures/arc_core/）。客户端缺失贴图时 Bedrock 自动不显示图标；
服务端 UI_ICONS_ENABLED 关闭时由插件整体降级为无图标。
"""

_BASE = "textures/arc_core"

# 主菜单
CHECKIN = f"{_BASE}/checkin.png"
NEWBIE = f"{_BASE}/newbie.png"
TELEPORT = f"{_BASE}/teleport.png"
LAND = f"{_BASE}/land.png"
BANK = f"{_BASE}/bank.png"
TOOLS = f"{_BASE}/tools.png"
OP = f"{_BASE}/op.png"
GUILD = f"{_BASE}/guild.png"

# 传送菜单
WARP = f"{_BASE}/warp.png"
HOME = f"{_BASE}/home.png"
RANDOM_TP = f"{_BASE}/random_tp.png"
DEATH_TP = f"{_BASE}/death_tp.png"
TPA = f"{_BASE}/tpa.png"
CROSS_SERVER = f"{_BASE}/cross_server.png"

# 银行
TRANSFER = f"{_BASE}/transfer.png"
MONEY_RANK = f"{_BASE}/money_rank.png"

# 邮箱
MAIL = f"{_BASE}/mail.png"

# 领地
LAND_MANAGE = f"{_BASE}/land_manage.png"
LAND_CREATE = f"{_BASE}/land_create.png"
LAND_CHECK = f"{_BASE}/land_check.png"

# 工具 / 我的信息
MY_INFO = f"{_BASE}/my_info.png"
HORN = f"{_BASE}/horn.png"
SUICIDE = f"{_BASE}/suicide.png"
FILL_INVITER = f"{_BASE}/fill_inviter.png"
CLAIM_REWARD = f"{_BASE}/claim_reward.png"
TITLE_MANAGE = f"{_BASE}/title_manage.png"
ACHIEVEMENTS = f"{_BASE}/achievements.png"
CHANGE_PASSWORD = f"{_BASE}/change_password.png"

# OP 面板
OP_RELOAD = f"{_BASE}/op_reload.png"
OP_SETTINGS = f"{_BASE}/op_settings.png"

# 通用
BACK = f"{_BASE}/back.png"
# 默认兜底图标（ARC logo）：主菜单按钮没有自带 icon 时使用。
# 外部插件按钮的专属图标由各插件注册时通过 icon 参数自行指定。
DEFAULT = f"{_BASE}/default.png"


def is_enabled_value(raw) -> bool:
    """UI_ICONS_ENABLED 配置解析：缺省/空 = 开启；0/false/off/no/否 = 关闭。"""
    if raw is None:
        return True
    text = str(raw).strip().lower()
    if not text:
        return True
    return text not in ("0", "false", "off", "no", "否", "关闭")
