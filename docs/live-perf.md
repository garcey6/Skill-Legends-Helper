# 实时识别性能记录

测试日期：2026-11-13  
环境：Windows，Python 3.11（DSH 运行时），2560×1600 桌面  
测试命令：加载一次 ROI 图，重复运行 `app.vision.pipeline.recognize_rois` 200 次；只测纯识别，不含实时抓帧/聚合等待。

| 夹具 | 客户区 | 实现 | P50 | P95 | 最大 | 流派 | 英雄 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `samples/draft_001.png` | 1800×1118 | 色度 + 字模（旧） | 52.3ms | 69.6ms | 88.8ms | 6.7ms | 41.6ms |
| `samples/window_draft.png` | 2153×1179 | 色度 + 字模（旧） | 61.9ms | 95.2ms | 111.9ms | 7.8ms | 46.9ms |

OCR + 符文版（单次，不含首次 RapidOCR 初始化约 1s）：

| 夹具 | 总耗时 | 英雄来源 |
| --- | --- | --- |
| `samples/draft_001.png` | 约 1.28s（含初始化） | OCR 3/3 |
| `samples/window_draft.png` | 约 0.15s | OCR 3/3 |
| `validation/case01_client.png` | 约 0.11s | OCR 3/3 |
| `validation/case02_client.png` | 约 0.14s | OCR 3/3 |

首次 OCR 初始化在 `agent.start_auto()` 里预热，不进入每局链路。上面的数字是单次实测，不是 200 局 P50/P95；真实对局仍需补测。

说明：

- 这是**识别纯计算**的数字，不是“从界面稳定到浮窗出结果”的端到端数字。实时链路还要加 5 帧 ROI 抓帧和 4×15ms 的聚合间隔；按当前实现估算端到端 P50 约 120~125ms、P95 约 155~165ms，但未做 200 局真实录制回放的端到端实测，因此不声称已通过 200 帧验收。
- 稳态探针用 stride=2 的底部 ROI；画面指纹不变时跳过完整识别。
- 回放 CLI 的 `--perf` 包含 PNG 解码和 5 帧采集，数字会明显高于上表；应以上表的纯识别数字或实机 `[live]` 日志为准。
- 未跑满 200 局真实对局录制；采集层 P50/P95 仍需用 `tools/record_frames.py` 录制的真实序列补测。

## 回归夹具

```text
samples/frames/draft_001/   示例画面（1800×1118）
samples/frames/draft_002/   窗口化截图（2153×1179）
```

每条命令：

```powershell
python -m tools.live_recognize --replay samples/frames/draft_002 --pretty
```

两条都应输出 `schools.status=ok`、8 启用 / 5 禁用和 3 个英雄名。
