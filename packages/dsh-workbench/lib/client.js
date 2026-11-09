/**
 * Seep 工作台 —— 面板（浏览器侧）
 *
 * 格式遵循 DSH 客户端模块协议：外层 window.__ModuleLoader__.load 包住，
 * factory(require) 返回 { apply, inject }。不用打包器 —— 只 require('react')，
 * 其余全走 ctx 上的服务。
 *
 * 面板同时挂在两个位置（同一个组件，两处入口）：
 *   1. 设置 → 插件 → seep-dsh-workbench → 我们那一行的「配置」
 *      （plugins.row.config，DSH 官方给 bundle row 的配置位；宿主会传 form 进来）
 *   2. 设置 → Seep 工作台（settings.section，独立一页，方便直接找到）
 *
 * 面板显示什么：
 *   · 现在挂没挂上（宿主侧 /seep-workbench/api 提供，浏览器读不到磁盘）
 *   · 工作台路径 / Python / 技能开关 / lab 开关（写回宿主配置）
 *   · 工具清单：哪个找到、哪个缺
 */

window.__ModuleLoader__.load({
  id: 'seep-dsh-workbench',
  factory: (require) => {
    const React = require('react');
    const ReactDOM = require('react-dom');
    const h = React.createElement;

    const NS = 'seep-workbench';
    const ENTRY_ID = 'seep-workbench-boot';
    const API = '/seep-workbench/api';

    // keyed slot 的 key 是 `<包名>#<行 id>`，这是 DSH 的约定。
    const ROW_KEY = 'seep-dsh-workbench#seep-workbench-boot';

    async function fetchStatus(deep) {
      const res = await fetch(deep ? `${API}?verify=1` : API, {
        method: 'GET',
        credentials: 'same-origin',
      });
      if (!res.ok) throw new Error(`接口返回 ${res.status}`);
      return res.json();
    }

    // ---------------------------------------------------------------- 样式
    // 全用内联样式 + DSH 的设计变量：不引入样式表，少一处要跟着前端版本维护的东西。
    const S = {
      page: { display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 820 },
      card: {
        border: '0.5px solid var(--dsw-alias-border-l3)',
        borderRadius: 16,
        background: 'var(--dsw-alias-settings-card-fill, var(--dsw-alias-bg-layer-2))',
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      },
      cardTitle: { fontSize: 14, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 10 },
      row: { display: 'flex', gap: 10, alignItems: 'center' },
      rowLabel: { fontSize: 13, color: 'var(--dsw-alias-label-secondary)', minWidth: 92, flex: 'none' },
      input: {
        boxSizing: 'border-box',
        flex: 1,
        minWidth: 0,
        height: 32,
        padding: '0 10px',
        fontSize: 13,
        color: 'var(--dsw-alias-label-primary)',
        background: 'var(--dsw-alias-bg-layer-1)',
        border: '0.5px solid var(--dsw-alias-border-l4)',
        borderRadius: 8,
        fontFamily: 'var(--ds-font-family-code, monospace)',
      },
      btn: {
        height: 32,
        padding: '0 14px',
        fontSize: 13,
        borderRadius: 8,
        cursor: 'pointer',
        border: '0.5px solid var(--dsw-alias-border-l3)',
        background: 'transparent',
        color: 'var(--dsw-alias-label-primary)',
        flex: 'none',
      },
      btnPrimary: {
        height: 32,
        padding: '0 16px',
        fontSize: 13,
        borderRadius: 8,
        cursor: 'pointer',
        border: 'none',
        background: 'var(--dsw-alias-button-primary-fill)',
        color: 'var(--dsw-alias-label-primary-foreground)',
        flex: 'none',
      },
      // 工具行右侧的小按钮：比主按钮矮一档，免得挤爆一行
      btnSmall: {
        height: 24,
        padding: '0 10px',
        fontSize: 12,
        borderRadius: 6,
        cursor: 'pointer',
        border: '0.5px solid var(--dsw-alias-border-l3)',
        background: 'transparent',
        color: 'var(--dsw-alias-label-secondary)',
        flex: 'none',
        whiteSpace: 'nowrap',
      },
      btnSmallPrimary: {
        height: 24,
        padding: '0 12px',
        fontSize: 12,
        borderRadius: 6,
        cursor: 'pointer',
        border: 'none',
        background: 'var(--dsw-alias-button-primary-fill)',
        color: 'var(--dsw-alias-label-primary-foreground)',
        flex: 'none',
        whiteSpace: 'nowrap',
      },
      editRow: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 0 8px 24px',
        borderBottom: '0.5px solid var(--dsw-alias-border-l1)',
      },
      quickBtn: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        height: 28,
        padding: '0 10px',
        fontSize: 12.5,
        borderRadius: 14,
        cursor: 'pointer',
        border: '0.5px solid var(--dsw-alias-border-l3)',
        background: 'transparent',
        color: 'var(--dsw-alias-label-secondary)',
        flex: 'none',
        whiteSpace: 'nowrap',
      },
      popover: {
        position: 'fixed',
        right: 24,
        bottom: 96,
        width: 380,
        zIndex: 2147483000,
        padding: 14,
        borderRadius: 12,
        border: '0.5px solid var(--dsw-alias-border-l2)',
        background: 'var(--dsw-alias-bg-layer-0)',
        boxShadow: '0 8px 32px rgba(0,0,0,.18)',
      },
      iconBtn: {
        border: 'none',
        background: 'transparent',
        cursor: 'pointer',
        fontSize: 16,
        lineHeight: '16px',
        color: 'var(--dsw-alias-label-tertiary)',
        padding: 0,
      },
      kv: { display: 'flex', gap: 8 },
      k: { color: 'var(--dsw-alias-label-tertiary)', flex: 'none', width: 62 },
      v: { color: 'var(--dsw-alias-label-primary)' },
      hint: { fontSize: 12, lineHeight: '18px', color: 'var(--dsw-alias-label-tertiary)', margin: 0 },
      err: { fontSize: 12, lineHeight: '18px', color: 'var(--dsw-alias-state-error-primary)', margin: 0 },
      okc: { fontSize: 12, lineHeight: '18px', color: 'var(--dsw-alias-state-success-primary)', margin: 0 },
      list: { listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column' },
      item: {
        display: 'grid',
        gridTemplateColumns: '16px 104px 60px 1fr auto',
        alignItems: 'center',
        gap: 8,
        fontSize: 12.5,
        lineHeight: '20px',
        padding: '3px 0',
        borderBottom: '0.5px solid var(--dsw-alias-border-l1)',
      },
      mono: { fontFamily: 'var(--ds-font-family-code, monospace)' },
    };

    const GLYPH = { READY: '✅', DEGRADED: '⚠️', OPTIONAL: '○', MISSING: '❌', UNKNOWN: '?' };
    const COLOR = {
      READY: 'var(--dsw-alias-state-success-primary)',
      DEGRADED: 'var(--dsw-alias-state-warn-label)',
      OPTIONAL: 'var(--dsw-alias-label-tertiary)',
      MISSING: 'var(--dsw-alias-state-error-primary)',
      UNKNOWN: 'var(--dsw-alias-label-tertiary)',
    };

    // ---------------------------------------------------------------- 组件

    /**
     * 面板本体。两种入口传进来的东西不一样：
     *   · plugins.row.config：宿主直接给 form = { state, mutate }
     *   · settings.section ：自己从 ctx.configForms 取
     * 所以先看 props.form，没有就退回 ctx。
     */
    function makePanel(ctx) {
      return function SeepWorkbenchPanel(props) {
        // 两个入口传进来的 form 形状不一样：
        //   · plugins.row.config：宿主给 { state, mutate }（只读快照 + 写操作）
        //   · settings.section ：我们自己的 ConfigForm（getSnapshot/subscribe/mutate）
        // 统一成「一个快照 + 一个 mutate」，两种都能用。
        //
        // 注意：ConfigForm 必须**每次渲染重新取**。保存后 profile 会重载，
        // 旧的控制器会被销毁，拿旧对象再写就会报错（实测：writeGeneration undefined）。
        const hostForm = (props && props.form) || null;
        const cf = hostForm ? null : ctx.configForms.get(ENTRY_ID);
        const view = (props && props.view) || 'page';

        const [selfSnap, setSelfSnap] = React.useState(() => (cf ? cf.getSnapshot() : null));
        React.useEffect(() => {
          if (!cf) return undefined;
          const sync = () => setSelfSnap(cf.getSnapshot());
          sync();
          return cf.subscribe(sync);
        }, [cf]);

        const snap = hostForm ? hostForm.state : selfSnap;
        const mutate = hostForm ? hostForm.mutate : cf && cf.mutate;

        const [status, setStatus] = React.useState(null);
        const [statusError, setStatusError] = React.useState('');
        const [busy, setBusy] = React.useState(false);
        const [notice, setNotice] = React.useState('');

        const load = React.useCallback((deep) => {
          setBusy(true);
          fetchStatus(deep)
            .then((data) => {
              setStatus(data);
              setStatusError('');
            })
            .catch((e) => setStatusError(String((e && e.message) || e)))
            .finally(() => setBusy(false));
        }, []);

        React.useEffect(() => {
          load(false);
        }, [load]);

        const value = (snap && snap.value) || {};
        // 一键更新的逐条结果：[{ label, ok, skipped, message }]
        const [updateSteps, setUpdateSteps] = React.useState(null);
        // 更新后要不要显示「重启」按钮：只有真有文件变化才出现，避免多一个没用的按钮
        const [needRestart, setNeedRestart] = React.useState(false);
        const [restarting, setRestarting] = React.useState(false);
        const [restartMsg, setRestartMsg] = React.useState('');
        const [root, setRoot] = React.useState(value.repoRoot || '');
        const [python, setPython] = React.useState(value.pythonPath || '');
        const [skills, setSkills] = React.useState(value.enableSkills !== false);
        const [labGate, setLabGate] = React.useState(value.labGate !== false);
        const [contentRoot, setContentRoot] = React.useState(value.contentRoot || '');
        const [ida, setIda] = React.useState(value.enableIda === true);
        const [playwright, setPlaywright] = React.useState(value.enablePlaywright === true);
        // 工具路径的人工指定：editing 是被展开的那个工具 id
        const [editing, setEditing] = React.useState('');
        const [draft, setDraft] = React.useState('');
        const [toolNotice, setToolNotice] = React.useState('');
        const [toolBusy, setToolBusy] = React.useState('');

        // 宿主值变了就同步草稿（按 revision，避免把正在输入的字冲掉）
        React.useEffect(() => {
          const v = (snap && snap.value) || {};
          setRoot(v.repoRoot || '');
          setPython(v.pythonPath || '');
          setSkills(v.enableSkills !== false);
          setLabGate(v.labGate !== false);
          setContentRoot(v.contentRoot || '');
          setIda(v.enableIda === true);
          setPlaywright(v.enablePlaywright === true);
        }, [snap && snap.revision]);

        const saved = value;
        const dirty =
          root !== (saved.repoRoot || '') ||
          python !== (saved.pythonPath || '') ||
          skills !== (saved.enableSkills !== false) ||
          labGate !== (saved.labGate !== false) ||
          contentRoot !== (saved.contentRoot || '') ||
          ida !== (saved.enableIda === true) ||
          playwright !== (saved.enablePlaywright === true);

        const save = async () => {
          setBusy(true);
          setNotice('');
          try {
            const ops = [
              { op: 'set', path: ['repoRoot'], value: root.trim() },
              { op: 'set', path: ['pythonPath'], value: python.trim() },
              { op: 'set', path: ['enableSkills'], value: skills },
              { op: 'set', path: ['labGate'], value: labGate },
              { op: 'set', path: ['contentRoot'], value: contentRoot.trim() },
              { op: 'set', path: ['enableIda'], value: ida },
              { op: 'set', path: ['enablePlaywright'], value: playwright },
            ];
            let okAccepted;
            try {
              okAccepted = await mutate(ops);
            } catch (first) {
              // 控制器可能刚被换代（保存后 profile 重载），重新取一次再试
              const fresh = ctx.configForms.get(ENTRY_ID);
              okAccepted = await fresh.mutate(ops);
            }
            setNotice(okAccepted ? '已保存，重启 DSH 后生效' : '宿主拒绝了这次修改（路径可能不合法）');
            if (okAccepted) load(false);
          } catch (e) {
            setNotice(`保存失败：${(e && e.message) || String(e)}`);
          } finally {
            setBusy(false);
          }
        };

        if (!snap) {
          return h('span', { style: { fontSize: 13, color: 'var(--dsw-alias-label-tertiary)' } }, 'Seep 工作台');
        }

        // 摘要视图：插件列表里那一行只用一句话（注意 form 来自 props，不是快照）
        if (view === 'summary') {
          const okNow = status && status.ok;
          return h(
            'span',
            { style: { fontSize: 13, color: okNow ? 'var(--dsw-alias-label-primary)' : 'var(--dsw-alias-label-secondary)' } },
            status
              ? okNow
                ? `已就绪 · ${status.wired || '未接线'}`
                : '未就绪 · 点开配置'
              : 'Seep 工作台',
          );
        }

        // ---- 状态卡
        const statusCard = h(
          'div',
          { style: S.card },
          h('div', { style: S.cardTitle }, '运行状态'),
          statusError
            ? h('p', { style: S.err }, `读不到状态：${statusError}（宿主侧接口没起来？）`)
            : !status
              ? h('p', { style: S.hint }, '正在读取…')
              : h(
                  'div',
                  { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
                  h(
                    'div',
                    { style: { display: 'flex', alignItems: 'center', gap: 10, fontSize: 14 } },
                    h('span', { style: { color: status.ok ? COLOR.READY : COLOR.MISSING } },
                      status.ok ? '● 就绪' : '● 未就绪'),
                    h('span', { style: { ...S.hint, fontSize: 12 } }, `仓库版本 ${status.version || '未知'}`),
                    h('span', { style: { ...S.hint, fontSize: 12 } }, `已接线：${status.wired || '无'}`),
                  ),
                  status.repoRoot
                    ? h('p', { style: S.hint }, '当前工作台：', h('code', { style: S.mono }, status.repoRoot))
                    : null,
                  ...(status.lines || []).map((line, i) =>
                    h('p', { key: i, style: status.ok ? S.hint : S.err }, line),
                  ),
                ),
        );

        // ---- 配置卡
        const configCard = h(
          'div',
          { style: S.card },
          h('div', { style: S.cardTitle }, '配置'),
          h(
            'div',
            { style: S.row },
            h('span', { style: S.rowLabel }, '工作台路径'),
            h('input', {
              style: S.input,
              value: root,
              spellCheck: false,
              placeholder: 'C:\\path\\to\\Seep-Reverse-Lab',
              onChange: (e) => setRoot(e.target.value),
            }),
          ),
          h(
            'div',
            { style: S.row },
            h('span', { style: S.rowLabel }, 'Python'),
            h('input', {
              style: S.input,
              value: python,
              spellCheck: false,
              placeholder: '留空自动找（按 setup/tool-registry.json 的候选链）',
              onChange: (e) => setPython(e.target.value),
            }),
          ),
          h(
            'label',
            { style: { display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 } },
            h('input', { type: 'checkbox', checked: skills, onChange: (e) => setSkills(e.target.checked) }),
            '在 DSH 里列出 10 个技能',
          ),
          h(
            'label',
            { style: { display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 } },
            h('input', { type: 'checkbox', checked: labGate, onChange: (e) => setLabGate(e.target.checked) }),
            '允许 lab 模式（总闸；关掉后连 lab： 口令也不认）',
          ),
          // 运行时开关：立刻生效、不用重启。总闸关着的时候它也没意义，所以禁用。
          h(
            'div',
            {
              style: {
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 10px', borderRadius: 8,
                background: 'var(--dsw-alias-bg-layer-1)',
                border: '0.5px solid var(--dsw-alias-border-l1)',
              },
            },
            h('span', { style: { fontSize: 13 } }, '当前：',
              h('b', null, status && status.lab && status.lab.injecting ? '已在 lab 模式' : '不在 lab 模式')),
            h('span', { style: { ...S.hint, fontSize: 11.5 } },
              status && status.lab && status.lab.injecting
                ? '这一轮开始注入作战纪律'
                : '普通对话，不注入任何作战纪律'),
            h('span', { style: { marginLeft: 'auto' } }),
            h('button', {
              style: status && status.lab && status.lab.injecting ? S.btnSmall : S.btnSmallPrimary,
              disabled: busy || !(status && status.lab) || !labGate,
              onClick: () => void toggleLab(!(status && status.lab && status.lab.injecting)),
            }, status && status.lab && status.lab.injecting ? '退出 lab' : '进入 lab'),
          ),
          status && status.repoGit && status.repoGit.ok
            ? h(
                'div',
                {
                  style: {
                    display: 'flex', flexDirection: 'column', gap: 6,
                    padding: '9px 11px', borderRadius: 8,
                    background: 'var(--dsw-alias-bg-layer-1)',
                    border: '0.5px solid var(--dsw-alias-border-l1)',
                  },
                },
                h('div', { style: { display: 'flex', gap: 8, alignItems: 'center', fontSize: 12.5, flexWrap: 'wrap' } },
                  h('span', { style: { fontWeight: 600 } }, '工作台'),
                  h('span', { style: { color: 'var(--dsw-alias-label-tertiary)' } },
                    `${status.repoGit.branch || '-'} @ ${status.repoGit.commit || '-'}`),
                  status.repoGit.behind > 0
                    ? h('span', { style: { color: 'var(--dsw-alias-state-warn-primary, #c9a227)' } },
                        `落后 ${status.repoGit.behind} 个提交`)
                    : h('span', { style: { color: 'var(--dsw-alias-state-success-primary)' } }, '已是最新'),
                  status.repoGit.dirty > 0
                    ? h('span', { style: { color: 'var(--dsw-alias-state-warn-primary, #c9a227)' } },
                        `本地改动 ${status.repoGit.dirty}`)
                    : null,
                  h('span', { style: { marginLeft: 'auto' } }),
                  h('button', {
                    style: S.btnSmallPrimary, disabled: busy,
                    title: '仓库 + 内容 + 插件一起更新；有东西变了会提示重启',
                    onClick: () => void updateAll(),
                  }, busy ? '更新中…' : '一键更新'),
                ),
                // 结果逐条列出来：哪一项动了、哪一项跳过、哪一项失败。
                updateSteps && updateSteps.length
                  ? h('div', { style: { display: 'flex', flexDirection: 'column', gap: 2, fontSize: 11.5, lineHeight: '17px' } },
                      updateSteps.map((s, i) =>
                        h('div', { key: i, style: {
                          color: s.ok
                            ? (s.skipped ? 'var(--dsw-alias-label-tertiary)' : 'var(--dsw-alias-state-success-primary)')
                            : 'var(--dsw-alias-state-error-primary, #d9534f)',
                        } }, `${s.ok ? (s.skipped ? '– ' : '✓ ') : '✕ '}${s.label}：${s.message}`)),
                    )
                  : null,
                // 有东西更新了才问「要不要重启」；没更新就不打扰。
                needRestart
                  ? h(
                      'div',
                      { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
                      h('span', { style: { ...S.hint, fontSize: 11.5, flex: 1 } },
                        '文件已就位，但跑着的还是旧进程。重启后新工具才生效。'),
                      h('button', {
                        style: S.btnSmallPrimary,
                        disabled: restarting,
                        title: '会断掉当前会话，页面大约十几秒后自己回来',
                        onClick: () => void restartDsh(),
                      }, restarting ? '重启中…' : '重启 DSH'),
                    )
                  : null,
                needRestart && restartMsg
                  ? h('div', { style: { fontSize: 11.5, color: 'var(--dsw-alias-label-tertiary)' } }, restartMsg)
                  : null,
                status.repoGit.commits && status.repoGit.commits.length
                  ? h('div', {
                      style: {
                        fontSize: 11.5, lineHeight: '17px',
                        color: 'var(--dsw-alias-label-tertiary)',
                        maxHeight: 92, overflow: 'auto', whiteSpace: 'pre-wrap',
                      },
                    }, status.repoGit.commits.join('\n'))
                  : null,
              )
            : null,
          h(
            'div',
            { style: { display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 } },
            h('span', { style: { flex: 'none', width: 96, color: 'var(--dsw-alias-label-secondary)' } }, '内容目录'),
            h('input', {
              style: { ...S.input, flex: 1 },
              placeholder: '留空 = 用仓库自带；填一个内容仓库的路径可单独更新',
              value: contentRoot,
              onChange: (e) => setContentRoot(e.target.value),
            }),
          ),
          status && status.content && status.content.git
            ? h('div', { style: { ...S.hint, fontSize: 12 } },
                '当前内容版本：', status.content.git.commit || '未提交',
                status.content.git.date ? `（${status.content.git.date}）` : '',
                status.content.root ? `　目录：${status.content.root}` : '')
            : null,
          h(
            'label',
            { style: { display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 } },
            h('input', { type: 'checkbox', checked: playwright, onChange: (e) => setPlaywright(e.target.checked) }),
            '额外挂 Playwright MCP（浏览器自动化，多 25 个工具）',
          ),
          h(
            'label',
            { style: { display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 } },
            h('input', { type: 'checkbox', checked: ida, onChange: (e) => setIda(e.target.checked) }),
            '额外挂 IDA MCP（本机要装 IDA + ida_pro_mcp）',
          ),
          h(
            'div',
            { style: { ...S.row, marginTop: 2 } },
            h('button', { style: dirty ? S.btnPrimary : S.btn, disabled: busy || !dirty, onClick: save },
              dirty ? '保存' : '已保存'),
            notice ? h('span', { style: notice.startsWith('已保存') ? S.okc : S.err }, notice) : null,
            h('span', { style: { ...S.hint, marginLeft: 'auto' } }, '改完需要重启 DSH 才生效'),
          ),
        );

        // 一个按钮干完三件事：仓库、内容、插件。逐条把结果摆出来，不猜。
        const updateAll = async () => {
          setBusy(true);
          setNotice('');
          setUpdateSteps(null);
          try {
            const res = await fetch(API, {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              credentials: 'same-origin',
              body: JSON.stringify({ action: 'updateAll' }),
            });
            const payload = await res.json();
            setUpdateSteps(payload.steps || []);
            setNeedRestart(Boolean(payload.needRestart));
            setNotice(payload.message || (payload.ok ? '已完成' : '没更新成功'));
            await load();
          } catch (e) {
            setNotice(e && e.message ? e.message : '更新失败');
            setUpdateSteps([{ label: '更新', ok: false, message: '请求没发出去（DSH 还活着吗）' }]);
          } finally {
            setBusy(false);
          }
        };

        // 点「重启 DSH」：先拿到「正在重启」的回复，再轮询等它活过来，然后自己刷新页面。
        // 拿不到回复（进程已经走了）也继续轮询 —— 那种情况通常说明重启成功了。
        const restartDsh = async () => {
          setRestarting(true);
          setRestartMsg('正在重启，页面会自己回来…');
          try {
            await fetch(API, {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              credentials: 'same-origin',
              body: JSON.stringify({ action: 'restart' }),
            });
          } catch {
            /* 重启时连接断掉是正常的，继续等 */
          }

          const deadline = Date.now() + 90000;
          while (Date.now() < deadline) {
            await new Promise((r) => setTimeout(r, 2000));
            try {
              const res = await fetch(API, { credentials: 'same-origin', cache: 'no-store' });
              if (res.ok) {
                setRestartMsg('已重启，正在刷新页面…');
                await new Promise((r) => setTimeout(r, 600));
                if (typeof location !== 'undefined' && location.reload) location.reload();
                return;
              }
            } catch {
              /* 还没起来 */
            }
          }

          setRestarting(false);
          setRestartMsg('90 秒还没回来。手动重启一次：在终端按 Ctrl+C，再输入 dsh 启动。');
        };

        const saveToolPath = async (id, path) => {
          setToolBusy(id);
          setToolNotice('');
          try {
            const res = await fetch(API, {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              credentials: 'same-origin',
              body: JSON.stringify({ tool: id, path }),
            });
            const payload = await res.json();
            if (!payload.ok) {
              setToolNotice(`${id}: ${payload.error || '保存失败'}`);
            } else {
              setToolNotice(`${id}: ${path ? '已指定路径' : '已恢复自动查找'}`);
              // 工具路径是开机时解析的，改完必须重启才认新的 —— 顺手把重启入口亮出来
              setNeedRestart(true);
              await load();
              setEditing('');
            }
          } catch (error) {
            setToolNotice(`${id}: ${error && error.message ? error.message : '保存失败'}`);
          } finally {
            setToolBusy('');
          }
        };

        // ---- 工具清单
        const tools = status && status.tools ? Object.entries(status.tools) : [];
        const toolCard = tools.length === 0 ? null : h(
          'div',
          { style: S.card },
          h(
            'div',
            { style: S.cardTitle },
            '工具清单',
            h('span', { style: { ...S.hint, fontSize: 12, fontWeight: 400 } },
              status.deep ? '深度检测：真跑过一次' : '快速检查：只看找没找到'),
            h(
              'div',
              { style: { marginLeft: 'auto', display: 'flex', gap: 8 } },
              h('button', { style: S.btn, disabled: busy, onClick: () => load(false) }, '重新检查'),
              h('button', { style: S.btn, disabled: busy, title: '会真的启动每个工具验一下，慢一些',
                onClick: () => load(true) }, '深度检测'),
            ),
          ),
          h(
            'ul',
            { style: S.list },
            tools.map(([id, t]) =>
              h(
                React.Fragment,
                { key: id },
                h(
                'li',
                { style: S.item },
                h('span', null, GLYPH[t.state] || '?'),
                h('span', { style: S.mono }, id),
                h('span', { style: { color: COLOR[t.state] || 'inherit', fontSize: 11.5 } }, t.state),
                h('span', {
                  style: {
                    color: 'var(--dsw-alias-label-tertiary)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    flex: 1,
                    minWidth: 0,
                  },
                  title: t.detail || t.path || '',
                }, t.detail || t.path || ''),
                h(
                  'button',
                  {
                    style: S.btnSmall,
                    onClick: () => {
                      setEditing(editing === id ? '' : id);
                      setDraft(t.source === 'user' ? (t.path || '') : '');
                      setToolNotice('');
                    },
                  },
                  t.source === 'user' ? '改路径' : '指定路径',
                ),
                ),
                editing === id
                  ? h(
                      'li',
                      { style: S.editRow },
                      h('input', {
                        style: { ...S.input, flex: 1 },
                        placeholder: '工具的可执行文件或安装目录，例如 D:/tools/jadx/bin/jadx.bat',
                        value: draft,
                        onChange: (e) => setDraft(e.target.value),
                      }),
                      h('button', {
                        style: S.btnSmallPrimary,
                        disabled: toolBusy === id,
                        onClick: () => saveToolPath(id, draft),
                      }, '保存'),
                      h('button', {
                        style: S.btnSmall,
                        disabled: toolBusy === id || !t.path,
                        onClick: () => saveToolPath(id, ''),
                      }, '恢复自动'),
                    )
                  : null,
              ),
            ),
          ),
          h('p', { style: S.hint }, '缺的不是核心项（○ OPTIONAL）就不用管；❌ MISSING 才要装。'),
          h('p', { style: S.hint }, '工具装在别处？点「指定路径」填进去，会写进 setup/tool-paths.local.json（不进 git），下次开机按它找。'),
          toolNotice ? h('p', { style: S.hint }, toolNotice) : null,
        );

        // ---- 兜底说明卡
        const tipCard = h(
          'div',
          { style: S.card },
          h('div', { style: S.cardTitle }, '想更彻底地查？'),
          h('p', { style: S.hint }, '面板只做快速判断。要真正确认每个工具都能跑，在仓库目录执行：'),
          h(
            'code',
            {
              style: {
                ...S.mono,
                fontSize: 12,
                lineHeight: '20px',
                padding: '8px 10px',
                borderRadius: 8,
                background: 'var(--dsw-alias-bg-layer-1)',
                border: '0.5px solid var(--dsw-alias-border-l1)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              },
            },
            'python setup/verify-dsh.py\npython Tool/mcp/tool_resolver.py --verify',
          ),
        );

        return h('div', { style: S.page }, statusCard, configCard, toolCard, tipCard);
      };
    }

    // ---------------------------------------------------------------- 输入框右侧的常驻入口
    // 为什么要有：设置面板要点三层才到（更多 → 设置 → Seep 工作台），
    // 平时只想瞄一眼「接上了没」的时候太绕。这个入口贴在输入框右侧，
    // 一点就出小卡片；完整面板仍然在设置里。
    function makeQuickEntry(ctx) {
      return function QuickEntry() {
        const [open, setOpen] = React.useState(false);
        const [status, setStatus] = React.useState(null);
        const [busy, setBusy] = React.useState(false);
        const [error, setError] = React.useState('');

        const load = React.useCallback(async () => {
          setBusy(true);
          setError('');
          try {
            setStatus(await fetchStatus(false));
          } catch (e) {
            setError(e && e.message ? e.message : '接口没响应');
          } finally {
            setBusy(false);
          }
        }, []);

        // 一进来就读一次：小圆点要在没点开的时候也有意义（绿=就绪，黄=有缺，红=没接上）
        React.useEffect(() => {
          if (!status) void load();
        }, [status, load]);

        // 开关只改内存状态：关掉立刻停止注入，打开下一条消息就带上纪律，不用重启。
        const toggleLab = async (on) => {
          setBusy(true);
          setError('');
          try {
            const res = await fetch(API, {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              credentials: 'same-origin',
              body: JSON.stringify({ action: 'lab', active: on, enabled: true }),
            });
            const payload = await res.json();
            if (!payload.ok) {
              setError(payload.error || '切换失败');
            } else if (status) {
              setStatus({ ...status, lab: payload.lab });
            }
          } catch (e) {
            setError(e && e.message ? e.message : '切换失败');
          } finally {
            setBusy(false);
          }
        };

        const tools = (status && status.tools) ? Object.values(status.tools) : [];
        const missing = tools.filter((t) => t.state === 'MISSING');
        const ready = tools.filter((t) => t.state === 'READY').length;
        const ok = status && status.ok;

        const dot = !status ? '#9aa0a6' : ok && missing.length === 0 ? '#1a9e5c' : ok ? '#c9a227' : '#d33a3a';

        // 浮层挂到 body：输入区有 overflow/transform，留在原地会被裁掉。
        const popover = open && ReactDOM.createPortal(
          h(
            'div',
            {
              style: S.popover,
              onMouseDown: (e) => e.stopPropagation(),
            },
            h(
              'div',
              { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 } },
              h('span', { style: { width: 8, height: 8, borderRadius: 4, background: dot, flex: 'none' } }),
              h('span', { style: { fontSize: 13, fontWeight: 600 } }, 'Seep 工作台'),
              h('span', {
                style: { marginLeft: 'auto', fontSize: 12, color: 'var(--dsw-alias-label-tertiary)' },
              }, ok ? '就绪' : '未就绪'),
              h('button', { style: S.iconBtn, onClick: () => setOpen(false), title: '收起' }, '×'),
            ),
            status && status.lab
              ? h(
                  'div',
                  {
                    style: {
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '8px 10px',
                      marginBottom: 10,
                      borderRadius: 8,
                      background: 'var(--dsw-alias-bg-layer-1)',
                      border: '0.5px solid var(--dsw-alias-border-l1)',
                    },
                  },
                  h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, 'Lab 工作台模式'),
                  h('span', {
                    style: { fontSize: 11.5, color: 'var(--dsw-alias-label-tertiary)' },
                  }, status.lab.injecting ? '已进入' : '未进入'),
                  h('span', { style: { marginLeft: 'auto' } }),
                  h('button', {
                    style: status.lab.injecting ? S.btnSmallPrimary : S.btnSmall,
                    disabled: busy,
                    title: '只影响当前 DSH 进程，关掉就不注入任何作战纪律',
                    onClick: () => void toggleLab(!status.lab.injecting),
                  }, status.lab.injecting ? '关闭' : '开启'),
                )
              : null,
            status && status.lab && status.lab.lastRewrite
              ? h(
                  'div',
                  {
                    style: {
                      fontSize: 11.5,
                      lineHeight: '17px',
                      padding: '8px 10px',
                      marginBottom: 10,
                      borderRadius: 8,
                      border: '0.5px dashed var(--dsw-alias-border-l2)',
                      color: 'var(--dsw-alias-label-secondary)',
                      wordBreak: 'break-all',
                    },
                  },
                  h('div', { style: { fontWeight: 600, marginBottom: 4 } }, '最近一次改写（界面里看不到，发给模型的是这份）'),
                  h('div', null, '原：', status.lab.lastRewrite.before),
                  h('div', null, '改：', status.lab.lastRewrite.after),
                )
              : null,
            error
              ? h('p', { style: S.err }, error)
              : status
                ? h(
                    'div',
                    { style: { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12.5 } },
                    h('div', { style: S.kv }, h('span', { style: S.k }, '版本'), h('span', { style: S.v }, status.version || '-')),
                    h('div', { style: S.kv }, h('span', { style: S.k }, '已接线'), h('span', { style: S.v }, status.wired || '-')),
                    h('div', { style: S.kv }, h('span', { style: S.k }, 'lab 开关'), h('span', { style: S.v }, status.labGate ? '已启用' : '已关闭')),
                    h('div', { style: S.kv }, h('span', { style: S.k }, '工具'), h('span', { style: S.v }, `${ready} 就绪${missing.length ? ` / ${missing.length} 缺失：${missing.map((m) => m.id).join(', ')}` : ''}`)),
                    h('div', { style: { ...S.kv, alignItems: 'flex-start' } }, h('span', { style: S.k }, '仓库'), h('span', { style: { ...S.v, wordBreak: 'break-all' } }, status.repoRoot || '-')),
                  )
                : h('p', { style: S.hint }, busy ? '正在读状态…' : '还没读到状态'),

            h(
              'div',
              { style: { display: 'flex', gap: 8, marginTop: 10 } },
              h('button', { style: S.btnSmall, disabled: busy, onClick: () => void load() }, busy ? '检查中…' : '重新检查'),
              h('button', {
                style: S.btnSmall,
                onClick: () => {
                  const root = (status && status.repoRoot) || '<仓库路径>';
                  void navigator.clipboard?.writeText(`cd "${root}"
python setup/verify-dsh.py`);
                },
              }, '复制校验命令'),
            ),
            h('p', { style: { ...S.hint, marginTop: 8 } },
              '完整面板：设置 → Seep 工作台（改路径、看全部 20 个工具、指定工具路径）'),
          ),
          document.body,
        );

        return h(
          React.Fragment,
          null,
          h(
            'button',
            {
              style: S.quickBtn,
              title: 'Seep 工作台状态',
              onClick: () => setOpen((v) => !v),
            },
            h('span', { style: { width: 7, height: 7, borderRadius: 4, background: dot, flex: 'none' } }),
            'Seep',
          ),
          popover,
        );
      };
    }

    // ---------------------------------------------------------------- 入口

    /** 这半侧需要的客户端服务。 */
    const inject = ['slots', 'configForms'];

    function apply(ctx) {
      const Panel = makePanel(ctx);

      // 入口一：设置 → 插件 → 我们的卡片 → 那一行的「配置」。
      // DSH 官方给 bundle row 的配置位，宿主会把 form 传进来。
      // 注意：keyed 槽位用 key（不是 id），值是 `<包名>#<行 id>`。
      ctx.slots.inject('plugins.row.config', () =>
        ctx.slots.register(
          {
            name: 'plugins.row.config',
            key: ROW_KEY,
            order: 10,
            label: () => 'Seep 工作台',
          },
          Panel,
        ),
      );

      // 入口〇：小按钮，两处都放同一个组件
      //   · conversation.hero.options —— 新会话时输入框上方那一行（工作区 / 标准模式 旁边）
      //   · conversation.input.right —— 有对话时输入框右侧（上面那行只在空会话出现）
      const QuickEntry = makeQuickEntry(ctx);
      ctx.slots.inject('conversation.hero.options', () =>
        ctx.slots.register(
          { name: 'conversation.hero.options', id: `${NS}-hero`, order: 20 },
          QuickEntry,
        ),
      );
      ctx.slots.inject('conversation.input.right', () =>
        ctx.slots.register(
          { name: 'conversation.input.right', id: `${NS}-quick`, order: 20 },
          QuickEntry,
        ),
      );

      // 入口二：设置左侧导航里单独一页，不用翻插件列表也能找到。
      // 这一处宿主不传 form，组件会退回 ctx.configForms.get()。
      ctx.slots.inject('settings.section', () =>
        ctx.slots.register(
          { name: 'settings.section', id: NS, order: 40, label: () => 'Seep 工作台' },
          Panel,
        ),
      );
    }

    return { apply, inject, NS };
  },
});
