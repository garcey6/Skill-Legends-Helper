## 变更内容

<!-- 一句话说明这个 PR 解决什么问题。 -->

## 验证

- [ ] `python -m unittest discover -s tests -t .`
- [ ] `python tools/validate_cases.py --strict`
- [ ] `python tools/run_accuracy.py --strict`
- [ ] 涉及浮窗 / 识别时，已用真实截图或回放夹具手动确认

## 风险

- [ ] 未修改识别阈值、评分权重或运行时数据
- [ ] 若修改了识别参数，已附 before/after 准确率与延迟
- [ ] 新增依赖已说明理由，并更新 `requirements.txt`
