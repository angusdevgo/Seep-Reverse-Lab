# Cases

跨板块综合案件索引层。

## 用途

Cases 是连接 samples → projects → exports → notes → reports → patches → scripts 的轻量索引。不存储大文件，只建立链接关系。

## 目录结构

```
cases/
├── _templates/    # Case 模板（从 templates/cases/ 初始化）
├── _archive/      # 已完成的 case 归档
└── <case-name>/   # 活跃 case
    ├── README.md   # Case 主索引
    ├── links.md    # 跨板块文件链接
    ├── timeline.md # 时间线
    └── findings.md # 关键发现
```

## 新建 Case

```powershell
# 从模板创建
Copy-Item -Recurse templates/cases/* cases/<new-case>/
```
