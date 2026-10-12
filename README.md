# TokenMe · 我的 AI 足迹

一个本地优先的个人 AI 用量统计原型，把可读取的真实记录变成个人档案与分享卡。

**当前阶段：0.1 技术验证，不是所有个人 AI 账号的一键同步器。**

## 项目目录

Git 仓库：[lmf112358/TokenMe](https://github.com/lmf112358/TokenMe)。当前本地检出目录为 `tokenme/repo`；执行命令前进入该目录。原型沿用 `token_footprint` Python 模块和 `token-footprint` 命令名称。

- `token_footprint/`：统计内核、适配器与报告界面。
- `tests/`、`docs/`：现有测试及接入、口径、验证说明。
- `../outputs/`：本机保留的产品设计 Word 文档及原始 0.1 发布包，位于仓库外；该压缩包是迁移前快照，不会随源码自动更新。
- `../.local/my-token-report/`：本机已生成的个人报告与分享卡，位于仓库外。
- `../.local/migration-work/`：原工作目录的调研、文档生成脚本和排版检查材料，作为仓库外的历史归档保留。

上述仓库外资料不会随 Git 克隆分发。仓库内的 `outputs/` 和 `.local/` 也已加入 Git 忽略，避免将个人报告、调研数据及包含个人截图的设计文档意外提交。后续扫描默认生成仓库内的 `.local/report/report.html`，不会覆盖外层已归档的个人报告。

## 已实现

- Codex：读取本机 `sessions` 与 `archived_sessions`，将累计计数转换成增量，处理重复快照和带原时间戳的 fork 历史。
- WorkBuddy：读取本机 `traces` 的模型用量汇总，按 trace ID 去重，缓存作为输入子集。
- OpenAI / Codex 账号：通过已有、已登录的原生 Codex 客户端调用官方 `account/usage/read`，保留累计摘要和每日桶，丢弃其他字段。
- ccusage 桥接：导入官方文档中的 unified daily JSON，扩展到其支持的 Kimi Code、Qwen Code 等；不下载或执行外部包。桥接按文档样例验证，尚未在此机上运行 ccusage 做实测。
- 本地 HTML 报告：切换月份、查看输入/输出/缓存、采集诊断、生成 PNG 分享卡。
- 统计内核及边界条件测试；Python 标准库实现，运行时零第三方依赖。

## 快速运行

需要 Python 3.10+。在本项目根目录执行，无需安装：

```powershell
python -m token_footprint scan --month 2026-10
```

双击 `.local/report/report.html`。扫描只读取指定客户端的保留日志；不读登录凭据，不联网，不上传。日志在本地解析后，仅输出白名单统计字段。

可单独选择来源或自定义数据目录：

```powershell
python -m token_footprint scan --sources workbuddy --workbuddy-root "D:/MyWorkBuddy" --offset +08:00
python -m token_footprint scan --codex-root "D:/MyCodex" --month 2026-10
```

`--home` 可指定含 `.codex` 和 `.workbuddy` 的测试或备份目录。默认 Codex 数据目录尊重现有 `CODEX_HOME`；不修改它。

## 可选：官方账号活动

使用已有 Codex 登录态，由官方客户端处理认证。本程序不打开认证文件、不提取 Cookie，也不获取 API Key。这个命令会联网查询用量，不发起模型任务。

```powershell
python -m token_footprint account --codex-bin "完整路径/codex.exe" --out .local/account-usage.json
python -m token_footprint scan --account-file .local/account-usage.json --month 2026-10
```

传入原生 `codex.exe` / `codex`，不能传 `codex.ps1`、`.cmd` 等 shell 包装器。当前客户端或账号可能不支持该接口；程序会明确报错。某些返回字段可能为 null；null 不等于零。

**账号活动和本地明细分别展示，禁止直接相加。** 官方文档未充分界定该摘要是否覆盖所有普通 ChatGPT 聊天，以及日桶的时区边界；界面保留这一不确定性。

## 可选：复用 ccusage 的已有导出

在你已安装、审查并固定版本的 ccusage 中生成：

```text
ccusage daily --by-agent --json --no-cost
```

把输出保存为 UTF-8 JSON，再导入：

```powershell
python -m token_footprint scan --sources workbuddy --ccusage ./my-ccusage.json --offset +08:00
```

`--offset` 必须与源导出的日界线一致。桥接只接受带 agent 的日桶，并核对 `totalTokens = inputTokens + cacheReadTokens + cacheCreationTokens + outputTokens`。原生 Codex 与 ccusage Codex 同时出现会拒绝导入，避免重复计数。不要把多个相互覆盖的账号、设备或账单直接相加。

## 统一口径

```text
总 Token = 输入总量（含缓存读取/写入）+ 输出总量（含推理）
```

- 缓存、推理是子集，不额外加到总量。
- 缺失的明细保留 null，不伪装成 0。
- 积分、金额、订阅百分比各自保留原单位，0.1 不做 Token 换算。
- 不同分词器的原生 Token 可以形成“原生 Token 数量之和”，不代表等价算力或价值。
- 当前本地统计默认 UTC+08:00；可设置固定偏移。尚不支持跨夏令时的历史 IANA 时区重算。
- WorkBuddy 的一个 trace 若跨日，暂归入结束日；多模型 trace 标为 mixed/unknown，不猜测拆分。
- 本地使用记录可被用户修改。字段一致性检查不等于服务商认证。

## 当前覆盖边界

| 入口 | 状态 | 说明 |
|---|---|---|
| Codex 本地桌面 / CLI | 已实测 | 仅此机保留记录；云端、远程机需另行接入 |
| WorkBuddy 桌面 | 已实测 | trace 级汇总；子代理、异常中断与被清理记录可能缺失 |
| OpenAI / Codex 账号摘要 | 已实测 | 官方接口原样口径；与本地明细独立 |
| Kimi / 千问 / DeepSeek 网页与 App | 未接入 | 尚未确认稳定的个人账号完整 Token 读取接口 |
| Kimi Code / Qwen Code | ccusage 桥接 | 是编程工具，不等于对应网页/App 全账号 |
| 开发者 API 账单 | 后续范围 | 不能替代个人订阅数据 |

## 开发与验证

```powershell
python -m unittest discover -s tests -v
```

测试使用合成数据，覆盖缓存/推理双计、累计差分、重复/fork、日界线、未知值、trace 更新、导入重叠、隐私白名单和 HTML 注入。真实使用文件仅在 `.local/` 或仓库外；不要提交个人报告。

项目说明见 [接入与统计设计](docs/design.md)、[来源与复用评估](docs/sources-and-reuse.md)。新增平台应先拿到脱敏字段样本和计数语义，再写适配器与边界测试。

## 开源

代码采用 MIT License。项目名称暂定，未检查商标或包名可用性。
