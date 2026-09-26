---
name: update
description: 【Seep 工作台专属增量发布与同步专家】当用户要求“同步案例到工作台”、“把这个案例/skill/mcp发布到GitHub”、“使用update skill同步新案例”、“更新工作台并推送GitHub”时加载此Skill。严格遵循白名单与显式指定机制，严禁未经指定自动扫描或搬运个人私有技能。支持案例（N+1）、Skill、MCP 与知识库的自动化脱敏、本地归档、README 双语指标更新、check.ps1 健康校验与 Git 规范化推送。
compatibility: Windows 10/11 x64, Git, PowerShell 5.1+
metadata:
  workbench_path: C:/Users/Angus/Desktop/Seep
  private_blacklist:
    - github
    - green
    - tg-reader
    - muse
    - ui
---

# UPDATE Skill — Seep 逆向工作台增量发布与同步规范

> 本 Skill 是 Seep Reverse Lab 独有的自动化运维与发布中枢。
> 专门解决：**显式目标同步、个人资产与工作台资产强隔离、防误传、自动化脱敏、双语 README 自动递增 (N+1) 与 GitHub 安全发布**。

---

## 一、 铁律与前置安全门禁（★ 最核心）

### 1. 显式指定原则（Explicit-Target Only）
- **严禁全盘自动扫描搬运**：本 Skill **绝对不会、也绝对禁止** 盲目扫描用户的系统目录（如 `~/.pi/agent/skills/`）或一次性同步所有未跟踪文件！
- **必须由主人明确指名**：只有当主人明确下达指令：“同步【案例X】”、“把【某某Skill】更新到Seep并推送”、“把新加的 MCP 工具发布”时，Skill 才**唯独**针对该指定对象进行精准操作。

### 2. 个人私有技能与凭据强隔离黑名单（Strict Blacklist）
以下个人专属/私密资产**严禁以任何理由同步或推送到 Seep 工作台和 GitHub**：
- 🚫 **个人专属 Skill**：`github`、`green`、`tg-reader`、`muse`、`ui` 等；
- 🚫 **个人凭据与认证**：`models.json`、`auth.json`、各类 API Key、Token、私有 SSH 密钥；
- 🚫 **未脱敏的目标文件**：任何带有真实公司名称、个人商业客户软件名或未脱敏文件绝对路径的工程。

### 3. 本地已存在判断（Idempotency / 幂等防重复添加）
- **如果在 Seep 工作台内已创建/编辑过**：若用户已经在 `C:\Users\Angus\Desktop\Seep\Tool\...` 目录下直接编写或修改了某个 Skill / MCP / 案例，**无需执行“跨目录搬运”步骤**，直接进入**“本地自检 $\rightarrow$ README 递增更新 $\rightarrow$ Git 推送”**流程，避免重复复制或破坏现有链接。

---

## 二、 工作台资产映射与 N+1 递增标准

当主人显式指定一个新对象时，对照下表进行类型判定与目录映射：

| 资产类型 | 存放物理路径 | 计数器与关联文件 | 中英 README 更新点 |
|---|---|---|---|
| **新逆向案例**<br>(如项目 J / 新样本分析) | `Tool/cases/项目X/` | 1. 案例计数从 N 变 **N+1**<br>2. 补充 `references/project-paradigms.md` | 1. 目录树案例总数<br>2. 核心技术范畴追加项目架构简析表格行 |
| **工作台专属新 Skill**<br>(如 wasm-reverse) | `Tool/skill/新技能名/` | 1. 技能计数从 N 变 **N+1**<br>2. `softseep/SKILL.md` 注册路由分发<br>3. `setup/install-pi.ps1` 加同步项 | 1. 顶部 Badge (Skill 数量)<br>2. 目录树与核心能力说明 |
| **新增 MCP 逆向工具**<br>(在服务端新增了函数) | `Tool/mcp/seep_mcp_server.py` | 1. MCP 工具数从 23 变 **N+1**<br>2. 确保 Python 语法校验自洽 | 1. 顶部 Badge (MCP Tools 数量)<br>2. `MCP Tool Matrix` 表格追加新工具行 |
| **新增实战笔记 / 知识库**<br>(新攻防笔记或技术文章) | `Tool/mcp/Tool/reverselab/kb/` | 1. 笔记计数从 289 变 **N+1** | 顶部 Badge (Knowledge Base 数量) |
| **新增战术专项 SOP**<br>(如新反调试/新架构指南) | `MANUAL/新手册.md` | 1. MANUAL 计数从 5 变 **N+1**<br>2. `setup/verify.ps1` 追加自检项 | 1. 顶部 Badge (MANUAL SOP 数量)<br>2. 目录树结构清单追加 |

---

## 三、 标准执行五步流水线（SOP）

当接收到主人指令时，严格按顺序分步执行，任何一步失败立即熔断：

### Step 1：目标资产定位与合规性审查
1. **核实指定目标**：确认主人指名的对象路径与类型（案例 / Skill / MCP / MANUAL）；
2. **黑名单比对**：若目标属于个人私有清单（如 `green`, `tg-reader` 等），直接拦截并向主人提示：“该资产属于个人专属私有技能，已按安全策略拦截，不会同步到公共工作台”；
3. **强制脱敏扫描**：
   - 扫描目标文本中是否存在：真实公司名、个人商业软件原名、个人机器绝对路径（如 `C:\Users\Angus` 须统一替换为 `C:\Users\Developer` 或相对路径）、实际网络凭据；
   - 若存在，先执行脱敏替换，再继续推进。

### Step 2：本地工作台精准同步（如果需要）
- **情况 A（外部文件导入）**：若该案例或代码在外部临时沙盒中，使用安全的命令将其规范复制到 `C:\Users\Angus\Desktop\Seep\Tool\...` 对应子目录；
- **情况 B（工作区直接新增/修改）**：若该资产已经在 `Seep` 目录中完成创建或编辑，跳过复制，直接记录变更集。

### Step 3：元数据与双语 README 自动递增更新
1. **更新 `README.md` (英文主控)**：
   - 检查顶部 Badges 中的数量徽标，执行数字 `N -> N+1`；
   - 在对应的表格（如 `MCP Tool Matrix`、`Industrial Paradigms` 等）中精准插入新资产的说明行；
2. **更新 `README.zh.md` (中文镜像)**：
   - 保持与英文版完全对称，同步更新 Badge 与表格说明；
3. **联动更新对应索引**：
   - 若是新案例：在 `references/project-paradigms.md` 中增加脱敏技术卡片；
   - 若是新 Skill：在 `softseep/SKILL.md` 的路由矩阵中注册触发条件。

### Step 4：本地健康自检（确保 100% 全绿）
在推送前，必须在 Seep 项目根目录自动执行一次完备性自检：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check.ps1
```
- 确认全部 35+ 项检查均显示 `[√ PASS]`，且输出 `[READY / 完备就绪]`；
- 若自检出现红色 FAIL，**坚决不推送到 GitHub**，立即排查修复。

### Step 5：Git 规范化提交与云端推送
在确认一切无误后，执行 Git 操作：
```bash
cd C:/Users/Angus/Desktop/Seep
git add -A
git commit -m "feat(<type>): add <asset_name> (N+1) and sync documentation"
git push origin main
```
*(注：推送时优先确保使用已配置的本地网络代理通道。)*

---

## 四、 交互与汇报规范

当全部流程跑完后，向主人以清晰的 Markdown 结构卡片汇报：
1. **同步资产**：明确列出本次同步的具体对象、类型与归档路径；
2. **脱敏确认**：声明已通过 S1 敏感词与绝对路径脱敏走查；
3. **文档与计数变更**：汇报中英文 README 更新点（如：案例总数 `9 -> 10`）；
4. **自检状态**：汇报 `check.ps1` 校验全绿通过；
5. **GitHub 状态**：附上最新的 Commit 标识与云端仓库链接。
