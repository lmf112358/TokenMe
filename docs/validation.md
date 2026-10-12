# 验证记录 · 2026-10-10

版本：0.1.0。环境：Windows，Python 3.14.6，Codex 内置浏览器。

## 已完成

- 18 项自动化测试全部通过：`python -m unittest discover -s tests -v`。
- 用本机保留的 Codex JSONL 与 WorkBuddy trace 完成真实扫描；异常记录保留诊断，未硬凑总量。
- 通过原生 Codex app-server 完成 initialize / initialized / account/usage/read，查询成功；未创建模型任务、未打印凭据。
- 浏览器实际打开报告，确认十月 / 全部历史切换会改变本地总量，官方账号累计保持独立。
- 点击分享按钮后生成有效 PNG；从页面预览保存为 1200 × 800 图片并做视觉检查。
- 页面控制台无 error / warn。首屏和分享卡已检查，无文字溢出。
- 自动下载事件在内置浏览器测试工具中未成功返回，因此加入了可见图片预览与右键保存入口；PNG 生成与预览保存已验证，不宣称所有浏览器下载行为均已验证。

## 尚未验证

- macOS / Linux 的真实客户端日志与 Codex 可执行文件启动。
- 所有历史版本、被重写时间戳的 fork、跨账号/多设备日志混合。
- WorkBuddy 子代理完整覆盖、异常中断的服务端计费用量。
- 官方账号摘要是否包含普通 ChatGPT 网页/App 全部活动，以及账号日桶时区。
- ccusage 安装包实跑：桥接仅根据公开 JSON 合同和合成样例测试。
- Kimi、千问、DeepSeek 普通网页/App 的实际 Token 接入。

个人使用记录和截图位于源码仓库外，不包含在源码发布包中。
