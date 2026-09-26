/*
 * PoC (方案B / 免改文件) —— 项目J 在线卡密授权客户端旁路
 * 用法: python poc_frida_run.py [目标exe路径]
 *
 * 旁路点：
 *   1) 0x401290  登录校验结果 -> 强制为 1
 *   2) 0x41AC81  授权心跳复检 #1 -> 强制走成功分支
 *   3) 0x41AE05  授权心跳复检 #2 -> 强制走成功分支
 */
'use strict';

var PATCHES = [
  { addr: 0x00401290, bytes: [0xC7,0x45,0xFC,0x01,0x00,0x00,0x00,0x90,0x90,0x90],
    desc: 'login check -> mov dword [ebp-4], 1' },
  { addr: 0x0041AC81, bytes: [0xE9,0x35,0x01,0x00,0x00,0x90],
    desc: 'heartbeat recheck #1 -> jmp success' },
  { addr: 0x0041AE05, bytes: [0xE9,0x35,0x01,0x00,0x00,0x90],
    desc: 'heartbeat recheck #2 -> jmp success' }
];

function applyPatches() {
  PATCHES.forEach(function (p) {
    var a = ptr(p.addr);
    Memory.protect(a, p.bytes.length, 'rwx');
    a.writeByteArray(p.bytes);
    send('[+] patched 0x' + p.addr.toString(16) + '  ' + p.desc);
  });
}

// 外壳解密完成前，0x41AB86 处是密文；等到出现 55 8B EC 再落补丁
var tries = 0;
var timer = setInterval(function () {
  tries++;
  var ok = false;
  try { ok = ptr(0x0041AB86).readU8() === 0x55; } catch (e) { ok = false; }
  if (ok) {
    clearInterval(timer);
    applyPatches();
    send('[+] .ev3n decrypted, patch set applied — 输入任意卡密点击「登陆」即可');
  } else if (tries > 1500) {
    clearInterval(timer);
    send('[!] timeout waiting for unpacker');
  }
}, 20);
