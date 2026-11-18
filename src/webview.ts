/**
 * 发音面板的网页。用浏览器自带的 Web Speech API（speechSynthesis）朗读。
 * 插件发来 speak / stop / show 消息，网页读完一个单词后回复 done。
 * 面板里的跳转控件发送 jump / jumpIndex / goTo 消息给插件。
 */
export function getWebviewHtml(nonce: string): string {
  return /* html */ `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 8px 12px; }
  .word { font-size: 1.8em; font-weight: 600; }
  .phonetic { opacity: .7; margin-left: .5em; font-size: .6em; font-weight: normal; }
  .meaning { margin-top: 4px; font-size: 1.1em; white-space: pre-line; line-height: 1.5; }
  .muted { opacity: .65; font-size: .9em; }
  .warn { color: var(--vscode-errorForeground); }
  button {
    margin-top: 8px; padding: 4px 12px; border: none; cursor: pointer;
    background: var(--vscode-button-background); color: var(--vscode-button-foreground);
  }
  button:hover { background: var(--vscode-button-hoverBackground); }
  button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
  button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
  button:disabled { opacity: .5; cursor: default; }
  .controls { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 4px; }
  .controls button { margin-top: 0; min-width: 72px; }
  #play { min-width: 96px; }
  .jump { margin: 4px 0 12px; max-width: 520px; }
  .jump input[type=range] { width: 100%; accent-color: var(--vscode-button-background); }
  .row { display: flex; gap: 6px; align-items: center; margin-top: 6px; }
  .row button { margin-top: 0; white-space: nowrap; }
  .row input[type=text] {
    flex: 1; min-width: 0; padding: 4px 6px;
    background: var(--vscode-input-background); color: var(--vscode-input-foreground);
    border: 1px solid var(--vscode-input-border, transparent);
  }
  .row input[type=text]:focus { outline: 1px solid var(--vscode-focusBorder); }
</style>
</head>
<body>
  <div class="word"><span id="word">—</span><span class="phonetic" id="phonetic"></span></div>
  <div class="meaning" id="meaning"></div>
  <p class="muted" id="progress"></p>
  <div class="controls">
    <button id="prev" class="secondary" title="上一个（Ctrl+Alt+[）">⏮ 上一个</button>
    <button id="play" title="播放 / 暂停（Ctrl+Alt+P）">▶ 播放</button>
    <button id="next" class="secondary" title="下一个（Ctrl+Alt+]）">下一个 ⏭</button>
    <button id="mute" class="secondary" title="静音时单词照常轮播，只是不发声（Ctrl+Alt+M）">🔇 静音</button>
    <button id="visible" class="secondary" title="显示 / 隐藏状态栏单词（Ctrl+Alt+H）">隐藏状态栏</button>
  </div>
  <div class="jump">
    <input type="range" id="slider" min="1" max="1" value="1" title="拖动选择从第几个单词开始">
    <div class="row">
      <input type="text" id="target" placeholder="从哪里开始？输入序号、百分比或单词，如 500、50%、abandon">
      <button id="go">跳转</button>
      <button id="search" class="secondary" title="按单词或中文意思搜索">搜索…</button>
    </div>
  </div>
  <button id="unlock" hidden>启用发音并播放</button>
  <p class="muted" id="voices">正在检测系统语音…</p>
  <p class="muted">快捷键：Ctrl+Alt+P 播放/暂停 · Ctrl+Alt+M 静音 · Ctrl+Alt+H 显示/隐藏 · Ctrl+Alt+[ / ] 上一个/下一个 · Ctrl+Alt+G 跳转<br>播放开始后可以收起这个面板，不影响发音。</p>

<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  const synth = window.speechSynthesis;
  const $ = (id) => document.getElementById(id);

  let voices = [];
  let token = 0;          // 每次 speak/stop 自增，用来作废旧的朗读
  const alive = new Set(); // 保留 utterance 引用，避免被回收后 onend 不触发（Chromium 的老问题）

  function loadVoices() {
    voices = synth.getVoices();
    const en = pick('en-US'), zh = pick('zh-CN');
    const name = (v) => v ? v.name : '<span class="warn">未找到</span>';
    $('voices').innerHTML = '英文语音：' + name(en) + '<br>中文语音：' + name(zh);
  }
  synth.onvoiceschanged = loadVoices;
  loadVoices();

  function pick(lang) {
    const l = lang.toLowerCase(), prefix = l.split('-')[0];
    return voices.find(v => v.lang.toLowerCase().replace('_', '-') === l)
        || voices.find(v => v.lang.toLowerCase().startsWith(prefix));
  }

  function say(text, lang, rate) {
    return new Promise((resolve, reject) => {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = lang;
      const v = pick(lang);
      if (v) u.voice = v;
      u.rate = rate;
      alive.add(u);
      u.onend = () => { alive.delete(u); resolve(); };
      u.onerror = (e) => { alive.delete(u); reject(e.error || 'unknown'); };
      synth.speak(u);
    });
  }

  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  async function speak(m) {
    const t = ++token;
    synth.cancel();
    try {
      await say(m.word, 'en-US', m.rate);
      if (t !== token) return;
      if (m.speakMeaning && m.meaning) {
        await wait(300);
        if (t !== token) return;
        await say(m.meaning, 'zh-CN', m.rate);
        if (t !== token) return;
      }
      vscode.postMessage({ type: 'done', id: m.id });
    } catch (err) {
      if (t !== token || err === 'interrupted' || err === 'canceled') return;
      if (err === 'not-allowed') $('unlock').hidden = false;
      vscode.postMessage({ type: 'error', id: m.id, error: String(err) });
    }
  }

  let dragging = false;  // 拖动进度条时不要被插件发来的进度覆盖
  let lastShow = null;

  function show(m) {
    lastShow = m;
    const w = m.word;
    const slider = $('slider');
    slider.max = String(Math.max(m.total, 1));
    if (!dragging) slider.value = String(m.index + 1);
    for (const id of ['slider', 'target', 'go', 'search', 'prev', 'play', 'next']) $(id).disabled = !m.total;
    $('play').textContent = m.playing ? '⏸ 暂停' : '▶ 播放';
    $('visible').textContent = m.visible ? '隐藏状态栏' : '显示状态栏';
    $('mute').textContent = m.muted ? '🔊 取消静音' : '🔇 静音';
    $('word').textContent = w ? w.word : '单词本为空';
    $('phonetic').textContent = w && w.phonetic ? w.phonetic : '';
    $('meaning').textContent = w ? (w.detail || [w.pos, w.meaning].filter(Boolean).join(' ')) : '';
    $('progress').textContent = w ? (m.playing ? '▶ 播放中' : '⏸ 已暂停') + (m.muted ? ' · 🔇 静音' : '') + ' · 第 ' + (m.index + 1) + ' / ' + m.total + ' 个' : '';
  }

  window.addEventListener('message', (e) => {
    const m = e.data;
    if (m.type === 'speak') speak(m);
    else if (m.type === 'stop') { token++; synth.cancel(); }
    else if (m.type === 'show') show(m);
  });

  // ---- 控制按钮 ----
  const control = (action) => vscode.postMessage({ type: 'control', action });
  $('play').addEventListener('click', () => {
    // 点击本身就是用户手势，顺便解锁发音，避免被浏览器拦截
    if (lastShow && !lastShow.playing) synth.speak(new SpeechSynthesisUtterance(''));
    $('unlock').hidden = true;
    control('togglePlay');
  });
  $('prev').addEventListener('click', () => control('previous'));
  $('next').addEventListener('click', () => control('next'));
  $('visible').addEventListener('click', () => control('toggleVisible'));
  $('mute').addEventListener('click', () => {
    if (lastShow && lastShow.muted) synth.speak(new SpeechSynthesisUtterance(''));  // 取消静音时顺便解锁发音
    control('toggleMute');
  });

  // ---- 跳转控件 ----
  $('slider').addEventListener('input', () => {
    dragging = true;
    if (lastShow) $('progress').textContent = '⇢ 松开后跳到第 ' + $('slider').value + ' / ' + lastShow.total + ' 个';
  });
  $('slider').addEventListener('change', () => {
    dragging = false;
    vscode.postMessage({ type: 'jumpIndex', index: Number($('slider').value) - 1 });
  });

  function jump() {
    const value = $('target').value.trim();
    if (!value) return;
    vscode.postMessage({ type: 'jump', value });
    $('target').value = '';
  }
  $('go').addEventListener('click', jump);
  $('target').addEventListener('keydown', (e) => { if (e.key === 'Enter') jump(); });
  $('search').addEventListener('click', () => vscode.postMessage({ type: 'goTo' }));

  // 如果发音被拦截（需要用户手势），点一下这个按钮就能解锁
  $('unlock').addEventListener('click', () => {
    synth.speak(new SpeechSynthesisUtterance(''));
    $('unlock').hidden = true;
    vscode.postMessage({ type: 'unlocked' });
  });

  vscode.postMessage({ type: 'ready' });
</script>
</body>
</html>`;
}
