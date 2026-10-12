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

当前工程没有打包或改编第三方实现代码，因此无第三方运行时版本锁定项；MIT 为本工程许可证。未来采用第三方库时，必须补充固定版本或 commit、许可证文本、必要的安全审查与平台验证。

ccusage 桥接遵循 [2026-10-10 查阅的 unified daily JSON 文档](https://ccusage.com/guide/json-output)：采用 per-agent 日桶，inputTokens 不含 cacheReadTokens / cacheCreationTokens，总量关系必须逐条吻合。该合同以合成样本测试，不代表已验证所有 ccusage 版本；不接受未知口径时自动猜测。

## 验证范围

- 本机实际数据：Codex JSONL、WorkBuddy JSON trace、官方 Codex 账号摘要。
- 合成数据测试：口径归一、去重、重置、截断、日期过滤、未知值、隐私白名单、ccusage 桥接、HTML 注入。
- 不包含：所有平台账号、跨设备/跨账号全量对账、服务商签名验证、所有版本日志兼容、借贷/职业能力评级。
