# 贡献 TokenMe

需要 Python 3.10+、Node.js 18+（只跑开发测试）。先阅读 [计数口径](docs/design.md) 和 [复用评估](docs/sources-and-reuse.md)。新增依赖需说明来源、固定版本、许可证与验证结果。

```shell
python -m unittest discover -s tests -v
node --test tests/test_share_card.cjs
git diff --check
```

适配器应提供合成或充分脱敏的 schema 样本，明确输入/缓存/推理语义、稳定身份、时间口径、覆盖和去重策略。不要提交个人日志、报告、账号返回、提示词、凭据或个人截图。

分享卡修改需验证全部等级、两个尺寸、长昵称、小用量、空值和精确阈值；二维码需检查静区与原图/压缩图解码。保留设计基线，更新验证说明。

重生成固定公开 URL 的二维码：`python -m pip install --require-hashes -r requirements-dev.txt`，然后 `python scripts/generate_qr.py`。生成器不是应用运行依赖。

PR 说明具体行为变化、验证结果和剩余限制。新增格式或粒度必须考虑已有历史，不能静默改变统计口径。
