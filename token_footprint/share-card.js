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
  const knownNames = { codex: 'Codex', workbuddy: 'WorkBuddy', kimi: 'Kimi Code', qwen: 'Qwen Code', claude: 'Claude Code' };
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
  function toolsLabel(sources) {
    const ordered = [...sources].filter(s => s.total_tokens > 0).sort((a, b) => b.total_tokens - a.total_tokens || String(a.source).localeCompare(String(b.source)));
    const labels = ordered.slice(0, 2).map(s => knownNames[s.source] || String(s.source));
    if (ordered.length > 2) labels.push('+' + (ordered.length - 2));
    return labels.join(' · ');
  }
  function monthAt(instant, offset) {
    const match = /^UTC([+-])(\d{2}):(\d{2})$/.exec(offset || '');
    if (!match) return '生成时间未提供';
    const delta = (Number(match[2]) * 60 + Number(match[3])) * (match[1] === '+' ? 1 : -1);
    const date = new Date(Date.parse(instant) + delta * 60000);
    return Number.isFinite(date.getTime()) ? date.toISOString().slice(0, 7).replace('-', '.') : '生成时间未提供';
  }
  function modelFor(bundle, nickname = '') {
    // Always pair cumulative I and grade with the same all-history ledger.
    // Never include the overlapping account summary or the dashboard month.
    const v = bundle.views && bundle.views.all;
    const total = v && v.total_tokens;
    if (!v || !validCount(total)) return { available: false, message: '累计记录不可用，暂不能生成分享图。' };
    const level = levelFor(total);
    if (!level) return { available: false, message: '暂无有效用量记录，暂未评级。未接入的平台不代表零用量。' };
    const first = v.first_observed_day || v.daily?.[0]?.date;
    const last = v.last_observed_day || v.daily?.at(-1)?.date;
    const range = first && last ? (first.slice(0, 7) === last.slice(0, 7) ? first.slice(0, 7).replace('-', '.') : first.slice(0, 7).replace('-', '.') + '—' + last.slice(0, 7).replace('-', '.')) : '观测日期未提供';
    const daily = (v.daily || []).filter(d => validCount(d.total_tokens)).map(d => Math.log1p(d.total_tokens));
    const max = Math.max(1, ...daily);
    return { available: true, total, level, value: formatI(total), nickname: String(nickname).trim() || '我的 AI 足迹',
      stamp: monthAt(bundle.generated_at, v.timezone), range, activeDays: v.active_days,
      tools: toolsLabel(v.sources || []), rhythm: daily.map(n => n / max) };
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
    text(model.nickname, 72, 207, 53, l.ink, 'left', 650);
    text(`L${l.number} · ${l.name}`, 1008, 204, 42, l.sub, 'right', 240);
    ctx.save(); ctx.translate(540, square ? (hasQR ? 374 : 418) : 531); ctx.scale(square ? (hasQR ? .64 : .76) : 1.04, square ? (hasQR ? .64 : .76) : 1.04);
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
    text('累计 I 量', 540, square ? (hasQR ? 590 : 660) : 872, 42, l.sub, 'center');
    const numberY = square ? (hasQR ? 719 : 797) : 1038;
    let numberSize = square ? 146 : 176;
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
    text(model.total.toLocaleString('en-US') + ' TOKENS', 540, square ? (hasQR ? 770 : 851) : 1098, 40, l.sub, 'center');
    const rule = square ? (hasQR ? 800 : 892) : 1154, metric = square ? 950 : 1230, foot = square ? 1008 : 1350;
    ctx.beginPath(); ctx.strokeStyle = l.line; ctx.lineWidth = 1.5; ctx.moveTo(72, rule); ctx.lineTo(1008, rule); ctx.stroke();
    if (hasQR) {
      const top = square ? 864 : 1210;
      text(model.activeDays + ' 活跃日', 72, top, 42, l.ink, 'left', 680);
      text(model.tools, 72, top + 52, 36, l.sub, 'left', 680);
      text(model.range, 72, top + 100, 30, l.sub, 'left', 680);
      text('本地记录 · 含缓存', 72, top + 150, 30, l.sub, 'left', 680);
      // Integer pixels, four-module quiet zone, opaque white background on every material.
      const cell = 4, size = (qr.length + 8) * cell, x = 1008 - size, y = h - 80 - size;
      ctx.fillStyle = '#ffffff'; ctx.fillRect(x, y, size, size);
      ctx.fillStyle = '#15251d';
      qr.forEach((row, iy) => Array.from(row).forEach((bit, ix) => { if (bit === '1') ctx.fillRect(x + (ix + 4) * cell, y + (iy + 4) * cell, cell, cell); }));
      text('生成我的', x + size / 2, h - 40, 28, l.sub, 'center', size);
      return canvas;
    }
    text(model.activeDays + ' 活跃日', 72, metric, 44, l.ink, 'left', 280);
    text(model.tools, 1008, metric, 40, l.sub, 'right', 600);
    text('本地记录 · 含缓存', 72, foot, 40, l.sub, 'left', 450);
    text(model.range, 1008, foot, 40, l.sub, 'right', 450);
    return canvas;
  }
  const api = { levelFor, formatI, toolsLabel, monthAt, modelFor, draw };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.TokenMeCard = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
