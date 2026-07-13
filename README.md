# 狮城雷达 SG Radar

新加坡活动与优惠聚合器：每天抓取 7 个来源，汇总成一个可随时打开的本地网页，
并通过**持续追踪**自动识别"长期营销"型假优惠（比如天天都有的 "up to 90% off"）。

## 快速开始

```
双击 update.bat        → 抓取最新数据并重新生成页面
打开 site\index.html   → 浏览（可加入浏览器书签/固定标签页）
```

首次运行会自动创建 `.venv` 并安装依赖。

## 每天自动更新（可选）

在命令行执行一次（每天上午 9 点自动抓取）：

```
schtasks /create /tn "SG Radar Daily" /tr "\"C:\Users\sinji\Desktop\DS_project\SG Event\update.bat\"" /sc daily /st 09:00
```

删除：`schtasks /delete /tn "SG Radar Daily"`

## 数据来源

| 来源 | 内容 | 方式 |
|---|---|---|
| SINGPromos | 优惠（标题多带截止日期） | RSS |
| MoneyDigest | 优惠/本地生活 | RSS |
| GreatDeals | 优惠 | RSS |
| Honeycombers | 活动/生活方式编辑推荐 | RSS |
| Little Day Out | 亲子活动 | RSS |
| Eventbrite SG | 结构化活动（场地/日期） | 页面内嵌 JSON-LD |
| Peatix SG | 社区活动/工作坊 | JSON 接口（按时区过滤） |

新增 RSS 来源：在 `src/config.py` 的 `RSS_SOURCES` 里加一行即可。

## 真实度识别逻辑

假优惠的破绽不在文案里，而在时间轴上：

- **限时** — 解析出明确截止日期（"until 14 July"、"14-16 Jul"、"June 16 to 21" 等格式）
- **待观察** — 没有截止日期，暂无重复记录
- **长期营销** — 同一促销指纹（去掉日期/数字后的标题签名）在 **21 天内出现 ≥3 次**
  → 基本每天都有，自动打灰划线，默认隐藏

历史全部存在 `data/tracker.db`（SQLite），**永不删除**——跑得越久识别越准。
过期促销会从页面剔除，但保留在库里用于复发检测。

## 小红书（可选源）

两条路，二选一。**推荐路 A（付费 API）**：人在境外时唯一稳定的方式。
路 B（自建爬虫）会撞境外 IP 风控，见下方说明。

### 路 A：TikHub 付费 API（推荐，境外可用、不碰你的账号）

[TikHub](https://tikhub.io) 在境内跑抓取，你只按量拿 JSON（约 $0.01/次请求，
一次搜索返回一页约 20 条），你的账号和 IP 完全不参与，无封号风险。

**接入 3 步**：
1. 到 [user.tikhub.io](https://user.tikhub.io) 注册（免信用卡，注册送免费额度），
   在控制台 API Keys 里新建一个 key 并复制（**只显示一次**）。
2. 在项目根目录建一个文件 `.tikhub_key`，把 key 粘进去（就一行，已在 .gitignore，不会外泄）。
3. 双击 `update.bat`（就是主更新脚本）。检测到 key 就自动接入小红书源，无需扫码、无需浏览器。

关键词/页数在 `src/config.py` 的 `XHS_KEYWORDS` / `XHS_PAGES_PER_KEYWORD`。
成本估算：4 关键词 × 2 页 = 8 次/天 ≈ **$0.08/天**，免费额度够试很久。

> TikHub 返回字段官方文档不全，接入代码已做多字段容错；万一首次跑发现某字段没映射对
> （比如点赞数为空），改 `src/scrapers/xhs_api.py` 的 `_note_fields()` 几行即可。

### 路 B：MediaCrawler 自建爬虫（用你自己的账号，境外 IP 会被风控）

基于开源项目 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)（vendor/MediaCrawler，
非商业学习许可），用 Playwright 驱动真实浏览器 + 你自己的账号搜索抓取。

> ⚠️ **已知限制**：从新加坡等境外 IP 跑，小红书会在登录成功后对搜索接口返回
> 「您当前登录的账号没有权限访问」（多维风控判定环境异常）。换 Spider_XHS 等其他
> 开源工具同样无效——根因是境外 IP + 环境突变，不是签名。要走这条得配国内住宅代理
> （`config/base_config.py` 的 `ENABLE_IP_PROXY`，代理池自备）。

**首次使用**：双击 `update_xhs.bat` → 弹出浏览器窗口显示二维码 → 用小红书 App 扫码登录
→ 自动抓取并重建页面。登录态会保存（`browser_data/`），之后运行不用再扫。

**配置**：关键词在 `vendor/MediaCrawler/config/base_config.py` 的 `KEYWORDS`
（当前：新加坡优惠/新加坡折扣/新加坡活动/新加坡周末，按时间排序，每词 15 条，不抓评论）。

**已知坑（重装时注意）**：
- MediaCrawler 新版默认开 CDP 模式（连你自己的 Chrome），会卡在"CDP port 9222 not accessible"。
  已在 `config/base_config.py` 关掉：`ENABLE_CDP_MODE = False`（用它自带的 Chromium）。
- 依赖 `xhshow` 必须钉死 `==0.1.9`；`0.2.0` 改了签名函数参数，会让 MediaCrawler 的
  猴子补丁报 `got multiple values for argument 'sign_state'`。已在 vendor 的 requirements.txt 钉好。

**风险须知（务实版）**：
- 用的是你自己的账号，平台风控可能触发滑块验证（手动完成即可）；极端情况有限流/封号风险
- 已按保守参数配置（低频、小量、请求间隔 3 秒）；建议**每天最多跑 1-2 次**，或考虑用小号
- 仅供个人使用，不要转发采集的数据集

无论走 A 还是 B，抓到的笔记都进小红书卡片墙。两条路输出格式一致，pipeline 优先用
TikHub（有 `.tikhub_key` 时），否则回落到 MediaCrawler 的抓取结果。封面图从笔记的
`images_list` 取（小红书 CDN 带时效签名链接，加载不出会自动回落成色块，跑一次即刷新）。

小红书是 dashboard 里的一个来源（`source_name=小红书`，可用「类型」筛选切换），
不是单独页面。

## 信息归一化（merchant · offer · price）

各来源标题排版天差地别(英文长句 / 中文 emoji 标题党 / 活动名),`src/normalize.py`
把它们统一成「**商家 · 一句话优惠 · 价格**」并判真伪,dashboard 才能一眼扫读。两层:

1. **规则清洗(免费,always-on,兼 LLM 兜底)**:切商家、正则抽价格、去 `Singapore/Promotion` 废词。
2. **LLM 增强(OpenRouter 免费模型)**:key 存 `.openrouter_key`(gitignore)。批处理 + 动态选可用
   `:free` 模型 + 回落链 + 成功后复用同模型(省免费额度,因为**失败请求也算额度**)。
   每次跑上限 120 条、优惠优先;结果存 `records.norm`,只算一次,LLM 失败的下次自动重试回填。

**OpenRouter 免费额度**:50 次/天(累计充值 < $10)或 1000 次/天(充过一次 $10,永久)。
本项目批处理 12 条/请求,每天几次请求就够,免费额度绰绰有余。没有 `.openrouter_key` 时
自动只用规则清洗,不影响运行。

## 维护

- `.venv\Scripts\python -m src.pipeline --reextract` — 改进日期解析规则后，
  对已入库的旧数据重新提取日期（以发帖日期为年份参照）
- 运行日志存在 `runs` 表：`SELECT * FROM runs ORDER BY run_at DESC`

## 路线图

- [x] 小红书：已通过 MediaCrawler 接入（见上节，需扫码启用）
- [ ] STB 官方活动 API（api.stb.gov.sg / TIH，需免费申请 key）
- [ ] 商场活动日历（CapitaLand / Frasers 各 mall 的 What's On 页）
- [ ] Telegram 优惠频道（公开频道可用 t.me/s/ 网页版抓取）
- [ ] 手机访问：GitHub Pages 或定期发布 Artifact
- [ ] 地点/区域筛选（Eventbrite 已有坐标数据存库）
