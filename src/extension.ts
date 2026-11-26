import * as vscode from 'vscode';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { randomBytes } from 'crypto';
import { getWebviewHtml } from './webview';

interface Word {
  word: string;
  /** 英式音标（内置词库来自 ECDICT）；自定义单词本里不区分英美时也写在这里 */
  phonetic?: string;
  /** 美式音标（内置词库来自 CMUdict） */
  phonetic_us?: string;
  pos?: string;
  /** 简短释义：显示在状态栏，也用于朗读 */
  meaning: string;
  /** 完整释义（可多行）：显示在悬停提示和发音面板里 */
  detail?: string;
  /** 朗读文本：系统语音直接读单词可能读错时（如 Nginx），改为朗读这段文本 */
  speak?: string;
}

/** 内置单词本，数据由 scripts/build_wordbooks.py 从 ECDICT 生成 */
const BUILTIN_BOOKS: Record<string, string> = {
  programmer: '程序员词汇',
  business: '商务英语',
  mispronounced: '程序员易读错词',
  cet4: '大学英语四级',
  cet6: '大学英语六级',
  kaoyan: '考研',
  ielts: '雅思 IELTS',
  toefl: '托福 TOEFL',
  gre: 'GRE',
  gaokao: '高考',
  zhongkao: '中考',
};

/** Webview -> 插件 的消息 */
type FromWebview =
  | { type: 'ready' }
  | { type: 'done'; id: number }
  | { type: 'error'; id: number; error: string }
  | { type: 'unlocked' }
  | { type: 'disposed' }
  /** 面板输入框：序号、百分比或单词 */
  | { type: 'jump'; value: string }
  /** 面板进度条：单词下标（从 0 开始） */
  | { type: 'jumpIndex'; index: number }
  /** 面板「搜索…」按钮 */
  | { type: 'goTo' }
  /** 面板控制按钮 */
  | { type: 'control'; action: 'togglePlay' | 'toggleVisible' | 'toggleMute' | 'toggleAccent' | 'next' | 'previous' }
  /** 面板单词本下拉框：切换内置单词本 */
  | { type: 'selectBook'; book: string }
  /** 面板单词本下拉框：从文件导入 */
  | { type: 'importBook' };
/** 首次安装时默认使用的单词本 */
const DEFAULT_BOOK = 'programmer';

const VIEW_ID = 'codevocab.player';
/** 一个单词如果 30 秒还没读完，就认为卡住了，直接跳到下一个 */
const WATCHDOG_MS = 30_000;

export function activate(context: vscode.ExtensionContext) {
  const player = new Player(context);
  context.subscriptions.push(
    player,
    vscode.window.registerWebviewViewProvider(VIEW_ID, player.view, {
      // 面板被收起时保留网页，否则一收起就停止发音
      webviewOptions: { retainContextWhenHidden: true },
    }),
    vscode.commands.registerCommand('codevocab.togglePlay', () => player.togglePlay()),
    vscode.commands.registerCommand('codevocab.toggleVisible', () => player.toggleVisible()),
    vscode.commands.registerCommand('codevocab.next', () => player.move(1)),
    vscode.commands.registerCommand('codevocab.previous', () => player.move(-1)),
    vscode.commands.registerCommand('codevocab.selectWordbook', () => player.selectWordbook()),
    vscode.commands.registerCommand('codevocab.goTo', () => player.goTo()),
    vscode.commands.registerCommand('codevocab.toggleMute', () => player.toggleMute()),
  );
}

export function deactivate() {}

// ---------------------------------------------------------------------------
// 发音面板（Webview）：只负责出声，播放进度由 Player 控制
// ---------------------------------------------------------------------------

class PlayerView implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  private ready = false;
  private readyWaiters: (() => void)[] = [];

  constructor(private readonly onMessage: (m: FromWebview) => void) {}

  resolveWebviewView(view: vscode.WebviewView) {
    this.view = view;
    this.ready = false;
    view.webview.options = { enableScripts: true };
    view.webview.html = getWebviewHtml(randomBytes(16).toString('hex'));
    view.webview.onDidReceiveMessage((m: FromWebview) => {
      if (m.type === 'ready') {
        this.ready = true;
        this.readyWaiters.splice(0).forEach((resolve) => resolve());
      }
      this.onMessage(m);
    });
    view.onDidDispose(() => {
      this.view = undefined;
      this.ready = false;
      this.onMessage({ type: 'disposed' });
    });
  }

  /** 确保发音面板已经加载。第一次使用时需要把面板打开一次，之后可以收起。 */
  async ensureReady(): Promise<boolean> {
    if (this.ready) {
      return true;
    }
    const waiting = new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => resolve(false), 8000);
      this.readyWaiters.push(() => {
        clearTimeout(timer);
        resolve(true);
      });
    });
    if (!this.view) {
      await vscode.commands.executeCommand(`${VIEW_ID}.focus`);
      // 把光标还给编辑器，不打断写代码
      await vscode.commands.executeCommand('workbench.action.focusActiveEditorGroup');
    }
    return waiting;
  }

  post(message: unknown) {
    void this.view?.webview.postMessage(message);
  }
}

// ---------------------------------------------------------------------------
// 播放器：单词本、进度、状态栏、快捷键逻辑
// ---------------------------------------------------------------------------

class Player implements vscode.Disposable {
  readonly view: PlayerView;
  private readonly status: vscode.StatusBarItem;
  private readonly disposables: vscode.Disposable[] = [];

  private words: Word[] = [];
  private bookPath = '';
  private index = 0;
  private playing = false;
  private visible: boolean;
  private muted: boolean;
  /** 每次朗读的编号，用来丢弃过期的“读完了”消息 */
  private speakId = 0;
  private nextTimer?: NodeJS.Timeout;
  private watchdog?: NodeJS.Timeout;

  constructor(private readonly ctx: vscode.ExtensionContext) {
    this.view = new PlayerView((m) => this.onMessage(m));
    this.status = vscode.window.createStatusBarItem('codevocab.status', vscode.StatusBarAlignment.Left, 0);
    this.status.name = 'CodeVocab';
    this.status.command = 'codevocab.togglePlay';
    this.visible = ctx.globalState.get('codevocab.visible', true);
    this.muted = ctx.globalState.get('codevocab.muted', false);

    this.disposables.push(
      this.status,
      vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration('codevocab.wordbookPath') || e.affectsConfiguration('codevocab.builtinWordbook')) {
          this.pause();
          this.load();
        } else if (e.affectsConfiguration('codevocab.accent') && this.playing && !this.muted) {
          // 换了口音：用新口音重读当前单词，马上就能听出区别
          this.speakCurrent();
        } else if (e.affectsConfiguration('codevocab')) {
          this.render();
        }
      }),
    );
    this.load();
  }

  dispose() {
    this.clearTimers();
    this.disposables.forEach((d) => d.dispose());
  }

  // ---- 命令 ----

  togglePlay() {
    if (this.playing) {
      this.pause();
    } else {
      void this.play();
    }
  }

  toggleVisible() {
    this.visible = !this.visible;
    void this.ctx.globalState.update('codevocab.visible', this.visible);
    this.render();
  }

  /** 静音：单词照常在状态栏轮播，只是不发出声音 */
  async toggleMute() {
    this.muted = !this.muted;
    void this.ctx.globalState.update('codevocab.muted', this.muted);
    if (!this.playing) {
      this.render();
      return;
    }
    if (this.muted) {
      // 停掉正在读的声音，当前单词按静音时长重新计时
      this.speakCurrent();
      return;
    }
    // 取消静音：确保发音面板已加载，然后重新读当前单词
    this.render();
    if (!(await this.view.ensureReady())) {
      vscode.window.showErrorMessage('CodeVocab：发音面板没有加载成功，请打开底部面板中的「CodeVocab」后重试。');
      return;
    }
    if (this.playing && !this.muted) {
      this.speakCurrent();
    }
  }

  /**
   * 切换朗读口音（美音 / 英音），写回设置 codevocab.accent。
   * 写到当前生效的那一层（工作区设置优先），否则工作区里的设置会盖住用户设置，点了没反应。
   */
  async toggleAccent() {
    const cfg = this.cfg();
    const next = accent(cfg) === 'en-GB' ? 'en-US' : 'en-GB';
    const info = cfg.inspect<string>('accent');
    const target =
      info?.workspaceFolderValue !== undefined
        ? vscode.ConfigurationTarget.WorkspaceFolder
        : info?.workspaceValue !== undefined
          ? vscode.ConfigurationTarget.Workspace
          : vscode.ConfigurationTarget.Global;
    await cfg.update('accent', next, target);
  }

  move(step: number) {
    if (!this.words.length) {
      return;
    }
    const n = this.words.length;
    this.jumpTo((((this.index + step) % n) + n) % n);
  }

  /** 跳到第 index 个单词（从 0 开始）。正在播放就从这个词接着播。 */
  private jumpTo(index: number) {
    if (index < 0 || index >= this.words.length) {
      return;
    }
    this.index = index;
    void this.ctx.globalState.update(this.progressKey(), this.index);
    if (this.playing) {
      this.speakCurrent();
    } else {
      this.render();
    }
  }

  /**
   * 弹出搜索框选择从哪个单词开始：
   * - 输入单词或中文意思搜索
   * - 输入数字（如 500）跳到第 500 个
   * - 输入百分比（如 50%）跳到单词本的一半
   */
  /**
   * 面板输入框的跳转：序号或百分比直接跳；完全匹配某个单词也直接跳；
   * 否则打开搜索框，把输入的内容带进去让用户挑选。
   */
  private jumpByText(value: string) {
    const text = value.trim();
    if (!text || !this.words.length) {
      return;
    }
    const position = parsePosition(text, this.words.length);
    if (position !== undefined) {
      this.jumpTo(position);
      return;
    }
    const lower = text.toLowerCase();
    const exact = this.words.findIndex((w) => w.word.toLowerCase() === lower);
    if (exact >= 0) {
      this.jumpTo(exact);
    } else {
      this.goTo(text);
    }
  }

  goTo(initialValue = '') {
    const total = this.words.length;
    if (!total) {
      vscode.window.showWarningMessage('CodeVocab：单词本是空的，请先选择单词本。');
      return;
    }
    type Item = vscode.QuickPickItem & { index: number };
    const wordItems: Item[] = this.words.map((w, i) => ({
      label: w.word,
      description: `#${i + 1}  ${[w.pos, w.meaning].filter(Boolean).join(' ')}`,
      index: i,
    }));

    const qp = vscode.window.createQuickPick<Item>();
    qp.title = `跳转到单词（当前第 ${this.index + 1} / ${total} 个）`;
    qp.placeholder = '输入单词或中文意思搜索，或输入序号（如 500）、百分比（如 50%）';
    qp.matchOnDescription = true;
    qp.items = wordItems;
    qp.activeItems = [wordItems[this.index]];

    const onValue = (value: string) => {
      const target = parsePosition(value.trim(), total);
      if (target === undefined) {
        qp.items = wordItems;
        return;
      }
      const w = this.words[target];
      // 输入的是序号时，把“跳到第 N 个”放在最前面，并且保持在搜索结果里
      const jumpItem: Item = {
        label: `$(arrow-right) 跳到第 ${target + 1} 个：${w.word}`,
        description: [w.pos, w.meaning].filter(Boolean).join(' '),
        alwaysShow: true,
        index: target,
      };
      qp.items = [jumpItem, ...wordItems];
      qp.activeItems = [jumpItem];
    };
    qp.onDidChangeValue(onValue);
    if (initialValue) {
      qp.value = initialValue;
      onValue(initialValue);
    }
    qp.onDidAccept(() => {
      const picked = qp.selectedItems[0] ?? qp.activeItems[0];
      qp.hide();
      if (picked) {
        this.jumpTo(picked.index);
      }
    });
    qp.onDidHide(() => qp.dispose());
    qp.show();
  }

  async selectWordbook() {
    const cfg = this.cfg();
    const custom = cfg.get<string>('wordbookPath', '').trim();
    const current = custom ? '' : cfg.get<string>('builtinWordbook', DEFAULT_BOOK);
    type Item = vscode.QuickPickItem & { book?: string; browse?: boolean };
    const items: Item[] = [
      { label: '内置单词本', kind: vscode.QuickPickItemKind.Separator },
      ...Object.entries(BUILTIN_BOOKS).map(([book, label]) => ({
        label: (book === current ? '$(check) ' : '') + label,
        description: book === current ? '当前' : undefined,
        book,
      })),
      { label: '自定义', kind: vscode.QuickPickItemKind.Separator },
      {
        label: '$(folder-opened) 从文件导入…',
        description: custom ? `当前：${path.basename(custom)}` : 'JSON / CSV / TSV / TXT',
        browse: true,
      },
    ];
    const choice = await vscode.window.showQuickPick(items, { title: '选择单词本' });
    if (!choice) {
      return;
    }
    if (choice.book) {
      await this.useBuiltinWordbook(choice.book);
    } else {
      await this.importWordbook();
    }
  }

  /** 切换到内置单词本。修改配置会触发 onDidChangeConfiguration，自动重新加载。 */
  private async useBuiltinWordbook(book: string) {
    if (!(book in BUILTIN_BOOKS)) {
      return;
    }
    const cfg = this.cfg();
    await cfg.update('builtinWordbook', book, vscode.ConfigurationTarget.Global);
    await cfg.update('wordbookPath', '', vscode.ConfigurationTarget.Global);
  }

  /** 从文件导入单词本 */
  private async importWordbook() {
    const picked = await vscode.window.showOpenDialog({
      title: '选择单词本文件',
      canSelectMany: false,
      filters: { 单词本: ['json', 'csv', 'tsv', 'txt'] },
    });
    if (picked?.[0]) {
      await this.cfg().update('wordbookPath', picked[0].fsPath, vscode.ConfigurationTarget.Global);
    }
  }

  /** 当前单词本：内置的返回 key，自定义的返回 'custom' */
  private currentBook(): { id: string; name: string } {
    const cfg = this.cfg();
    const custom = cfg.get<string>('wordbookPath', '').trim();
    if (custom) {
      return { id: 'custom', name: path.basename(custom) };
    }
    const book = cfg.get<string>('builtinWordbook', DEFAULT_BOOK);
    const id = book in BUILTIN_BOOKS ? book : DEFAULT_BOOK;
    return { id, name: BUILTIN_BOOKS[id] };
  }

  // ---- 播放流程 ----

  private async play() {
    if (!this.words.length) {
      vscode.window.showWarningMessage('CodeVocab：单词本是空的，请先选择单词本。');
      return;
    }
    this.playing = true;
    if (this.muted) {
      // 静音时只轮播状态栏，不需要发音面板
      this.speakCurrent();
      return;
    }
    this.render();
    const ok = await this.view.ensureReady();
    if (!ok) {
      this.playing = false;
      this.render();
      vscode.window.showErrorMessage('CodeVocab：发音面板没有加载成功，请打开底部面板中的「CodeVocab」后重试。');
      return;
    }
    if (this.playing) {
      this.speakCurrent();
    }
  }

  private pause() {
    this.playing = false;
    this.clearTimers();
    this.speakId++;
    this.view.post({ type: 'stop' });
    this.render();
  }

  private speakCurrent() {
    this.clearTimers();
    const w = this.words[this.index];
    const id = ++this.speakId;
    const cfg = this.cfg();
    this.render();
    if (this.muted) {
      // 静音：不发声，每个单词停留一段时间后切到下一个
      this.view.post({ type: 'stop' });
      this.nextTimer = setTimeout(() => this.move(1), cfg.get<number>('mutedDuration', 5000));
      return;
    }
    this.view.post({
      type: 'speak',
      id,
      word: w.speak || w.word,
      meaning: w.meaning,
      lang: accent(cfg),
      speakMeaning: cfg.get<boolean>('speakMeaning', true),
      rate: cfg.get<number>('rate', 0.9),
    });
    this.watchdog = setTimeout(() => this.onSpoken(id), WATCHDOG_MS);
  }

  /** 一个单词读完：等一会儿再播下一个 */
  private onSpoken(id: number) {
    if (id !== this.speakId || !this.playing) {
      return;
    }
    this.clearTimers();
    this.nextTimer = setTimeout(() => this.move(1), this.cfg().get<number>('interval', 2000));
  }

  private onMessage(m: FromWebview) {
    switch (m.type) {
      case 'ready':
        this.render();
        break;
      case 'done':
        this.onSpoken(m.id);
        break;
      case 'error':
        if (m.id !== this.speakId || !this.playing) {
          return;
        }
        this.pause();
        vscode.window.showWarningMessage(
          m.error === 'not-allowed'
            ? 'CodeVocab：发音被拦截了，请在底部面板「CodeVocab」中点击「启用发音并播放」。'
            : `CodeVocab：发音失败（${m.error}）。`,
        );
        break;
      case 'unlocked':
        void this.play();
        break;
      case 'disposed':
        if (this.playing) {
          this.pause();
        }
        break;
      case 'jump':
        this.jumpByText(m.value);
        break;
      case 'jumpIndex':
        this.jumpTo(Math.floor(m.index));
        break;
      case 'goTo':
        this.goTo();
        break;
      case 'selectBook':
        void this.useBuiltinWordbook(m.book);
        break;
      case 'importBook':
        void this.importWordbook();
        break;
      case 'control':
        switch (m.action) {
          case 'togglePlay':
            this.togglePlay();
            break;
          case 'toggleVisible':
            this.toggleVisible();
            break;
          case 'toggleMute':
            void this.toggleMute();
            break;
          case 'toggleAccent':
            void this.toggleAccent();
            break;
          case 'next':
            this.move(1);
            break;
          case 'previous':
            this.move(-1);
            break;
        }
        break;
    }
  }

  private clearTimers() {
    clearTimeout(this.nextTimer);
    clearTimeout(this.watchdog);
    this.nextTimer = this.watchdog = undefined;
  }

  // ---- 单词本 ----

  private cfg() {
    return vscode.workspace.getConfiguration('codevocab');
  }

  private progressKey() {
    return `codevocab.progress:${this.bookPath}`;
  }

  private load() {
    const configured = this.cfg().get<string>('wordbookPath', '').trim();
    let builtin = this.cfg().get<string>('builtinWordbook', DEFAULT_BOOK);
    if (!(builtin in BUILTIN_BOOKS)) {
      builtin = DEFAULT_BOOK;
    }
    const file = configured
      ? resolvePath(configured)
      : path.join(this.ctx.extensionPath, 'wordbooks', `${builtin}.json`);
    this.bookPath = file;
    try {
      this.words = parseWordbook(file);
    } catch (e) {
      this.words = [];
      vscode.window.showErrorMessage(`CodeVocab：无法读取单词本 ${file}：${(e as Error).message}`);
    }
    const saved = this.ctx.globalState.get<number>(this.progressKey(), 0);
    this.index = saved >= 0 && saved < this.words.length ? saved : 0;
    this.render();
  }

  // ---- 界面 ----

  private render() {
    const w = this.words[this.index];
    if (!w) {
      this.status.text = '$(book) CodeVocab：单词本为空';
      this.status.tooltip = '点击或运行命令「CodeVocab: 选择单词本…」';
      this.status.command = 'codevocab.selectWordbook';
    } else {
      const max = this.cfg().get<number>('maxMeaningLength', 30);
      const icon = (this.playing ? '$(debug-pause)' : '$(play)') + (this.muted ? ' $(mute)' : '');
      const meaning = w.meaning.length > max ? w.meaning.slice(0, max) + '…' : w.meaning;
      const phoneticText = formatPhonetic(w);
      const phonetic = this.cfg().get<boolean>('showPhonetic', false) && phoneticText ? ` ${phoneticText}` : '';
      this.status.text = `${icon} ${w.word}${phonetic}  ${[w.pos, meaning].filter(Boolean).join(' ')}`;
      this.status.command = 'codevocab.togglePlay';

      const tip = new vscode.MarkdownString();
      tip.appendMarkdown('**');
      tip.appendText(w.word);
      tip.appendMarkdown('**');
      if (phoneticText) {
        tip.appendText(`  ${phoneticText}`);
      }
      for (const line of (w.detail ?? [w.pos, w.meaning].filter(Boolean).join(' ')).split('\n')) {
        tip.appendMarkdown('\n\n');
        tip.appendText(line);
      }
      tip.appendMarkdown('\n\n---\n\n');
      tip.appendText(`第 ${this.index + 1} / ${this.words.length} 个 · 点击播放/暂停 · Ctrl+Alt+G 跳转${this.muted ? ' · 已静音' : ''}`);
      this.status.tooltip = tip;
    }
    if (this.visible) {
      this.status.show();
    } else {
      this.status.hide();
    }
    this.view.post({
      type: 'show',
      word: w ? { ...w, phoneticText: formatPhonetic(w) } : null,
      accent: accent(this.cfg()),
      index: this.index,
      total: this.words.length,
      playing: this.playing,
      visible: this.visible,
      muted: this.muted,
      book: this.currentBook(),
      builtinBooks: BUILTIN_BOOKS,
    });
  }
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/** 朗读口音：codevocab.accent，只接受 en-US / en-GB */
function accent(cfg: vscode.WorkspaceConfiguration): 'en-US' | 'en-GB' {
  return cfg.get<string>('accent', 'en-US') === 'en-GB' ? 'en-GB' : 'en-US';
}

/** 音标显示文本：两种都有时写成「英 /…/ 美 /…/」，只有一种时直接显示（只有美式时标上“美”） */
function formatPhonetic(w: Word): string {
  const { phonetic: gb, phonetic_us: us } = w;
  if (gb && us && gb !== us) {
    return `英 ${gb} 美 ${us}`;
  }
  if (gb) {
    return gb;
  }
  return us ? `美 ${us}` : '';
}

/** 把 "500"、"#500"、"50%" 解析成单词下标（从 0 开始），不是位置就返回 undefined */
function parsePosition(value: string, total: number): number | undefined {
  const percent = /^(\d+(?:\.\d+)?)\s*%$/.exec(value);
  if (percent) {
    const p = Math.min(Number(percent[1]), 100);
    return Math.min(Math.floor((p / 100) * total), total - 1);
  }
  const num = /^#?(\d+)$/.exec(value);
  if (num) {
    const n = Number(num[1]);
    return n >= 1 && n <= total ? n - 1 : undefined;
  }
  return undefined;
}

function resolvePath(p: string): string {
  if (p.startsWith('~')) {
    p = path.join(os.homedir(), p.slice(1));
  }
  if (!path.isAbsolute(p)) {
    const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (root) {
      p = path.join(root, p);
    }
  }
  return p;
}

/**
 * 支持两种格式：
 * - JSON：[{ "word": "abandon", "phonetic": "/əˈbændən/", "phonetic_us": "/əˈbændən/", "pos": "v.", "meaning": "放弃" }]
 *   phonetic 是英式音标（不区分英美时也写在这里），phonetic_us 是美式音标，都可以省略
 * - CSV / TSV / TXT：每行「单词,词性,释义」或「单词,释义」，# 开头的行是注释
 */
function parseWordbook(file: string): Word[] {
  const text = fs.readFileSync(file, 'utf8').replace(/^﻿/, '');
  let raw: Partial<Word>[];
  if (file.toLowerCase().endsWith('.json')) {
    const data = JSON.parse(text);
    if (!Array.isArray(data)) {
      throw new Error('JSON 单词本必须是一个数组');
    }
    raw = data;
  } else {
    raw = text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#'))
      .map((line) => {
        const sep = line.includes('\t') ? '\t' : ',';
        const [word, second = '', ...rest] = line.split(sep);
        return rest.length ? { word, pos: second, meaning: rest.join(sep) } : { word, meaning: second };
      });
  }
  return raw
    .filter((w) => w && typeof w.word === 'string' && w.word.trim())
    .map((w) => ({
      word: String(w.word).trim(),
      phonetic: w.phonetic ? String(w.phonetic).trim() : undefined,
      phonetic_us: w.phonetic_us ? String(w.phonetic_us).trim() : undefined,
      pos: w.pos ? String(w.pos).trim() : undefined,
      meaning: String(w.meaning ?? '').trim(),
      detail: w.detail ? String(w.detail).trim() : undefined,
      speak: w.speak ? String(w.speak).trim() : undefined,
    }));
}
