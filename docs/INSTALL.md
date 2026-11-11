# 安装与启动

本文只讲环境、依赖、启动器和命令行参数。日常操作见 [USER_GUIDE](USER_GUIDE.md)，出问题见 [TROUBLESHOOTING](TROUBLESHOOTING.md)。

## 运行环境

- Windows 10 / 11。
- Python 3.10 或更高版本，需带 Tkinter（Windows 官方安装包默认包含）。
- 第三方依赖只有 `numpy` 和 `Pillow`。
- 不需要 OpenCV、OCR 模型、Electron、WebView2 或浏览器自动化。

启动器会优先使用带 `numpy / Pillow / tkinter` 的 DSH 运行时；没有时再找系统 Python。

## 获取项目

完整项目根目录应同时包含：

```text
agent.py
run.py
requirements.txt
data/
static/
启动助手.bat
```

不要只复制 `static/` 或 `data/`。直接双击 `static/library.html` 无法加载数据，必须通过本地服务打开。

## 安装依赖

在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
python -c "import numpy, PIL, tkinter; print('依赖检查通过')"
```

如果启动器找不到 Python，安装一个带 Tkinter 的官方 Python，再重新双击启动器。使用多个 Python 时，安装依赖和启动应用要用同一个解释器。

`openpyxl` 只在重新导入 Excel 或运行攻略核验时需要，不是日常启动的必需依赖。

## 启动方式

| 文件 | 用途 |
| --- | --- |
| `启动助手.bat` | 启动浮窗助手，等价于 `启动浮窗.bat` |
| `启动浮窗.bat` | 直接启动浮窗主程序 |
| `启动网页版.bat` | 只启动网页控制台，不显示浮窗 |
| `打开设置.bat` | 打开当前端口的网页控制台 |

启动浮窗后会：

1. 在控制台打印实际快捷键和网页地址；
2. 在屏幕右侧显示「浮窗已就绪」卡片；
3. 同时启动本地网页控制台。

浮窗是单实例的。重复双击会提示「浮窗助手已经在运行」，请先关闭旧控制台，或按实际退出键退出旧实例。

## 默认快捷键

| 按键 | 作用 | 被占用时的常见回退 |
| --- | --- | --- |
| `Alt+C` | 识别当前画面并推荐 | `F6` |
| `Alt+X` | 显示 / 隐藏浮窗 | `F7` |
| `Ctrl+Alt+Q` | 退出助手 | `Ctrl+Shift+Q` |

快捷键是全局的，游戏在前台也能触发。被其他程序占用时会自动换键，**以控制台和浮窗显示的为准**。

## 命令行参数

```powershell
python agent.py
python agent.py --capture-key Alt+C --toggle-key Alt+X --quit-key Ctrl+Alt+Q
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--capture-key` | `Alt+C` | 识别快捷键 |
| `--toggle-key` | `Alt+X` | 显示 / 隐藏 |
| `--quit-key` | `Ctrl+Alt+Q` | 退出 |
| `--port` | `8777` | 网页控制台端口，占用时自动顺延 |
| `--hud-scale` | `0` | 浮窗缩放；0 表示按屏幕宽度自动 |
| `--alpha` | `0.97` | 浮窗不透明度 |
| `--no-server` | 关 | 不启动网页控制台 |
| `--no-ready` | 关 | 启动时不显示提示卡 |
| `--no-save-capture` | 关 | 不保存最近一次截图 |

想长期修改快捷键，就改 `启动浮窗.bat` 中最后一行 `agent.py` 命令的参数。

## 端口与运行文件

网页控制台默认 `http://127.0.0.1:8777`。如果 8777 被占用，会自动尝试 8778 及之后的端口；实际地址会打印在控制台，也会写入：

```text
data/server_url.txt
```

常见运行文件：

- `data/captures/last.png`：最近一次截图，便于排查；可用 `--no-save-capture` 关闭。
- `data/server_url.txt`：网页控制台实际地址。
- `data/overlay_position.json`：浮窗上次拖动后的位置。
- `data/settings.json`：保存网页设置后生成，可能包含可选的 AI Key，不会上传。

## 下一步

- [USER_GUIDE](USER_GUIDE.md)：浮窗、图鉴、网页控制台和手动修正。
- [TROUBLESHOOTING](TROUBLESHOOTING.md)：启动失败、识别没反应、黑屏、端口占用。
