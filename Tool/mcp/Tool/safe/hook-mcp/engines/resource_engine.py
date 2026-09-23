import os, re, zipfile
from androguard.core.apk import APK
from androguard.core import axml

_apk_path = None
_apk: APK = None


def load_apk(apk_path: str):
    global _apk_path, _apk
    _apk_path = os.path.abspath(apk_path)
    _apk = APK(_apk_path)


def _paginate(items, limit, page, offset, default_limit=30):
    total = len(items)
    if offset is None and page is not None:
        offset = (page - 1) * limit
    if offset is None:
        offset = 0
    if limit is None:
        limit = default_limit
    end = offset + limit
    return items[offset:end], total


def list_layouts(
    name_filter: str = None,
    limit: int = 30,
    page: int = None,
    offset: int = None,
) -> str:
    files = _apk.get_files()
    layout_files = [f for f in files if f.startswith("res/layout") and f.endswith(".xml")]
    if name_filter:
        nf = name_filter.lower()
        layout_files = [f for f in layout_files if nf in f.lower()]
    layout_files.sort()
    items, total = _paginate(layout_files, limit, page, offset, 30)
    lines = [f"// Found {total} layout(s), showing {len(items)}:"]
    for f in items:
        lines.append(f"  {f}")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def read_layout(layout_path: str) -> str:
    if not layout_path.startswith("res/layout"):
        layout_path = "res/layout/" + layout_path
    files = _apk.get_files()
    found = [f for f in files if f == layout_path or f.endswith("/" + layout_path)]
    if not found:
        return f"// Layout not found: {layout_path}"
    try:
        raw = _apk.get_file(found[0])
        if not raw:
            return f"// Error: empty layout file"
        axml_obj = axml.AXMLPrinter(raw)
        data = axml_obj.get_buff()
        return data.decode("utf-8", errors="replace")
    except Exception as e:
        return f"// Error reading layout: {e}"


def list_resources(
    res_type: str = None,
    name_filter: str = None,
    limit: int = 30,
    page: int = None,
    offset: int = None,
) -> str:
    files = _apk.get_files()
    res_files = [f for f in files if f.startswith("res/") and not f.endswith(".xml")]
    if res_type and res_type != "all":
        res_files = [f for f in res_files if f.startswith(f"res/{res_type}/")]
    if name_filter:
        nf = name_filter.lower()
        res_files = [f for f in res_files if nf in f.lower()]
    res_files.sort()
    items, total = _paginate(res_files, limit, page, offset, 30)
    lines = [f"// Found {total} resource(s), showing {len(items)}:"]
    for f in items:
        size = len(_apk.get_file(f) or b"")
        lines.append(f"  {f} ({size} bytes)")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def search_string_resources(
    key: str = None,
    limit: int = 30,
    page: int = None,
    offset: int = None,
) -> str:
    try:
        raw = _apk.get_file("resources.arsc")
        if not raw:
            return "// No resources.arsc found"
        from androguard.core.resources import ARSCParser
        arsc = ARSCParser(raw)
        results = []
        for pkg in arsc.get_packages_names():
            for res_type in ["string"]:
                try:
                    items = list(arsc.get_strings(pkg))
                    for item_name, item_value in items:
                        if key:
                            if key.lower() in item_name.lower() or key.lower() in item_value.lower():
                                results.append((item_name, item_value))
                        else:
                            results.append((item_name, item_value))
                except:
                    pass
        results.sort(key=lambda x: x[0])
        items, total = _paginate(results, limit, page, offset, 30)
        lines = [f"// Found {total} string resource(s), showing {len(items)}:"]
        for name, val in items:
            disp = val[:120] + "..." if len(val) > 120 else val
            lines.append(f"  {name} = \"{disp}\"")
        if len(items) < total:
            lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
        return "\n".join(lines)
    except Exception as e:
        return f"// Error reading resources: {e}"


def read_manifest(
    component_type: str = "all",
    limit: int = 50,
    page: int = None,
    offset: int = None,
) -> str:
    pm = _apk.get_android_manifest_axml()
    if not pm:
        return "// Error: No AndroidManifest.xml"
    components = []
    pkg_name = _apk.get_package()
    apk_fn = _apk.get_filename() or _apk_path
    if component_type in ("all", "activity"):
        for a in _apk.get_activities():
            components.append(("Activity", a))
    if component_type in ("all", "service"):
        for s in _apk.get_services():
            components.append(("Service", s))
    if component_type in ("all", "receiver"):
        for r in _apk.get_receivers():
            components.append(("Receiver", r))
    if component_type in ("all", "provider"):
        for p in _apk.get_providers():
            components.append(("Provider", p))
    if component_type in ("all", "permission"):
        for p in _apk.get_permissions():
            components.append(("Permission", p))
    items, total = _paginate(components, limit, page, offset, 50)
    lines = [f"// Package: {pkg_name}"]
    lines.append(f"// APK path: {apk_fn}")
    lines.append(f"// Total: {total} components, showing {len(items)}:")
    for ctype, cname in items:
        lines.append(f"  {ctype}: {cname}")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)
