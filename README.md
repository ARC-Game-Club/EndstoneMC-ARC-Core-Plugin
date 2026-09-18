<div align="center">

# EndStone ARC Core Plugin / EndStone弧光核心

[![Codacy Grade](https://app.codacy.com/project/badge/Grade/2f830615baf347258558dcc2a5ab85a1)](https://app.codacy.com/gh/DEVILENMO/EndstoneMC-ARC-Core-Plugin/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)
[![Version](https://img.shields.io/badge/version-v0.9.63-blue)](https://github.com/ARC-Game-Club/EndstoneMC-ARC-Core-Plugin)
[![Python](https://img.shields.io/badge/python-3.13+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![EndStone API](https://img.shields.io/badge/EndStone_API-0.7+-black)](https://github.com/EndstoneMC/endstone)
[![License](https://img.shields.io/github/license/ARC-Game-Club/EndstoneMC-ARC-Core-Plugin)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/ARC-Game-Club/EndstoneMC-ARC-Core-Plugin)](https://github.com/ARC-Game-Club/EndstoneMC-ARC-Core-Plugin/stargazers)

</div>

## 概述

EndStone ARC Core 是一个功能完整的 EndStone (Minecraft 基岩版服务器) 插件，为服务器提供全方位的核心功能模块。该插件包含玩家管理、经济系统、领地管理、传送系统、公告系统、清道夫系统、天眼行为审计、**侧边栏总控**等丰富功能，是构建现代化 Minecraft 服务器的理想选择。插件体验服：IP：arcclub.top，端口：19132，你可以在这个服务器试用体验本插件。

## 作者信息

- **作者**: DEVILENMO
- **邮箱**: DEVILENMO@gmail.com
- **版本**: 0.9.63
- **API 版本**: 0.7+
- **推荐 Python 版本**: 3.13

## ✨ 主要功能

### 🗄️ 数据库管理
- 基于 SQLite 的高性能数据库，线程安全的连接管理，自动创建数据库文件和目录
- **XUID 主键系统** - 全面使用 XUID 作为玩家主键，提升数据一致性和查询性能
- **说明** - 不再支持从 UUID 到 XUID 的自动迁移，请使用已迁移至 XUID 的数据库或旧版本完成迁移后再升级

### 🌍 多语言支持
- 完整的国际化系统，动态语言文件加载
- 默认支持中文 (ZH-CN)，可扩展其他语言包

### 🧭 主菜单与子命令（`/arc`）
- **进服自动弹出主菜单**：玩家加入服务器后约 **1 秒**（20 ticks）会 **自动弹出 ARC 主菜单一次**，无需配置；可直接关闭表单继续游玩，亦可随时输入 **`/arc`** 再开。此项 **不是**「强制登录」——浏览菜单不设密码门槛；敏感操作见「玩家管理系统」。
- **按钮优先级排序**：所有主菜单按钮带优先级，**数字越小越靠前（0 最高）**，同优先级按按钮文本排序。核心内置：每日签到未签到 **0**、已签到 **99**、新手引导 **3**、传送 **4**、领地 **5**、银行 **6**、工具 **8**、OP 面板 **50**。
- **外部插件自注册**：核心不硬编码检测任何外部插件。UShop、按钮商店、证券交易所、PvP KD、枪战、别踩白块、公会（arc_guild）等外部功能，均由各插件在自己的 `on_enable` 中调用 `api_register_main_menu_button` 注册主菜单按钮（建议 priority≈6），`on_disable` 时注销。未安装对应插件就不显示入口。
- **按钮图标**：主菜单与各核心面板按钮带 **Minecraft 像素风图标**，贴图由客户端资源包 **弧光核心RP** 提供（`textures/arc_core/`）。外部插件注册时传 `icon="textures/arc_core/xxx.png"` 即可自带图标，**不传则显示 ARC logo 兜底图**；客户端未装资源包时 Bedrock 自动不显示图标，不影响使用。配置 **`UI_ICONS_ENABLED`**（缺省 `True`）可整体关闭图标（OP 配置面板「通用」可改）。
- **`/arc land`**、**`/arc tp`**、**`/arc bank`**、**`/arc guild`** 分别直接打开 **领地菜单**、**传送菜单**、**银行菜单**、**公会菜单**（公会菜单由 arc_guild 提供，未安装则提示；若从控制台/命令方块执行，会按 **命令发送者名称** 解析在线玩家，与 `/connecttoserver` 相同机制）。进入菜单后，**转账、创建/管理领地、公会创建等敏感操作**仍会按需弹出密码验证（未设密会先引导设密），详见「玩家管理系统」。

### 👤 玩家管理系统
- **敏感操作密码验证（非进服门禁）**：打开 **`/arc`**、浏览主菜单 **无需** 预先输入密码；**转账、创建或管理领地、公会创建等敏感操作**会在执行前要求 **账户密码验证**。同一 **游戏会话**（自进服至退出）内验证成功 **一次** 即可重复使用；若尚未在数据库中设置密码，会先弹出 **设密（两次确认）** 再继续敏感操作。
- **会话内验证状态**：密码以 **SHA-256** 哈希存储；验证通过后本会话内标记为已验证（修改密码会清除该标记，需重新验证）。语言提示见 **`dist/ARCCore/ZH-CN.txt`** 中 **`SENSITIVE_*`** 等键。
- **注册确认密码**：首次设密 / 注册时需输入两次密码，一致方可完成。
- **修改密码（我的信息）**：主菜单 **我的信息** →「修改密码」。已设置账户密码时需填写 **当前密码**、**新密码** 与 **确认新密码**（新密码不可与当前密码相同）；尚未设置密码时打开与首次注册相同的设密表单。修改成功后，本会话内「敏感操作已验证」状态清除，之后转账、领地等需用 **新密码** 再验证一次。语言键见 `dist/ARCCore/ZH-CN.txt` 中 `CHANGE_PASSWORD_*`
- 玩家数据持久化存储（跨服账号：`player_basic_info`；本服档案：`player_local_info`）
- 在线状态实时管理、玩家加入/离开消息提示
- **免费领地格子**、**OP 标记**、**签到** 均为本服数据，不随同步中心跨服覆盖
- **游戏时长 / 进服次数** 写在跨服表 `player_basic_info`，随同步中心或共享库跨服累计

### 👁️ 天眼系统（Sky Eye）
- **用途**：可选开启的玩家行为审计；写入独立 SQLite，供排查与弧光天星即时查询
- **配置**（`core_setting.yml`）：**`ENABLE_SKY_EYE`**（默认关闭）、**`SKY_EYE_MAX_RETENTION_DAYS`**（保留天数，默认 **7**；**`0`** 表示不自动删除）
- **存储**：**`plugins/ARCCore/sky_eye/skyeye.db`**（独立库，不进主库、不走跨服同步）
- **记录字段**：时间、行为、玩家名、XUID、维度、坐标、主手物品（含附魔摘要）、`detail`、**是否在领地内**、领地 ID/名称/主人、攻击对象（打了谁 / 被谁打）
- **战斗增强**：每次玩家攻击记录 `damage` / `hp_before` / `hp_after` / `max_hp` / `cause`；PvP 另记 `victim_armor`（被打方当时装备+附魔）；死亡记录 `armor` 与 `inv`（背包格子摘要）
- **已挂钩行为**：进服 / 离服、方块破坏与放置、对方块交互与无方块交互、与实体交互、**玩家造成的伤害（含 PvP）**、玩家死亡（含击杀者与死亡时装备/背包）；关闭开关时不写盘
- **对外查询 API**（其它插件 / 天星）：`api_sky_eye_query`、`api_sky_eye_query_text`、`api_sky_eye_player_now`，详见「API 接口」。天星工具：`mc_skyeye_player` / `mc_skyeye_combat` / `mc_skyeye_events` / `mc_skyeye_location`（仅 OP / QQ 管理）
- **查询增强**：玩家名默认**模糊匹配**（子串、忽略大小写）；`action` 支持类别别名（`death`/`pvp`/`pve`/`combat`/`死亡`/`打怪` 等）；可不传玩家名仅按事件类型+时间查全服（如「最近 24 小时谁死了」）

### 💰 银行经济系统
- 完整的货币管理系统，**金钱精确到分**（float 存储，两位小数）
- 玩家余额存储和查询
- **两步式转账** - 先选择玩家再输入金额，支持小数金额
- **定期存款** - 按月复利（30 天记 1 个月），存期档位 1/3/6/12 个月，**各档独立月利率** `FIXED_DEPOSIT_RATE_1M/3M/6M/12M` 可配（[全服]，默认 5%），功能开关 `ENABLE_FIXED_DEPOSIT`（[本服]）；未到期支取仅返还本金，到期后利息封顶（不自动续存），进服自动提醒到期存单；存单随 `SYNC_CLIENT_SYNC_ECONOMY` 跨服同步
- 富豪榜排行系统、管理员金钱操作命令、实时余额变动提醒
- **财富榜首富头衔** - 配置 `RICHEST_TITLE_NAME`（默认「首富」）、传奇稀有度；金钱变动后自动刷新财富榜第一，首富易主则撤销旧头衔并授予新首富；同分按 xuid 稳定排序；跨服仅主服计算、从服只消费同步头衔；可在 **OP 面板 → 经济管理 → 经济参数配置** 中修改

### 📮 邮箱系统
- **网游式邮箱** - 主菜单「邮箱」入口（有未读时按钮显示数量），或 `/arc mail` 直接打开；进服有未读邮件时 toast 提醒
- **个人邮件 / 全服邮件** - OP 在 **OP 面板 → 邮件管理** 发信：给单个玩家（支持不在线玩家，按 XUID 落库）或发全服邮件；发件人显示为操作 OP 的名字
- **附件物品与金币** - 邮件可附多件物品（格式 `物品ID 数量;物品ID 数量`，单封最多 12 条）与金币；玩家在邮件详情 **「领取附件」**，或列表页 **「一键领取全部附件」**；金币入账；物品支持两种条目：普通条目（`物品ID 数量`）逐条 `give` 入包；**富物品条目**（`api_send_mail` 传入 arc_inventory 格式，含 `nbt_b64`/`enchants`/`lore`/`name`）经 arc_inventory 还原完整 NBT 后入包——潜影盒内容物、附魔、Lore 不丢失（需 `arc_inventory` 在场，否则按普通条目发放）
- **全服通告** - 发全服邮件时聊天栏广播公告；带附件的公告会提示玩家从邮箱领取
- **已读 / 领取状态** - 个人邮件状态记在邮件行上；全服邮件每名玩家独立记录（`player_mail_claim` 表，同一封每人只能领一次）；个人邮件附件领取后才可删除，防误删丢附件
- **领取前空位检测** - 带物品附件的邮件领取前检查主背包是否还有空位：背包已满时聊天栏提示「物品栏已满，暂时无法领取附件」，**不发放、不标记已领**，领取按钮保留；「一键领取」会跳过这类邮件并汇总提示，纯金币邮件不受影响
- **剩余时长展示** - 邮箱列表按钮带「[剩N天]」标记（向上取整）；邮件详情显示**发放时间**与**截止时间（含剩余天数）**，永不过期的邮件标注「本邮件永不过期」
- **过期作废** - 配置 `MAIL_EXPIRE_DAYS`（[全服]，默认 30 天，`0` 永不过期）：到期邮件连同未领附件自动删除（打开邮箱时 + 每 30 分钟定时清理）
- **跨服同步** - 邮件与领取状态随 `SYNC_CLIENT_SYNC_MAIL`（默认开）跨服同步：任意服发信全服可见，附件跨服只能领一次
- **对外 API** - `api_send_mail` / `api_send_global_mail` / `api_count_player_mails`，供其它插件发活动奖励邮件；`items` 参数支持富物品条目（含 NBT，见上），详见「API 接口」

### 📊 侧边栏总控
- **原生计分板 SIDE_BAR**：每玩家独立 `Scoreboard`，复用稳定 objective 原地刷新（避免频繁销毁重建导致客户端闪退）
- **多页面 + 定时翻页**：可见页 ≥ 2 时默认每 **10 秒**自动切换；可用 `/sidebar lock` 锁定
- **核心主页面 `arc_core_main`**：现实时间、金钱、**TPS**、在线人数、**玩家延迟**等（模板可配；默认不含生命/饱食）
- **其它插件注册页面**：`api_sidebar_register_page` + 行模板 `{key}`，数值变更用 `api_sidebar_set_value(s)` 推送（等定时 tick 渲染），详见「API 接口」
- **玩家命令**：`/sidebar`（别名 `/sb`）支持 `on` / `off` / `next` / `prev` / `lock` / `unlock` / `list`；开关与锁定偏好持久化到 SQLite
- **刷新策略**：调度每 1 tick 检查到期玩家；进服时记录 `join_tick`，`(当前tick - join_tick) % SIDEBAR_REFRESH_TICKS == 0` 时重绘，自然错峰；TPS/时间等缓存在整服周期 tick 更新；插件 `set_value` 只写缓存；`/sidebar` 命令仍即时刷新
- **配置**：`SIDEBAR_ENABLE`、`SIDEBAR_DEFAULT_ON`、`SIDEBAR_TITLE`、`SIDEBAR_SWITCH_INTERVAL`、`SIDEBAR_REFRESH_TICKS`（20=1秒，默认 60≈3秒）、`SIDEBAR_JOIN_DELAY_TICKS`（默认 40）、`SIDEBAR_MAIN_LINES`、`SIDEBAR_MAX_LINES`（亦可在 OP 面板「侧边栏」分组修改）

### 🏠 领地管理系统
- **三维领地** - 按 min/max X/Y/Z 圈地，按体积计价；粒子显示立方体边界
- **创建领地流程** - 菜单「创建新领地」后按提示 **交互四个方块**：水平矩形两角（取 X/Z）→ 最低 Y → 最高 Y，完成后进入 **购买确认面板**（可再次播放边界粒子、修改 min/max X/Y/Z、确认购买）；亦可用 **「手动输入六向坐标」** 或 **`/land pos1`、`/land pos2`、`/land buy`** 快捷选点
- **待购面板** - 购买前可随时用 **`/land buy`** 重新打开同一面板；该指令为打开面板而非直接扣款
- **领地保护机制** - 防止破坏/建造/方块互动
- **免费领地格子系统** - 新玩家可获得免费格子，购买领地时自动减免费用
- **领地授权系统** - 可将领地权限授权给其他玩家
- **子领地系统** - 领地主人可在领地内创建子领地并授权他人；子领地为三维、不可重叠、不可超出父领地；交互时先判子领地权限再判父领地
- **公共领地** - 可开启「允许圈内购买私人领地」；**三级优先级** `public_priority`（1/2/3，**3 最高**，默认 1），高优先级公共可覆盖低优先级公共，同级不可重叠；生效顺序：**私人/公会 > 公共(3>2>1)**，私人子领地权限仍先于父私人领地
- **公共领地「拦截生物生成」** - 每个公共领地可单独开关（`block_actor_spawn`）。全局配置 **`PUBLIC_LAND_BLOCK_ACTOR_SPAWN_MODE`**：**whitelist**（默认）= 名单上的不拦截、其余拦截（名单为空则拦截全部）；**blacklist** = 只拦截名单上的。名单见 **`PUBLIC_LAND_BLOCK_ACTOR_SPAWN_LIST`**（逗号分隔实体 ID）。**`LAND_BLOCK_ACTOR_SPAWN_SCOPE`**：`public`（默认）= 仅公共领地且看各领地开关；`all` = 任意领地均按全局名单拦截。经 `ActorSpawnEvent` 取消匹配实体生成（含模组生物，不含玩家）
- **领地移交** - 可将领地转移给其他玩家
- **私人领地上架出售** - 领地详情中 **「出售领地（上架/改价/下架）」**：主人可设置正数标价并上架；其他玩家进入该私人领地时会收到 **购买表单**。购买时扣买家款、过户给买家、清空授权列表；卖家在线会收到成交通知。数据库 `lands` 表含 `for_sale`、`sale_price`（旧库启动时自动 `ALTER`）。**公共领地 / 公会领地** 不适用；入账失败会尝试回滚过户并退款
- **成交增值税** - 配置 **`LAND_SALE_VAT_RATE`**（默认 `0.1` 即 10%，取值 0～1，**`0` 关闭**）。成交时买家按标价全额付款，**卖家实收** = 成交价 − 增值税额；**税基（溢价）** = `max(0, 成交价 − 过户前 owner_paid_money)`。平价或低于买入价成交不产生增值税。OP 重载配置后刷新税率
- **爆炸保护** - 可单独控制领地内是否允许爆炸；全局 **`BLOCK_ALL_EXPLOSIONS`**（默认开）与领地禁止爆炸时优先 **清空 `block_list`**（不拆方块、尽量保留实体伤害），失败则回退取消整次爆炸；全局关闭时按领地 `allow_explosion` 做 **逐方块** 保护
- **方块互动开放 / 生物保护 / 展示框权限** - 可设置领地对所有人开放方块互动；可控制与生物交互和攻击生物；可禁止对展示框/发光展示框及各材质展示架的互动与破坏（默认禁止）；关闭展示框权限时，主人、授权玩家、子领地权限持有者及（若开启「公会成员可交互」）同公会成员仍可操作
- **领地范围重设** - 私人/公会领地在 **我的领地 → 领地详情**，公共领地在 **OP 领地管理 → 领地详情**。流程与新建领地相同，确认面板显示 **原/新体积与补差价或退差价**：私人领地扩大优先消耗免费格再按 `LAND_PRICE` 补款，缩小按 `LAND_SELL_REFUND_COEFFICIENT` 退款；**OP 改私人领地**不扣款；**公会领地**仅会长/管理者、消耗/退还 **公会公共贡献点**；**公共领地**仅 OP、不扣款。确认后更新边界、**重建 chunk 索引**（`land_id` 不变），传送点超出新范围会自动移到新范围中心；**上架出售中**不可重设；**子领地**超出新范围会阻止。语言键 `LAND_RESIZE_*`
- **全局禁用方块** - `DISABLED_BLOCKS` 列表内方块对非 OP 玩家禁止放置与交互，OP 跳过检查
- **其它** - 领地尺寸限制（默认长宽必须都大于 5 格）、当前位置领地信息查看、边界粒子可视化、重叠提示、传送点设置、重命名、可配置价格与最小距离、智能传送命令生成（自动处理含空格玩家名）

### 🎯 成就系统（已拆至独立插件）
- **独立插件**：`endstone_arc_achievement` / plugin id **`arc_achievement`**，仓库目录 `EndstoneMC-ARC-Achievement`，数据目录 `plugins/ARCAchievement/`
- **核心职责**：菜单入口转发（检测到插件时显示「我的成就」「成就管理」，执行 `/ach`、`/achop`）；头衔解锁与发奖仍走本核心 API
- **活动统计**：击杀 / 破坏 / 放置累计写入本服表 **`player_activity_stats`**；对外只读 API（见「API 接口」）。成就插件经 API 查询，**不得直写核心库**
- **定义文件**：`plugins/ARCAchievement/achievements.json`（首次启用时若仅有旧版 `plugins/ARCCore/achievements.json` 会自动复制）
- **说明**：未安装 `arc_achievement` 时，核心仍统计活动数据，但不显示成就入口

### 📊 玩家活动统计
- 表 **`player_activity_stats`**：`kill_total` / `kill:{entity_id}`（含 `minecraft:player`）、`break_total` / `break:{block_id}`、`place_total` / `place:{block_id}`
- 生物击杀在 `ActorDeathEvent` 记账；玩家击杀在 `PlayerDeathEvent` 记账；方块破坏/放置仅在事件**未取消**时记账
- 本服独立，不跨服同步；旧表 `player_achievement_stats` 中的统计列启动时一次性迁入本表后 DROP
- API：`api_get_player_stat` / `api_get_player_stats` / `api_get_player_kill_count` / `api_get_player_block_break_count` / `api_get_player_block_place_count`

### 📅 每日签到
- **可签到条件**：本服 `player_local_info.last_checkin_date` 与服务器本地日期不同即可签到（**每服独立**，不跨服共享）
- **连续签到奖励**：按连续签到天数发放递增金钱奖励（可配置步长）
- **前几名签到奖励**：可配置每日前 X 名的额外金钱与额外物品奖励
- **奖励**：配置存款 + 按权重 **不放回** 随机物品；每日抽取条数在 **`CHECKIN_REWARD_PICK_MIN`～`CHECKIN_REWARD_PICK_MAX`** 之间随机
- **统计与排行**：`total_checkin_count` 累计次数、`last_checkin_at` 记录最近签到时刻，用于 **当日签到先后** 与 **累计签到榜** 排序
- **全服广播**：签到成功后广播完成提示（今日先后、累计榜前 10），聊天中 **按行发送**
- **公会贡献点**：配置 `CHECKIN_GUILD_CONTRIBUTION_POINTS`（默认 `10`，`0` 关闭）— 签到成功时，若玩家已加入公会且安装了 **arc_guild**，经其 API 同时增加 **私人贡献点** 与 **公会公共贡献点**；未入会或未安装则跳过
- **主要配置**：`CHECKIN_DAILY_MONEY`、`CHECKIN_REWARD_LIST`（JSON 数组，每项 `[物品ID, 数量, 权重]`）、`CHECKIN_CONTINUOUS_DAYS_MONEY_INCREMENT`（连续签到金钱递增步长）、`CHECKIN_TOP_RANK_LIMIT`（每日前 X 名，`0` 关闭）、`CHECKIN_TOP_RANK_BONUS_MONEY_STEP`、`CHECKIN_TOP_RANK_BONUS_ITEM_COUNT`、`CHECKIN_REWARD_PICK_MIN` / `CHECKIN_REWARD_PICK_MAX`
- **OP 面板 → 签到配置**：总览 + 存款/条数表单 + 奖励列表管理

### 💀 击杀生物金钱奖励（已拆至独立插件）
- 击杀金钱奖励与「击杀 → 公会贡献点」已拆出至独立插件 **arc_hunter**（`EndstoneMC-ARC-Hunter`，弧光猎魔人）：配置文件 `plugins/ARCHunter/kill_reward.txt`，贡献点直连 arc_guild API
- 核心仅保留击杀统计（活跃统计 / 成就联动），不再发放杀怪奖励

### 📍 传送系统
- **功能开关** - 传送面板每项可单独开关，默认全开：`ENABLE_TELEPORT_PUBLIC_WARP`、`ENABLE_TELEPORT_HOME`、`ENABLE_RANDOM_TELEPORT`、`ENABLE_TELEPORT_DEATH_LOCATION`、`ENABLE_TELEPORT_PLAYER`、`ENABLE_TELEPORT_CROSS_SERVER`。关闭后传送系统面板不显示对应按钮（`/connecttoserver` 在跨服关闭时也不可用）。可在 **OP 面板 → 配置文件设置 → 传送** 中修改
- **私人传送点 (Home)** - 玩家可设置多个传送点
- **公共传送点 (Warp)** - 管理员可创建公共传送点
- **跨服传送** - 数据库维护跨服目标；`/connecttoserver` **无参数**时打开跨服目标 **选择面板**，有参数时按名称执行传送；控制台/命令方块执行时可通过发送者名称解析在线玩家
- **玩家传送请求 (TPA/TPHERE)** - 发送时用 **下拉框** 选择请求类型与目标玩家；**被请求方收到请求时自动弹出表单**并 toast 提示；亦可用 **`/tpa accept`** / **`/tpa deny`** 快速响应最近一条请求
- **死亡回归** - 玩家死亡后可传送回死亡地点；死亡坐标在同一次服务器运行期间保持（实际传送成功后清除记录）
- **随机传送** - 随机传送到指定范围内，自动附加缓降效果（**30 秒**）
- **传送付费** - 每种传送类型可独立配置收费（`TELEPORT_COST_*`），支持余额检查
- **跨维度支持** - 主世界、下界、末地之间自由传送；自动使用 `execute in <dimension> run tp`，原版三维度用短名，自定义维度用完整 `namespace:id`
- 传送倒计时提示（倒计时中受伤自动打断）

### 🔌 外部插件集成（注册制）
核心 **不硬编码检测任何外部插件**，主菜单的第三方入口一律由各插件 **自己注册**：插件在 `on_enable` 调用 `api_register_main_menu_button` 添加按钮（可带 `icon` 图标），`on_disable` 时调用 `api_unregister_main_menu_button` 注销。**安装即显示入口，未安装不显示**，核心侧无需任何配置。

已适配此机制的插件包括（按钮名为各插件注册时传入的文本）：

| 插件 | 功能 | 主菜单按钮 |
|------|------|-----------|
| `arc_guild` | 公会系统 | 公会 |
| `arc_achievement` | 成就系统 | 我的成就 / 成就管理（核心检测到后转发 `/ach`、`/achop`） |
| `arc_hunter` | 击杀奖励（猎魔人） | 无菜单入口 |
| `arc_button_shop` | 玩家按钮商店 | 按钮商店 |
| `arc_sign_shop` | 木牌商店 | 木牌商店 |
| `up_and_down` | 证券交易所 | 证券交易所 |
| `arc_pvp_kd` | PvP KD 排行榜 | PvP KD 排行榜（点击执行 `/kd` 单独弹榜） |
| `arc_shooter_game` | 枪战游戏 | 枪战游戏 |
| `arc_dtwt` | 别踩白块小游戏 | 别踩白块小游戏 |
| `arc_esper` | 异能与职业 | 序列异能 |
| `arc_attribute_core` | 属性管理器 | 属性管理器（仅 OP 可见） |
| UShop（第三方插件） | 商店系统 | 商店 |

注册方式与参数详见「API 接口 → 主菜单按钮」。

### 📢 公告系统
- 定时循环播放公告消息，支持多条公告轮播，间隔可配置（`BROADCAST_INTERVAL`）
- 从 `broadcast.txt` 文件读取公告内容
- **动态占位符**：`{date}` - 当前日期、`{time}` - 当前时间、`{online_player_number}` - 在线玩家数

### 🧹 清道夫系统
- 定时自动清理掉落物，间隔可配置（`CLEANER_INTERVAL`）
- 清理前 10 秒倒计时警告、清理过程状态提示
- 可通过 `ENABLE_CLEANER` 开启/关闭

### 🎊 新人欢迎系统
- **新玩家自动识别** - 基于数据库记录智能判断新玩家
- **自定义欢迎消息** - `newbie_welcome.txt`
- **自动执行指令** - `newbie_commands.txt`，指令中 `{player}` 自动替换为新玩家名称
- **数据库自动初始化** - 新玩家加入时自动创建基础数据和经济账户，并获得配置的初始资金
- 文件读取失败不影响插件正常运行

### 🔐 OP 状态追踪
- **OP 状态持久化** - 本服权限记在 **`player_local_info.is_op`**（**不跨服同步**，每服独立）；跨服排行排除用 **`player_basic_info.once_op`**（任意服以 OP 登录过即永久标记）
- **离线状态查询**、**加入时自动同步本服 OP 状态**
- **金钱排行榜隐藏** - 可配置在金钱排行榜中隐藏 OP 玩家（`HIDE_OP_IN_MONEY_RANKING`）

### 🛡️ 出生点保护
- 可配置的出生点保护范围（`IF_PROTECT_SPAWN`、`SPAWN_PROTECT_RANGE`）
- 防止玩家在出生点附近建筑/破坏
- 多维度出生点支持

### ⚙️ OP 管理面板
- **主菜单顺序**（自上而下）：重载配置 → **配置文件设置** → **工具** → **经济管理** → 领地管理 → 传送管理 → 成就管理（需安装 `arc_achievement`）→ 签到配置 → 邀请奖励配置 → 头衔管理 → 返回
- **配置文件设置** - 按分类浏览并修改 `core_setting.yml`：开关/多选用下拉框；逗号分隔列表与签到奖励池为「条目按钮 + 增加新配置」，点进单条可删除。保存后即时写入并刷新缓存（路径/同步类项建议重启）
- **工具**：切换游戏模式、清除掉落物、记录坐标 1/2、调试模式、执行命令（`@p1`/`@p2`、留空重复上次命令）
- **经济管理**：**增减在线玩家存款**；**经济参数配置** 写入 `PLAYER_INIT_MONEY_NUM`、`HIDE_OP_IN_MONEY_RANKING`、`RICHEST_TITLE_NAME`、`FIXED_DEPOSIT_RATE_1M/3M/6M/12M`、`ENABLE_FIXED_DEPOSIT`
- **领地管理**：管理所有领地、管理脚下领地、重建领地区块映射；**公共领地** 详情内可 **重设公共领地范围**（不扣款）
- **传送管理**：**管理公共传送点**（创建/删除 Warp）；**传送参数配置**（`MAX_PLAYER_HOME_NUM`、随机传送中心/半径、各类传送费用等）
- **签到配置**：总览展示当前存款/随机条数区间/奖励条目数；存款与随机条数表单（含每日签到公会贡献点）；奖励列表按条目编辑/删除/新增
- 邀请奖励配置、头衔管理、成就管理
- **重载配置** - 重载 `core_setting`、广播、语言、**entity_display_name.txt** 等（杀怪奖励配置改用 `/archunter reload`）
- **调试模式**：开启后，在方块破坏/放置、方块交互、生物攻击、生物交互时向该 OP 发送聊天调试消息（事件类型、目标、维度、位置）

### 🏷️ 头衔系统
- **聊天头衔展示** - 远古 QQ 风格：首行 `[前缀…]玩家名(年.月.日-时:分)：`，下一行消息内容；前缀按注册 priority 升序（内置头衔 3；公会 2 由 arc_guild 注册），头衔段按稀有度上色（MC 格式码 §f/§9/§d/§6/§c）
- **数据** - 玩家解锁时间仅存 **`player_title_unlock_time`**（`xuid`、`title`、`unlocked_at`）；废弃表 **`player_title_extra`** 在启动时自动 DROP
- **头衔属性** - 每个头衔支持：**稀有度**（普通/稀有/史诗/传奇/神话，对应白/蓝/紫/橙/红）、**头衔介绍**、**解锁时间**、**解锁奖励**（金钱 + 物品列表）
- **默认头衔** - 配置 `DEFAULT_TITLE`（逗号分隔），**进服时**为每位玩家写入解锁记录（与成就无关）；OP 可在头衔属性管理中修改介绍与奖励
- **OP 专属头衔** - 配置 `OP_TITLE`（单个），仅 OP 拥有；非 OP 进服时若正佩戴该头衔则自动解除
- **头衔管理（玩家）** - 主菜单「我的信息」→「头衔管理」：选择佩戴/不佩戴
- **OP 头衔管理** - OP 面板→「头衔管理」：**头衔属性管理**（稀有度、介绍、解锁奖励）、**创建新头衔**、**给所有玩家添加头衔**、**给玩家单独添加头衔**；解锁时若玩家在线则发放解锁奖励
- **解锁头衔自动佩戴** - 通过 `api_unlock_title` 等途径解锁头衔时，若当前未佩戴任何头衔，则自动佩戴新解锁的头衔

### 🏰 公会系统（已拆至独立插件）
- **独立插件**：`arc_guild`（仓库 `EndstoneMC-ARC-Guild`）— 公会的全部玩法 UI（创建/邀请/职级/规模升级/改名/浏览/入会审批等）与公会 API 均在此插件，OP 管理命令为 **`/arcguildop`**
- **入口**：主菜单「公会」按钮由 arc_guild 自行注册；**`/arc guild`** 由核心转发至 arc_guild（未安装则提示）
- **核心保留**：
  - **数据模块** `GuildSystem.py` 与数据表 **`guilds`**、**`guild_members`**（供 arc_guild 复用，含规模档位、贡献点、入会审批等字段与自动补列）
  - **软依赖集成点**：领地系统创建/管理 **公会领地**（消耗/退还 **公会公共贡献点**，arc_guild 缺失时不显示该选项）、每日签到发放贡献点（见「每日签到」）、展示名前缀槽位（arc_guild 注册 `guild`，priority=2）
  - **跨服同步**：`SYNC_CLIENT_SYNC_GUILD` 开启时仍由核心同步公会数据表
- **公会数据 API**：`api_get_player_guild_info`、`api_add_guild_contribution` 等请在安装 arc_guild 后 **直接调用该插件**；核心查询公会信息失败一律视为无公会

### 🔄 跨服数据同步
- **用途**：在多服架构下，让玩家账号级数据、经济、头衔、公会等在多个 ARC Core 实例之间保持一致
- **拓扑（纯网络）**：
  - **主服 / 同步中心**：**`ENABLE_SYNC_SERVER=True`** + **`ENABLE_SYNC_CLIENT=False`**，监听 **`SYNC_SERVER_PORT`**
  - **子服**：**`ENABLE_SYNC_CLIENT=True`**，连接同步中心（**`SYNC_SERVER_IP`** + **`SYNC_CLIENT_PORT`**），首次连接全量拉取、之后接收 **`PUSH_NOTIFY`** 推送；本地写库经 **`sync_outbox`** 可靠上行（断线不丢，重连后重放）
- **分项同步开关（仅远程客户端）**：**`SYNC_CLIENT_SYNC_PLAYER`**、**`SYNC_CLIENT_SYNC_ECONOMY`**、**`SYNC_CLIENT_SYNC_TITLE`**、**`SYNC_CLIENT_SYNC_GUILD`** 可单独开关
- **条件头衔权威服**：**`CONDITIONAL_TITLE_AUTHORITY`** 显式指定是否由本机计算首富等条件头衔；留空则自动推断
- **玩法配置以同步中心为准**：开启对应分项后，从服连接时会拉取并覆盖该类别的玩法配置（写入本机 `core_setting.yml`），主服改配置或重载后推送给已连接从服。本机路径、端口、`SYNC_CLIENT_*`、清道夫、出生点保护等仍各服独立
- **从服时长/次数以主服为准**：从服进退服向同步中心上报该玩家 `session_count`/`total_playtime`，本地只缓存；`api_get_player_playtime` 展示前先向主服拉取
- **模块**：`sync_protocol.py`、`sync_server.py`、`sync_client.py`、`sync_config.py`、`sync_outbox.py`、`sync_plugin_api.py`、`sync_write.py`
- **可同步数据表**：跨服玩家账号信息（`player_basic_info`，含 **`once_op`** 粘性列）、经济（`player_economy`、`player_fixed_deposit` 定期存款存单）、头衔（`title_definitions` / `player_title_unlock_time` / `player_title_equipped`）、公会（`guilds` / `guild_members` / `guild_invites`）、邮箱（`player_mail` / `player_mail_claim`，邮件正副本与全服邮件每人领取状态）
- **本服本地表（不同步）**：**`player_local_info`** — 本服 `is_op`、剩余免费领地格、签到（每服独立）
- **第三方插件表同步**：其它插件可把自己的表纳入跨服同步（协议 v4，逻辑名 `plugin_id:table`），见「API 接口 → 跨服插件表同步」与 `docs/compose/spec/sync-plugin-api.md`
- **OP 面板**：点「跨服同步」即发起全面对账并显示运行状态
- **QQ 群消息**：跨服 QQ 互通由 **AstrBot 弧光 EndStone 消息中枢** + **endstone-arc-qq-sync-astrbot** 负责；ARCCore **不再**经 SyncServer 做 QQ 事件中继。死亡播报调用本机 QQ Sync 的 `api_send_event("death", …)`
- **群聊死亡播报模式**：`QQ_DEATH_BROADCAST_MODE` = `off` / `pvp`（仅 PvP）/ `all`（默认）；仅影响群聊
- **游戏内死亡播报开关**：`ENABLE_DEATH_BROADCAST`（默认 `True`）；设为 `False` 关闭全服聊天栏死亡播报
- **启动迁移**：签到迁入本服表；时长 / 进服次数保留在跨服 `player_basic_info`

### ⏱️ 游戏时长统计（跨服）
- 表：**`player_basic_info`**（`total_playtime` 秒、`session_count`、`last_join_time` / `last_quit_time`）
- 进服 / 离服自动记账；关服时结算在线会话；随 SyncServer / 共享库跨服累计
- 对外 API：**`api_get_player_playtime(raw_player_name="", xuid="")`**

### 🔌 插件 API 系统
- **统一玩家标识** - 多数接口同时支持游戏名与 **xuid**（填一个即可，xuid 优先）；旧的只传玩家名的调用仍可用
- **调用入口**：`server.get_plugin("arc_core")`（与 pyproject entry-point 一致）
- **接口分组**：经济、活动统计、头衔/发奖、领地、传送、侧边栏、天眼、邮箱、跨服插件表同步、主菜单按钮注册、聊天前缀、玩家解析/时长/新手引导（详见下方「API 一览表」）；公会 API 已拆至 `arc_guild`
- **线程安全设计**，支持多插件并发调用

## 命令列表

| 命令 | 描述 | 权限 | 用法 |
|------|------|------|------|
| `/arc` | 打开 ARC Core 主菜单 | 默认 | `/arc` |
| `/arc op` | 直接打开 OP 面板（仅 OP） | OP | `/arc op` |
| `/arc land` | 直接打开领地系统菜单 | 默认 | `/arc land` |
| `/arc tp` | 直接打开传送系统菜单 | 默认 | `/arc tp` |
| `/arc bank` | 直接打开银行菜单 | 默认 | `/arc bank` |
| `/arc guild` | 直接打开公会菜单（转发 arc_guild） | 默认 | `/arc guild` |
| `/arc mail` | 直接打开邮箱 | 默认 | `/arc mail` |
| `/pos1` | 记录当前坐标为坐标 1（OP 快捷，对应 OP 面板记录坐标 1） | OP | `/pos1` |
| `/pos2` | 记录当前坐标为坐标 2 并打开 OP 面板（OP 快捷） | OP | `/pos2` |
| `/updatespawnpos` | 更新当前维度的出生点位置 | OP | `/updatespawnpos` |
| `/suicide` | 自杀命令 | 默认 | `/suicide` |
| `/spawn` | 传送到出生点 | 默认 | `/spawn` |
| `/land pos1` | 领地选点 1（记录当前站立方块坐标） | 默认 | `/land pos1` |
| `/land pos2` | 领地选点 2 并打开待购面板 | 默认 | `/land pos2` |
| `/land buy` | 打开待购领地购买面板 | 默认 | `/land buy` |
| `/tpa accept` | 接受最近一条传送请求 | 默认 | `/tpa accept` |
| `/tpa deny` | 拒绝最近一条传送请求 | 默认 | `/tpa deny` |
| `/sidebar` | 侧边栏开关/翻页/锁定（别名 `/sb`） | 默认 | `/sidebar on\|off\|next\|prev\|lock\|unlock\|list` |
| `/connecttoserver` | 无参数时打开跨服目标列表；有参数时按名称传送 | 默认 | `/connecttoserver` 或 `/connecttoserver <名称>` |

## 📂 文件结构

插件会在 `plugins/ARCCore/` 目录下创建以下文件：

- `core_setting.yml` - 主要配置文件
- `broadcast.txt` - 公告消息文件
- `{语言代码}.txt` - 语言文件 (如 ZH-CN.txt)
- `entity_display_name.txt` - 生物显示名翻译（死亡播报等）
- `newbie_welcome.txt` / `newbie_commands.txt` - 新人欢迎消息与自动指令
- SQLite 数据库文件
- `sky_eye/skyeye.db` - 天眼审计独立数据库（开启天眼时）

成就定义见独立插件 `plugins/ARCAchievement/`（`arc_achievement`），击杀奖励配置见 `plugins/ARCHunter/kill_reward.txt`（`arc_hunter`）。

## ⚙️ 配置文件

### core_setting.yml - 主要配置选项

```yaml
# 基础设置
DEFAULT_LANGUAGE_CODE=ZH-CN          # 默认语言
DATABASE_PATH=ARCCore.db             # 数据库文件路径
PLAYER_INIT_MONEY_NUM=10000          # 玩家初始金钱

# 出生点保护
IF_PROTECT_SPAWN=True                # 是否保护出生点
SPAWN_PROTECT_RANGE=8                # 出生点保护范围

# 领地系统
ENABLE_LAND_SYSTEM=True              # 领地系统总开关；False 时不启位置追踪线程（无进出领地提示）
ALLOW_LAND_CLAIM=True                # 是否允许圈地（本服独立，不跨服同步；False 时无法新建领地，管理/调整范围仍可用）
MIN_LAND_DISTANCE=1                  # 领地最小距离
LAND_PRICE=100                       # 领地价格 (每格)
LAND_SELL_REFUND_COEFFICIENT=0.9     # 领地出售退款系数
LAND_MIN_SIZE=5                      # 领地最小尺寸 (长宽必须都大于此值)
LAND_SALE_VAT_RATE=0.1               # 私人领地上架成交增值税：对 (成交价−过户前owner_paid_money) 的溢价按比例征税，从卖家实收扣除；0=关闭

# 全局禁用方块（逗号分隔，对非 OP 禁止放置与交互）
DISABLED_BLOCKS=

# 传送系统
MAX_PLAYER_HOME_NUM=5                # 玩家最大家园数量

# 传送系统面板各项开关（默认全开；关闭后传送面板不显示对应按钮）
ENABLE_TELEPORT_PUBLIC_WARP=True     # 公共传送点
ENABLE_TELEPORT_HOME=True            # 私人传送点
ENABLE_RANDOM_TELEPORT=True          # 随机传送
ENABLE_TELEPORT_DEATH_LOCATION=True  # 死亡点传送
ENABLE_TELEPORT_PLAYER=True          # 玩家互传（TPA/TPHERE）
ENABLE_TELEPORT_CROSS_SERVER=True    # 跨服传送

# 随机传送范围
RANDOM_TELEPORT_CENTER_X=0           # 随机传送中心点X坐标
RANDOM_TELEPORT_CENTER_Z=0           # 随机传送中心点Z坐标
RANDOM_TELEPORT_RADIUS=5000          # 随机传送半径 (格)

# 传送收费配置（0表示免费）
TELEPORT_COST_PUBLIC_WARP=0          # 公共传送点费用
TELEPORT_COST_HOME=0                 # 私人传送点费用
TELEPORT_COST_LAND=0                 # 领地传送费用
TELEPORT_COST_DEATH_LOCATION=0       # 死亡地点传送费用
TELEPORT_COST_RANDOM=100             # 随机传送费用
TELEPORT_COST_PLAYER=50              # 玩家互传费用 (TPA/TPHERE)

# 公告系统
BROADCAST_INTERVAL=180               # 公告发送间隔 (秒)

# 清道夫系统
ENABLE_CLEANER=True                  # 是否启用清道夫
CLEANER_INTERVAL=600                 # 清理间隔 (秒)

# 全局爆炸拦截（默认开启）：True=禁止破坏方块（清空 block_list，尽量保留伤害；失败则取消事件）；False=仅按领地 allow_explosion 保护
BLOCK_ALL_EXPLOSIONS=True

# 表单按钮图标（弧光核心RP 贴图，OP 面板「通用」可改）
UI_ICONS_ENABLED=True

# 天眼系统（Sky Eye）：独立 SQLite plugins/ARCCore/sky_eye/skyeye.db
ENABLE_SKY_EYE=False                 # 是否启用天眼日志
SKY_EYE_MAX_RETENTION_DAYS=7         # 按自然日保留天数，0=不自动删旧记录

# 新人欢迎系统和OP设置（部分项也可在 OP 面板「经济管理」中修改）
HIDE_OP_IN_MONEY_RANKING=True        # 金钱排行榜是否隐藏OP玩家

# 首富头衔（亦可 OP 经济管理）
RICHEST_TITLE_NAME=首富

# 定期存款（各档月利率亦可 OP 经济管理；[全服] 随 SYNC_CLIENT_SYNC_ECONOMY 下发）
FIXED_DEPOSIT_RATE_1M=5              # 1 个月档月利率（%），按月复利，30 天=1 个月
FIXED_DEPOSIT_RATE_3M=5              # 3 个月档月利率（%）
FIXED_DEPOSIT_RATE_6M=5              # 6 个月档月利率（%）
FIXED_DEPOSIT_RATE_12M=5             # 12 个月档月利率（%）
ENABLE_FIXED_DEPOSIT=True            # 定期存款开关（[本服] 各服独立）

# 邮箱系统（OP 面板 → 邮件管理 发个人/全服邮件，可附物品与金币）
MAIL_EXPIRE_DAYS=30                  # 邮件保留天数（[全服] 随 SYNC_CLIENT_SYNC_MAIL 下发）；0 永不过期，过期未领附件作废

# 领地系统
DEFAULT_FREE_LAND_BLOCKS=100         # 新玩家默认免费领地格子数

# 公共领地白名单保护生物（逗号分隔）
PUBLIC_LAND_PROTECTED_ENTITIES=minecraft:villager,minecraft:iron_golem,minecraft:snow_golem

# 公共领地拦截生物生成
# 模式：whitelist=白名单（名单上的不拦截，空名单则拦截全部）；blacklist=黑名单（只拦截名单上的）
# 各公共领地在 OP 公共领地设置中单独开关拦截
PUBLIC_LAND_BLOCK_ACTOR_SPAWN_MODE=whitelist
# 作用范围：public=仅公共领地且看各领地开关（默认）；all=任意领地均按名单拦截（不看各领地开关）
LAND_BLOCK_ACTOR_SPAWN_SCOPE=public
# 拦截名单（逗号分隔实体 ID）：白名单=名单上的不拦截；黑名单=只拦截名单上的
PUBLIC_LAND_BLOCK_ACTOR_SPAWN_LIST=

# 头衔系统：逗号分隔为默认头衔；OP_TITLE 仅一个，仅 OP 拥有。稀有度、介绍、解锁奖励可在 OP 面板→头衔管理中编辑
DEFAULT_TITLE=创始玩家, 核心成员, ARC Player
OP_TITLE=管理员

# 公会系统（数据层在核心，玩法 UI 在独立插件 arc_guild）
GUILD_CREATE_COST=100000
# 公会规模：small / medium / large 三档，下列三个值为各档成员人数上限（含会长）
GUILD_SIZE_SMALL_MAX=10
GUILD_SIZE_MEDIUM_MAX=20
GUILD_SIZE_LARGE_MAX=40
# 公会规模升级所消耗的公会公共贡献点
GUILD_UPGRADE_TO_MEDIUM_COST=10000
GUILD_UPGRADE_TO_LARGE_COST=100000
# 会长改名公会需支付的金钱（0 表示免费）
GUILD_RENAME_COST=0

# 每日签到公会贡献点（需安装 arc_guild，0 关闭）
CHECKIN_GUILD_CONTRIBUTION_POINTS=10

# 死亡播报
ENABLE_DEATH_BROADCAST=True          # 游戏内全服死亡播报开关
QQ_DEATH_BROADCAST_MODE=all          # 群聊死亡播报：off / pvp / all

# 跨服数据同步
# 主服 ENABLE_SYNC_SERVER=True；子服 ENABLE_SYNC_CLIENT=True 连接同步中心

# ----- 同步中心（可选） -----
ENABLE_SYNC_SERVER=False
SYNC_SERVER_PORT=19999
SYNC_SERVER_AUTH_KEY=

# ----- 远程客户端（子服） -----
ENABLE_SYNC_CLIENT=False
SYNC_SERVER_IP=127.0.0.1
SYNC_CLIENT_PORT=19999
SYNC_CLIENT_SERVER_ID=server_001
SYNC_CLIENT_SERVER_NAME=服务器01
SYNC_CLIENT_AUTH_KEY=
SYNC_CLIENT_SYNC_PLAYER=True
SYNC_CLIENT_SYNC_ECONOMY=True
SYNC_CLIENT_SYNC_TITLE=True
SYNC_CLIENT_SYNC_GUILD=True
# 开启某类别时，该类别相关玩法配置也以同步中心为准（初始金钱、公会升级消耗等）
```

### broadcast.txt - 公告消息文件

每行一条公告，支持占位符：

```txt
欢迎来到ARC弧光基岩服务器！你可以在聊天框发送/arc命令打开服务器操作菜单
请遵守服务器规则，文明游戏，共建和谐游戏环境！
现在是北京时间{date} {time}，请注意休息，爱护眼睛你我做起。
当前服务器在线人数{online_player_number}，求生者们请互帮互助
```

### newbie_welcome.txt - 新人欢迎消息文件

新玩家第一次加入服务器时显示的欢迎消息：

```txt
欢迎来到ARC弧光大陆服务器！这里是一个恐怖+种田+模拟生活的多模组服务器，拥有丰富的玩法和特色系统！在聊天框输入/arc命令即可打开服务器操作菜单，进行购物、传送、领地管理等操作。

```

### newbie_commands.txt - 新人自动执行指令文件

新玩家第一次加入服务器时自动执行的指令，每行一个指令：

```txt
# 新人指令文件
# 每行一个指令，{player} 会被替换为玩家名称
# 示例：
gamemode 0 {player}
# clear {player}
give {player} minecraft:bread 5
give {player} krep:m1911
give {player} krep:acp45 42
```

#### 新人指令文件说明
- **注释支持**: 以 `#` 开头的行为注释，不会执行
- **占位符替换**: `{player}` 会自动替换为新玩家的名称
- **指令格式**: 使用标准的Minecraft指令格式，无需添加 `/` 前缀
- **错误处理**: 单个指令执行失败不会影响其他指令

### 支持的占位符

| 占位符 | 描述 | 示例输出 |
|--------|------|----------|
| `{date}` | 当前日期 | `2024-01-15` |
| `{time}` | 当前时间 | `14:30` |
| `{online_player_number}` | 在线玩家数 | `5` |
| `{player}` | 玩家名称 (仅新人指令文件) | `PlayerName` |

## 安装说明

1. 确保您的服务器运行 EndStone 框架
2. 将插件文件放入服务器的 `plugins` 目录
3. 重启服务器
4. 插件会自动创建必要的配置文件和数据库

## 依赖要求

- EndStone 框架 (API 版本 0.7+)
- Python 3.x
- SQLite3 (通常内置于 Python)

## 🎮 使用指南

### 快速开始
1. 玩家进入服务器后，约 **1 秒** 内会 **自动弹出主菜单一次**（可直接关闭）；也可随时用 **`/arc`** 手动打开。
2. **首次**进行转账、圈地购地、创建公会等 **敏感操作** 时，若尚未设置账户密码，会引导 **设密（两次确认）**；已设密则弹出 **密码验证**，本会话内验证通过一次后，同类验证在一段时间内不必重复输入（退出游戏后失效）。
3. 可在主菜单使用银行、领地、传送、公会等功能；具体步骤中凡涉及资金安全或领地变更的环节仍会按需验证密码（见「玩家管理系统」）。

### 功能操作指南
- **银行系统**: 在主菜单点击"银行"进行转账、查看余额等
  - **转账操作**: 两步式转账流程，先从在线玩家列表中选择目标玩家，再输入转账金额
- **领地系统**: 
  - 推荐：主菜单 **领地 → 创建新领地**，按提示交互四个方块；或使用 **`/land pos1` / `/land pos2`** 在对角两点定范围，再用 **`/land buy`** 打开购买面板
  - 领地长宽必须都大于配置的最小尺寸（默认 5 格）；**`/pos1` `/pos2` 为 OP 记录坐标指令，与圈地无关**
  - 新玩家享有免费领地格子，购买时会自动使用免费格子抵扣费用
  - 在领地详情中可设置爆炸保护、方块互动开放、展示框权限等高级选项；**重设领地范围** 与新建圈地流程一致，确认前可预览粒子、改坐标
  - 支持将领地权限授权给其他玩家或完全移交领地
- **传送系统**: 在主菜单的"传送系统"中管理传送点和发送传送请求
- **公告查看**: 定时播放的公告会自动显示当前时间和在线人数
- **新人欢迎系统**: 
  - 编辑 `newbie_welcome.txt` 自定义新玩家欢迎消息
  - 编辑 `newbie_commands.txt` 配置新玩家自动执行的指令
  - 使用 `{player}` 占位符在指令中引用玩家名称
  - 新玩家首次加入时自动获得初始资金和执行欢迎流程

## 🗃️ 数据存储

插件使用 SQLite 数据库存储以下数据：
- **玩家信息**: 用户名、XUID、密码哈希、OP状态、剩余免费领地格子数、邀请人(inviter_xuid)、待领取邀请奖励次数、注册时间
- **经济数据**: 玩家余额、交易记录
- **领地信息**: 领地坐标、拥有者、传送点、共享用户、爆炸保护设置、方块互动开放设置、生物保护设置、展示框权限设置
- **传送点**: 私人传送点、公共传送点坐标信息
- **玩家活动统计**: **`player_activity_stats`** — 击杀 / 破坏 / 放置累计（只读 API）；成就解锁标记由成就插件本地库维护
- **成就定义**: JSON 在 **`plugins/ARCAchievement/achievements.json`**（独立插件）
- **服务器配置**: 出生点坐标、系统设置
- **天眼审计**: 独立 SQLite **`plugins/ARCCore/sky_eye/skyeye.db`**，按 `SKY_EYE_MAX_RETENTION_DAYS` 滚动删除

### 数据库自动升级
- **智能检测**: 自动检测数据库结构并执行必要的升级（自动 `ALTER` 补列、废弃表自动 DROP、旧表数据一次性迁移）
- **向后兼容**: 完全兼容旧版本数据，无需手动迁移
- **安全升级**: 升级过程包含完整的错误处理机制
- **XUID 主键**: 使用 XUID 作为玩家主键（不支持 UUID→XUID 自动迁移）

## 🛠️ 开发信息

### 项目结构
```
EndStone-ARC-CORE/
├── src/endstone_arc_core/
│   ├── __init__.py              # 插件初始化
│   ├── arc_core_plugin.py       # 主插件类（事件、表单 UI、命令、API）
│   ├── DatabaseManager.py       # 数据库管理器（线程安全、表级路由）
│   ├── Economy.py               # 经济系统
│   ├── LandSystem.py            # 领地系统
│   ├── TeleportSystem.py        # 传送系统
│   ├── GuildSystem.py           # 公会数据层（玩法 UI 在独立插件 arc_guild）
│   ├── TitleSystem.py           # 头衔系统
│   ├── PlayerActivityStats.py   # 玩家活动统计
│   ├── SidebarSystem.py         # 侧边栏总控
│   ├── ConditionalTitle.py      # 条件头衔（首富等）
│   ├── setting_catalog.py       # OP 配置文件设置目录
│   ├── op_settings_ui.py        # OP 配置文件设置 UI
│   ├── sky_eye_log.py           # 天眼独立 SQLite 与滚动清理
│   ├── ui_icons.py              # 表单按钮图标路径常量
│   ├── arc_error_log.py         # 错误日志
│   ├── bedrock_glyphs.py        # 基岩版字形处理
│   ├── dimension_utils.py       # 维度 ID 规范化
│   ├── mc_command_format.py     # MC 命令参数格式化
│   ├── EntityDisplayNameManager.py  # 生物显示名管理
│   ├── LanguageManager.py       # 语言管理器
│   ├── SettingManager.py        # 设置管理器
│   ├── sync_protocol.py         # 跨服同步协议
│   ├── sync_server.py           # 跨服同步后端服务端
│   ├── sync_client.py           # 跨服同步远程客户端
│   ├── sync_config.py           # 跨服同步模式与分项开关
│   ├── sync_outbox.py           # 从服可靠上行队列
│   ├── sync_plugin_api.py       # 第三方插件表同步
│   └── sync_write.py            # 跨服写入辅助
├── dist/ARCCore/
│   ├── core_setting.yml         # 配置文件
│   ├── broadcast.txt            # 公告文件
│   ├── entity_display_name.txt
│   ├── newbie_welcome.txt       # 新人欢迎消息文件
│   ├── newbie_commands.txt      # 新人自动执行指令文件
│   └── ZH-CN.txt               # 中文语言包
├── docs/compose/spec/           # 跨服同步等规范文档
└── pyproject.toml              # 项目配置
```

### 核心技术特性
- **线程安全**: 数据库操作完全线程安全（线程本地连接）
- **多线程架构**: 位置检测系统使用独立线程
- **事件驱动**: 基于 EndStone 事件系统
- **定时任务**: 使用 Scheduler 实现定时功能
- **模块化设计**: 各功能模块独立，易于维护
- **动态配置**: 支持运行时配置重载
- **精确坐标计算**: 所有坐标计算统一使用 `math.floor()`，确保负坐标处理正确
- **XUID 主键系统**: 全面使用 XUID 作为玩家标识
- **统一接口设计**: API 和内部功能基于同一套底层接口
- **可视化领地系统**: 支持粒子效果显示领地边界

### API 兼容性
- **EndStone API**: 0.7+
- **Python**: 3.13+

## 📈 性能特性

- **高效的区块索引**: 领地系统使用区块映射，快速定位
- **内存优化**: 合理的缓存策略，减少数据库查询
- **异步处理**: 耗时操作使用定时任务处理
- **资源清理**: 自动清理过期的传送请求和临时数据

## 🔒 安全特性

- **密码保护**：玩家密码使用 SHA-256 哈希存储；**敏感操作**（如转账、领地与部分公会管理）在 **会话内** 验证一次密码即可，兼顾安全与操作流畅度。
- **权限系统**: 基于 EndStone 权限系统
- **输入验证**: 所有用户输入都经过严格验证
- **SQL 注入防护**: 使用参数化查询
- **公会名防注入**: 公会名统一剥离 MC 格式码并禁用 `[]` `"` 等字符

## 🔌 API 接口

其它 EndStone 插件通过 **`server.get_plugin("arc_core")`** 获取核心实例后调用下列方法。多数接口同时支持 **游戏名** 与 **xuid**（填一个即可，**xuid 优先**）；只传游戏名的旧写法仍然有效。接口线程安全。圈地 / 转账 / 建会等敏感写操作仍走游戏内密码验证，不对外提供。

插件 id：`arc_core`（与 pyproject entry-point 一致）。公会 API 见独立插件 `arc_guild`，成就见 `arc_achievement`。

### API 引用示例

以查询指定玩家金钱为例：

```python
from endstone.plugin import Plugin

class MyPlugin(Plugin):
    def on_enable(self):
        self.arc = self.server.get_plugin("arc_core")
        if self.arc is None:
            self.logger.error("未找到 arc_core，请先安装 EndStone ARC Core")
            return

    def check_balance(self, player):
        # 推荐：用 xuid（改名不影响）
        money = self.arc.api_get_player_money(xuid=player.xuid)
        # 亦可：只传游戏名
        # money = self.arc.api_get_player_money(player.name)
        self.logger.info(f"{player.name} 当前金钱: {money}")
```

### API 一览表

#### 经济 / 活动统计

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_get_player_money` | `player_name=""`，`xuid=""` | `float`：余额；找不到为 `0.0` |
| `api_change_player_money` | `player_name=""`，`money_to_change=0`，`xuid=""`，`notify=True` | `bool`：是否成功。正加负减；`notify=False` 不发余额提示 |
| `api_adjust_player_money` | `delta`，`player_name=""`，`xuid=""`，`notify=True` | `dict`：`ok`，`error`，`xuid`，`money`（变动后），`delta`。错误码：`PLAYER_NOT_FOUND` / `MONEY_INVALID_AMOUNT` / `MONEY_DB_ERROR` |
| `api_get_player_money_rank` | `player_name=""`，`xuid=""` | `int`：财富排名（从 1 起）；找不到为 `0` |
| `api_get_all_money_data` | 无 | `dict`：`{玩家名: 金钱}` |
| `api_get_richest_player_money_data` | 无 | `list`：`[玩家名, 金钱]`；无数据为 `["", 0]` |
| `api_get_poorest_player_money_data` | 无 | `list`：`[玩家名, 金钱]`；无数据为 `["", 0]` |
| `api_get_player_stat` | `stat_key`，`player_name=""`，`xuid=""` | `int`：单项活动统计（如 `kill_total`、`kill:minecraft:player`） |
| `api_get_player_stats` | `prefix=""`，`player_name=""`，`xuid=""` | `dict[str,int]`：按前缀筛选；空前缀返回全部 |
| `api_get_player_kill_count` | `entity_id="*"`，`player_name=""`，`xuid=""` | `int`：`*` 为总击杀，否则指定生物 |
| `api_get_player_block_break_count` | `block_id="*"`，`player_name=""`，`xuid=""` | `int`：破坏方块累计 |
| `api_get_player_block_place_count` | `block_id="*"`，`player_name=""`，`xuid=""` | `int`：放置方块累计 |
| `api_get_player_total_assets` | `player_name=""`，`xuid=""` | `dict`：`balance`（现金），`deposits`（定期存款本金），`lands`（名下私人领地成本合计），`total`（三者之和）。供拍卖验资等场景 |

#### 邮箱

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_send_mail` | `title`，`content=""`，`player_name=""`，`xuid=""`，`items=None`，`money=0`，`sender_name="系统"`，`expire_days=None` | `bool`：是否入库成功。支持不在线玩家；在线会收到新邮件 toast。`items` 格式 `[{"item_name": id, "count": n}]`；`expire_days` 缺省用 `MAIL_EXPIRE_DAYS`，`<=0` 永不过期 |
| `api_send_global_mail` | `title`，`content=""`，`items=None`，`money=0`，`sender_name="系统"`，`announce=False`，`expire_days=None` | `bool`：是否入库成功。全服每名玩家各自领取附件；`announce=True` 同时聊天栏全服通告 |
| `api_count_player_mails` | `player_name=""`，`xuid=""`，`unread_only=False` | `int`：邮箱邮件数（含全服邮件）；`unread_only=True` 只数未读 |

#### 侧边栏

其它插件注册页面并推送键值。行模板里的 `{key}` 按 **玩家私有值 → 页面全局值 → 核心内置变量** 解析；缺失键且 `hide_line_if_missing=True` 时整行隐藏。

内置变量：`{time}` `{date}` `{player}` `{money}` `{hp}` `{max_hp}` `{food}` `{tps}` `{mspt}` `{online}` `{max_players}` `{ping}` `{mc_time}` `{title}` `{guild}` `{page}` `{page_total}`。

```python
arc = self.server.get_plugin("arc_core")
arc.api_sidebar_register_page(
    "ars_health",
    "§a健康状态",
    ["§b口渴 §f{thirst}", "§c感染 §f{infection}%", "§e营养 §f{nutrition}"],
    owner="arc_realistic_survival",
    priority=10,
)
# 数值变化时
arc.api_sidebar_set_values(
    "ars_health",
    {"thirst": 78, "infection": 0, "nutrition": "良好"},
    xuid=player.xuid,
)
```

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_sidebar_register_page` | `page_id`，`title`，`lines`，`owner=""`，`priority=0`，`hide_line_if_missing=True` | `bool` |
| `api_sidebar_unregister_page` | `page_id` | `bool`（不可注销 `arc_core_main`） |
| `api_sidebar_set_page_lines` | `page_id`，`lines` | `bool` |
| `api_sidebar_set_page_title` | `page_id`，`title` | `bool` |
| `api_sidebar_set_value` | `page_id`，`key`，`value`，`player_name=""`，`xuid=""` | `bool`：有玩家参数则写私有值，否则写全局值 |
| `api_sidebar_set_values` | `page_id`，`values: dict`，`player_name=""`，`xuid=""` | `bool` |
| `api_sidebar_get_value` | `page_id`，`key`，`player_name=""`，`xuid=""`，`default=None` | 任意 |
| `api_sidebar_clear_values` | `page_id`，`player_name=""`，`xuid=""` | `bool` |
| `api_sidebar_set_global_value` | `page_id`，`key`，`value` | `bool` |
| `api_sidebar_set_page_visible` | `page_id`，`visible`，`player_name=""`，`xuid=""` | `bool`：按玩家显隐（主页不可隐） |
| `api_sidebar_refresh` | `player_name=""`，`xuid=""` | `None`：立即重绘；不传玩家则刷新全部在线 |
| `api_sidebar_list_pages` | 无 | `list[dict]`：`page_id` / `title` / `owner` / `priority` / … |

#### 头衔 / 发奖

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_unlock_title` | `player`（Player），`title` | `bool`：成功；新解锁且在线则发奖，未佩戴时自动佩戴 |
| `api_unlock_title_by_xuid` | `xuid`，`title` | `bool`：离线可记解锁；在线且新解锁则发奖并可能自动佩戴 |
| `api_set_title_definition` | `title`，`rarity`，`description`，`reward_money`，`reward_items=None` | `bool`：创建或**覆盖**定义。`reward_items` 形如 `[{"item_name":"minecraft:diamond","count":1}]`（亦接受键 `id`） |
| `api_ensure_title_definition` | `title`，`rarity="普通"`，`description=""`，`reward_money=0.0`，`reward_items=None` | `bool`：仅当头衔不存在时插入，不覆盖已有定义 |
| `api_get_title_definition` | `title` | `dict \| None`：`title` / `rarity` / `description` / `reward_money` / `reward_items` |
| `api_has_title_definition` | `title`，`rarity="普通"` | `bool`：是否已注册指定名称+稀有度的头衔 |
| `api_list_title_definitions` | 无 | `list[dict]`：全部头衔定义（字段同上） |
| `api_has_unlocked_title` | `title`，关键字：`player=None`，`player_name=""`，`xuid=""` | `bool`：解析顺序 `xuid` → `player` → `player_name` |
| `api_get_equipped_title` | `player_name=""`，`xuid=""` | `str`：当前佩戴头衔；未佩戴 / 找不到为 `""` |
| `api_list_unlocked_titles` | `player_name=""`，`xuid=""` | `list[str]`：已解锁头衔名 |
| `api_give_player_items` | `player=None`，`items=None`，`player_name=""`，`xuid=""` | `bool`：向**在线**玩家 `give`；至少发出一条有效物品为 `True` |

#### 领地

维度会规范化（如 `Overworld` → `minecraft:overworld`）；坐标按三维 AABB（含 Y）。生效顺序：私人/公会 > 公共(`public_priority` 3>2>1)。

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_if_position_in_land` | `dimension`，`position=(x,y,z)` | `int \| None`：生效主领地 `land_id`；不在领地为 `None` |
| `api_resolve_land_at_position` | `dimension`，`position` | `dict`：`dimension`，`land_id`，`sub_land_id`，`is_public`，`public_priority`，`owner_xuid`，`covering_land_ids` |
| `api_list_lands_at_position` | `dimension`，`position` | `list[dict]`：覆盖该点的全部主领地（含 `land_id`），按生效优先级降序 |
| `api_get_land_info` | `land_id` | `dict`：领地详情；不存在为 `{}`。常见键：`land_name`，`dimension`，`min_/max_x/y/z`，`tp_x/y/z`，`shared_users`，`owner_xuid`，`for_sale`，`sale_price`，各类开关，`public_priority`，`block_actor_spawn`，`owner_paid_money` |
| `api_get_player_lands` | `player_name=""`，`xuid=""` | `list[dict]`：该玩家私人领地（含 `land_id`） |
| `api_get_guild_lands` | `guild_id` | `list[dict]`：该公会领地（含 `land_id`） |
| `api_check_land_access` | `dimension`，`position`，`player_name=""`，`xuid=""`，`action="build"` | `dict`：`allowed`，`land_id`，`sub_land_id`，`is_public`，`wilderness`，`action`。静默检查，不发聊天。`action` 为 `build` 或 `interact` |

#### 传送

仅对**在线**玩家生效。

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_teleport_player_to` | `dimension`，`x`，`y`，`z`，`player_name=""`，`xuid=""` | `dict`：`ok`，`error`。错误码：`PLAYER_NOT_ONLINE` / `TELEPORT_FAILED` |
| `api_teleport_player_to_home` | `home_name`，`player_name=""`，`xuid=""` | `dict`：`ok`，`error`。另含 `PLAYER_NOT_FOUND` / `HOME_NOT_FOUND` |
| `api_teleport_player_to_warp` | `warp_name`，`player_name=""`，`xuid=""` | `dict`：`ok`，`error`。另含 `WARP_NOT_FOUND` |
| `api_list_player_homes` | `player_name=""`，`xuid=""` | `list[dict]`：`home_name`，`dimension`，`x`，`y`，`z` |
| `api_list_public_warps` | 无 | `list[dict]`：`warp_name`，`dimension`，`x`，`y`，`z` |
| `api_list_spawn_locations` | 无 | `list[dict]`：`dimension`，`display`，`x`，`y`，`z` |
| `api_list_public_lands` | `limit=50` | `list[dict]`：公共领地摘要（`land_id`，`land_name`，`dimension`，传送点） |
| `api_get_server_landmarks_text` | 无 | `str`：出生点 + Warp + 公共领地，供 AI 指路 |

#### 天眼（Sky Eye）

需服务器开启 `ENABLE_SKY_EYE` 写入（查询历史在关闭后仍可读）。

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_sky_eye_log` | `action`，关键字：`player=None`，`player_name=""`，`player_xuid=""`，`dimension=""`，`x/y/z=0.0`，`detail=""`，`target_name=""`，`target_xuid=""`，`target_type=""`，`resolve_online=True` | `bool`：供其它插件 / 离线场景写入天眼记录；`resolve_online=False` 不反查在线玩家与坐标（进服早期事件用） |
| `api_sky_eye_query` | `player_name=""`，`xuid=""`，`action=""`，`minutes=30`，`time_from=""`，`time_to=""`，`dimension=""`，`x/y/z=None`，`radius=8`，`combat_role=""`，`in_land=None`，`name_fuzzy=True`，`limit=40` | `list[dict]`：事件列表（新→旧）。玩家名默认模糊匹配；`action` 支持精确名或类别别名（`death`/`pvp`/`死亡`/`打怪` 等）；可不传玩家名按时间/坐标查全服 |
| `api_sky_eye_query_text` | 同 `api_sky_eye_query`（另可传 `heading`） | `str`：查询结果纯文本，供弧光天星 / 机器人直接阅读 |
| `api_sky_eye_player_now` | `player_name=""`，`xuid=""` | `dict`：在线返回实时坐标、维度与所在领地；离线返回最近一条天眼记录；含 `name_matches` 模糊匹配列表 |

#### 主菜单按钮 / 聊天前缀

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_register_main_menu_button` | `button_id`，`text`，`on_click`，`priority=6`，`icon=None` | `bool`：向 `/arc` 主菜单注册按钮；`priority` 越小越靠前；同优先级按 `text` 排序；同 id 覆盖；`text`/`icon`/`priority` 可传按玩家计算的 callable；`icon` 为弧光核心RP 内贴图路径（`textures/arc_core/xxx.png`，带 `.png`），缺省显示 ARC logo 兜底图。在 `on_enable` 注册、`on_disable` 时注销 |
| `api_unregister_main_menu_button` | `button_id` | `bool`：注销已注册按钮 |
| `api_register_chat_prefix` | `prefix_name`，`priority=0` | `bool`：注册聊天/展示名前缀槽位；`priority` 越小越靠前（最低 0）；同名覆盖。核心内置 `title=3`；`guild=2` 由 arc_guild 注册 |
| `api_set_player_chat_prefix` | `prefix_name`，`text`，`player_name=""`，`xuid=""`，`visible=None` | `bool`：设置玩家该前缀的展示文本（可含 § 颜色码）；`text` 为空且未传 `visible` 则清除；`text` 传 `None` 可只改显隐；须已注册；不可改内置 `title`；在线则刷新 `name_tag` |
| `api_set_player_chat_prefix_visible` | `prefix_name`，`visible`，`player_name=""`，`xuid=""` | `bool`：仅开关某前缀是否显示，保留已写入文本（如倒地显示/复活隐藏） |

示例（其它插件 `on_enable` 注册主菜单按钮）：

```python
arc = self.server.plugin_manager.get_plugin("arc_core")
if arc and hasattr(arc, "api_register_main_menu_button"):
    arc.api_register_main_menu_button(
        "my_plugin:main",
        "我的功能",
        on_click=self.show_my_panel,  # callable(player)
        priority=6,
        icon="textures/arc_core/my_icon.png",  # 可选：弧光核心RP 内贴图路径；缺省显示 ARC logo 兜底图
    )
```

示例（聊天前缀，priority=1 会出现在公会/头衔之前）：

```python
arc = self.server.plugin_manager.get_plugin("arc_core")
if arc and hasattr(arc, "api_register_chat_prefix"):
    arc.api_register_chat_prefix("vip", priority=1)
    # 之后按玩家设置展示文本：
    # arc.api_set_player_chat_prefix("vip", "§6[VIP]§r", xuid=player.xuid)
```

#### 玩家 / 其它

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_get_player_xuid_by_name` | `player_name` | `str \| None`：在线优先，其次数据库（大小写不敏感） |
| `api_get_player_name_by_xuid` | `xuid`，`with_title=False` | `str`：找不到为 `""`；`with_title=True` 时为公会/头衔展示名 |
| `api_get_player_playtime` | `raw_player_name=""`，`xuid=""` | `dict`：`session_count`，`total_playtime`（秒，含当前会话），`is_online`，`last_join_time`，`last_quit_time`，`xuid`；找不到时时长为 0 |
| `api_get_newbie_guide_text` | 无 | `str`：`newbie_welcome.txt` 全文；失败为 `""` |

#### 跨服插件表同步

第三方插件把自己的 SQLite 表纳入 ARC 跨服同步：业务数据仍写在插件自己的库，下行经 `on_apply` 回调写回。详细规范见 `docs/compose/spec/sync-plugin-api.md`。

| 函数 | 参数 | 返回值 |
|------|------|--------|
| `api_sync_register_namespace` | `plugin_id`，`tables`，`on_apply` | `dict`：`success`，`plugin_id`，`tables`。`tables` 形如 `{table: {"fields": {列: SQL类型}, "primary_keys": [列]}}`；`on_apply(namespace, table, op, data)` 处理下行，`op` 为 `full` / `upsert` / `delete` |
| `api_sync_unregister_namespace` | `plugin_id` | `bool`：注销命名空间，不再接收该命名空间推送 |
| `api_sync_upsert` | `plugin_id`，`table`，`row` | `dict`：`success`，`synced`，`errors`。本地写库成功后整行上行 |
| `api_sync_delete` | `plugin_id`，`table`，`where`，`params=None` | `dict`：`success`，`synced`，`errors`。本地删除成功后上行删除条件 |
| `api_sync_list_namespaces` | 无 | `list`：已注册的同步命名空间 |
| `api_sync_namespace_status` | `plugin_id` | `dict`：`registered`，`tables`，`mode`（`hub`/`client`/`none`），`client`（`active`/`connected`/`server_protocol`/`outbox_pending`） |

#### 公会

公会玩法 API 已拆至独立插件 **`arc_guild`**（仓库 `EndstoneMC-ARC-Guild`）：`api_get_player_guild_info`、`api_get_player_guild_id`、`api_get_guild_info`、`api_list_guild_members`、`api_add_guild_contribution`、`api_get/change_guild_total_contribution`、`api_get/change_member_guild_contribution`、`api_set_guild_size_tier` 等均在该插件上，请 **`server.get_plugin("arc_guild")`** 后调用。核心仅保留软依赖（公会领地、签到贡献点、展示名前缀槽位），查询失败一律视为无公会。

## 📄 许可证

本项目采用开源许可证，详见 LICENSE 文件。

## 🤝 支持与反馈

- **作者邮箱**: DEVILENMO@gmail.com
- **问题反馈**: 请详细描述问题和复现步骤
- **功能建议**: 欢迎提供改进建议

## 📋 近期更新日志

### v0.9.63（当前版本）

- ✅ **外部插件按钮图标改由各插件自带**：`api_register_main_menu_button` / `_put_main_menu_button` 的 `icon` 参数由各插件注册时传入（弧光核心RP 贴图路径，如 `textures/arc_core/guild.png`）；核心移除 `BUTTON_ICONS` 集中映射
- ✅ 已适配自带图标：公会 / 按钮商店 / 木牌商店 / 别踩白块 / 异能与职业 / PvP KD 排行榜 / 枪战游戏 / 证券交易所 / UShop / 属性管理器（仅 OP 可见）

### v0.9.62

- ✅ **主菜单按钮图标三级回退**：按钮自带 `icon` → `button_id` 集中映射 → ARC logo 兜底图 `default.png`

### v0.9.61

- ✅ 版本号顺延：修复表单图标功能与「从服上报」功能占用的 v0.9.60 撞号

### v0.9.60

- ✅ **核心表单按钮接入自定义像素图标**：新增 `ui_icons` 路径常量模块；`/arc` 主菜单与核心面板 37 个按钮带图标；`_put_main_menu_button` / `api_register_main_menu_button` 新增可选 `icon` 参数（支持按玩家计算的 callable）；贴图由客户端资源包「弧光核心RP」提供（`textures/arc_core/`），缺失时 Bedrock 自动不显示图标
- ✅ **`UI_ICONS_ENABLED` 开关**（缺省 `True`）：关闭后全部表单按钮降级为无图标；OP 配置面板「通用」可改
- ✅ **从服时长/次数以主服为准**：从服进退服向同步中心上报该玩家 `session_count`/`total_playtime`，本地只缓存；`api_get_player_playtime` 展示前先向主服拉取
- ✅ **进服记账提前到 delay=1**，便于 QQ 播报读到最新次数

### v0.9.59

- ✅ **修复全新服务器启动崩溃**：空 `core_setting.yml` 首启播种 `DATABASE_PATH` 默认值并兜底
- ✅ 从服进退服向主服上报时长/次数（首版）

### v0.9.58

- ✅ **修复 `/sidebar`、`/sb lock` 重复枚举注册**：两条 usage 合并为可选参数 `[page: str]`

### v0.9.57

- ✅ **杀怪奖励拆出至独立插件 `arc_hunter`（猎魔人）**：贡献点直连 `arc_guild`

### v0.9.56

- ✅ **命令/TPA 弹表单前 `close_form`**；传送倒计时受伤自动打断

### v0.9.55

- ✅ **OP 面板不再含公会管理**：公会管理完全独立，使用 `arc_guild` 的 `/arcguildop`；修复面板仍引用已删除方法导致的报错

### v0.9.54

- ✅ **简化 TPA 倒计时**：去掉 `run_two_player_task`；目标玩家 xuid/name 存进 `run_player_task` 闭包，到期再解析是否仍在线

### 计划中的功能
- 🔄 更多语言包支持
- 🔄 数据备份和恢复

---

*ARC Core 是一个功能完整、性能优异的 EndStone 插件，为服务器管理者提供了一站式的解决方案。*
