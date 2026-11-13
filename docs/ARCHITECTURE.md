# 架构与实现

本文面向需要改代码或排查底层问题的人。日常使用见 [USER_GUIDE](USER_GUIDE.md)。

## 进程与线程

浮窗模式是一个 Python 进程，自动识别包含：

- **Tk 主线程**：只做浮窗渲染、拖动、热键事件消费；不碰 GDI，不跑识别。
- **live-capture 线程**：探针、ROI 抓帧、多帧中位数、稳定门；唯一持有 GDI 资源的线程。
- **live-recognition 线程**：色度流派匹配、RapidOCR 英雄名 + 字模兜底、推荐打分；纯 CPU，不抓帧。
- **热键线程**：`RegisterHotKey` 消息循环，把 `Alt+C / Alt+X / Ctrl+Alt+Q` 投递到队列。
- **HTTP 线程**：本地网页控制台，与浮窗共用同一进程和攻略库。

采集线程和识别线程之间用长度上限 2 的队列传 `uint8` ROI 数组；满了丢最旧。结果通过线程安全队列交给 Tk 主线程，`Alt+C` 只是给采样器一个强制重算信号。

网页版仍走原来的上传截图/手动修正路径；自动浮窗走 `app/live/` 的实时层。

## 为什么用 Tkinter + Pillow

- 不需要 Electron、WebView2 或浏览器窗口，启动快、占用低。
- 浮窗可以用 Win32 扩展样式做置顶、不进任务栏、不抢焦点。
- 整张卡片由 Pillow 绘制，排版和网页版视觉一致，改版不用改 Tk 布局。
- 只依赖 Python 标准库和已有的 `numpy / Pillow`。

## 实时抓帧（自动识别）

自动层只抓两个相对 ROI，不抓整幅客户区：

1. `EnumWindows` 按标题匹配「选技大乱斗 / Skill Legends / 选技」，取客户区面积最大的窗口；游戏不在前台也能抓。
2. 缓存句柄，每 500ms 或抓帧失败时复检；客户区尺寸变化后重建 ROI 像素坐标。
3. `GetDC(NULL) + BitBlt(SRCCOPY | CAPTUREBLT)` 抓 ROI；全黑时退 `PrintWindow(PW_RENDERFULLCONTENT)`；仍黑则 `black_frame`。
4. 启动时设置 **Per-Monitor DPI Aware V2**，保证 125% / 150% 缩放下坐标一致。
5. ROI 定义在 `data/recognize/layout.json`：
   - 底部图标条 `icons`：识别 8 个启用流派；
   - 顶部名牌 `nameplates`：只取前 3 个英雄，范围收窄到 `x≤0.62`，避免浮窗和「特权/随机」框干扰。

采集线程每 15Hz 用 stride=2 的降采样探针检查底部 run 数；疑似进入选人界面后连抓 5 帧两 ROI，逐像素中位数聚合，并用 `diff_ratio` 稳定门过滤动画/指针/飘字。稳定后才把 ROI 数组交给识别线程。

## 流派识别

流派主判是**归一化色度**，不是 OCR，也不检测红环；色度分不开的槽位用白色符文决胜：

1. 底部图标条逐列统计 `sat > 40`，合并成 8 个 run；run 数不是 8 直接 `failed`。
2. 用 run 中位宽 / 模板基准宽自标定 `scale`，半窗口 `round(base_half * scale)`。
3. 每个槽位取饱和像素均值，除以通道和，得到亮度/Gamma 不变的色度。
4. 与 13 个学校色度模板做一对一匈牙利分配（避免两本书判成同一流派），计算每槽 margin。
5. 8 个启用确定后，禁用 = 13 全集 − 启用；**不识别禁用图标**。
6. 对 margin 不足的槽位，取书本上的白色符文二值掩码，与 13 个符文模板做 NCC；只有符文以 ≥0.05 的差距明显胜出时才替换该槽，否则保持 `partial`。
7. 8 个启用确定后禁用 = 13 全集 − 启用；任一槽仍未解决 → `partial`，`banned=null`，不猜。

模板由 `tools/build_school_templates.py` / `tools/build_school_runes.py` 生成；`data/recognize/schools_chroma.json` 保留面板图标和底部书包的干净变体，`school_runes.json` 保留 13 个白色符文变体。

## 英雄识别

英雄名主路径是 **RapidOCR**，闭集字模保留为兜底：

1. 名牌 ROI 先用灰度/HSV 找石质名牌矩形（约 5 个，取前 3 个），不依赖连通域是否把暗字切全。
2. 每个名牌裁出后放大 2×，用 RapidOCR **rec-only**（不做检测）读出整行；3 个名牌约 40~120ms。
3. OCR 文本去空格/标点，先精确匹配 60 个英雄名；否则做编辑距离 ≤1 的闭集校正，置信度 <0.45 不采纳。
4. 某个槽 OCR 为空/不匹配时，回退到 155 字 16×16 字模（4 连通 + 2~5 字分组 + top-5 序列约束）。
5. 字模来自 Windows 6 个 CJK 字体 + 示例帧真实字模；OCR 模型为 `rapidocr_onnxruntime`，首次加载约 1s，之后单次 3 个名字约 40~120ms。

英雄槽位恒为 3 个；未识别返回 `null` 占位。`data/art` 的 300×300 立绘只用于显示。

## 旧的手动截图路径

`app/vision/recognizer.py` 仍保留给网页手动上传和 `--no-auto` 兼容路径：它按右侧 13 流派面板/红环和工作区坐标识别。自动浮窗不再走这条路径；两条路径共用推荐引擎和攻略库。

## 浮窗渲染

- 卡片尺寸 620×560，按屏幕宽度缩放 1.0~1.3 倍。
- 四种状态：待机卡、识别中、错误、结果卡。
- 结果卡包含首选、评分、理由、核心卡、开局路线、备选、8/5 流派。
- 用 Tk `Canvas` 显示 Pillow 图片并接收鼠标事件，整张卡片可拖动。
- 窗口置顶；扩展样式为 `WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED`。
- 为了支持拖动，默认**不使用** `WS_EX_TRANSPARENT`；浮窗会接收鼠标，但 `WS_EX_NOACTIVATE` 保证不抢游戏焦点。
- 拖动结束把左上角写入 `data/overlay_position.json`；启动和每次显示时读取并按显示器工作区裁剪。

## 本地 HTTP / API

`ThreadingHTTPServer` 监听 `127.0.0.1`，默认 8777；占用时自动顺延。主要路由：

- `/`：网页控制台
- `/library`：英雄图鉴 / 卡牌库 / 规则
- `/api/status`：状态
- `/api/heroes`、`/api/hero`：英雄数据
- `/api/cards`、`/api/rules`：卡牌和规则
- `/api/recommend`、`/api/sample`：推荐
- `/api/guides`、`/api/guide`：攻略
- `/api/art-check`：立绘/图标自检
- `/static/*`、`/data/templates/*`、`/data/art/*`：静态资源

服务只监听本机，不对外网开放。

## 性能

当前自动层实测（`samples/frames/draft_002`，2153×1179，5 帧聚合）：

- 色度/符文流派匹配约 16~30ms；
- RapidOCR 3 个英雄名约 40~120ms（不含首次模型加载约 1s）；
- 识别总计约 60~150ms（不含抓帧/聚合等待）；
- 稳态探针只用 stride=2 的底部 ROI，指纹不变时跳过完整识别。

`python -m tools.live_recognize --replay ... --perf N` 可重复测；完整 P50/P95 以实机 200 帧回放为准，见 [live-perf](live-perf.md)（如果有实测数据）。

AI 点评只在网页按钮触发，不在浮窗识别链路里。

## 已知限制

- 自动层只认标题包含「选技大乱斗 / Skill Legends / 选技」的窗口；标题被改掉时不会抓帧。
- 自动层需要底部 8 个书包图标和顶部前 3 个英雄名牌；右下 13 流派面板/红环完全不参与。
- 游戏大版本改 UI 后，需要更新 `data/recognize/layout.json` 的两个 ROI，并重新生成 `schools_chroma.json` / `glyphs.json`。
- 独占全屏：浮窗无法覆盖、截图可能黑屏；请用无边框窗口。
- 受保护画面或反作弊渲染可能阻止 GDI 截屏。
- 浮窗只读，不支持在浮窗上修正英雄/流派。
- OCR 是新增依赖（`rapidocr_onnxruntime` + OpenCV/ONNX Runtime）；不可用时自动回退字模。
- 英雄名仍是闭集校正：OCR 结果不在 60 人表或置信度不足时返回 `null`，不会猜。
- 白色符文决胜只在低 margin 槽位启用；符文阈值/权重需要用真实 holdout 继续验证。
- 网页上传截图/`--no-auto` 仍使用旧的右侧面板路径，不是自动层。
