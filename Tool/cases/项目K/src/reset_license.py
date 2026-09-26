"""项目K 许可复位脚本 — 删除两处本地许可存储，下次启动将重新生成 30 天试用。

用法: python reset_license.py [机器码]
     机器码留空时自动从既有许可文件名反推。
"""
import os
import sys
import winreg

SALT = "<REDACTED_SALT>"          # 与目标程序一致的盐值（完整值见本地私有报告）
KEYS_DIR = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Crypto', 'Keys')


def jqm_from_files():
    if not os.path.isdir(KEYS_DIR):
        return None
    for n in os.listdir(KEYS_DIR):
        stem = os.path.splitext(n)[0]
        if len(stem) == 32 and all(c in '0123456789abcdefABCDEF' for c in stem):
            up = stem.upper()
            return '-'.join(up[i:i + 4] for i in range(0, 32, 4))
    return None


def reg_sub(jqm):
    s = ''.join(c for c in jqm.replace('-', '') if not c.isdigit())
    return 'SOFTWARE\\Microsoft\\' + (s[:3] if len(s) >= 3 else 'LLA')


def main():
    jqm = sys.argv[1] if len(sys.argv) > 1 else jqm_from_files()
    if not jqm:
        print('[!] 无法确定机器码，请手动传入')
        return
    sub = reg_sub(jqm)
    print('machine code :', jqm)
    print('registry     :', 'HKCU\\' + sub)
    print('hidden file  :', os.path.join(KEYS_DIR, jqm.replace('-', '').lower()))

    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub, 0, winreg.KEY_ALL_ACCESS)
        winreg.DeleteValue(k, 'Configuration')
        winreg.CloseKey(k)
        print('[+] registry value removed')
    except FileNotFoundError:
        print('[-] registry value not present')
    except Exception as e:
        print('[!] registry:', e)

    fp = os.path.join(KEYS_DIR, jqm.replace('-', '').lower())
    try:
        if os.path.exists(fp):
            os.chmod(fp, 0o600)
            os.remove(fp)
            print('[+] hidden file removed')
        else:
            print('[-] hidden file not present')
    except Exception as e:
        print('[!] file:', e)

    print('\n完成。下次启动 项目K 将重新生成 30 天试用许可。')


if __name__ == '__main__':
    main()
