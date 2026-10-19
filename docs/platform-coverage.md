# 多平台覆盖 · v0.2.0.dev3

2026-10-14 补充：增加 [Tokscale graph 文件桥接](tokscale-import.md)，按其 4.x 合同导入更多平台的日汇总。原生读取与桥接导入分别标记，不把登记的平台数量当作真实客户端实测数量。

检查日期：2026-10-13。覆盖的是下列客户端的指定数据格式，不是同品牌所有产品、所有版本或全部账号。默认扫描离线，不启动模型、不读取登录凭据、不上传对话。不能取得真实计数的入口显示“待接入”，不填零或用字数估算。

| 来源 | 接入方式 | 口径 / 验证范围 |
| --- | --- | --- |
| Codex | `.codex/sessions`、`archived_sessions` | 累计差分、重放去重；Windows 真实记录 |
| WorkBuddy | `.workbuddy/traces` | 已结束 trace 最新快照；Windows 真实记录 |
| Claude Code | `.claude/projects`、`transcripts`，递归含 subagents | input + cache read + cache creation + output；同响应 ID 的最新快照；Windows 真实记录 |
| Pi Agent | `.pi/agent/sessions` | input + cacheRead + cacheWrite + output；reasoning 属于 output，cacheWrite1h 属于 cacheWrite；消息、工具及已有摘要 usage；Windows 真实记录 |
| Gemini CLI | `.gemini/tmp/*/chats/*.json`、`*.jsonl` | input + output + thoughts；cached 属于 input；校验 total；重放/回溯不删除已消耗用量；合成样本 |
| OpenCode | `.local/share/opencode/opencode*.db` 和 `storage/message` JSON | input + cache.read + cache.write + output + reasoning；已完成消息；数据库只读，JSON/SQLite 同 ID 去重；合成样本 |
| Qwen Code | `.qwen/projects/*/chats/*.jsonl` | usageMetadata 的 prompt + candidates + thoughts；cached 属于 prompt；不是 contextWindowSize；合成样本 |
| Kimi Code / CLI | `.kimi/sessions`、`.kimi-code/sessions` 下 `wire.jsonl` | StatusUpdate.token_usage / usage.record 的 turn 用量；非缓存输入 + 缓存读写 + 输出；合成样本 |
| Cursor | 显式 `--cursor-csv` | 官方用量 CSV 的四个独立 Token 桶，必须与 Total Tokens 一致；合成样本，真实导出待验证 |
| TRAE 国际版 | 显式 `--trae-json` | 会话用量数组中 extra_info 的四个独立 Token 桶；兼容已同步的 Tokscale session cache 格式；合成样本，真实导出待验证 |
| TRAE 中国版 | 待接入 | 企业 API/导出与国际版不同，不能互套 |
| Qoder | 待接入 | 已发现本机安装，但未取得可验证的 Token 记录；已查接口主要为 Credits |
| 豆包电脑版 | 待接入 | 已发现本机安装，但未取得可验证的原始 Token 记录；会员次数/时长不是 Token |

## 使用

```shell
python -m token_footprint doctor --json
python -m token_footprint run --json
python -m token_footprint run --sources claude,pi --json
python -m token_footprint run --claude-root /backup/.claude --pi-root /backup/.pi/agent --json
python -m token_footprint run --sources none --cursor-csv /private/cursor.csv --json
python -m token_footprint run --sources none --trae-json /private/trae-sessions.json --json
```

`all`（默认）只选择 8 个本地适配器，不会自动登录 Cursor/TRAE 或抓取账号。`--sources none` 配合文件导入；两个导入参数可重复指定。`--sources` 是本次采集范围，历史报告仍含该库全部来源。

各 `--<source>-root` 指客户端数据根目录，后面由程序补齐 sessions、projects、tmp 等路径。`--home` 指一个备份用户目录，避免误读真实用户目录的环境变量。默认真实用户目录下尊重 `CODEX_HOME`、`CLAUDE_CONFIG_DIR`、`PI_CODING_AGENT_DIR`、`GEMINI_CLI_HOME`、`XDG_DATA_HOME`。Kimi 自定义 root 后只扫描该 root 下的 sessions。

## 导入合同

Cursor CSV 必须含 Date、Model、Input (w/ Cache Write)、Input (w/o Cache Write)、Cache Read、Output Tokens、Total Tokens。列顺序无关，可多出费用等列，但费用不计入 I。名称中的 `Input (w/ Cache Write)` 在此支持的导出合同中表示独立的缓存写入桶。必须满足四桶相加等于 Total Tokens；不满足则拒绝整个导入。

Date 必须带明确时区；不猜测系统时区。没有 Request ID 的行采用时间、模型、Kind、Cloud Agent ID、Automation ID 组合标识。同一文件中无法区分的同键事件会拒绝导入；跨次计数冲突也拒绝，不以新数值拼接虚增。支持带规范千位分隔符的整数，不支持 K/M 缩写或近似值。

TRAE JSON 是数组，各行要求 session_id、usage_time（Unix 秒）和 extra_info.input_token/output_token/cache_read_token/cache_write_token。按 session_id + usage_time + model_name 去重；同键不同计数需先对账。没有缓存字段、只有金额/Credits 的输入拒绝，不能把空字段当零。不读取 Tokscale 的凭据，不执行其 sync/login。

## 一致性边界

- 一个历史库只用于一个人的已确认数据范围。未知账号、跨设备复制和导出范围重叠仍需核对。
- ccusage 同来源日桶和本地逐请求记录禁止混用；claude-code/claude 等已知别名也会拦截。旧库出现多种同义来源名称时必须先对账，不能自动相加。
- 未知/缺失缓存字段不是零。部分不完整记录会跳过并计入诊断；正常读取数不代表账号全量。
- JSON/CSV 导入保持 `local_record` 证据等级：即使源自官方导出，本地文件仍可修改，不宣称服务商签名认证。
- 没有凭据解密、浏览器 Cookie 获取、在线自动同步或全品牌兼容承诺。

已知缺陷与验收条件见 [平台接入缺陷清单](platform-gaps.md)。
