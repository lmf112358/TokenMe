/* TokenMe share image v0.1. Native Canvas; no network or third-party runtime. */
(function (root) {
  'use strict';
  const levels = [
    { min: 1, name: '素棉', paper: '#f2eee3', ink: '#304538', sub: '#526454', foil: '#617449', line: '#b5b9a3', shine: .07 },
    { min: 10000000, name: '染纸', paper: '#617564', ink: '#f4f0de', sub: '#e8ead9', foil: '#ece4b5', line: '#adbea6', shine: .13 },
    { min: 100000000, name: '珠光', paper: '#344b61', ink: '#e8eef0', sub: '#d1dde4', foil: '#b7d6d4', line: '#7794a5', shine: .35 },
    { min: 1000000000, name: '钛银', paper: '#b3bfc3', ink: '#243b43', sub: '#344e55', foil: '#314d59', line: '#6f878c', shine: .65 },
    { min: 10000000000, name: '墨金', paper: '#202923', ink: '#e4c78a', sub: '#cfbf9e', foil: '#d2b16a', line: '#8f7e55', shine: .11 }
  ];
  const knownNames = { codex: 'Codex', workbuddy: 'WorkBuddy', kimi: 'Kimi Code', qwen: 'Qwen Code', claude: 'Claude Code', pi: 'Pi Agent', gemini: 'Gemini CLI', opencode: 'OpenCode', cursor: 'Cursor', trae: 'TRAE' };
  function validCount(n) { return Number.isSafeInteger(n) && n >= 0; }
  function levelFor(total) {
    if (!validCount(total) || total === 0) return null;
    let index = 0;
    for (let i = 1; i < levels.length; i++) if (total >= levels[i].min) index = i;
    return { ...levels[index], number: index + 1 };
  }
  function formatI(total) {
    if (!validCount(total)) return '—';
    if (total > 0 && total < 10000) return '<0.01';
    const n = Math.floor(total / 10000) / 100;
    if (n >= 1000000) return (Math.floor(n / 10000) / 100).toLocaleString('en-US', { maximumFractionDigits: 2 }) + 'M';
    return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
  }
  function toolsLabel(sources, platforms = []) {
    const ordered = [...sources].filter(s => s.total_tokens > 0).sort((a, b) => b.total_tokens - a.total_tokens || String(a.source).localeCompare(String(b.source)));
    const labels = ordered.slice(0, 2).map(s => platforms.find(p => p.source === s.source)?.name || knownNames[s.source] || String(s.source));
    if (ordered.length > 2) labels.push('+' + (ordered.length - 2));
    return labels.join(' · ');
  }
  function dayAt(instant, offset) {
    const match = /^UTC([+-])(\d{2}):(\d{2})$/.exec(offset || '');
    if (!match || Number(match[2]) > 14 || Number(match[3]) > 59 || (Number(match[2]) === 14 && Number(match[3]) !== 0)) return null;
    const delta = (Number(match[2]) * 60 + Number(match[3])) * (match[1] === '+' ? 1 : -1);
    const date = new Date(Date.parse(instant) + delta * 60000);
    return Number.isFinite(date.getTime()) ? date.toISOString().slice(0, 10) : null;
  }
  function monthAt(instant, offset) {
    const day = dayAt(instant, offset);
    return day ? day.slice(0, 7).replace('-', '.') : '生成时间未提供';
  }
  const dayMs = 86400000;
  const collaborationRule = 'TokenMe 使用习惯规则 v1：持续使用者需近 30 天至少活跃 8 天，且截至评估日的最近四个 7 天区间均有记录。仅计入正用量的日期，同日多次使用只算一天；不评价能力、成果或全球排名。';
  function dayNumber(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
    const time = Date.parse(value + 'T00:00:00Z');
    return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? time / dayMs : null;
  }
  function collaborationFor(bundle, period = 'all') {
    const all = bundle.views?.all;
    const today = dayNumber(dayAt(bundle.generated_at, all?.timezone));
    const waiting = { available: false, stage: '正在积累记录', headline: '等待足够的日期记录，再判断使用习惯。',
      evidence: '评估日期或日记录未提供。', basis: '依据已采集的本地记录评估', rule: collaborationRule };
    if (today === null || !Array.isArray(all?.daily)) return waiting;
    let end = today;
    if (period !== 'all') {
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period) || !bundle.views?.[period]) return waiting;
      const start = dayNumber(period + '-01');
      if (start === null || start > today) return waiting;
      const monthEnd = new Date(start * dayMs);
      monthEnd.setUTCMonth(monthEnd.getUTCMonth() + 1);
      end = Math.min(today, monthEnd.getTime() / dayMs - 1);
    }
    const from = end - 29, days = new Set();
    for (const row of all.daily) {
      const date = dayNumber(row.date);
      if (date !== null && date >= from && date <= end && validCount(row.total_tokens) && row.total_tokens > 0) days.add(date);
    }
    const intervals = Array.from({ length: 4 }, (_, i) => {
      const last = end - i * 7, first = last - 6;
      return { from: new Date(first * dayMs).toISOString().slice(0, 10), through: new Date(last * dayMs).toISOString().slice(0, 10),
        activeDays: [...days].filter(day => day >= first && day <= last).length };
    });
    let consecutiveWeeks = 0;
    for (const interval of intervals) { if (!interval.activeDays) break; consecutiveWeeks++; }
    const activeDays = days.size, sustained = activeDays >= 8 && consecutiveWeeks === 4;
    const stage = sustained ? '持续使用者' : activeDays === 1 ? '初次探索' : '正在积累记录';
    const headline = sustained ? '你正在形成持续的 AI 协作习惯。' : activeDays === 1 ? '你已留下与 AI 协作的足迹。' :
      activeDays ? '你正在积累与 AI 协作的记录。' : '等待新的足迹，继续积累协作记录。';
    return { available: true, stage, headline, activeDays, consecutiveWeeks, intervals,
      from: new Date(from * dayMs).toISOString().slice(0, 10), through: new Date(end * dayMs).toISOString().slice(0, 10),
      evidence: `近 30 天活跃 ${activeDays} 天 · 最近连续 ${consecutiveWeeks} 周有记录`,
      basis: waiting.basis, rule: collaborationRule };
  }
  function modelFor(bundle, nickname = '', period = 'all') {
    // A monthly souvenir has its own amount; material always describes cumulative history.
    const cumulative = bundle.views && bundle.views.all;
    if (!cumulative || !validCount(cumulative.total_tokens)) return { available: false, message: '累计记录不可用，暂不能生成分享图。' };
    const v = bundle.views && bundle.views[period];
    const total = v && v.total_tokens;
    if (!v || !validCount(total)) return { available: false, message: '该周期记录不可用，暂不能生成分享图。' };
    if (total === 0 && period !== 'all') return { available: false, message: '这个月暂无有效记录，选择其他月份或累计档案。' };
    const level = levelFor(cumulative.total_tokens);
    if (!level) return { available: false, message: '暂无有效用量记录，暂未评级。未接入的平台不代表零用量。' };
    const first = v.first_observed_day || v.daily?.[0]?.date;
    const last = v.last_observed_day || v.daily?.at(-1)?.date;
    const range = first && last ? (first.slice(0, 7) === last.slice(0, 7) ? first.slice(0, 7).replace('-', '.') : first.slice(0, 7).replace('-', '.') + '—' + last.slice(0, 7).replace('-', '.')) : '观测日期未提供';
    const daily = (v.daily || []).filter(d => validCount(d.total_tokens)).map(d => Math.log1p(d.total_tokens));
    const max = Math.max(1, ...daily);
    return { available: true, total, level, value: formatI(total), nickname: String(nickname).trim() || '我的 AI 足迹',
      scope: period, label: period === 'all' ? '累计 I 量' : period.replace('-', '.') + ' I 量',
      gradeLabel: (period === 'all' ? '' : '累计 ') + `L${level.number} · ${level.name}`,
      stamp: monthAt(bundle.generated_at, v.timezone), range, activeDays: v.active_days,
      tools: toolsLabel(v.sources || [], bundle.platforms || []), rhythm: daily.map(n => n / max), collaboration: collaborationFor(bundle, period) };
  }
  function draw(canvas, model, format = 'portrait', options = {}) {
    if (!model.available) throw new Error(model.message);
    const square = format === 'square', h = square ? 1080 : 1440;
    canvas.width = 1080; canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('当前浏览器不支持图片绘制。');
    const l = model.level;
    const qr = options.qr?.matrix;
    const hasQR = Array.isArray(qr) && qr.length >= 21 && qr.length <= 37 && qr.every(row => typeof row === 'string' && row.length === qr.length && /^[01]+$/.test(row));
    function text(value, x, y, size, color, align = 'left', width = 936, weight = 400) {
      ctx.textAlign = align; ctx.fillStyle = color;
      ctx.font = `${weight} ${size}px "Segoe UI", "Microsoft YaHei", sans-serif`;
      let s = String(value);
      while (ctx.measureText(s).width > width && size > 36) {
        size -= 1; ctx.font = `${weight} ${size}px "Segoe UI", "Microsoft YaHei", sans-serif`;
      }
      if (ctx.measureText(s).width > width) {
        const chars = Array.from(s);
        while (chars.length && ctx.measureText(chars.join('') + '…').width > width) chars.pop();
        s = chars.join('') + '…';
      }
      ctx.fillText(s, x, y);
    }
    ctx.fillStyle = l.paper; ctx.fillRect(0, 0, 1080, h);
    ctx.fillStyle = 'rgba(255,255,255,.045)';
    for (let x = 1; x < 1080; x += 6) ctx.fillRect(x, 0, 1, h);
    const sheen = ctx.createLinearGradient(0, 0, 1080, h * .85);
    sheen.addColorStop(0, 'rgba(255,255,255,0)'); sheen.addColorStop(.38, `rgba(255,255,255,${l.shine * .75})`);
    sheen.addColorStop(.54, 'rgba(255,255,255,0)'); sheen.addColorStop(.86, `rgba(255,255,255,${l.shine * .36})`);
    sheen.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = sheen; ctx.fillRect(0, 0, 1080, h);
    ctx.fillStyle = l.foil; ctx.fillRect(0, h - 5, 1080, 5);
    text('TokenMe', 72, 112, 44, l.ink, 'left', 400, 500);
    text(model.stamp, 1008, 112, 40, l.sub, 'right', 480);
    text(model.nickname, 72, 207, 53, l.ink, 'left', model.scope === 'all' ? 650 : 565);
    text(model.gradeLabel || `L${l.number} · ${l.name}`, 1008, 204, model.scope === 'all' ? 42 : 36, l.sub, 'right', 350);
    ctx.save(); ctx.translate(540, square ? 343 : 477); ctx.scale(square ? .58 : .88, square ? .58 : .88);
    const foil = ctx.createLinearGradient(-230, -230, 240, 240);
    foil.addColorStop(0, l.foil); foil.addColorStop(.43, l.number === 5 ? '#f3e1b5' : l.ink); foil.addColorStop(.64, l.foil); foil.addColorStop(1, l.ink);
    ctx.strokeStyle = foil; ctx.lineWidth = 1.6;
    for (let i = 0; i < 29; i++) {
      const t = i / 28;
      const bucket = model.rhythm.length ? model.rhythm[Math.min(model.rhythm.length - 1, Math.floor(t * model.rhythm.length))] : .5;
      const shift = (bucket - .5) * 16;
      ctx.globalAlpha = .32 + t * .68; ctx.beginPath(); ctx.moveTo(-214 + t * 126, -102 - t * 58);
      ctx.bezierCurveTo(43 + t * 137, -300 + t * 60 + shift, 281 - t * 42, -119 + t * 161, 204 - t * 90, 121 + t * 97);
      ctx.bezierCurveTo(57 - t * 176, 290 - t * 86, -286 + t * 37, 144 - t * 92 + shift, -214 + t * 126, -102 - t * 58); ctx.stroke();
    }
    ctx.restore();
    text(model.label || '累计 I 量', 540, square ? 511 : 720, 36, l.sub, 'center');
    const numberY = square ? 626 : 865;
    let numberSize = square ? 132 : 160;
    ctx.font = '400 60px "Segoe UI", "Microsoft YaHei", sans-serif';
    const unitWidth = ctx.measureText('I').width, gap = 18;
    let valueWidth;
    do {
      ctx.font = `300 ${numberSize}px "Segoe UI", "Microsoft YaHei", sans-serif`;
      valueWidth = ctx.measureText(model.value).width;
      if (valueWidth + gap + unitWidth <= 936) break;
      numberSize -= 1;
    } while (numberSize > 60);
    const numberX = 540 - (valueWidth + gap + unitWidth) / 2;
    text(model.value, numberX, numberY, numberSize, l.ink, 'left', 936, 300);
    text('I', numberX + valueWidth + gap, numberY, 60, l.sub, 'left', unitWidth + 1);
    text(model.total.toLocaleString('en-US') + ' TOKENS', 540, square ? 676 : 925, 32, l.sub, 'center');
    const rule = square ? 710 : 977;
    ctx.beginPath(); ctx.strokeStyle = l.line; ctx.lineWidth = 1.5; ctx.moveTo(72, rule); ctx.lineTo(1008, rule); ctx.stroke();
    const c = model.collaboration;
    const top = square ? 759 : 1040, width = hasQR ? 700 : 936;
    text(c.headline, 72, top, square ? 32 : 38, l.ink, 'left', 936, 600);
    text(c.evidence, 72, top + 49, square ? 28 : 32, l.sub, 'left', width);
    text('TokenMe 协作阶段：' + c.stage, 72, top + 96, 30, l.ink, 'left', width);
    text(c.basis, 72, top + 139, 26, l.sub, 'left', width);
    text(c.available ? '截至 ' + c.through + ' · 近 30 天' : '日期记录待补充', 72, top + 180, 26, l.sub, 'left', width);
    text(`${model.activeDays} 活跃日 · ${model.tools}`, 72, square ? 1002 : 1310, 28, l.sub, 'left', width);
    text(model.range + ' · 本地记录 · 含缓存', 72, square ? 1044 : 1360, 26, l.sub, 'left', width);
    if (hasQR) {
      // Integer pixels, four-module quiet zone, opaque white background on every material.
      const cell = 4, size = (qr.length + 8) * cell, x = 1008 - size, y = h - 80 - size;
      ctx.fillStyle = '#ffffff'; ctx.fillRect(x, y, size, size);
      ctx.fillStyle = '#15251d';
      qr.forEach((row, iy) => Array.from(row).forEach((bit, ix) => { if (bit === '1') ctx.fillRect(x + (ix + 4) * cell, y + (iy + 4) * cell, cell, cell); }));
      text('生成我的', x + size / 2, h - 40, 28, l.sub, 'center', size);
      return canvas;
    }
    return canvas;
  }
  const api = { levelFor, formatI, toolsLabel, monthAt, collaborationFor, modelFor, draw };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.TokenMeCard = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
