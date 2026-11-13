# 架构与实现

本文面向需要改代码或排查底层问题的人。日常使用见 [USER_GUIDE](USER_GUIDE.md)。

## 进程与线程

浮窗模式是一个 Python 进程，自动识别包含：

- **Tk 主线程**：只做浮窗渲染、拖动、热键事件消费；不碰 GDI，不跑识别。
- **live-capture 线程**：探针、ROI 抓帧、多帧中位数、稳定门；唯一持有 GDI 资源的线程。
- **live-recognition 线程**：色度流派匹配、字模英雄匹配、推荐打分；纯 CPU，不抓帧。
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

流派主判是**归一化色度**，不是形状/灰度/OCR，也不检测红环：

1. 底部图标条逐列统计 `sat > 40`，合并成 8 个 run；run 数不是 8 直接 `failed`。
2. 用 run 中位宽 / 模板基准宽自标定 `scale`，半窗口 `round(base_half * scale)`。
3. 每个槽位取饱和像素均值，除以通道和，得到亮度/Gamma 不变的色度。
4. 与 13 个学校色度模板做一对一匈牙利分配（避免两本书判成同一流派），计算每槽 margin。
5. 8 个启用确定后，禁用 = 13 全集 − 启用；**不识别禁用图标**。
6. 任一槽 margin < `margin_min` 或色度为 `None` → `partial`，只输出高置信启用子集，`banned=null`；不猜。

模板由 `tools/build_school_templates.py` 生成；`data/recognize/schools_chroma.json` 同时保留面板图标和底部书包的干净变体，以吸收不同窗口/亮度下的色差。

## 英雄识别

英雄名用 **155 字闭集字模**，不用通用 OCR：

1. 名牌 ROI 亮度取 72 百分位二值化，4 连通（显式 `[[0,1,0],[1,1,1],[0,1,0]]`），过滤面积碎块。
2. 按 x 聚成前 3 个名牌；每个名牌的连通域再做 2~5 个字的分组枚举。
3. 每组 resize 到 16×16 灰度，减均值除标准差，L2 归一化；与字模矩阵做 NCC，每槽取 top-5。
4. 枚举同字数英雄名，要求每个字都在对应 top-5；最高分并列也返回 `null`，不压缩槽位。
5. 字模来自 Windows CJK 字体的 6 个变体 + 示例帧里真实切出的字，兼顾不同分辨率和字体粗细。

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

- 色度流派匹配约 16~26ms；
- 字模英雄匹配约 50~66ms；
- 识别总计约 77~83ms（不含抓帧/聚合等待）；
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
- 字库是闭集；某个字模缺失时对应槽位返回 `null`，不会猜；补字模后生效。
- 网页上传截图/`--no-auto` 仍使用旧的右侧面板路径，不是自动层。
