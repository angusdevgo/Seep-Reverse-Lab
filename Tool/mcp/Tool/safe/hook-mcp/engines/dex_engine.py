from androguard.core.apk import APK
from androguard.core.dex import DEX, EncodedMethod
import io, os, re, zlib

_apk_path = None
_apk: APK = None
_dex_data: dict[str, DEX] = {}
_all_classes: list = None
_string_pool: set = None


def load_apk(apk_path: str) -> str:
    global _apk_path, _apk, _dex_data, _all_classes, _string_pool
    _apk_path = os.path.abspath(apk_path)
    if not os.path.isfile(_apk_path):
        return f"// Error: APK not found at {_apk_path}"
    _apk = APK(_apk_path)
    _dex_data = {}
    _all_classes = None
    _string_pool = None
    for fname in _apk.get_files():
        if fname.endswith(".dex") and not fname.startswith("META-INF"):
            raw = _apk.get_file(fname)
            if raw:
                try:
                    data = bytearray(raw)
                    if len(data) >= 12:
                        adler = zlib.adler32(data[12:])
                        import struct
                        struct.pack_into("<I", data, 8, adler & 0xFFFFFFFF)
                    dvm = DEX(bytes(data))
                    _dex_data[fname] = dvm
                except Exception as e:
                    pass
    total = sum(len(list(d.get_classes())) for d in _dex_data.values())
    return f"// APK loaded: {_apk_path}\n// DEX files: {len(_dex_data)}, total classes: {total}"


def _get_all_classes():
    global _all_classes
    if _all_classes is not None:
        return _all_classes
    result = []
    for dvm in _dex_data.values():
        for cls in dvm.get_classes():
            result.append(cls)
    _all_classes = result
    return result


def _get_string_pool():
    global _string_pool
    if _string_pool is not None:
        return _string_pool
    pool = set()
    for dvm in _dex_data.values():
        for s in dvm.get_strings():
            pool.add(s)
    _string_pool = pool
    return pool


def _paginate(items, limit, page, offset, default_limit=20):
    total = len(items)
    if offset is None and page is not None:
        offset = (page - 1) * limit
    if offset is None:
        offset = 0
    if limit is None:
        limit = default_limit
    end = offset + limit
    page_items = items[offset:end]
    return page_items, total


def _cls_name(cls) -> str:
    return cls.get_name().lstrip("L").rstrip(";").replace("/", ".")


def _cls_name_int(cls) -> str:
    return cls.get_name().lstrip("L").rstrip(";").replace("/", ".")


def search_classes(keyword: str, limit: int = 20, page: int = None, offset: int = None) -> str:
    classes = _get_all_classes()
    keyword_lower = keyword.lower()
    matched = [c for c in classes if keyword_lower in _cls_name(c).lower()]
    matched.sort(key=lambda c: _cls_name(c))
    items, total = _paginate(matched, limit, page, offset)
    lines = [f"// Found {total} class(es), showing {len(items)}:"]
    for c in items:
        lines.append(f"  {_cls_name(c)}")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


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
    classes = _get_all_classes()
    matched = list(classes)
    if class_name_pattern:
        pat = class_name_pattern.lower()
        matched = [c for c in matched if pat in _cls_name(c).lower()]
    if pkg:
        matched = [c for c in matched if any(_cls_name(c).startswith(p + ".") for p in pkg)]
    if super_class:
        matched = [c for c in matched if c.get_superclassname() and super_class.replace("/", ".") in c.get_superclassname().replace("/", ".")]
    if interfaces:
        iface_names = set()
        for c in matched:
            iface = c.get_interfaces()
            if iface:
                refs = [x.get_name().lstrip("L").rstrip(";").replace("/", ".") for x in iface if x]
                if any(any(i.replace("/", ".") in r for r in refs) for i in interfaces):
                    iface_names.add(c)
        matched = [c for c in matched if c in iface_names] if interfaces else matched
    if using_strings:
        def _has_strings(cls):
            for m in cls.get_methods():
                for s in m.get_strings() if hasattr(m, "get_strings") else []:
                    if any(u in s for u in using_strings):
                        return True
            return False
        matched = [c for c in matched if _has_strings(c)]
    matched.sort(key=lambda c: _cls_name(c))
    items, total = _paginate(matched, limit, page, offset, 5)
    lines = [f"// Found {total} class(es), showing {len(items)}:"]
    for c in items:
        lines.append(f"  {_cls_name(c)}")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


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
    classes = _get_all_classes()
    results = []
    for cls in classes:
        cname = _cls_name(cls)
        if in_class and in_class not in cname:
            continue
        for m in cls.get_methods():
            mname = m.get_name()
            desc = m.get_descriptor()
            if method_name_pattern and method_name_pattern.lower() not in mname.lower():
                continue
            if return_type and return_type not in desc:
                continue
            if param_types:
                match = True
                for pt in param_types:
                    if pt not in desc:
                        match = False
                        break
                if not match:
                    continue
            if using_strings:
                strs = m.get_strings() if hasattr(m, "get_strings") else []
                if not any(any(u in s for u in using_strings) for s in strs):
                    continue
            results.append((cname, mname, desc))
    results.sort(key=lambda x: (x[0], x[1]))
    items, total = _paginate(results, limit, page, offset, 10)
    lines = [f"// Found {total} method(s), showing {len(items)}:"]
    for cname, mname, desc in items:
        lines.append(f"  {cname}.{mname}{desc}")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def find_field(
    field_name_pattern: str = None,
    in_class: str = None,
    type_str: str = None,
    limit: int = 10,
    page: int = None,
    offset: int = None,
) -> str:
    classes = _get_all_classes()
    results = []
    for cls in classes:
        cname = _cls_name(cls)
        if in_class and in_class not in cname:
            continue
        for f in cls.get_fields():
            fname = f.get_name() if hasattr(f, "get_name") else str(f)
            ftype = f.get_descriptor() if hasattr(f, "get_descriptor") else ""
            if field_name_pattern and field_name_pattern.lower() not in fname.lower():
                continue
            if type_str and type_str not in ftype:
                continue
            results.append((cname, fname, ftype))
    results.sort(key=lambda x: (x[0], x[1]))
    items, total = _paginate(results, limit, page, offset, 10)
    lines = [f"// Found {total} field(s), showing {len(items)}:"]
    for cname, fname, ftype in items:
        lines.append(f"  {cname}.{fname}: {ftype}")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def find_usage(
    keyword: str,
    search_in: str = "both",
    limit: int = 10,
    page: int = None,
    offset: int = None,
) -> str:
    classes = _get_all_classes()
    results = []
    kw = keyword.lower()
    for cls in classes:
        cname = _cls_name(cls)
        found_in_class = False
        found_in_methods = []
        if search_in in ("class", "both"):
            if kw in cname.lower():
                found_in_class = True
        if search_in in ("method", "both"):
            for m in cls.get_methods():
                mname = m.get_name()
                desc = m.get_descriptor()
                if kw in mname.lower() or kw in desc.lower():
                    found_in_methods.append(f"{mname}{desc}")
                strs = m.get_strings() if hasattr(m, "get_strings") else []
                for s in strs:
                    if kw in s.lower():
                        found_in_methods.append(f"{mname}: string=\"{s[:60]}\"")
                        break
        if found_in_class or found_in_methods:
            results.append((cname, found_in_class, found_in_methods))
    results.sort(key=lambda x: x[0])
    items, total = _paginate(results, limit, page, offset, 10)
    lines = [f"// Found {total} result(s), showing {len(items)}:"]
    for cname, in_cls, in_methods in items:
        if in_cls:
            lines.append(f"  {cname} [class match]")
        for m in in_methods[:5]:
            lines.append(f"  {cname} -> {m}")
        if len(in_methods) > 5:
            lines.append(f"    ... +{len(in_methods)-5} more methods")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def find_class_usage(
    class_name: str,
    limit: int = 20,
    page: int = None,
    offset: int = None,
) -> str:
    classes = _get_all_classes()
    target = class_name.replace("/", ".").lstrip("L").rstrip(";")
    results = []
    for cls in classes:
        cname = _cls_name(cls)
        if cname == target:
            continue
        refs = []
        if cls.get_superclassname() and target.replace(".", "/") in cls.get_superclassname():
            refs.append("EXTENDS")
        iface = cls.get_interfaces()
        if iface:
            for x in iface:
                if x and target.replace(".", "/") in x.get_name():
                    refs.append("IMPLEMENTS")
                    break
        for m in cls.get_methods():
            desc = m.get_descriptor()
            if target.replace(".", "/") in desc:
                refs.append(f"PARAM/RETURN {m.get_name()}")
        if refs:
            results.append((cname, refs))
    results.sort(key=lambda x: x[0])
    items, total = _paginate(results, limit, page, offset, 20)
    lines = [f"// Found {total} reference(s) to {class_name}, showing {len(items)}:"]
    for cname, refs in items:
        ref_str = ", ".join(refs[:3])
        lines.append(f"  {cname} [{ref_str}]")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def find_caller(
    class_name: str,
    method_name: str,
    limit: int = 20,
    page: int = None,
    offset: int = None,
) -> str:
    classes = _get_all_classes()
    target = class_name.replace("/", ".").lstrip("L").rstrip(";")
    results = []
    for cls in classes:
        cname = _cls_name(cls)
        for m in cls.get_methods():
            if m.get_name() == "<init>" or m.get_name() == "<clinit>":
                continue
            strs = m.get_strings() if hasattr(m, "get_strings") else []
            for s in strs:
                if target in s or method_name in s:
                    results.append((cname, m.get_name(), m.get_descriptor()))
                    break
    results.sort(key=lambda x: (x[0], x[1]))
    items, total = _paginate(results, limit, page, offset, 20)
    lines = [f"// Found {total} caller(s) for {class_name}.{method_name}, showing {len(items)}:"]
    for cname, mname, desc in items:
        lines.append(f"  {cname}.{mname}{desc}")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def class_hierarchy(class_name: str, depth: int = 3) -> str:
    classes = _get_all_classes()
    target = class_name.replace("/", ".").lstrip("L").rstrip(";")
    cls_map = {}
    for c in classes:
        cn = _cls_name(c)
        cls_map[cn] = c
    if target not in cls_map:
        return f"// Class not found: {target}"
    lines = []
    lines.append(f"// Class hierarchy for {target}:")
    def get_super(cls_name):
        c = cls_map.get(cls_name)
        if not c:
            return None
        s = c.get_superclassname()
        if s:
            return s.lstrip("L").rstrip(";").replace("/", ".")
        return None
    def get_subclasses(cls_name):
        subs = []
        for cn, c in cls_map.items():
            s = c.get_superclassname()
            if s and cls_name.replace(".", "/") in s:
                subs.append(cn)
        return subs
    def print_hierarchy(name, indent, max_depth, going_up):
        if indent > max_depth:
            return
        prefix = ""
        if indent > 0:
            prefix = "  " * indent + ("└─ " if going_up else "├─ ")
        lines.append(prefix + name)
        if going_up:
            sup = get_super(name)
            if sup:
                print_hierarchy(sup, indent + 1, max_depth, True)
        else:
            subs = get_subclasses(name)
            for sub in sorted(subs)[:depth]:
                print_hierarchy(sub, indent + 1, max_depth, False)
    lines.append(f"\n--- Up (superclasses) ---")
    print_hierarchy(target, 0, depth, True)
    lines.append(f"\n--- Down (subclasses) ---")
    subs = get_subclasses(target)
    for sub in sorted(subs)[:depth]:
        print_hierarchy(sub, 1, depth, False)
    if len(subs) > depth:
        lines.append(f"  ... +{len(subs)-depth} more subclasses")
    return "\n".join(lines)


def search_strings(
    keyword: str,
    limit: int = 30,
    page: int = None,
    offset: int = None,
) -> str:
    pool = _get_string_pool()
    kw = keyword.lower()
    matched = sorted([s for s in pool if kw in s.lower()])
    items, total = _paginate(matched, limit, page, offset, 30)
    lines = [f"// Found {total} string(s) matching '{keyword}', showing {len(items)}:"]
    for s in items:
        disp = s[:120] + "..." if len(s) > 120 else s
        lines.append(f"  \"{disp}\"")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def view_strings(
    class_name: str,
    limit: int = 30,
    page: int = None,
    offset: int = None,
) -> str:
    classes = _get_all_classes()
    target = class_name.replace("/", ".").lstrip("L").rstrip(";")
    cls = None
    for c in classes:
        if _cls_name(c) == target:
            cls = c
            break
    if not cls:
        return f"// Class not found: {target}"
    all_strings = set()
    for m in cls.get_methods():
        strs = m.get_strings() if hasattr(m, "get_strings") else []
        all_strings.update(strs)
    sorted_strs = sorted(all_strings)
    items, total = _paginate(sorted_strs, limit, page, offset, 30)
    lines = [f"// {target}: {total} string(s), showing {len(items)}:"]
    for s in items:
        disp = s[:120] + "..." if len(s) > 120 else s
        lines.append(f"  \"{disp}\"")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)
