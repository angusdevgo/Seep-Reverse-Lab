# 社区进化：向主仓库贡献经验

## 机制说明

每次你完成一个项目并生成 field-journal 条目后，AI 会询问：

```
✅ 经验已记录到 field-journal/

📤 是否将本次经验贡献到社区主仓库？
- 数据已按模板要求脱敏（域名/IP/Token/PII 已替换）
- 只会提交 field-journal/ 目录下的新文件
- 不会提交你的 tool-index、scope、findings 等私有文件
- 贡献后其他用户也能复用你的经验

回复"是"提交，回复"否"跳过。
```

## 贡献流程

```text
1. AI 生成 field-journal 条目（已脱敏）
2. AI 询问用户是否贡献
3. 用户同意 → AI 执行以下步骤：
   a. 检查脱敏是否完整（二次确认无真实域名/IP/Token）
   b. 检查是否与主仓库已有条目重复（只读 _index.md，~200 token）
   c. 如果不重复 → 创建 PR 到主仓库
   d. PR 标题格式：[field-journal] YYYY-MM-DD 场景类型 - 关键词
4. GitHub Actions 自动审核：
   - ✓ 只修改了 field-journal/*.md
   - ✓ 无 prompt injection 特征
   - ✓ 无未脱敏的 API key/token
   - ✓ 无可执行代码
   - ✓ 文件大小 < 50KB
5. 审核通过 → 自动合并（无需仓库维护者手动操作）
6. 审核失败 → 自动评论说明原因，PR 保持 open 等待修正
```

### 安全保障

| 威胁 | 防护 |
|------|------|
| 修改非 journal 文件 | Actions 检查 changed files 白名单 |
| Prompt injection | 正则检测 "ignore previous"/"you are now" 等特征 |
| 恶意代码伪装 | 检测 `#!/`、`import`、`exec(`、`eval(` 等 |
| 未脱敏 token | 正则检测 AWS key/npm token/GitHub token 模式 |
| 垃圾数据 | 单文件 50KB 上限 |
| 大量垃圾 PR | GitHub 自带 rate limit + 可以加 CODEOWNERS 审核 |

## 技术实现

### 方式 1：GitHub CLI（推荐）

```bash
# 1. Fork 主仓库（如果还没 fork）
gh repo fork &lt;你的GitHub用户名&gt;/&lt;仓库名&gt; --clone=false

# 2. 在本地创建贡献分支
git checkout -b contribute/journal-YYYY-MM-DD-keyword

# 3. 只添加 field-journal 文件
git add skills/field-journal/YYYY-MM-DD_*.md
git add skills/field-journal/_index.md

# 4. 提交
git commit -m "[field-journal] 场景类型: 关键词摘要"

# 5. 推送到 fork
git push origin contribute/journal-YYYY-MM-DD-keyword

# 6. 创建 PR
gh pr create --repo &lt;你的GitHub用户名&gt;/&lt;仓库名&gt; \
  --title "[field-journal] YYYY-MM-DD 场景类型 - 关键词" \
  --body "## 贡献内容\n- 场景：xxx\n- 关键词：xxx\n- 脱敏确认：✓\n\n## 数据安全声明\n本条目已按模板要求完成脱敏，不包含真实目标信息。"
```

### 方式 2：直接推送（如果用户有主仓库写权限）

```bash
git checkout -b contribute/journal-YYYY-MM-DD-keyword
git add skills/field-journal/YYYY-MM-DD_*.md
git add skills/field-journal/_index.md
git commit -m "[field-journal] 场景类型: 关键词摘要"
git push origin contribute/journal-YYYY-MM-DD-keyword
gh pr create --repo &lt;你的GitHub用户名&gt;/&lt;仓库名&gt; \
  --title "[field-journal] YYYY-MM-DD 场景类型 - 关键词" \
  --body "脱敏确认：✓"
```

## 去重规则（低 Token 消耗）

AI 在提交前**只需要读 `_index.md` 一个文件**进行去重，不需要读每个 journal 条目的完整内容。

### 去重流程

```text
1. 读取主仓库的 field-journal/_index.md（通常只有几十行）
2. 提取本次条目的：场景分类 + 关键词列表
3. 在 _index.md 中搜索同类场景下的已有条目
4. 关键词匹配：
   - 重叠 ≥ 3 个关键词 → 视为重复，不提交
   - 重叠 1-2 个关键词 → 可能是变体，可以提交
   - 无重叠 → 全新场景，直接提交
```

### 为什么这样够用

- `_index.md` 格式是固定的：`- [日期] 简称 — 关键词: k1, k2, k3`
- 每条只有一行，100 条经验也就 100 行
- AI 只需要做字符串匹配，不需要理解完整内容
- Token 消耗：读 _index.md ≈ 200-500 token（vs 读所有 journal ≈ 10000+ token）

### 如果 _index.md 不可用

如果无法获取主仓库的 _index.md（网络问题等），直接提交，由主仓库维护者人工去重。

## 只允许提交的文件

**白名单**（只有这些文件可以出现在 PR 中）：
- `skills/field-journal/YYYY-MM-DD_*.md`（新的经验条目）
- `skills/field-journal/_index.md`（索引更新）

**黑名单**（绝对不能出现在 PR 中）：
- `tool-index.*`（包含用户本机路径）
- `pentest-tools/templates/scope.md`（包含目标信息）
- `pentest-tools/templates/findings.md`（包含漏洞详情）
- `pentest-tools/templates/progress.md`（包含操作记录）
- `.claude/`（用户配置）
- `.kiro/`（用户配置）
- 任何 `.env`、`*.key`、`*.pem` 文件

## 脱敏二次检查

AI 在提交前必须扫描待提交文件，确认不包含：

- [ ] 真实域名（非 `example.com`/`target.example.com`）
- [ ] 真实 IP（非 `10.x.x.x`/`192.168.x.x`）
- [ ] Token/Cookie/API Key 原文
- [ ] 手机号/邮箱/用户名原文
- [ ] 公司名/产品名（如果是 SRC 目标）

如果发现任何一项未脱敏，停止提交并提示用户修改。

## 对用户的价值

- 你贡献的经验会帮助其他用户避免踩同样的坑
- 主仓库的 field-journal 越丰富，所有用户的 AI 越聪明
- 你的贡献会在 _index.md 中保留（匿名，只有场景和关键词）
