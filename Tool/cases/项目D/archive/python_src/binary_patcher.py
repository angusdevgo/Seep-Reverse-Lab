import os
import shutil

class IDMBinaryPatcher:
    """
    原生二进制补丁引擎：直接在内存中比对或修改 项目D.exe 核心校验点
    彻底脱离外部 Ali.Dbg 原版程序
    """

    # 提取自 Ali.Dbg <目标版本> 的核心补丁特征规则表 (Pattern -> Replacement)
    PATCH_RULES = [
        {
            "name": "Bypass Reg Check 1",
            "search": bytes.fromhex("0051ff150440690085c00f851b010000c6"),
            "replace": bytes.fromhex("0051ff150440690033c00f851b010000c6")
        },
        {
            "name": "Force Unlimited Days (0x7FFFFFFF)",
            "search": bytes.fromhex("dc9c7700f7d81bc083e00f83c00fa3e09c7700885dcf"),
            "replace": bytes.fromhex("dc9c7700f7d81bc0b8ffffff7f90a3e09c7700885dcf")
        },
        {
            "name": "Bypass Fake Serial Nag 1",
            "search": bytes.fromhex("10e8aa030e0084c0742a807c2407007523"),
            "replace": bytes.fromhex("10e8aa030e0084c0eb2a807c2407007523")
        },
        {
            "name": "Disable Anti-Crack Thread 1",
            "search": bytes.fromhex("ec000000c3cccccc6aff683b84660064a1"),
            "replace": bytes.fromhex("ec000000c3ccccccc3ff683b84660064a1")
        },
        {
            "name": "Disable Anti-Crack Thread 2",
            "search": bytes.fromhex("010000c3cccccccc6aff687884660064a1"),
            "replace": bytes.fromhex("010000c3ccccccccc3ff687884660064a1")
        },
        {
            "name": "Disable Anti-Crack Thread 3",
            "search": bytes.fromhex("cccccccccccccccc6aff68cb8c660064a1"),
            "replace": bytes.fromhex("ccccccccccccccccc3ff68cb8c660064a1")
        },
        {
            "name": "Disable Anti-Crack Thread 4",
            "search": bytes.fromhex("cccccccccccccccc6aff689c8d660064a1"),
            "replace": bytes.fromhex("ccccccccccccccccc3ff689c8d660064a1")
        },
        {
            "name": "Disable Watchdog Nag 1",
            "search": bytes.fromhex("c41c100000c3cccc6aff689c8d660064a1"),
            "replace": bytes.fromhex("c41c100000c3ccccc3ff689c8d660064a1")
        },
        {
            "name": "Disable Watchdog Nag 2",
            "search": bytes.fromhex("cccccccccccccccc558bec83e4f86aff68"),
            "replace": bytes.fromhex("cccccccccccccccc8bc0c3f86aff68") # or ret
        },
        {
            "name": "Bypass Fake Serial Nag 2",
            "search": bytes.fromhex("00e814d2030084c0742a807c2407007523"),
            "replace": bytes.fromhex("00e814d2030084c0eb2a807c2407007523")
        },
        {
            "name": "Bypass License Expiry Popup",
            "search": bytes.fromhex("c975f92bc283f8020f85d2010000e8596ffb"),
            "replace": bytes.fromhex("c975f92bc283f80290e9d2010000e8596ffb")
        },
        {
            "name": "Trial Days Overflow Constant",
            "search": bytes.fromhex("01000000010000001e0000003883690030f36900"),
            "replace": bytes.fromhex("0100000001000000ffffff7f3883690030f36900")
        }
    ]

    @classmethod
    def patch_file(cls, exe_path, backup=True, log_fn=print):
        if not os.path.exists(exe_path):
            log_fn(f"错误: 目标文件不存在: {exe_path}")
            return False

        if backup:
            bak_path = exe_path + ".BAK"
            if not os.path.exists(bak_path):
                try:
                    shutil.copy2(exe_path, bak_path)
                    log_fn(f"已创建原版备份: {bak_path}")
                except Exception as e:
                    log_fn(f"备份失败: {e}")

        with open(exe_path, "rb") as f:
            data = bytearray(f.read())

        applied_count = 0
        for rule in cls.PATCH_RULES:
            idx = data.find(rule["search"])
            if idx != -1:
                data[idx:idx+len(rule["replace"])] = rule["replace"]
                applied_count += 1
                log_fn(f"成功修补特征点: {rule['name']}")

        if applied_count == 0:
            log_fn("未匹配到待修补特征点（文件可能已经被打过补丁，或为新特征）")
            return False

        try:
            with open(exe_path, "wb") as f:
                f.write(data)
            log_fn(f"补丁写入成功！共修补 {applied_count} 处安全校验点。")
            return True
        except Exception as e:
            log_fn(f"写入补丁失败: {e}")
            return False

    @classmethod
    def restore_backup(cls, exe_path, log_fn=print):
        bak_path = exe_path + ".BAK"
        if not os.path.exists(bak_path):
            log_fn("未检测到原版备份文件 (项目D.exe.BAK)")
            return False
        try:
            shutil.copy2(bak_path, exe_path)
            log_fn("已成功将 项目D.exe 恢复至未打补丁的原版纯净状态！")
            return True
        except Exception as e:
            log_fn(f"还原备份失败: {e}")
            return False
