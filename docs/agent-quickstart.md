# Agent 使用 TokenMe

目标：用户说“生成我的 AI 足迹”时，调用经过测试的统计规则，返回本地报告与可分享图。

## 安装

需要 Python 3.10+。在用户授权的机器上取得并审查 TokenMe 的固定版本源码；不要执行未经检查的远程脚本，不把用户日志送去在线服务。以下命令针对当前 v0.2 开发检出，公开稳定版 v0.1 尚无此入口。

```shell
python scripts/bootstrap.py --check
python scripts/bootstrap.py --run
```

安装到 `~/.tokenme/venv`，报告保存到 `~/.tokenme/report/report.html`。安装源码时 pip 可能联网获取构建工具；扫描离线。不会修改全局 Python、PATH 或登录状态。`--prefix` 或 `TOKENME_HOME` 可自定义位置；重复安装复用虚拟环境。

已有匹配 wheel 时可离线安装：

```shell
python scripts/bootstrap.py --wheel dist/v0.2/token_footprint_local-0.2.0.dev1-py3-none-any.whl --run
```

`--open` 可与 `--run` 合用，显式打开报告。默认不打开浏览器。安装不是自动更新器；升级应使用明确版本，不从浮动远端执行脚本。

## 调用协议

使用安装器返回的 `python` 路径执行模块；不依赖全局 PATH。安装器 `--run` 的成功结果与 `run --json` 一致。以下 `python` 指隔离环境的解释器。

```shell
python -m token_footprint doctor --json
python -m token_footprint run --json
python -m token_footprint timeline --json
python -m token_footprint backup --out /your/private/backup.sqlite3 --json
```

成功结构：

```json
{"schema_version":"0.2","ok":true,"command":"run","data":{"report":"绝对路径","store":"绝对路径","history":{}}}
```

失败结构与非零退出码：

```json
{"schema_version":"0.2","ok":false,"command":"run","error":{"code":"operation_failed","message":"说明"}}
```

参数错误为 `invalid_arguments`，可能没有 command。检查退出码和 `ok`，不要把空来源、无效输入或失败描述成成功扫描。`doctor` 不读取日志正文，`directory_found` 只说明目录存在；检查成功不等于账本完整。

使用 `run` 返回的绝对 `store` 路径调用 `report --store ...`、`export --store ...` 或 `backup --store ...`，避免工作目录歧义。自定义安装 `--prefix` 后，后续 `run` 也应传入相应的 `--out`，或持续设置 `TOKENME_HOME`；仅切换解释器不会改变数据目录。`scan/report/export` 的旧默认路径 `.local/report` 为兼容 v0.1 保留；不要混淆 `run` 的固定用户目录。

## 迁移旧数据

优先继续使用已知原库：`run --store <原库> --out <报告目录> --json`。首次升级自动保留 v1 备份。若需迁移到用户目录，先 `backup --store <原库> --out <新库>` 再指定新库运行；不要重复混入多个来源不明的账号或设备。

JSONL 只搬运规范化记录；恢复后重新建立快照起点，不伪造历史快照。需要完整档案请备份 SQLite。

## 交付给用户

展示本地报告，说明读取到的来源、缺失范围、本次新增和修订。用户在报告中选择昵称、分享月份、尺寸与二维码，导出 PNG。不得擅自上传报告、生成公开个人档案、把 Token 叫作能力或信用评分，或声称已读取未支持的普通网页/App 账号。
