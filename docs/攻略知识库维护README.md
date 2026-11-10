# 攻略知识库维护README

知识库包含60位英雄的主副流派方案、每系18种候选卡的优先级，以及13流派的基础值和原始描述模板。数据基于仓库提交`2922416928acb75c3059f9aae677d81ea63bfd6b`，社区检索截至2026-11-09。

阅读入口：[全英雄构筑速查](全英雄构筑速查.md)、[网站版与浮窗完整教程](网站版与浮窗助手版完整教程.md)、[规则核对](规则与数据核对.md)、[社区来源及版本差异](社区来源与版本差异.md)。

## 文件职责

|文件或目录|用途|
|---|---|
|`data/guides/`|60篇可由原项目直接加载的Markdown攻略|
|`data/curated_plans.json`|逐英雄的流派、判定依据、核心卡、例外和来源引用|
|`data/sources.json`|社区与官方链接、日期、用途和版本限制|
|`data/hero_builds.json`|生成的完整卡池、分品阶顺序和共享卡去重结果|
|`data/build_audit.json`|生成时的资料哈希、数量和证据边界|
|`data/guide_validation.json`|最近一次原表、文档和检索核验的结果|
|`docs/流派卡池/`|13流派的完整基础卡池目录|
|`tools/build_guides.py`|带分步骤注释的生成器，使用Python标准库|
|`tools/verify_guides.py`|带分步骤注释的核验器，读取Excel需要openpyxl|

## 更新与生成

先修改`data/curated_plans.json`中的方案与`data/sources.json`中的来源；需要调整卡牌理由或排序时，再改`tools/build_guides.py`。不要修改源表以迎合既有攻略。

```powershell
# 步骤1：进入项目根目录，按自己的实际路径修改。
Set-Location 'D:\Games\Skill-Legends-Helper'
# 步骤2：生成60篇攻略、13个流派目录、导航和审计记录。
python -X utf8 tools/build_guides.py
# 步骤3：检查生成差异，保存自己认可的内容后再提交。
git diff --stat
git diff -- data/guides docs
```

生成器会覆盖它负责的Markdown和JSON。手工在网页改过攻略时，应先把需要保留的内容同步到方案或生成器；原始英雄、卡牌JSON和Excel不会被改写。

生成器支持可选`--install-to`，用于把生成结果写入另一个已有项目。目标同名攻略会先备份到`data/guide_backups/时间戳/`，文档也会同步；目标必须包含`app/kb/guides.py`和`data/heroes.json`。安装前应自行核对目标数据版本。

## 核验方法

```powershell
# 步骤1：为当前Python安装原表核验依赖；日常使用助手不需要openpyxl。
python -m pip install openpyxl
# 步骤2：核对Excel与JSON、每系14/3/1候选池、相对链接和知识库检索。
python -X utf8 tools/verify_guides.py
# 步骤3：运行项目原有测试，检查识别、推荐、资源与接口。
python -m unittest discover -s tests -t . -v
```

核验器默认检查当前仓库，也支持`--repo`指定已安装同一批攻略的另一份项目。任一检查失败会返回非零退出码，并在`data/guide_validation.json`中列出失败原因。检查以代码运行后写出的记录为准。

本次已在Windows、Python 3.12.14环境运行：原项目33项测试通过；60位英雄属性与技能、156张卡牌字段与原始Excel一致；每个流派普通14、稀有3、传奇1；两系合并去重为35种。原知识库加载60篇攻略、1020个检索片段，60位英雄逐位检索通过。文档相对链接也纳入核验。

## 规则与证据范围

技能和卡牌数值以源表为准；社区讨论按来源和日期标注，历史帖子不作为当前版本强度榜。尚无对应英雄的近期讨论时，方案明确属于机制推导。

源表没有完整品阶倍率表；11张卡的`{valN}`模板保留待核实。双流派归属可由源表确定，双系经验分配、单边禁用后的可获取性等细则保留不确定性。14／3／1是候选卡种结构，不代表玩家必须买满18张。

评分、主副系权重和界面的简短核心卡仍沿用原程序；本知识库不自动替代评分模型。未验证真实游戏胜率、桌面置顶、全局快捷键或全部英雄截图；原项目测试中的示例识别通过不等于所有实战界面都能识别。
