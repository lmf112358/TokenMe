const test = require('node:test');
const assert = require('node:assert/strict');
const card = require('../token_footprint/share-card.js');

test('imported platform names reach the card and zero-token rows stay out', () => {
  const sources = [{source:'openclaw',total_tokens:100},{source:'hermes',total_tokens:20},{source:'warp',total_tokens:0}];
  const platforms = [{source:'openclaw',name:'OpenClaw'},{source:'hermes',name:'Hermes Agent'}];
  assert.equal(card.toolsLabel(sources, platforms), 'OpenClaw · Hermes Agent');
  assert.equal(card.toolsLabel([{source:'codex',total_tokens:1}]), 'Codex');
  const view = {total_tokens:120,active_days:1,sources,daily:[{date:'2026-10-01',total_tokens:120}],timezone:'UTC+08:00',first_observed_day:'2026-10-01',last_observed_day:'2026-10-01'};
  const model = card.modelFor({generated_at:'2026-10-02T00:00:00Z',views:{all:view},platforms});
  assert.equal(model.tools, 'OpenClaw · Hermes Agent');
});
