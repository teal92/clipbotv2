import test from 'node:test';
import assert from 'node:assert/strict';

test('all completed routes and Publishing render with one set of handlers', async () => {
  const names = ['dashboard', 'streamers', 'clips', 'processing', 'publishing', 'davey', 'logs', 'settings', 'account', 'usage', 'reports', 'connections'];
  const handlers = new Map();
  const content = { innerHTML: '' };
  const title = {};
  const subtitle = {};
  const nav = names.map(name => ({
    dataset: { view: name }, active: false,
    classList: { remove() { nav.find(item => item.dataset.view === name).active = false; }, add() { nav.find(item => item.dataset.view === name).active = true; } },
    addEventListener(_type, callback) { this.navigate = callback; },
  }));
  globalThis.document = {
    getElementById(id) { return { 'app-content': content, 'page-title': title, 'page-subtitle': subtitle }[id]; },
    querySelectorAll() { return nav; },
    querySelector(selector) { return nav.find(item => selector.includes(`"${item.dataset.view}"`)); },
    addEventListener(type, callback) { handlers.set(type, [...(handlers.get(type) ?? []), callback]); },
  };
  globalThis.sessionStorage = { getItem() { return null; } };
  try {
    await import('../frontend/js/app.js');
    for (let cycle = 0; cycle < 2; cycle++) for (const item of nav) {
      item.navigate();
      assert.equal(title.textContent.toLowerCase(), item.dataset.view==='connections'?'connect accounts':item.dataset.view==='settings'?'account':item.dataset.view);
      assert.ok(content.innerHTML.includes(`${item.dataset.view==='settings'?'account':item.dataset.view}-page`) || item.dataset.view === 'dashboard' || item.dataset.view === 'streamers');
      assert.equal(nav.filter(button => button.active).length, 1);
      assert.ok(nav.find(button=>button.dataset.view===(item.dataset.view==='settings'?'account':item.dataset.view)).active);
    }
    assert.equal(handlers.get('submit').length, 10);
    assert.equal(handlers.get('click').length, 20);
    for(const type of ['click','submit','keydown'])assert.equal(new Set(handlers.get(type)).size,handlers.get(type).length);
  } finally { delete globalThis.document; delete globalThis.sessionStorage; }
});
