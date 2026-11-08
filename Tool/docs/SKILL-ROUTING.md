# Seep 技能路由调优（SKILL-ROUTING.md）

> 技能多不是问题，**"同一件事有多个入口都能接"才是问题**。
> Agent 选技能靠描述匹配，描述越像越容易选错——而选错的代价是加载了错的战术纪律。

---

## 一、两层的成本完全不同

| 层 | 机制 | 上下文成本 | 结论 |
| :--- | :--- | :--- | :--- |
| **MCP 工具** | 全部 `codemode` 曝光 | **≈ 0**（工具定义不进上下文，系统提示只列 server 名） | 143 个工具也不构成负担 |
| **Skill** | 启动时把 `name + description + path` 灌进系统提示 | **每个任务都付** | 这才是真正的税 |

所以：**要剪的是 Skill，不是 MCP。**

唯一的 MCP 侧问题：`lifecycle: "eager"` 的 server 会常驻拉起。
`ida` 原本是 eager（48 工具常驻，即使没开 IDA），已改为 `lazy`。

---

## 二、当前分层（AUTO 10 / EXPLICIT 11）

### 参与自动路由（10 个）

| 技能 | 覆盖 |
| :--- | :--- |
| `softseep` | 总控判型调度器 |
| `apkseep` | Android APK/DEX/SO 全链路 |
| `webseep` | Web / 流媒体取证（HLS · 防盗链 · spider） |
| `exe-reverse` | Windows PE / .NET / IL2CPP / 驱动 |
| `ida-reverse` | IDA Pro 自动化联动 |
| `mcp-js-reverse-playbook` | JS 签名链路定位与本地复现 |
| `client-license-validation-bypass` | 许可/激活/卡密校验突破 |
| `seeptool-add` | SeepTool 双轨扩展 + 靶场发布 |
| `update` | 工作台经验归档同步 |
| `write-notes-like-deepseek` | 工程决策与避坑笔记 |

### 降级为显式调用（11 个，`/skill:name` 仍可用）

| 技能 | 降级理由 |
| :--- | :--- |
| `apk-reverse` | 与 `apkseep` 重复（8 文件 vs 112 文件） |
| `radare2` | 工具级说明，`seep_r2_*` 已覆盖 |
| `reverse-engineering` | 通用方法论，按需读 |
| `cf` `github` `codeberg` `muse` `vps` `tg-reader` | 基础设施类，与逆向无关，会污染路由 |
| `ui` `ui-ann` | 设计系统，非逆向 |

---

## 三、怎么调（可逆，不删文件）

用的是 pi 原生开关 —— frontmatter 里的：

```yaml
disable-model-invocation: true
```

效果：技能**保留**（`/skill:name` 显式调用照常工作），但**退出自动模型选择**，不再占描述税。

```powershell
# 看当前分布
powershell -File Tool\scripts\skills-tune.ps1 -Action list

# 降级（默认剪那 11 个；也可指定）
powershell -File Tool\scripts\skills-tune.ps1 -Action apply
powershell -File Tool\scripts\skills-tune.ps1 -Action apply -Names cf,github

# 一键恢复全部自动路由
powershell -File Tool\scripts\skills-tune.ps1 -Action restore
```

**生效方式**：`/reload` 重新扫描技能；MCP 工具变更需重启会话。

### 脚本会改哪些文件

| 位置 | 说明 |
| :--- | :--- |
| `~/.pi/agent/skills/<name>/SKILL.md` | 部署副本（真正被 Agent 读取的） |
| `Tool/skill/<name>` · `Tool/skill/safe-skills/<name>` · `Tool/safe/skills/<name>` | 工作台自有源（避免重部署被覆盖） |
| `Tool/upstream/**` | ⛔ **绝不修改**（上游防外溢铁律） |

---

## 四、两条体检护栏

`setup/verify.ps1` 已加：

| 检查 | 作用 |
| :--- | :--- |
| 技能 SKILL.md 无 UTF-8 BOM（**仓库 + 部署副本双扫**） | BOM 会让部分 Agent 静默跳过整个技能 |
| 自动路由技能数 ≤ 12 | 防止技能池再次膨胀到互相抢路由 |

> 之前 BOM 检查只扫仓库不扫部署目录，曾漏过 3 个带 BOM 的部署副本（`apk-reverse` / `ida-reverse` / `radare2`），已修正。

---

## 五、什么时候该解禁

| 场景 | 做法 |
| :--- | :--- |
| 要天天推 GitHub / Codeberg | `-Action restore -Names github,codeberg` |
| 要连着做 UI 改造 | `-Action restore -Names ui,ui-ann` |
| 要只用 radare2 不用 IDA | `-Action restore -Names radare2`；同时考虑把 `ida-reverse` 降级 |
| 想临时全开 | `-Action restore`（不带 `-Names` 即全体） |
