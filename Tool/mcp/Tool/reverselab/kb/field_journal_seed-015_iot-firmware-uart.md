# [种子] IoT 路由器固件提取 + UART 串口拿 root

## 场景分类
固件 / IoT 安全

## 目标概述
一台中低端家用路由器，从厂商网站拿到 firmware bin，用 binwalk 提取 squashfs，再用串口接到设备 UART 拿到 root shell，分析其 Web 管理界面与启动脚本。

## 完整执行链路

### 第 1 部分：固件分析

1. 下载固件文件（厂商官网 / OpenWRT / 自己 dump 闪存）
2. 基础识别
   ```bash
   file firmware.bin
   binwalk firmware.bin                    # 看到 LZMA / SquashFS / U-Boot
   binwalk -E firmware.bin                 # 熵图判断有无加密
   ```
3. 提取
   ```bash
   binwalk -e firmware.bin
   cd _firmware.bin.extracted/squashfs-root
   ```
4. 静态分析关键点
   ```bash
   find . -name 'shadow' -exec cat {} \;          # 默认密码 hash
   find . -name '*.cgi' -o -name 'lighttpd*'      # Web 服务
   find . -name 'rcS' -o -name 'init.d'           # 启动脚本
   grep -r 'telnetd\|busybox' .                   # 可疑后门
   strings $(find . -name 'httpd') | grep -i 'admin\|debug\|backdoor'
   ```
5. 拿到 `/etc/shadow` 离线破：
   ```bash
   john --wordlist=rockyou.txt shadow
   ```

### 第 2 部分：硬件 UART

1. 拆机看 PCB → 找 4 针 / 6 针未占的接口（通常未焊或焊有针脚）
2. 用万用表识别
   - GND（连接地铜片）
   - VCC（3.3V，启动时稳定）
   - TX（启动时电平跳变较多，向 UART → PC 方向输出）
   - RX（启动时基本不变）
3. 接 USB-TTL 转换器（CP2102 / FT232）
   - 路由 TX → USB-TTL RX
   - 路由 RX → USB-TTL TX
   - 路由 GND → USB-TTL GND
   - **不接 VCC**（设备自供电）
4. 在主机上开串口监听
   ```bash
   sudo screen /dev/ttyUSB0 115200
   # 或：minicom / picocom
   ```
5. 上电启动 → 看 U-Boot 输出 → Linux 启动 → 通常进入 login 提示
6. 尝试默认凭据 / 破出来的 shadow 密码 → 拿到 root shell

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| binwalk 提取后是空目录 | 部分固件用了非标准格式（厂商私有头） | 用 `dd` 切片对照偏移手动提取，或 `unblob` 替代 binwalk | 1h |
| binwalk -E 显示熵接近 1 | 整体加密 | 找到固件升级时的解密 key（通常硬编码在 OEM 工具里）| 数小时 |
| UART 看不到任何字符 | 波特率不对 | 试 9600 / 38400 / 57600 / 115200 / 460800 / 921600 | 30min |
| UART 看到字符但是乱码 | TX/RX 接反 / 电平不匹配 | 1) 互换 TX RX  2) 确认 USB-TTL 是 3.3V 而非 5V | 30min |
| login 提示但无密码可用 | 没破出来 + 厂商默认密码已改 | U-Boot 阶段按键中断 → `setenv bootargs ${bootargs} init=/bin/sh` → 进单用户 | 1.5h |
| U-Boot 没有按键中断响应 | 厂商关闭了 console / 改了 prompt | 在固件里找 `bootdelay`，物理短接 SPI flash 制造启动失败让 U-Boot 进交互 | 数小时 |
| 进了 root 但 telnetd 不工作 | 镜像里没 dropbear/telnetd | mount usb 上拷一个 busybox-static 进去 | 1h |

## 工具链发现

- **unblob** 比 binwalk 更强（自动识别更多格式，不会卡在私有头）
- **firmware-mod-kit** 老牌但仍能用于解包/打包
- **firmwalker** 自动扫提取后 squashfs 里的"敏感线索"（凭据/私钥/URL/二进制后门）
- **EMBA** 是综合固件审计平台（自动化版 firmwalker + 二进制 CVE 扫描 + 模拟启动）
- **FirmAE** 用 QEMU 模拟启动 IoT 固件，不需要真机就能动态分析 Web 界面
- **ChirpStack USB-TTL** / **Bus Pirate** / **Tigard** 都行，便宜的 CP2102 也够

## 关键代码/命令

固件审计一条龙：

```bash
# 1. 提取
unblob -k firmware.bin -o extracted/

# 2. 跑 firmwalker
git clone https://github.com/craigz28/firmwalker
./firmwalker.sh extracted/squashfs-root

# 3. 模拟启动（如果支持）
docker run -it --rm -v $(pwd):/firmware firmae:latest \
  /work/run.sh -d 1 /firmware/firmware.bin

# 4. 已模拟起 Web → 用 nuclei / nikto / curl 直接扫
```

UART 自动尝试常见波特率：

```bash
for baud in 9600 19200 38400 57600 115200 460800 921600; do
    echo "--- $baud ---"
    timeout 3 sudo cat /dev/ttyUSB0 < <(stty -F /dev/ttyUSB0 $baud cs8 -cstopb -parenb)
done
```

U-Boot 单用户 bypass 经典招：

```text
# U-Boot 阶段按键中断（一般是按住空格或 Ctrl+C）
=> setenv bootargs "console=ttyS0,115200 root=/dev/mtdblock2 rootfstype=squashfs init=/bin/sh"
=> saveenv
=> boot
# 启动后直接进 sh，无需密码
```

## 对本包的改进建议

- `reverse-engineering/platforms.md` 已含固件章节，建议拆出 `references/iot-firmware-cheatsheet.md`
- 新增 `reverse-engineering/references/uart-debug.md` 涵盖 UART/JTAG/SWD 入门
- bootstrap manifest 加入 unblob / firmwalker

## 可复用的模式/脚本片段

**IoT 安全测试 4 阶段**：

```text
阶段 1 — 软件
  · 厂商固件下载 + binwalk/unblob 提取
  · firmwalker 跑一遍
  · grep 默认凭据 / 私钥 / 后门字符串
  · QEMU 模拟启动跑 Web 漏扫

阶段 2 — 硬件
  · 拆机找 UART/JTAG 焊点
  · 万用表识别 GND/VCC/TX/RX
  · USB-TTL 接线，确认电平 3.3V

阶段 3 — 调试
  · screen/minicom 监听
  · U-Boot 阶段中断进交互
  · init=/bin/sh 单用户绕密码

阶段 4 — 利用
  · 拿到 root → 看 /etc/shadow 离线破
  · 看 Web 管理界面 CGI 二进制 → 找命令注入 / SSRF
  · 看 UPnP / mDNS / 蓝牙广播逻辑
```

**默认凭据速查**（厂商常见）：

```text
admin / admin
admin / password
root / root
root / 1234
support / support
ubnt / ubnt          # Ubiquiti
admin / 1234         # ZyXEL
```

## 进化动作
- [ ] 拆出 iot-firmware-cheatsheet.md
- [ ] 新建 uart-debug.md
- [ ] bootstrap-manifest 加入 unblob / firmwalker

## 环境信息
- Kali 2026.x（binwalk / unblob / squashfs-tools / firmwalker）
- USB-TTL 转换器: CP2102 / FT232（3.3V 电平）
- 目标: ARMv7 / MIPS 路由器（OpenWRT 衍生固件常见）

## 脱敏要求
本条目为种子数据，基于公开 IoT 安全测试方法编写，不涉及任何真实厂商或型号。
