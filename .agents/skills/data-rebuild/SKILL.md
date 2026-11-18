---
name: data-rebuild
description: 从游戏数据、社区表和美术素材重建英雄/卡牌/流派/立绘资产；当新增版本数据、图片缺失或需要全量重建时使用。
---

# 数据重建

## 触发条件

- 游戏版本更新，英雄、卡牌、流派或数值变化。
- 新增英雄立绘、天赋/大招图标。
- `data/` 中结构化数据与攻略/网页不一致，需要全量重建。

## 数据流

```
外部数据/截图/素材
  -> tools/import_game_data.py      # 英雄、卡牌、流派等结构化数据
  -> tools/import_art_assets.py     # 立绘、图标、静态资源
  -> tools/build_guides.py          # 攻略索引
  -> tools/build_templates.py 等    # 识别模板
  -> data/ + static/                # 运行时读取
```

## 工作流

1. 备份当前 `data/` 或确认 git 干净；重建会覆盖生成物。
2. 更新输入：游戏数据表、社区来源、图片素材；在 `docs/DATA_SOURCES.md` 记录来源与日期。
3. 按顺序执行：
   ```powershell
   python tools/import_game_data.py
   python tools/import_art_assets.py
   python tools/build_guides.py
   python tools/build_templates.py
   python tools/build_school_templates.py
   python tools/build_school_runes.py
   python tools/build_glyph_templates.py
   ```
4. 跑 `python tools/verify_guides.py`、`python -m unittest discover -s tests -t .`。
5. 打开网页图鉴抽查英雄头像、卡牌和流派是否 404 或错位。

## 验收清单

- [ ] 英雄、卡牌、流派数量与来源表一致（当前 60 / 156 / 13）。
- [ ] 没有空名字、重复 id、悬空图片路径。
- [ ] 生成物都在 git 中可 diff；没有把本机绝对路径写进数据。
- [ ] 不手工编辑生成物；下一次重建会覆盖。
- [ ] 数据来源与授权在 `docs/DATA_SOURCES.md` 中可追溯。

## 不要做

- 不要把游戏本体、未授权素材或破解文件提交到仓库。
- 不要在未备份时运行会清空 `data/` 的脚本。
- 不要把个人对局截图中的昵称原样作为公开数据提交。
