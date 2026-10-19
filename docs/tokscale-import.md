# Tokscale 多平台导入

TokenMe 可读取 Tokscale 4.x 的 `graph --output` JSON，将其多平台统计接到本地历史、I 量、材质和分享图。当前核对版本为 **4.18.0**，上游 commit `bd62b8c4e07269e5314fac06c6d23262dc714633`。这是文件桥接；TokenMe 不安装、启动、登录 Tokscale，也不读取它的凭据或上传数据。

## 两步生成档案

已有 Tokscale 的用户先导出，再导入 TokenMe。下面假定 Tokscale 的日界线为亚洲上海时区（固定 UTC+08:00）：

```shell
tokscale graph --output usage.json
python -m token_footprint run --sources none --tokscale usage.json --tokscale-offset +08:00 --out .local/tokscale-report --open
```

安装过 TokenMe 后可将 `python -m token_footprint` 换成 `tokenme`。使用独立输出目录可避免与此前原生采集的同平台记录重叠。Tokscale 导出动作本身可能同步其已配置的账号或读取定价；这不属于 TokenMe 的离线导入行为。

**必须核对原导出日界线。** Tokscale graph 文件没有携带足够的时区信息；其日界线取决于 Tokscale 的 `scanner.bucketTimezone` 设置。`--tokscale-offset` 是使用者对原导出日界线的明确声明，必须与 TokenMe 的 `--offset` 相同。默认 `--offset` 为 `+08:00`。例如原数据按固定 UTC 统计时，两项均设 `+00:00`。不能将纽约跨夏令时历史简单声明为固定偏移；当前应重新按固定时区导出或留待后续 IANA 支持。

## 只补充缺少的平台

```shell
python -m token_footprint run --sources codex,claude --tokscale usage.json --tokscale-offset +08:00 --tokscale-clients openclaw,cline,hermes --out .local/combined-report --open
```

`--tokscale-clients` 使用 Tokscale client ID，逗号分隔。它只过滤这次的文件导入，不删除已保存历史；整个文件仍先经过一致性校验。`--tokscale` 可以重复指定，但同次输入中同平台同日计数冲突会拒绝，不猜测哪个文件更新。

本版登记了上游的 58 个 client ID，涵盖 OpenClaw、Hermes、Cline、Roo Code、Kilo、Cursor、TRAE 国际版、Copilot、Amp、Droid、CodeBuddy、WorkBuddy、Gemini、Kimi、Qwen、OpenCode 等，并接受规范的 `cc-mirror/<name>`。完整 ID 见 `token_footprint/tokscale.py` 的 `CLIENT_NAMES`。

登记 ID 表示可接收相同格式的汇总，不代表我们已实测这 58 款客户端，也不保证 Tokscale 对每个平台都能取得 Token。只有金额、Credits 或请求次数的数据不会换算成 I。豆包普通聊天、Qoder 等不因此自动获得原始 Token 接入。

## 统计与历史规则

- Tokscale 的五桶为独立计数：`input + output + cacheRead + cacheWrite + reasoning`。TokenMe 归一为输入含缓存、输出含推理；不重复加 reasoning。
- 逐项核验 client 五桶之和 = 当天 `tokenBreakdown`，当天五桶之和 = `totals.tokens`，所有天总和 = `summary.totalTokens`。汇总、年份和明细不会重复累计。
- 每个平台每日保存一个 `daily_bucket`。多个模型/供应商合并成该日完整快照，模型记为 `mixed/unknown`；当前不保留模型分布、会话、消息数、费用或时长。这样修订时不会残留已消失模型的旧数值。
- 同一文件重复导入不累加；同平台同日的新导入替代该日旧桶。**最后一次导入为权威版本**，与现有 ccusage 规则相同。不要使用旧导出、其他账号/设备、只筛选部分模型或不完整的当日快照覆盖原数据。`generatedAt` 仅做格式及未来日期校验，当前不用于跨批次新旧排序。
- 未出现在新文件中的日期/平台继续保留。明确出现的零值桶可以将旧值修订到零，零值不算活跃日；空文件不会清空历史。
- 同一平台的 Tokscale、ccusage 日桶、原生逐请求采集不能在同一库混用，即使日期暂不重叠。已有历史、备份恢复和 `--no-history` 均检查。Claude 别名及 cc-mirror 也在冲突范围内。
- 导入记录维持 `local_record` 证据等级：上游标准化结果和本地导出文件不等于服务商签名验证。个人档案的完整性依赖源数据。

报告对平台标注“已导入（日汇总）”；重新从历史库生成报告仍保留这一标识。新增平台名称也会用于分享图。

## 不支持的输入与隐私

目前仅支持上述 camelCase graph 合同。TUI 按 `e` 导出的 models/sessions JSON、Rust 内部 snake_case、网页排行榜的嵌套 models 结构、缺字段/未知版本/重复或冲突记录会拒绝。所有输入解析完成后才合并账本。

导出中可能含 `device`、`mcpServers` 或其他额外信息；TokenMe 只保留平台、日期和归一计数等账本白名单。不会把设备名、MCP 名称、对话、项目路径、费用等额外字段写入报告。原始 `usage.json` 仍应自行保管，不要提交到公共仓库。

## 复用依据

- [上游 CLI 序列化与 graph 命令](https://github.com/junhoyeo/tokscale/blob/bd62b8c4e07269e5314fac06c6d23262dc714633/crates/tokscale-cli/src/main.rs)：`run_graph_command`、`to_ts_token_contribution_data`。
- [计数桶定义](https://github.com/junhoyeo/tokscale/blob/bd62b8c4e07269e5314fac06c6d23262dc714633/crates/tokscale-core/src/lib.rs)：`TokenBreakdown::total`。
- [client ID 合同](https://github.com/junhoyeo/tokscale/blob/bd62b8c4e07269e5314fac06c6d23262dc714633/packages/frontend/src/lib/types.ts)。

Tokscale 为 MIT；我们独立编写标准库文件解析器，只参考公开数据合同，未复制其实现、打包其程序或增加运行依赖。没有安装或执行上游脚本，没有完成其完整安全审计。当前验证为合成合同样本和 TokenMe 端到端测试，尚未在本机运行 Tokscale 做真实日志对账。
