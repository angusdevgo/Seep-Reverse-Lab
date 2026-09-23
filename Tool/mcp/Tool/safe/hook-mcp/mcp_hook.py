"""
Hook MCP Server - APK 逆向分析 + BSH Hook 插件开发工具

使用方式:
    mcp run mcp_hook.py             # 通过 MCP CLI 启动
    python mcp_hook.py              # 直接运行 (stdio)

依赖:
    pip install mcp androguard
"""

import os, sys, json, time, re, subprocess
import logging
from datetime import datetime
from pathlib import Path
try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except ImportError:
    from mcp.server import MCPServer

# 静音 androguard 等第三方库的 DEBUG 日志，保持 stderr 干净（MCP stdio 线不受影响）
for _name in ("androguard", "mcp", "anyio", "httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)

import engines.dex_engine as dex
import engines.resource_engine as res
import engines.smali_engine as smali

# ------------------------------------------------------------
# 全局状态
# ------------------------------------------------------------
_apk_path = None
_plugins_dir = None
_jadx_jar = None

# ------------------------------------------------------------
# MCP Server 初始化
# ------------------------------------------------------------
mcp = MCPServer(
    "Hook",
    instructions="""Hook MCP Server - APK 逆向分析 + BSH Hook 插件开发工具

使用方法:
  1. 先用 load_apk(path) 加载目标 APK
  2. 用 search_classes / find_class 等工具搜索目标类和方法
  3. 用 decompile_class / get_class_smali 反编译查看代码
  4. 用 create_hook_plugin 生成 Hook 插件 (BSH)
  5. 用 write_plugin / read_plugin / edit_plugin 编辑插件
  6. 将 plugins/ 目录下的插件复制到设备 Hook 插件目录即可加载
"""
)


@mcp.tool()
def load_apk(apk_path: str) -> str:
    """加载目标 APK 文件，初始化所有分析引擎。必须先调用此工具才能使用其他分析功能。

    Args:
        apk_path: APK 文件的绝对路径
    """
    global _apk_path, _plugins_dir, _jadx_jar
    _apk_path = os.path.abspath(apk_path)

    _plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")

    jadx_candidates = [
        os.path.join(os.path.dirname(__file__), "..", "jadx", "lib", "jadx-1.5.6-all.jar"),
        os.path.join(os.path.dirname(__file__), "..", "..", "Tool", "jadx", "lib", "jadx-1.5.6-all.jar"),
        os.path.join(os.path.dirname(__file__), "..", "jadx", "lib", "jadx-1.5.1-all.jar"),
        os.path.join(os.path.dirname(__file__), "..", "..", "Tool", "jadx", "lib", "jadx-1.5.1-all.jar"),
    ]
    for p in jadx_candidates:
        if os.path.isfile(p):
            _jadx_jar = p
            break

    lines = []
    lines.append(dex.load_apk(_apk_path))
    res.load_apk(_apk_path)
    smali.load_apk(_apk_path, _jadx_jar)

    if _jadx_jar:
        lines.append(f"// jadx found at: {_jadx_jar}")
    else:
        lines.append("// jadx not found; Java decompile will fall back to smali")

    os.makedirs(_plugins_dir, exist_ok=True)
    lines.append(f"// Plugin output dir: {_plugins_dir}")

    return "\n".join(lines)


# ------------------------------------------------------------
# 一、类搜索与定位 (5个)
# ------------------------------------------------------------

@mcp.tool()
def search_classes(keyword: str, limit: int = 20, page: int = None, offset: int = None) -> str:
    """按关键词在类名中模糊搜索（类似 DexKit 模糊匹配）

    Args:
        keyword: 搜索关键词，如 "revoke"、"MainActivity"
        limit: 每页返回数，默认 20
        page: 页码（从1开始），与 offset 二选一
        offset: 偏移量（0-based），与 page 二选一
    """
    return dex.search_classes(keyword, limit, page, offset)


@mcp.tool()
def find_class(
    class_name_pattern: str = None,
    pkg: list = None,
    super_class: str = None,
    interfaces: list = None,
    using_strings: list = None,
    limit: int = 5,
    page: int = None,
    offset: int = None,
) -> str:
    """用多维度条件精确筛选类。支持包名、父类、接口、使用的字符串等过滤。

    Args:
        class_name_pattern: 类名包含此字符串
        pkg: 只搜这些包下的类，如 ["com.tencent.mm"]
        super_class: 父类全名，如 "android.app.Activity"
        interfaces: 实现的接口全名列表，如 ["android.view.View$OnClickListener"]
        using_strings: 类中使用的字符串列表，如 ["vip", "member"]
        limit: 每页返回数，默认 5
        page: 页码
        offset: 偏移量
    """
    return dex.find_class(class_name_pattern, pkg, super_class, interfaces, using_strings, limit, page, offset)


@mcp.tool()
def find_usage(keyword: str, search_in: str = "both", limit: int = 10, page: int = None, offset: int = None) -> str:
    """通过字符串常量查找使用它的类或方法

    Args:
        keyword: 搜索的字符串关键词
        search_in: 搜索范围，"class" / "method" / "both"（默认）
        limit: 每页返回数，默认 10
    """
    return dex.find_usage(keyword, search_in, limit, page, offset)


@mcp.tool()
def find_class_usage(class_name: str, limit: int = 20, page: int = None, offset: int = None) -> str:
    """查询指定类在哪些地方被引用（字段类型、返回值、参数、继承、实现、调用）

    Args:
        class_name: 目标类完整类名，如 "com.tencent.mm.ui.chatting.RevokeMsgListener"
        limit: 每页返回数，默认 20
    """
    return dex.find_class_usage(class_name, limit, page, offset)


@mcp.tool()
def class_hierarchy(class_name: str, depth: int = 3) -> str:
    """查看类的完整继承树（上行父类 + 下行子类）

    Args:
        class_name: 完整类名
        depth: 递归深度，默认 3
    """
    return dex.class_hierarchy(class_name, depth)


# ------------------------------------------------------------
# 二、方法/字段级分析 (3个)
# ------------------------------------------------------------

@mcp.tool()
def find_method(
    method_name_pattern: str = None,
    in_class: str = None,
    return_type: str = None,
    param_types: list = None,
    using_strings: list = None,
    limit: int = 10,
    page: int = None,
    offset: int = None,
) -> str:
    """按精确条件查找方法

    Args:
        method_name_pattern: 方法名包含此字符串
        in_class: 所在类名
        return_type: 返回值类型
        param_types: 参数类型列表
        using_strings: 方法中使用的字符串
        limit: 每页返回数，默认 10
    """
    return dex.find_method(method_name_pattern, in_class, return_type, param_types, using_strings, limit, page, offset)


@mcp.tool()
def find_field(
    field_name_pattern: str = None,
    in_class: str = None,
    type_str: str = None,
    limit: int = 10,
    page: int = None,
    offset: int = None,
) -> str:
    """按条件查找成员变量

    Args:
        field_name_pattern: 字段名包含此字符串，如 "isPro"
        in_class: 所在类名
        type_str: 字段类型
        limit: 每页返回数，默认 10
    """
    return dex.find_field(field_name_pattern, in_class, type_str, limit, page, offset)


@mcp.tool()
def find_caller(class_name: str, method_name: str, limit: int = 20, page: int = None, offset: int = None) -> str:
    """查找某个方法的所有调用者（通过字符串引用追踪）

    Args:
        class_name: 方法所在类
        method_name: 方法名
        limit: 每页返回数，默认 20
    """
    return dex.find_caller(class_name, method_name, limit, page, offset)


# ------------------------------------------------------------
# 三、反编译与代码阅读 (6个)
# ------------------------------------------------------------

@mcp.tool()
def decompile_class(class_name: str, from_line: int = None, to_line: int = None, limit: int = 0, page: int = None, offset: int = None) -> str:
    """反编译指定类的 Smali 代码

    Args:
        class_name: 完整类名
        from_line: 起始行（1-based）
        to_line: 结束行
        limit: 每页行数
    """
    return smali.decompile_class(class_name, from_line, to_line, limit, page, offset)


@mcp.tool()
def decompile_method(class_name: str, method_name: str) -> str:
    """查看单个方法的签名信息

    Args:
        class_name: 类名
        method_name: 方法名
    """
    return smali.decompile_method(class_name, method_name)


@mcp.tool()
def decompile_class_methods_only(class_name: str) -> str:
    """列出指定类的所有方法签名

    Args:
        class_name: 完整类名
    """
    return smali.decompile_class_methods_only(class_name)


@mcp.tool()
def decompile_class_fields(class_name: str, limit: int = 20, page: int = None, offset: int = None) -> str:
    """列出指定类的所有字段

    Args:
        class_name: 完整类名
        limit: 每页返回数，默认 20
    """
    return smali.decompile_class_fields(class_name, limit, page, offset)


@mcp.tool()
def get_class_smali(class_name: str, from_line: int = None, to_line: int = None, limit: int = 0, page: int = None, offset: int = None) -> str:
    """获取类的 Smali 代码（dexlib2/baksmali 反汇编）

    Args:
        class_name: 完整类名
        from_line: 起始行（1-based）
        to_line: 结束行
        limit: 每页行数
    """
    return smali.get_class_smali(class_name, from_line, to_line, limit, page, offset)


@mcp.tool()
def get_method_smali(class_name: str, method_name: str, from_line: int = None, to_line: int = None) -> str:
    """获取单个方法的 Smali 代码

    Args:
        class_name: 类名
        method_name: 方法名
        from_line: 起始行
        to_line: 结束行
    """
    return smali.get_method_smali(class_name, method_name, from_line, to_line)


# ------------------------------------------------------------
# 四、资源文件与清单 (5个)
# ------------------------------------------------------------

@mcp.tool()
def list_layouts(name_filter: str = None, limit: int = 30, page: int = None, offset: int = None) -> str:
    """列出 APK 中所有布局 XML 文件

    Args:
        name_filter: 按文件名模糊搜索，如 "donate"
        limit: 每页返回数，默认 30
    """
    return res.list_layouts(name_filter, limit, page, offset)


@mcp.tool()
def read_layout(layout_path: str) -> str:
    """读取指定布局 XML（Android 二进制 XML 自动解码）

    Args:
        layout_path: 如 "activity_main.xml" 或 "layout/activity_main.xml"
    """
    return res.read_layout(layout_path)


@mcp.tool()
def list_resources(res_type: str = None, name_filter: str = None, limit: int = 30, page: int = None, offset: int = None) -> str:
    """列出 APK 中指定类型的所有资源文件

    Args:
        res_type: 如 layout / drawable / raw / anim / mipmap
        name_filter: 按文件名模糊搜索
        limit: 每页返回数，默认 30
    """
    return res.list_resources(res_type, name_filter, limit, page, offset)


@mcp.tool()
def search_string_resources(key: str = None, limit: int = 30, page: int = None, offset: int = None) -> str:
    """在 strings.xml 资源中搜索字符串

    Args:
        key: 搜索关键词（在名称和值中搜索）
        limit: 每页返回数，默认 30
    """
    return res.search_string_resources(key, limit, page, offset)


@mcp.tool()
def read_manifest(component_type: str = "all", limit: int = 50, page: int = None, offset: int = None) -> str:
    """读取 AndroidManifest.xml 组件信息

    Args:
        component_type: all / activity / service / receiver / provider / permission
        limit: 每页返回数，默认 50
    """
    return res.read_manifest(component_type, limit, page, offset)


# ------------------------------------------------------------
# 五、字符串搜索 (2个)
# ------------------------------------------------------------

@mcp.tool()
def search_strings(keyword: str, limit: int = 30, page: int = None, offset: int = None) -> str:
    """在 DEX 字符串池中搜索字符串

    Args:
        keyword: 搜索关键词
        limit: 每页返回数，默认 30
    """
    return dex.search_strings(keyword, limit, page, offset)


@mcp.tool()
def view_strings(class_name: str, limit: int = 30, page: int = None, offset: int = None) -> str:
    """查看指定类中使用的所有字符串

    Args:
        class_name: 完整类名
        limit: 每页返回数，默认 30
    """
    return dex.view_strings(class_name, limit, page, offset)


# ------------------------------------------------------------
# 六、BSH 插件管理 (7个)
# ------------------------------------------------------------

def _plugin_path(name: str) -> str:
    base = _plugins_dir or os.path.join(os.path.dirname(__file__), "plugins")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, name)


def _get_template(hook_type: str) -> str:
    tmpl_dir = os.path.join(os.path.dirname(__file__), "templates")
    tmpl_map = {
        "before": "hook_before.bsh",
        "after": "hook_after.bsh",
        "replace": "hook_replace.bsh",
    }
    tmpl_file = os.path.join(tmpl_dir, tmpl_map.get(hook_type, "hook_before.bsh"))
    if os.path.isfile(tmpl_file):
        with open(tmpl_file, "r", encoding="utf-8") as f:
            content = f.read()
        f.close()
        return content
    return None


@mcp.tool()
def create_hook_plugin(
    name: str,
    target_class: str,
    target_method: str,
    target_desc: str = "",
    hook_type: str = "before",
    callback_code: str = "",
    author: str = "LSPilot",
) -> str:
    """创建 BSH Hook 插件。生成 main.java + info.prop 到本地 plugins/ 目录。

    Args:
        name: 插件名称（唯一标识）
        target_class: 目标类完整名，如 "com.example.MyClass"
        target_method: 目标方法名，如 "checkVip"
        target_desc: 方法描述符，如 "(Ljava/lang/String;)Z"
        hook_type: Hook 类型，before / after / replace
        callback_code: 自定义回调 Java 代码
        author: 作者名
    """

    plugin_dir = _plugin_path(name)
    os.makedirs(plugin_dir, exist_ok=True)

    info_path = os.path.join(plugin_dir, "info.prop")
    props = {
        "name": name,
        "author": author,
        "version": "1.0.0",
        "desc": f"LSPilot Hook: {target_class}.{target_method} ({hook_type})",
    }
    with open(info_path, "w", encoding="utf-8") as f:
        for k, v in props.items():
            f.write(f"{k}={v}\n")

    tmpl = _get_template(hook_type)
    if not tmpl:
        return f"// Error: Unknown hook type '{hook_type}'"

    if target_desc:
        pre_find = (
            f'targetMethod = ReflectUtils.findMethodExact(targetClass, "{target_method}", new Class[0]);\n'
            f'if (targetMethod == null) {{ targetMethod = ReflectUtils.findMethodBestMatch(targetClass, "{target_method}", new Object[0]); }}'
        )
    else:
        pre_find = f'targetMethod = ReflectUtils.findMethodExact(targetClass, "{target_method}", new Class[0]);\nif (targetMethod == null) {{ targetMethod = ReflectUtils.findMethodBestMatch(targetClass, "{target_method}", new Object[0]); }}'

    content = (tmpl
        .replace("${GEN_TIME}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        .replace("${PLUGIN_NAME}", name)
        .replace("${TARGET_CLASS}", target_class)
        .replace("${TARGET_METHOD}", target_method)
        .replace("${TARGET_DESC}", target_desc)
        .replace("${PRE_FIND_METHOD}", pre_find)
        .replace("${CALLBACK_CODE}", callback_code)
    )

    main_path = os.path.join(plugin_dir, "main.java")
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(content)

    return (
        f"// Hook plugin created: {name}\n"
        f"// Target: {target_class}.{target_method} ({hook_type})\n"
        f"// Plugin dir: {plugin_dir}\n"
        f"// Files: info.prop, main.java\n"
        f"// Copy {plugin_dir} to LSPilot plugin directory on device to activate.\n"
        f"// Use write_plugin/read_plugin/edit_plugin to modify."
    )


@mcp.tool()
def write_plugin(name: str, content: str) -> str:
    """写入 BSH 插件代码（覆盖 main.java）

    Args:
        name: 插件名称
        content: main.java 文件内容
    """
    plugin_dir = _plugin_path(name)
    if not os.path.isdir(plugin_dir):
        return f"// Plugin not found: {name}"
    main_path = os.path.join(plugin_dir, "main.java")
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"// Plugin main.java saved: {name} ({len(content)} chars)"


@mcp.tool()
def read_plugin(name: str, from_line: int = None, to_line: int = None) -> str:
    """读取 BSH 插件的 main.java 代码

    Args:
        name: 插件名称
        from_line: 起始行
        to_line: 结束行
    """
    plugin_dir = _plugin_path(name)
    if not os.path.isdir(plugin_dir):
        return f"// Plugin not found: {name}"
    main_path = os.path.join(plugin_dir, "main.java")
    if not os.path.isfile(main_path):
        return f"// main.java not found: {name}"
    with open(main_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    s = (from_line - 1) if from_line else 0
    e = to_line if to_line else total
    shown = lines[s:e]
    result = [f"// Plugin {name} ({total} lines total, showing {s+1}-{e}):"]
    for i, line in enumerate(shown):
        result.append(f"{s+i+1:5d}|{line.rstrip()}")
    return "\n".join(result)


@mcp.tool()
def edit_plugin(name: str, old_string: str, new_string: str, expected_replacements: int = 1) -> str:
    """编辑 BSH 插件代码（查找替换）

    Args:
        name: 插件名称
        old_string: 要替换的旧字符串
        new_string: 新字符串
        expected_replacements: 期望的替换次数，默认 1
    """
    plugin_dir = _plugin_path(name)
    if not os.path.isdir(plugin_dir):
        return f"// Plugin not found: {name}"
    main_path = os.path.join(plugin_dir, "main.java")
    if not os.path.isfile(main_path):
        return f"// main.java not found: {name}"
    with open(main_path, "r", encoding="utf-8") as f:
        content = f.read()
    count = content.count(old_string)
    if count == 0:
        return f"// Error: old_string not found in main.java"
    if count != expected_replacements:
        return f"// Error: Expected {expected_replacements} replacement(s), found {count}"
    new_content = content.replace(old_string, new_string)
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    old_lines = old_string.count("\n") + 1
    new_lines = new_string.count("\n") + 1
    return f"// Plugin edited: {name} ({old_lines}L → {new_lines}L, {count} replacement(s))"


@mcp.tool()
def list_plugins() -> str:
    """列出所有已生成的 BSH 插件"""
    base = _plugins_dir or os.path.join(os.path.dirname(__file__), "plugins")
    os.makedirs(base, exist_ok=True)
    dirs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    if not dirs:
        return f"// No plugins. Plugin dir: {base}"
    result = [f"// Found {len(dirs)} plugin(s) in {base}:"]
    for i, d in enumerate(sorted(dirs), 1):
        main_java = os.path.join(base, d, "main.java")
        size = os.path.getsize(main_java) if os.path.isfile(main_java) else 0
        result.append(f"  {i}. {d} ({size} bytes)")
    return "\n".join(result)


@mcp.tool()
def delete_plugin(name: str) -> str:
    """删除一个 BSH 插件

    Args:
        name: 插件名称
    """
    import shutil
    plugin_dir = _plugin_path(name)
    if not os.path.isdir(plugin_dir):
        return f"// Plugin not found: {name}"
    shutil.rmtree(plugin_dir)
    return f"// Plugin deleted: {name}"


# ------------------------------------------------------------
# 主入口
# ------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
