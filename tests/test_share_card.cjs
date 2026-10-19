const test = require('node:test');
const assert = require('node:assert/strict');
const card = require('../token_footprint/share-card.js');

test('grade boundaries use exact native token integers, including zero and unknown', () => {
  for (const value of [null, undefined, -1, 1.5, NaN, Infinity, '10000000', Number.MAX_SAFE_INTEGER + 1, 0]) {
    assert.equal(card.levelFor(value), null);
  }
  for (const [tokens, grade] of [[1, 1], [9999999, 1], [10000000, 2], [99999999, 2],
    [100000000, 3], [999999999, 3], [1000000000, 4], [9999999999, 4], [10000000000, 5]]) {
    assert.equal(card.levelFor(tokens).number, grade, String(tokens));
  }
});

test('display does not round into a higher grade or turn small positive use into zero', () => {
  assert.equal(card.formatI(1), '<0.01');
  assert.equal(card.formatI(9999), '<0.01');
  assert.equal(card.formatI(10000), '0.01');
  assert.equal(card.formatI(9999999), '9.99');
  assert.equal(card.formatI(999999999), '999.99');
  assert.equal(card.formatI(1000000000), '1,000');
  assert.equal(card.formatI(1000000000000), '1M');
  assert.equal(card.formatI(null), '—');
});

function bundle() {
  return { generated_at: '2026-09-30T17:00:00Z', default_view: '2026-10',
    account: { summary: { lifetimeTokens: 99999999999 } },
    views: { all: { total_tokens: 1000000000, active_days: 2, timezone: 'UTC+08:00',
      first_observed_day: '2026-09-30', last_observed_day: '2026-10-01',
      daily: [{ date: '2026-09-30', total_tokens: 900000000 }, { date: '2026-10-01', total_tokens: 100000000 }],
      sources: [{ source: 'codex', total_tokens: 900000000 }, { source: 'workbuddy', total_tokens: 100000000 }] },
      '2026-10': { total_tokens: 100000000 } } };
}

test('card keeps cumulative grade, I, days, tools and scope together; never sums account data', () => {
  const b = bundle(), m = card.modelFor(b, '<script>literal nickname</script>');
  assert.equal(m.total, 1000000000);
  assert.equal(m.level.number, 4);
  assert.equal(m.value, '1,000');
  assert.equal(m.activeDays, 2);
  assert.equal(m.stamp, '2026.10');
  assert.equal(m.range, '2026.09—2026.10');
  assert.equal(m.tools, 'Codex · WorkBuddy');
  assert.equal(m.nickname, '<script>literal nickname</script>');
  b.default_view = 'all';
  assert.deepEqual(card.modelFor(b, m.nickname), m);
});

test('unavailable cumulative ledger never falls back to the selected month or account', () => {
  const b = bundle(); delete b.views.all;
  assert.equal(card.modelFor(b).available, false);
  b.views.all = { total_tokens: 0 };
  assert.equal(card.modelFor(b).available, false);
});

test('source names sort by real contribution, exclude zero and summarize extra tools', () => {
  const sources = [{ source: 'qwen', total_tokens: 3 }, { source: 'codex', total_tokens: 20 },
    { source: 'workbuddy', total_tokens: 10 }, { source: 'empty', total_tokens: 0 }];
  assert.equal(card.toolsLabel(sources), 'Codex · WorkBuddy · +1');
  assert.equal(sources[0].source, 'qwen');
  assert.equal(card.toolsLabel([]), '');
});

test('generation month respects report timezone at month boundaries', () => {
  assert.equal(card.monthAt('2026-10-01T01:00:00Z', 'UTC-08:00'), '2026.09');
  assert.equal(card.monthAt('2026-09-30T17:00:00Z', 'UTC+08:00'), '2026.10');
});

test('monthly souvenir uses monthly amount and cumulative material, explicitly labeled', () => {
  const b = bundle();
  b.views['2026-10'] = {...b.views.all, total_tokens: 100000000, active_days: 1,
    first_observed_day: '2026-10-01', last_observed_day: '2026-10-01'};
  const model = card.modelFor(b, 'Demo', '2026-10');
  assert.equal(model.total, 100000000);
  assert.equal(model.value, '100');
  assert.equal(model.level.number, 4);
  assert.equal(model.gradeLabel, '累计 L4 · 钛银');
  assert.equal(model.label, '2026.10 I 量');
  assert.equal(model.activeDays, 1);
  assert.equal(model.range, '2026.10');
  assert.equal(card.modelFor(b).total, 1000000000);
});

test('empty or unavailable monthly views do not borrow cumulative or account usage', () => {
  const b = bundle();
  b.views['2026-10'].total_tokens = 0;
  assert.equal(card.modelFor(b, '', '2026-10').available, false);
  assert.equal(card.modelFor(b, '', '2026-11').available, false);
});

function activity(offsets, tokens = 1) {
  const end = Date.parse('2026-10-13T00:00:00Z');
  const daily = offsets.map(offset => ({ date: new Date(end - offset * 86400000).toISOString().slice(0, 10), total_tokens: tokens }));
  return { generated_at: '2026-10-12T17:00:00Z', views: { all: {
    timezone: 'UTC+08:00', total_tokens: daily.length * tokens, daily
  } } };
}

test('habit rating depends on activity spread, never token volume or account usage', () => {
  const lowVolume = activity([0, 1, 7, 8, 14, 15, 21, 22]);
  const c = card.collaborationFor(lowVolume);
  assert.equal(c.stage, '持续使用者');
  assert.equal(c.activeDays, 8);
  assert.equal(c.consecutiveWeeks, 4);
  assert.equal(c.through, '2026-10-13');
  assert.equal(c.from, '2026-09-14');
  assert.equal(card.collaborationFor(activity([0], 10000000000)).stage, '初次探索');
  const concentrated = activity([0, 1, 2, 3, 4, 5, 6, 7]);
  concentrated.account = { summary: { lifetimeTokens: 10000000000 } };
  assert.equal(card.collaborationFor(concentrated).stage, '正在积累记录');
  assert.equal(card.collaborationFor(activity([0, 1, 7, 14, 15, 21, 22])).stage, '正在积累记录');
});

test('recent window includes 30th day, excludes old, future, invalid and zero dates, deduplicates days', () => {
  const b = activity([0, 0, 29, 30, -1]);
  b.views.all.daily.push({ date: '2026-10-12', total_tokens: 0 },
    { date: '2026-09-31', total_tokens: 999 }, { date: '2026-10-11', total_tokens: null });
  const c = card.collaborationFor(b);
  assert.equal(c.activeDays, 2);
  assert.equal(c.consecutiveWeeks, 1);
  const gap = card.collaborationFor(activity([0, 1, 7, 8, 21, 22, 23, 24]));
  assert.equal(gap.activeDays, 8);
  assert.equal(gap.consecutiveWeeks, 2);
  assert.equal(gap.stage, '正在积累记录');
  assert.equal(card.collaborationFor(activity([7, 14, 21])).consecutiveWeeks, 0);
});

test('monthly rating is evaluated at month end using cumulative day evidence, including cross-month days', () => {
  const b = activity([13, 14, 20, 21, 27, 28, 34, 35]);
  b.views['2026-09'] = { total_tokens: 8, daily: [] };
  const c = card.collaborationFor(b, '2026-09');
  assert.equal(c.through, '2026-09-30');
  assert.equal(c.from, '2026-09-01');
  assert.equal(c.stage, '持续使用者');
  assert.notEqual(card.collaborationFor(b).stage, '持续使用者');
  b.views['2026-10'] = { total_tokens: 1 };
  assert.equal(card.collaborationFor(b, '2026-10').through, '2026-10-13');
  b.generated_at = '2024-03-02T00:00:00Z';
  b.views['2024-02'] = { total_tokens: 1 };
  assert.equal(card.collaborationFor(b, '2024-02').through, '2024-02-29');
});

test('empty, stale and unavailable records cannot establish a habit; timezone changes the cutoff', () => {
  for (const b of [activity([]), activity([90, 120])]) {
    const c = card.collaborationFor(b);
    assert.equal(c.activeDays, 0);
    assert.equal(c.stage, '正在积累记录');
    assert.equal(c.available, true);
  }
  const b = activity([0]);
  b.views.all.timezone = 'UTC-08:00';
  assert.equal(card.collaborationFor(b).through, '2026-10-12');
  assert.equal(card.collaborationFor(b).activeDays, 0);
  for (const mutate of [b => {delete b.views.all.daily;}, b => {b.generated_at = 'unknown';},
    b => {b.views.all.timezone = 'UTC+14:01';}]) {
    const changed = activity([0]); mutate(changed);
    assert.equal(card.collaborationFor(changed).available, false);
  }
  assert.equal(card.collaborationFor(b, '2026-15').available, false);
  b.views['2026-11'] = { total_tokens: 1 };
  assert.equal(card.collaborationFor(b, '2026-11').available, false);
});
