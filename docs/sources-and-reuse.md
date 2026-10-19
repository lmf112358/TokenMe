# 来源与复用评估

检查日期：2026-10-10。网络材料仅作为证据与接口说明；没有执行外部仓库脚本，也没有复制其实现代码。

## 第一手来源

- [Codex App Server](https://learn.chatgpt.com/docs/app-server)：初始化协议与 `account/usage/read`。本机实际调用成功；返回摘要、65 个日桶，其他字段通过白名单剔除。接口的普通 ChatGPT 产品覆盖和日界线仍不确定。
- [OpenAI Usage API](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions)：组织 API 用量需要相应管理认证，输入包含缓存；不拿此接口冒充个人订阅统计。本项目未实现此组织接口。
- [OpenAI 订阅与用量说明](https://learn.chatgpt.com/docs/pricing)：订阅额度与 API 定价独立，提示词长度不足以推算消耗。
- [WorkBuddy 套餐与用量](https://www.workbuddy.cn/docs/workbuddy/Usage)：官方索引说明账号页面提供积分明细；本轮网页正文抓取失败。Token 字段的实现依据是本机实际 trace schema，不是推测积分换算。
- [WorkBuddy Enterprise 积分说明](https://cloud.tencent.com/document/product/1831/134339)：积分是平台资源配额单位，会随任务与模型变化。
- [Kimi Code 会话存储](https://www.kimi.com/code/docs/en/kimi-code-cli/guides/sessions.html)：编程工具的本地 session 记录；不能推论成 Kimi 网页/App 的全账号接口。
- [Qwen Code 配置](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/settings.md)：代码工具遥测与本地记录边界。
- [千问个人 Token Plan FAQ](https://platform.qianwenai.com/docs/token-plan/personal/token-plan-personal-faq)：Token Plan 与普通聊天分开确认。
- [DeepSeek 隐私政策](https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html)：可以导出历史对话；该说明未承诺包含真实计费 Token 字段。
- [百炼模型用量](https://help.aliyun.com/zh/model-studio/model-usage-statistics)：控制台与账单导出适用于模型服务账号，与千问聊天入口分开。

## 复用选择

| 候选 | 适配与许可证 | 维护、平台和集成成本 | 本次决定 |
|---|---|---|---|
| Python 标准库 | JSON、时间、路径、子进程、测试已满足 MVP | 零运行时依赖；Windows 实测，其他平台未实测 | 直接使用 |
| [ccusage](https://github.com/ccusage/ccusage) | MIT；成熟的多编程工具用量采集和 JSON 输出；不覆盖所有网页/App，当前支持列表未列 WorkBuddy | 活跃项目；支持多系统，但版本和 schema 会变化；直接安装增加供应链及运行时范围，安全记录尚未完整审计 | 实现可替换的 JSON 导入桥接；不安装、不打包源码 |
| [WorkBuddy Token Tracker](https://github.com/abc1317679842-ui/workbuddy-token-tracker) | MIT；针对 WorkBuddy 的较完整统计、hook 与通知体系 | 项目规模较小、更新频繁；通知偏 Windows；包含当前任务不需要的价格、hook、网络功能；仓库提示过同名 npm 包风险，未独立核验 | 仅参考公开的覆盖边界线索；依据本机字段独立实现小型只读 trace 适配器 |
| [TokenRank](https://github.com/tokenrank/tokenrank) | MIT；公开身份、排行榜、上传后端 | 完整 Web 栈比当前本地验证范围大；不解决所有个人平台原始数据可得性 | 暂不引入 |

应用运行仍未打包第三方实现代码，MIT 为本工程许可证。SQLite 使用 Python 标准库，避免维护自制事务存储。二维码复用开发工具生成固定素材，运行时只读取矩阵并由 Canvas 绘制，见下文。

### 二维码复用（2026-10-12）

- 工具：[Nayuki QR Code generator](https://www.nayuki.io/page/qr-code-generator-library)，[PyPI qrcodegen 1.8.0](https://pypi.org/project/qrcodegen/1.8.0/)，MIT。
- 适配：纯 Python、单文件，无传递依赖，可生成四级纠错的模块矩阵，适合固定公开链接。无需运行时网络、图片服务或整个 UI 组件库。
- 固定 wheel SHA-256：`06bf87021bc351f1c6e722ac67db8a059c4fe27bbfbca39ed7a9a2364abdd7a6`，开发 requirements 以 hash 固定。官方 1.8.0 发布较早；成熟编码格式无需追逐新版本，未来改链路时复核维护与安全状态。
- 审查：下载 wheel 后读取源码许可、编码入口及 AST 导入/调用集合；仅标准库数学、序列、正则等，无文件/网络/进程执行。没有声称完成全面安全审计或确认不存在漏洞。
- 集成：`scripts/generate_qr.py` 生成 `share-qr.json`，矩阵只包含固定公开仓库 URL。库源码不拷入产品，用户安装不引入依赖；未来可替换生成器。
- 独立验证：本地测试工具 zxing-cpp 2.3.0（Apache-2.0）解码实际 PNG 和模拟压缩图；Pillow 11.3.0（MIT-CMU，按 wheel 元数据核验）仅做验证图像处理，均安装在 Git 忽略目录，不随应用分发。

ccusage 桥接遵循 [2026-10-10 查阅的 unified daily JSON 文档](https://ccusage.com/guide/json-output)：采用 per-agent 日桶，inputTokens 不含 cacheReadTokens / cacheCreationTokens，总量关系必须逐条吻合。该合同以合成样本测试，不代表已验证所有 ccusage 版本；不接受未知口径时自动猜测。

## 验证范围

### 多平台扩展复用评估（2026-10-13）

- 现有 `normalize_usage`、`UsageRecord`、SQLite 事务、诊断与历史去重继续复用。新增解析使用标准库 `json/csv/sqlite3`，没有引入运行依赖或复制第三方实现。
- [Tokscale](https://github.com/junhoyeo/tokscale)，本轮固定查阅 commit `bd62b8c4e07269e5314fac06c6d23262dc714633`（MIT）：覆盖广、持续维护，含 Rust 核心与 Node/Bun CLI。其 scope 包含登录、凭据恢复、缓存同步、计价、公开排名，直接嵌入的依赖与安全审查成本明显超过当前离线读取需求。只用其 Cursor CSV/TRAE cache 字段合同作为格式参考，独立编写严格解析器；不执行仓库脚本或登录流程。未完成其完整漏洞/依赖审计，不声称其安全已验证。
- [ccusage](https://github.com/ccusage/ccusage)（MIT）：保留现有文件桥接，不自动安装或追随 latest；各版本输出需按合同验证。新原生源与其同义 agent 名称发生重叠时拒绝合并。
- [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)：本地会话与 API usage、缓存排除于 input 的合同；另以本机 JSONL 样本核实结构，不导出正文。
- [Pi 消息合同](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/message-types.md)：input/output/cacheRead/cacheWrite、reasoning 子集、toolResult usage；[session 合同](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/session-format.md)用于分支与摘要记录。
- [Gemini 记录器](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingService.ts)、[Qwen 记录器](https://github.com/QwenLM/qwen-code/blob/main/packages/core/src/services/chatRecordingService.ts)：chat JSON/JSONL 与 usageMetadata 字段；未知 tool 用量合同保守跳过。
- [OpenCode getUsage](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/session.ts)：持久化 output 排除了 reasoning，input 排除了缓存，因此归一时补回相应子集。数据库为只读，兼容旧 JSON。
- [Cursor analytics](https://cursor.com/docs/account/teams/analytics)：导出入口与权限边界。具体 CSV 合同参考固定 Tokscale schema；尚缺真实个人导出样本。
- [TRAE 企业个人用量](https://docs.trae.cn/enterprise_check-individual-usage)：CN 企业导出与国际版 cache 区分；[优惠用量说明](https://docs.trae.cn/enterprise_half-price-campaign-for-trae-built-in-models)说明不能把折后用量当原始 Token。
- [Qoder CLI](https://docs.qoder.com/cli/commands)、[Qoder usage API](https://docs.qoder.com/account/teams/openapi/usage)：文档提及 Token，但所查事件示例与字段主要为 Credits，当前没有将它换算进账本。
- [豆包会员说明](https://www.doubao.com/legal/ey01)：次数/时长展示不构成原始 Token 导出合同。

以上来源用于字段与范围核对，不代表全部客户端版本经过真实验证。可读性、许可证和维护范围已评估；未采用外部运行代码，因此不增加第三方运行许可证负担。后续决定集成外部采集器时仍须重新审查版本、依赖、安全记录与凭据访问。

- 本机实际数据：Codex JSONL、WorkBuddy JSON trace、官方 Codex 账号摘要。
- 合成数据测试：口径归一、去重、重置、截断、日期过滤、未知值、隐私白名单、ccusage 桥接、HTML 注入。
- 不包含：所有平台账号、跨设备/跨账号全量对账、服务商签名验证、所有版本日志兼容、借贷/职业能力评级。

### Tokscale 桥接复用（2026-10-14）

沿用已核对的 MIT 仓库 commit `bd62b8c4e07269e5314fac06c6d23262dc714633`，Cargo 工作区版本 4.18.0。核对 CLI graph 的 camelCase 序列化、五桶独立相加和 client ID 定义。采用统一文件桥接，复用上游采集成果；独立实现 Python 标准库解析与 TokenMe 现有日桶事务，不嵌入 Rust/Node 栈，不执行下载源码或登录流程。依赖规模保持不变，后续可替换或停用桥接，不声称完成上游完整安全审计。具体固定来源、输入范围和验证限制见 [Tokscale 导入](tokscale-import.md)。
