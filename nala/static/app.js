// Nala Mission Control — vanilla JS, no build step. Every interpolated
// string that could ever carry untrusted content (email subjects, model
// reasoning, chat replies, event payloads) goes through esc().

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------------------------------------------------------------- purposes
const PURPOSES = [
  { name: 'Projects', risk: 'act+confirm', active: true },
  { name: 'Finance', m5: true },
  { name: 'Baby', m5: true },
  { name: 'Relationships', m5: true },
  { name: 'Home', m5: true },
  { name: 'News', m5: true },
  { name: 'Interests', m5: true },
  { name: 'Purchase', m5: true },
];

function renderPurposeRail() {
  const nav = document.getElementById('purposeNav');
  nav.innerHTML = PURPOSES.map(p => `
    <button class="purpose-btn ${p.active ? 'active' : 'dimmed'}" ${p.m5 ? 'disabled' : ''}>
      <div class="row1">
        <span class="p-dot" style="background:${p.active ? 'var(--accent)' : '#5a6678'}"></span>
        <span class="p-name">${esc(p.name)}</span>
      </div>
      ${p.active ? `<span class="risk-badge risk-amber">${esc(p.risk)}</span>` : '<span class="tag-m5">M5</span>'}
    </button>
  `).join('');
}

// ---------------------------------------------------------------- mode switching
const modeTabs = document.querySelectorAll('.mode-tab');
const views = {
  monitor: document.getElementById('view-monitor'),
  chat: document.getElementById('view-chat'),
  memory: document.getElementById('view-memory'),
};
const mobileTabs = document.querySelectorAll('.mtab');
const monitorGrid = document.getElementById('monitorGrid');
const monitorSubtabs = document.querySelectorAll('.monitor-subtabs button');

function setMode(mode) {
  modeTabs.forEach(t => t.classList.toggle('active', t.dataset.mode === mode));
  Object.entries(views).forEach(([k, el]) => el.classList.toggle('active', k === mode));
  if (mode === 'chat' || mode === 'memory') {
    mobileTabs.forEach(b => b.classList.toggle('active', b.dataset.mobile === mode));
  }
  if (mode === 'memory') loadMemory();
}
modeTabs.forEach(t => t.addEventListener('click', () => setMode(t.dataset.mode)));

function setMobileTab(tab) {
  mobileTabs.forEach(b => b.classList.toggle('active', b.dataset.mobile === tab));
  if (tab === 'chat' || tab === 'memory') {
    setMode(tab);
    return;
  }
  setMode('monitor');
  monitorGrid.classList.toggle('mobile-show-feed', tab === 'feed');
  monitorGrid.classList.toggle('mobile-show-actions', tab === 'actions');
  monitorSubtabs.forEach(b => b.classList.toggle('active', b.dataset.subtab === tab));
}
mobileTabs.forEach(b => b.addEventListener('click', () => setMobileTab(b.dataset.mobile)));
monitorSubtabs.forEach(b => b.addEventListener('click', () => setMobileTab(b.dataset.subtab)));

// ---------------------------------------------------------------- top bar: in-doubt + spend
const indoubtChipEl = document.getElementById('indoubtChip');
const spendChipEl = document.getElementById('spendChip');
const spendDropdownEl = document.getElementById('spendDropdown');
const spendWrapEl = document.getElementById('spendWrap');

spendChipEl.addEventListener('click', () => spendDropdownEl.classList.toggle('open'));
document.addEventListener('click', (e) => {
  if (!spendWrapEl.contains(e.target)) spendDropdownEl.classList.remove('open');
});

function renderSpend(data) {
  spendChipEl.textContent = `$${Number(data.today_total).toFixed(4)} / $${Number(data.ceiling).toFixed(2)}`;
  const rows = (data.by_model || []).slice().sort((a, b) => b.total - a.total);
  let html = '<div class="sd-head">Spend by model · today</div>';
  html += rows.length
    ? rows.map(r => `<div class="spend-row"><span class="m-name">${esc(r.model)}</span><span>$${Number(r.total).toFixed(4)}</span></div>`).join('')
    : '<div class="spend-row"><span class="m-name">no spend yet today</span></div>';
  html += `<div class="sd-head" style="margin-top:8px;">yesterday: $${Number(data.yesterday_total).toFixed(4)}</div>`;
  spendDropdownEl.innerHTML = html;
}

async function pollSpend() {
  try {
    const resp = await fetch('/api/spend');
    const data = await resp.json();
    renderSpend(data);
  } catch (e) {
    spendChipEl.textContent = 'spend: unreachable';
  }
}

// ---------------------------------------------------------------- repo status + watcher health
const repoTagEl = document.getElementById('repoTag');
const repoListEl = document.getElementById('repoList');
const watcherTagEl = document.getElementById('watcherTag');
const watcherListEl = document.getElementById('watcherList');

function renderRepoList(repos) {
  repoTagEl.textContent = `${repos.length} repos`;
  repoListEl.innerHTML = repos.map(r => {
    if (r.error) {
      return `<div class="repo-card notgit">
        <div class="repo-top">
          <span class="dot" style="background:var(--faint)"></span>
          <span class="repo-name">${esc(r.repo)}</span>
          <span class="repo-flag" style="color:var(--faint)">${esc(r.error)}</span>
        </div>
      </div>`;
    }
    const flagColor = r.dirty ? 'var(--amber)' : 'var(--emerald)';
    const flagText = r.dirty ? 'dirty' : 'clean';
    const meta = r.ahead != null ? `↑${r.ahead} ↓${r.behind}` : '(no upstream)';
    return `<div class="repo-card ${r.dirty ? 'dirty' : ''}">
      <div class="repo-top">
        <span class="dot" style="background:${flagColor}"></span>
        <span class="repo-name">${esc(r.repo)}</span>
        <span class="repo-flag" style="color:${flagColor}">${esc(flagText)}</span>
      </div>
      <div class="repo-meta">${esc(r.branch)} ${esc(meta)}</div>
    </div>`;
  }).join('');
}

async function pollStatus() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    indoubtChipEl.textContent = `in-doubt: ${data.in_doubt}`;
    indoubtChipEl.className = 'chip ' + (data.in_doubt > 0 ? 'indoubt-some' : 'indoubt-zero');
    renderRepoList(data.repos || []);
  } catch (e) {
    indoubtChipEl.textContent = 'in-doubt: unreachable';
    indoubtChipEl.className = 'chip indoubt-some';
  }
}

function renderWatcherList(health) {
  const names = Object.keys(health.watchers || {});
  watcherTagEl.textContent = `${names.length + 2} tracked`;
  let rows = names.map(name => {
    const w = health.watchers[name];
    const ok = !!w.last_poll;
    return `<div class="watcher-row">
      <span class="dot" style="background:${ok ? 'var(--emerald)' : 'var(--faint)'}"></span>
      <span class="watcher-name">${esc(name)}</span>
      <span class="watcher-time">${ok ? esc(w.last_poll) : 'never polled'}</span>
    </div>`;
  }).join('');
  rows += `<div class="watcher-row">
    <span class="dot" style="background:${health.ollama_reachable ? 'var(--emerald)' : 'var(--red)'}"></span>
    <span class="watcher-name">ollama</span>
    <span class="watcher-time">${health.ollama_reachable ? 'reachable' : 'unreachable'}</span>
  </div>`;
  rows += `<div class="watcher-row">
    <span class="dot" style="background:${health.google_token_ok ? 'var(--emerald)' : 'var(--red)'}"></span>
    <span class="watcher-name">google token</span>
    <span class="watcher-time">${health.google_token_ok ? 'ok' : 'missing/invalid'}</span>
  </div>`;
  watcherListEl.innerHTML = rows;
}

async function pollHealth() {
  try {
    const resp = await fetch('/api/health');
    const data = await resp.json();
    renderWatcherList(data);
  } catch (e) {
    watcherListEl.innerHTML = '<div class="queue-empty">watcher health unreachable</div>';
  }
}

// ---------------------------------------------------------------- model router (static — fetched once)
async function loadRouting() {
  const routerListEl = document.getElementById('routerList');
  try {
    const resp = await fetch('/api/routing');
    const routes = await resp.json();
    routerListEl.innerHTML = routes.map(r => `
      <div class="route-row">
        <span class="route-from">${esc(r.task)}</span>
        <span class="route-arrow">→</span>
        <span class="route-to">${esc(r.model)}${r.tier === 'local' ? ' · local' : ''}</span>
        <span class="route-note">${esc(r.cost_note || '')}</span>
      </div>`).join('');
  } catch (e) {
    routerListEl.innerHTML = '<div class="queue-empty">router policy unreachable</div>';
  }
}

// ---------------------------------------------------------------- observability feed
const TYPE_COLORS = {
  signal: '#22d3ee', triage: '#94a3b8', utterance: '#38bdf8',
  llm_request: '#a78bfa', llm_response: '#a78bfa',
  tool_call: '#fbbf24', tool_result: '#34d399',
  rejected: '#fbbf24', error: '#f87171', briefing: '#94a3b8',
};

let lastEventId = 0;
const feedEl = document.getElementById('feed');
const autoScrollEl = document.getElementById('autoScroll');
const feedFilterEls = document.querySelectorAll('.feed-filter');

function feedCategory(type) {
  if (type === 'signal') return 'signal';
  if (type === 'triage') return 'triage';
  if (type === 'llm_request' || type === 'llm_response') return 'llm';
  if (type === 'tool_call' || type === 'tool_result') return 'tool';
  if (type === 'error' || type === 'rejected') return 'error';
  return null; // e.g. utterance, briefing — always shown, no filter applies
}

function activeFeedFilters() {
  const set = new Set();
  feedFilterEls.forEach(cb => { if (cb.checked) set.add(cb.value); });
  return set;
}

function summarizePayload(type, payload) {
  try {
    if (type === 'signal') return `${payload.source}: ${payload.title}`;
    if (type === 'triage') {
      if (payload.classification) return `${payload.classification} — ${payload.reason || ''}`;
      if (payload.rejected) return `rejected — ${payload.reason || ''}`;
      return JSON.stringify(payload);
    }
    if (type === 'tool_call') return `${payload.action_type} ${JSON.stringify(payload.args || {})}`;
    if (type === 'tool_result') return `${payload.action_type} → result`;
    if (type === 'utterance') return `"${payload.text}"`;
    if (type === 'llm_request') return `${payload.model || ''}: ${String(payload.utterance || '').slice(0, 60)}`;
    if (type === 'llm_response') return `tool=${payload.tool_name || 'none'}`;
    if (type === 'error') return `${payload.context || ''}: ${payload.message || ''}`;
    if (type === 'rejected') return payload.reason || JSON.stringify(payload);
    return JSON.stringify(payload);
  } catch (e) {
    return '(unrenderable payload)';
  }
}

function applyFeedFilters() {
  const filters = activeFeedFilters();
  feedEl.querySelectorAll('.feed-row').forEach(row => {
    const cat = row.dataset.cat;
    row.style.display = (!cat || filters.has(cat)) ? '' : 'none';
  });
}
feedFilterEls.forEach(cb => cb.addEventListener('change', applyFeedFilters));

function appendFeedRow(row) {
  let payload = {};
  try { payload = JSON.parse(row.payload_json); } catch (e) { payload = { raw: row.payload_json }; }

  // The web UI's own 60s /api/status cache-refresh runs report_status
  // through the chokepoint too — still logged (nothing is ever off-log),
  // just excluded from the hero feed by default so routine polling doesn't
  // drown out real activity.
  if (payload.actor === 'status-cache') return;

  const emptyEl = feedEl.querySelector('.feed-empty');
  if (emptyEl) emptyEl.remove();

  const cat = feedCategory(row.type);
  const div = document.createElement('div');
  div.className = 'feed-row';
  if (cat) div.dataset.cat = cat;
  const color = TYPE_COLORS[row.type] || '#8a97a8';
  div.innerHTML = `
    <div class="f-line">
      <span class="f-time">${esc(String(row.ts).slice(11, 19))}</span>
      <span class="f-type" style="color:${color};background:${color}22;">${esc(row.type)}</span>
      <span class="f-payload">${esc(summarizePayload(row.type, payload))}</span>
    </div>
    <div class="f-expand">${esc(JSON.stringify(payload, null, 2))}</div>
  `;
  div.addEventListener('click', () => div.classList.toggle('expanded'));

  const filters = activeFeedFilters();
  if (cat && !filters.has(cat)) div.style.display = 'none';

  feedEl.appendChild(div);
}

async function pollEvents() {
  try {
    const resp = await fetch(`/api/events?since=${lastEventId}`);
    const rows = await resp.json();
    if (rows.length === 0) return;
    for (const row of rows) {
      lastEventId = Math.max(lastEventId, row.id);
      appendFeedRow(row);
    }
    while (feedEl.children.length > 300) feedEl.removeChild(feedEl.firstChild);
    if (autoScrollEl.checked) feedEl.scrollTop = feedEl.scrollHeight;
  } catch (e) {
    const div = document.createElement('div');
    div.className = 'feed-row';
    div.innerHTML = '<div class="f-line"><span class="f-type" style="color:#f87171;">error</span><span class="f-payload">events feed unreachable</span></div>';
    feedEl.appendChild(div);
  }
}

// ---------------------------------------------------------------- action queue
const queueListEl = document.getElementById('queueList');
const queueTagEl = document.getElementById('queueTag');

function statusBadgeClass(status) {
  return { awaiting_confirm: 'amber', done: 'emerald', failed: 'red', rejected: 'slate', pending: 'amber' }[status] || 'slate';
}

function renderOriginBlock(origin) {
  if (!origin || origin.kind !== 'proactive') {
    return '<div class="origin-block user"><span class="o-label">user-initiated</span>requested directly by the operator</div>';
  }
  return `<div class="origin-block proactive"><span class="o-label">proactive proposal</span>` +
    `proposed by ${esc(origin.model || 'unknown model')} · from ${esc(origin.source || 'unknown source')}: ` +
    `${esc(origin.signal_title || '(no title)')} · reason: ${esc(origin.reason || '(no reason given)')}</div>`;
}

function renderAwaitingCard(a) {
  const token = a.idempotency_key.slice(0, 8);
  return `<div class="queue-card status-awaiting_confirm">
    <div class="q-top">
      <span class="q-title">${esc(a.action_type)} ${esc(a.args_json)}</span>
      <span class="badge badge-amber">awaiting confirm</span>
    </div>
    ${renderOriginBlock(a.origin)}
    <div class="q-meta">token: ${esc(token)}</div>
    <div class="q-actions">
      <button class="btn btn-confirm" onclick="resolveAction('${esc(token)}','confirm')">Confirm</button>
      <button class="btn btn-reject" onclick="resolveAction('${esc(token)}','reject')">Reject</button>
    </div>
  </div>`;
}

function renderRecentCard(a) {
  return `<div class="queue-card status-${esc(a.status)}">
    <div class="q-top">
      <span class="q-title">${esc(a.action_type)}</span>
      <span class="badge badge-${statusBadgeClass(a.status)}">${esc(a.status)}</span>
    </div>
    <div class="q-meta">${esc(a.created_at || '')}</div>
  </div>`;
}

async function pollActions() {
  try {
    const resp = await fetch('/api/actions');
    const actions = await resp.json();
    const awaiting = actions.filter(a => a.status === 'awaiting_confirm');
    const recent = actions.filter(a => a.status !== 'awaiting_confirm').slice(0, 15);

    queueTagEl.textContent = `${awaiting.length} awaiting`;

    let html = awaiting.length
      ? awaiting.map(renderAwaitingCard).join('')
      : '<div class="queue-empty">nothing awaiting confirmation</div>';

    if (recent.length) {
      html += '<div class="tag" style="margin:10px 2px 6px;">recent</div>' + recent.map(renderRecentCard).join('');
    }

    queueListEl.innerHTML = html;
  } catch (e) {
    queueTagEl.textContent = 'unreachable';
  }
}

async function resolveAction(token, verb) {
  try {
    await fetch(`/api/actions/${encodeURIComponent(token)}/${verb}`, { method: 'POST' });
  } catch (e) {
    // fall through — pollActions() reflects whatever state actually landed, never silent
  }
  pollActions();
}

// ---------------------------------------------------------------- chat
const chatThreadEl = document.getElementById('chatThread');
const chatInputEl = document.getElementById('chatInput');
const chatSendEl = document.getElementById('chatSend');

function appendUserBubble(text) {
  const emptyEl = chatThreadEl.querySelector('.chat-empty');
  if (emptyEl) emptyEl.remove();
  const row = document.createElement('div');
  row.className = 'bubble-row user';
  row.innerHTML = `<div class="bubble">${esc(text)}</div><div class="bubble-meta">${esc(new Date().toLocaleTimeString())}</div>`;
  chatThreadEl.appendChild(row);
  chatThreadEl.scrollTop = chatThreadEl.scrollHeight;
}

function renderInlineConfirmCard(token) {
  return `<div class="queue-card status-awaiting_confirm" style="margin-top:8px;">
    <div class="q-top"><span class="q-title">awaiting confirmation</span></div>
    <div class="q-meta">token: ${esc(token)}</div>
    <div class="q-actions">
      <button class="btn btn-confirm" data-inline-confirm="${esc(token)}">Confirm</button>
      <button class="btn btn-reject" data-inline-reject="${esc(token)}">Reject</button>
    </div>
  </div>`;
}

async function resolveInline(token, verb, row) {
  let statusText = 'request failed';
  try {
    const resp = await fetch(`/api/actions/${encodeURIComponent(token)}/${verb}`, { method: 'POST' });
    const data = await resp.json();
    statusText = `${data.status}: ${data.message}`;
  } catch (e) {
    statusText = 'request failed — network error';
  }
  const card = row.querySelector('.queue-card');
  if (card) card.outerHTML = `<div class="q-meta" style="margin-top:8px;">${esc(statusText)}</div>`;
  pollActions();
}

function wireInlineConfirmButtons(row) {
  const c = row.querySelector('[data-inline-confirm]');
  const r = row.querySelector('[data-inline-reject]');
  if (c) c.addEventListener('click', () => resolveInline(c.dataset.inlineConfirm, 'confirm', row));
  if (r) r.addEventListener('click', () => resolveInline(r.dataset.inlineReject, 'reject', row));
}

function appendAssistantBubble(data) {
  const row = document.createElement('div');
  row.className = 'bubble-row assistant';

  let inner = `<div class="bubble">${esc(data.reply_text || '')}</div><div class="bubble-meta">${esc(data.status || '')}</div>`;

  if (data.events && data.events.length) {
    const chips = data.events.map(e => `<span class="trace-chip">${esc(e.type)}</span>`).join('');
    inner += `<details class="turn-trace"><summary>under the hood · ${data.events.length} events</summary><div class="trace-chips">${chips}</div></details>`;
  }

  if (data.status === 'awaiting_confirm' && data.confirm_token) {
    inner += renderInlineConfirmCard(data.confirm_token);
  }

  row.innerHTML = inner;
  chatThreadEl.appendChild(row);
  wireInlineConfirmButtons(row);
  chatThreadEl.scrollTop = chatThreadEl.scrollHeight;
}

async function sendChatMessage() {
  const text = chatInputEl.value.trim();
  if (!text) return;
  chatInputEl.value = '';
  chatSendEl.disabled = true;
  appendUserBubble(text);
  try {
    const resp = await fetch('/api/turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await resp.json();
    appendAssistantBubble(data);
  } catch (e) {
    appendAssistantBubble({ reply_text: 'request failed — ' + (e.message || 'network error'), status: 'failed', events: [] });
  } finally {
    chatSendEl.disabled = false;
    chatInputEl.focus();
  }
}

chatSendEl.addEventListener('click', sendChatMessage);
chatInputEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChatMessage(); });

// ---------------------------------------------------------------- memory graph
const KIND_COLORS = {
  person: '#f472b6', project: '#38bdf8', preference: '#a78bfa',
  event: '#fbbf24', thing: '#34d399', place: '#22d3ee',
};
const MEMORY_PURPOSES = ['people', 'projects', 'finance', 'baby', 'relationships', 'home', 'news', 'interests', 'purchase'];

let memoryData = { nodes: [], edges: [], observations: [] };
let memoryActivePurpose = null; // null = all
let memorySelectedNodeId = null;

const memorySearchEl = document.getElementById('memorySearch');
const memoryGraphSvgEl = document.getElementById('memoryGraphSvg');
const memoryEmptyEl = document.getElementById('memoryEmpty');
const memoryNodeBodyEl = document.getElementById('memoryNodeBody');
const memoryRecentBodyEl = document.getElementById('memoryRecentBody');

// Hand-rolled force layout — no build step, no external libs, and this is a
// personal graph (dozens of nodes, not thousands), so a few hundred
// synchronous iterations of repulsion + spring-per-edge is plenty.
function layoutGraph(nodes, edges, width, height) {
  const positioned = nodes.map((n, i) => {
    const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
    const radius = Math.min(width, height) * 0.32;
    return {
      ...n,
      x: width / 2 + Math.cos(angle) * radius + (Math.random() - 0.5) * 12,
      y: height / 2 + Math.sin(angle) * radius + (Math.random() - 0.5) * 12,
      vx: 0, vy: 0,
    };
  });
  const byId = new Map(positioned.map(n => [n.node_id, n]));
  const REPULSION = 2200, SPRING_LENGTH = 110, SPRING_STRENGTH = 0.02, CENTER_PULL = 0.01, DAMPING = 0.85;

  for (let iter = 0; iter < 220; iter++) {
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        const a = positioned[i], b = positioned[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const distSq = Math.max(dx * dx + dy * dy, 0.01);
        const dist = Math.sqrt(distSq);
        const force = REPULSION / distSq;
        const fx = (dx / dist) * force, fy = (dy / dist) * force;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }
    }
    for (const e of edges) {
      const a = byId.get(e.src_node), b = byId.get(e.dst_node);
      if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
      const diff = dist - SPRING_LENGTH;
      const fx = (dx / dist) * diff * SPRING_STRENGTH, fy = (dy / dist) * diff * SPRING_STRENGTH;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }
    for (const n of positioned) {
      n.vx += (width / 2 - n.x) * CENTER_PULL;
      n.vy += (height / 2 - n.y) * CENTER_PULL;
      n.x += n.vx * 0.15;
      n.y += n.vy * 0.15;
      n.vx *= DAMPING; n.vy *= DAMPING;
      n.x = Math.max(30, Math.min(width - 30, n.x));
      n.y = Math.max(30, Math.min(height - 30, n.y));
    }
  }
  return positioned;
}

function renderMemoryGraph() {
  const nodes = memoryData.nodes || [];
  const edges = memoryData.edges || [];

  if (!nodes.length) {
    memoryGraphSvgEl.innerHTML = '';
    memoryEmptyEl.style.display = 'flex';
    return;
  }
  memoryEmptyEl.style.display = 'none';

  const rect = memoryGraphSvgEl.getBoundingClientRect();
  const width = rect.width || 600, height = rect.height || 400;
  memoryGraphSvgEl.setAttribute('viewBox', `0 0 ${width} ${height}`);

  const positioned = layoutGraph(nodes, edges, width, height);
  const byId = new Map(positioned.map(n => [n.node_id, n]));

  let svg = '';
  for (const e of edges) {
    const a = byId.get(e.src_node), b = byId.get(e.dst_node);
    if (!a || !b) continue;
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    svg += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#1e2430" stroke-width="1.5" />`;
    svg += `<text x="${mx}" y="${my}" class="mg-edge-label" text-anchor="middle">${esc(e.rel)}</text>`;
  }
  for (const n of positioned) {
    const color = KIND_COLORS[n.kind] || '#8a97a8';
    const selected = n.node_id === memorySelectedNodeId;
    svg += `<g class="mg-node" data-node-id="${esc(n.node_id)}" transform="translate(${n.x},${n.y})">
      <circle r="${selected ? 16 : 13}" fill="${color}22" stroke="${color}" stroke-width="${selected ? 2.5 : 1.5}" />
      <text class="mg-node-label" text-anchor="middle" dy="26">${esc(n.label)}</text>
    </g>`;
  }
  memoryGraphSvgEl.innerHTML = svg;
  memoryGraphSvgEl.querySelectorAll('.mg-node').forEach(g => {
    g.addEventListener('click', () => selectMemoryNode(g.dataset.nodeId));
  });
}

function formatProvenanceChip(o) {
  const d = new Date(o.observed_at);
  const label = o.source === 'user_said' ? 'you said' : o.source;
  const dateStr = isNaN(d) ? '' : `${d.getMonth() + 1}/${d.getDate()}`;
  return dateStr ? `${label} ${dateStr}` : label;
}

function selectMemoryNode(nodeId) {
  memorySelectedNodeId = nodeId;
  const node = (memoryData.nodes || []).find(n => n.node_id === nodeId);
  if (!node) return;

  const obs = (memoryData.observations || []).filter(o => o.node_id === nodeId);
  const factsHtml = obs.length
    ? obs.map(o => `<div class="mem-obs">
        <div class="mem-obs-fact">${esc(o.fact)}</div>
        <span class="prov-chip">${esc(formatProvenanceChip(o))}</span>
      </div>`).join('')
    : '<div class="queue-empty">no observations recorded yet</div>';

  memoryNodeBodyEl.innerHTML = `
    <div class="mem-node-head">
      <span class="dot" style="background:${KIND_COLORS[node.kind] || '#8a97a8'}"></span>
      <span class="mem-node-label">${esc(node.label)}</span>
      <span class="badge badge-slate">${esc(node.kind)}</span>
    </div>
    <div class="mem-node-scope">scope: ${esc(node.purpose_scope)}</div>
    ${factsHtml}
    <button class="btn btn-reject" style="margin-top:10px;width:100%;" onclick="undoMemoryNode('${esc(node.node_id)}')">Delete this node</button>
  `;
  renderMemoryGraph(); // re-render so the selected node's ring updates
}

function renderMemoryPurposePills() {
  const el = document.getElementById('memoryPurposePills');
  const pills = [{ value: '', label: 'all' }, ...MEMORY_PURPOSES.map(p => ({ value: p, label: p }))];
  el.innerHTML = pills.map(p => `<button class="mem-pill ${(!p.value && !memoryActivePurpose) || p.value === memoryActivePurpose ? 'active' : ''}" data-purpose="${esc(p.value)}">${esc(p.label)}</button>`).join('');
  el.querySelectorAll('.mem-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      memoryActivePurpose = btn.dataset.purpose || null;
      renderMemoryPurposePills();
      loadMemory();
    });
  });
}

let memorySearchTimer = null;
memorySearchEl.addEventListener('input', () => {
  clearTimeout(memorySearchTimer);
  memorySearchTimer = setTimeout(loadMemory, 250);
});

async function loadMemory() {
  const params = new URLSearchParams();
  const label = memorySearchEl.value.trim();
  if (label) params.set('label', label);
  if (memoryActivePurpose) params.set('purpose_scope', memoryActivePurpose);

  try {
    const resp = await fetch(`/api/memory?${params.toString()}`);
    const data = await resp.json();
    memoryData = data.nodes ? data : { nodes: [], edges: [], observations: [] };
    renderMemoryGraph();
  } catch (e) {
    memoryData = { nodes: [], edges: [], observations: [] };
    memoryEmptyEl.textContent = 'memory graph unreachable';
    memoryEmptyEl.style.display = 'flex';
  }
}

function memoryWriteOp(row) {
  try { return JSON.parse(row.args_json).op; } catch (e) { return null; }
}

function formatMemoryWriteSummary(row) {
  let args = {}, result = {};
  try { args = JSON.parse(row.args_json); } catch (e) { /* leave empty */ }
  try { result = row.result_json ? JSON.parse(row.result_json) : {}; } catch (e) { /* leave empty */ }
  const op = args.op || '?';
  if (op === 'delete_node') return `deleted node ${result.label || args.node_id || ''}`;
  if (op === 'upsert_node') return `${result.created ? 'created' : 'updated'} ${args.kind || ''}: ${args.label || ''}`;
  if (op === 'add_observation') return `observed on ${args.label || result.node_id || ''}: ${args.fact || ''}`;
  if (op === 'add_edge') return `linked ${args.src_node || ''} —${args.rel || ''}→ ${args.dst_node || ''}`;
  return op;
}

function renderMemoryWriteRow(row) {
  let result = {};
  try { result = row.result_json ? JSON.parse(row.result_json) : {}; } catch (e) { /* leave empty */ }
  const op = memoryWriteOp(row);
  const canUndo = row.status === 'done' && result.node_id && (op === 'upsert_node' || op === 'add_observation');
  return `<div class="queue-card status-${esc(row.status)}">
    <div class="q-top">
      <span class="q-title">${esc(formatMemoryWriteSummary(row))}</span>
      <span class="badge badge-${statusBadgeClass(row.status)}">${esc(row.status)}</span>
    </div>
    <div class="q-meta">${esc(row.created_at || '')}</div>
    ${canUndo ? `<div class="q-actions"><button class="btn btn-reject" onclick="undoMemoryNode('${esc(result.node_id)}')">Undo</button></div>` : ''}
  </div>`;
}

async function pollMemoryRecent() {
  try {
    const resp = await fetch('/api/memory/writes');
    const rows = await resp.json();
    memoryRecentBodyEl.innerHTML = rows.length ? rows.map(renderMemoryWriteRow).join('') : '<div class="queue-empty">no memory writes yet</div>';
  } catch (e) {
    memoryRecentBodyEl.innerHTML = '<div class="queue-empty">memory writes unreachable</div>';
  }
}

async function undoMemoryNode(nodeId) {
  try {
    await fetch(`/api/memory/undo/${encodeURIComponent(nodeId)}`, { method: 'POST' });
  } catch (e) {
    // fall through — loadMemory()/pollMemoryRecent() reflect whatever state actually landed
  }
  if (memorySelectedNodeId === nodeId) {
    memorySelectedNodeId = null;
    memoryNodeBodyEl.innerHTML = '<div class="queue-empty">click a node to see its observations</div>';
  }
  loadMemory();
  pollMemoryRecent();
}

// ---------------------------------------------------------------- polling loops
function fastTick() {
  pollEvents();
  pollActions();
}
function slowTick() {
  pollStatus();
  pollHealth();
  pollSpend();
  pollMemoryRecent();
}

renderPurposeRail();
renderMemoryPurposePills();
loadRouting();
fastTick();
slowTick();
setInterval(fastTick, 2000);
setInterval(slowTick, 10000);
