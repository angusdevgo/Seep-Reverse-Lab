import os, re, zlib, struct
from androguard.core.apk import APK
from androguard.core.dex import DEX, ClassDefItem

_apk_path = None
_dex_data: dict[str, DEX] = {}
_jadx_jar = None


def load_apk(apk_path: str, jadx_jar_path: str = None):
    global _apk_path, _dex_data, _jadx_jar
    _apk_path = os.path.abspath(apk_path)
    _jadx_jar = jadx_jar_path
    apk_obj = APK(_apk_path)
    _dex_data = {}
    for fname in apk_obj.get_files():
        if fname.endswith(".dex") and not fname.startswith("META-INF"):
            raw = apk_obj.get_file(fname)
            if raw:
                try:
                    data = bytearray(raw)
                    if len(data) >= 12:
                        adler = zlib.adler32(data[12:])
                        struct.pack_into("<I", data, 8, adler & 0xFFFFFFFF)
                    dvm = DEX(bytes(data))
                    _dex_data[fname] = dvm
                except:
                    pass


def _find_class(class_name: str) -> ClassDefItem:
    target = class_name.replace("/", ".").lstrip("L").rstrip(";")
    for dvm in _dex_data.values():
        for cls in dvm.get_classes():
            cn = cls.get_name().lstrip("L").rstrip(";").replace("/", ".")
            if cn == target:
                return cls
    return None


def _paginate_smali(smali_lines, from_line, to_line, limit, offset, default_limit=0):
    total = len(smali_lines)
    if from_line and to_line:
        s = max(0, from_line - 1)
        e = min(total, to_line)
        return smali_lines[s:e], total
    if offset is None:
        offset = 0
    if limit is None or limit == 0:
        limit = total
    end = offset + limit
    return smali_lines[offset:end], total


def decompile_class_methods_only(class_name: str) -> str:
    cls = _find_class(class_name)
    if not cls:
        return f"// Class not found: {class_name}"
    cname = cls.get_name().lstrip("L").rstrip(";").replace("/", ".")
    methods = list(cls.get_methods())
    if not methods:
        return f"// No methods in {cname}"
    lines = [f"// Methods in {cname} ({len(methods)} total):"]
    for m in methods:
        lines.append(f"  {cname}.{m.get_name()}{m.get_descriptor()}")
    return "\n".join(lines)


def decompile_class_fields(
    class_name: str,
    limit: int = 20,
    page: int = None,
    offset: int = None,
) -> str:
    cls = _find_class(class_name)
    if not cls:
        return f"// Class not found: {class_name}"
    cname = cls.get_name().lstrip("L").rstrip(";").replace("/", ".")
    fields = list(cls.get_fields())
    items, total = _paginate_smali(fields, None, None, limit, offset)
    lines = [f"// Fields in {cname} ({len(fields)} total), showing {len(items)}:"]
    for f in items:
        fname = f.get_name() if hasattr(f, "get_name") else str(f)
        ftype = f.get_descriptor() if hasattr(f, "get_descriptor") else ""
        lines.append(f"  {ftype} {fname}")
    if len(items) < total:
        lines.append(f"// Use page={((offset or 0)//limit)+2} or offset={((offset or 0)+limit)} to see more")
    return "\n".join(lines)


def get_class_smali(
    class_name: str,
    from_line: int = None,
    to_line: int = None,
    limit: int = 0,
    page: int = None,
    offset: int = None,
) -> str:
    import io as _io, sys as _sys
    cls = _find_class(class_name)
    if not cls:
        return f"// Class not found: {class_name}"
    try:
        _old = _sys.stdout
        _sys.stdout = _io.StringIO()
        try:
            cls.show()
        finally:
            smali_text = _sys.stdout.getvalue()
            _sys.stdout = _old
        if not smali_text:
            return f"// Empty smali for {class_name}"
        smali_lines = smali_text.split("\n")
        items, total = _paginate_smali(smali_lines, from_line, to_line, limit, offset)
        cname = cls.get_name().lstrip("L").rstrip(";").replace("/", ".")
        lines = [f"// {cname} ({total} lines total, showing {len(items)}):"]
        start_line = (from_line or 1)
        if offset:
            start_line = offset + 1
        for i, line in enumerate(items):
            lines.append(f"{start_line + i:5d}|{line}")
        if len(items) < total:
            remaining = total - (start_line + len(items) - 1)
            lines.append(f"// ... {remaining} more line(s). Use from_line={start_line + len(items)} to continue.")
        return "\n".join(lines)
    except Exception as e:
        return f"// Error getting smali: {e}"


def get_method_smali(
    class_name: str,
    method_name: str,
    from_line: int = None,
    to_line: int = None,
) -> str:
    import io as _io2, sys as _sys2
    cls = _find_class(class_name)
    if not cls:
        return f"// Class not found: {class_name}"
    try:
        _old2 = _sys2.stdout
        _sys2.stdout = _io2.StringIO()
        try:
            cls.show()
        finally:
            full_smali = _sys2.stdout.getvalue()
            _sys2.stdout = _old2
        if not full_smali:
            return f"// Empty smali for {class_name}"
        smali_lines = full_smali.split("\n")
        method_start = None
        method_end = None
        in_method = False
        method_lines = []
        marker = f"->{method_name}("
        for i, line in enumerate(smali_lines):
            stripped = line.strip()
            if not in_method and marker in stripped:
                method_start = i
                in_method = True
                method_lines = [line]
                continue
            if in_method:
                method_lines.append(line)
                has_next_method = any(
                    (">" in smali_lines[j] and "->" in smali_lines[j] and smali_lines[j].strip())
                    for j in [i + 1]
                    if j < len(smali_lines)
                )
                if i + 1 >= len(smali_lines) or (
                    i + 1 < len(smali_lines)
                    and "->" in smali_lines[i + 1]
                    and smali_lines[i + 1].strip()
                ):
                    method_end = i + 1
                    break
        if not method_lines:
            return f"// Method not found: {class_name}.{method_name}"
        items, total = _paginate_smali(method_lines, from_line, to_line, 0, None)
        start_line = (method_start or 0) + 1
        if from_line:
            start_line = from_line
        lines = [f"// {class_name}.{method_name} ({len(method_lines)} lines total, showing {len(items)}):"]
        for i, line in enumerate(items):
            lines.append(f"{start_line + i:5d}|{line}")
        return "\n".join(lines)
    except Exception as e:
        return f"// Error getting method smali: {e}"


def decompile_class(
    class_name: str,
    from_line: int = None,
    to_line: int = None,
    limit: int = 0,
    page: int = None,
    offset: int = None,
) -> str:
    if _jadx_jar:
        return _decompile_via_jadx(class_name, from_line, to_line, limit, page, offset)
    return _decompile_via_show(class_name, from_line, to_line, limit, page, offset)


def _decompile_via_show(class_name, from_line, to_line, limit, page, offset):
    import io as _io3, sys as _sys3
    cls = _find_class(class_name)
    if not cls:
        return f"// Class not found: {class_name}"
    try:
        _old3 = _sys3.stdout
        _sys3.stdout = _io3.StringIO()
        try:
            cls.show()
        finally:
            raw_text = _sys3.stdout.getvalue()
            _sys3.stdout = _old3
        if not raw_text:
            return f"// Empty class data"
        lines = raw_text.split("\n")
        items, total = _paginate_smali(lines, from_line, to_line, limit, offset)
        cname = cls.get_name().lstrip("L").rstrip(";").replace("/", ".")
        lines_out = [f"// {cname} (smali, {total} lines total, showing {len(items)}):"]
        start_line = (from_line or 1)
        if offset:
            start_line = offset + 1
        for i, line in enumerate(items):
            lines_out.append(f"{start_line + i:5d}|{line}")
        if len(items) < total:
            remaining = total - (start_line + len(items) - 1)
            lines_out.append(f"// ... {remaining} more line(s). Use from_line={start_line + len(items)} to continue.")
        return "\n".join(lines_out)
    except Exception as e:
        return f"// Error: {e}"


def _decompile_via_jadx(class_name, from_line, to_line, limit, page, offset):
    import subprocess, tempfile
    jadx_path = _jadx_jar
    try:
        result = subprocess.run(
            ["java", "-jar", jadx_path, "--show-bad-code", "-d", tempfile.mkdtemp(), _apk_path],
            capture_output=True, text=True, timeout=120
        )
    except:
        return "// jadx not available. Use get_class_smali instead."
    return _decompile_via_show(class_name, from_line, to_line, limit, page, offset)


def decompile_method(class_name: str, method_name: str) -> str:
    cls = _find_class(class_name)
    if not cls:
        return f"// Class not found: {class_name}"
    methods = list(cls.get_methods())
    for m in methods:
        if m.get_name() == method_name:
            return f"// {class_name}.{method_name}\n// Descriptor: {m.get_descriptor()}\n// Use get_method_smali for full bytecode/smali"
    return f"// Method not found: {class_name}.{method_name}"
