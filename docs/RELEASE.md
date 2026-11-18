# 发行包

发行包是 **one-folder** 的 PyInstaller 构建，不是单文件 exe。识别资产有几十 MB，单文件模式每次启动都会解压到临时目录，既慢又容易被杀软拦截。

## 构建

构建依赖只在构建时安装，不进入 `requirements.txt`：

```powershell
python -m pip install -r requirements-build.txt
python -X utf8 tools/build_release.py
```

输出：

```text
dist/
├─ XuanJiHelper/
│  ├─ XuanJiHelper.exe
│  ├─ release.json
│  └─ _internal/            # Python 运行时 + data/ + static/
└─ XuanJiHelper-0.1.0-windows-x64.zip
└─ XuanJiHelper-0.1.0-windows-x64.zip.sha256
```

先看会打包哪些文件、是否混入本地状态：

```powershell
python -X utf8 tools/build_release.py --dry-run
```

## 打包内容

包含：

- `data/` 下的英雄、卡牌、规则、攻略、立绘、识别模板；
- `static/` 网页控制台；
- `README.md`、`LICENSE`、`CHANGELOG.md`、`docs/USER_GUIDE.md`、`docs/RISK.md` 等文档。

**永不打包**：

- `data/settings.json`（可能含 AI Key）；
- `data/server_url.txt`、`data/overlay_position.json`、`data/meta_stats.json`；
- `data/captures/`、`data/uploads/`、`data/source/`；
- `samples/`、`tests/`、`docs/superpowers/`、`.git/`；
- 构建机上的临时环境（`.buildtools`、`.venv`）。

`release.json` 记录版本、构建时间、Python/平台和每个文件的 SHA256，用于核对发行包内容。

## 验证

1. 解压 zip 到新目录（路径可以带中文，但不要放到需要管理员权限的目录）。
2. 双击 `XuanJiHelper.exe`，确认浮窗出现、网页控制台能打开。
3. 进入游戏选人界面，确认 1–5 个英雄都能识别；按 `Alt+X` 隐藏/显示。
4. 退出后确认没有在程序目录生成 `settings.json` 以外的异常文件；`settings.json` 只应在用户主动保存设置后出现。
5. 用 `.sha256` 核对 zip：

```powershell
Get-FileHash .\XuanJiHelper-0.1.0-windows-x64.zip -Algorithm SHA256
Get-Content .\XuanJiHelper-0.1.0-windows-x64.zip.sha256
```

## 已知限制

- 只构建 Windows x64；没有自动更新、安装器、代码签名。
- 首次启动可能被杀软误报，需要用户自行判断是否放行；不要为此关闭系统防护。
- 识别仍只读屏幕像素，不读写游戏内存、不模拟输入；边界和风险见 [RISK](RISK.md)。
- 发行包不含 `rapidocr_onnxruntime` 时仍可用字模兜底；构建机安装了它则会自动收集，包会明显变大。
