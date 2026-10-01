/* 채팅방: SSE 실시간 수신, 읽음 수 갱신, 메시지/파일 전송, @멘션 자동완성. */
(() => {
  'use strict';
  const dataEl = document.getElementById('chat-data');
  if (!dataEl) return;
  const data = JSON.parse(dataEl.textContent);
  const roomId = data.room_id;
  const me = data.me;
  const maxBytes = data.max_upload_mb * 1024 * 1024;
  let members = data.members;   // [{id, name}]
  let readers = data.readers;   // {userId: 마지막으로 읽은 메시지 id}

  const list = document.getElementById('messages');
  const form = document.getElementById('composer');
  const input = document.getElementById('chat-input');
  const fileInput = document.getElementById('chat-file');
  const fileChip = document.getElementById('file-chip');
  const box = document.getElementById('mention-box');
  const live = document.getElementById('live-status');
  const toast = (msg, type) => (window.GB ? window.GB.toast(msg, type) : alert(msg));
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const nearBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight < 150;
  const scrollBottom = () => { list.scrollTop = list.scrollHeight; };
  const lastId = () => {
    const items = list.querySelectorAll('.msg[data-id]');
    return items.length ? Number(items[items.length - 1].dataset.id) : 0;
  };

  // ---------- 읽음 수 ----------
  function updateReads() {
    list.querySelectorAll('.msg[data-user]').forEach((li) => {
      const id = Number(li.dataset.id);
      const sender = li.dataset.user ? Number(li.dataset.user) : null;
      let n = 0;
      Object.entries(readers).forEach(([uid, last]) => { if (Number(uid) !== sender && last >= id) n += 1; });
      const el = li.querySelector('.reads');
      if (el) el.textContent = n > 0 ? `${n}명 읽음` : '';
    });
  }

  let readTimer = null;
  function markRead() {
    if (document.hidden) return;
    clearTimeout(readTimer);
    readTimer = setTimeout(() => {
      fetch(`/chat/${roomId}/read`, { method: 'POST', headers: { 'X-Requested-With': 'fetch' } }).catch(() => {});
    }, 250);
  }
  document.addEventListener('visibilitychange', markRead);

  // ---------- 메시지 추가 ----------
  function addMessage(html, id) {
    if (document.getElementById(`msg-${id}`)) return null; // SSE와 전송 응답 중복 방지
    const stick = nearBottom();
    const tpl = document.createElement('template');
    tpl.innerHTML = html.trim();
    const li = tpl.content.firstElementChild;
    if (li.dataset.user && Number(li.dataset.user) === me) li.classList.add('mine');
    const empty = document.getElementById('no-msg');
    if (empty) empty.remove();
    list.appendChild(li);
    updateReads();
    if (stick || Number(li.dataset.user) === me) scrollBottom();
    return li;
  }

  async function fetchMissed() {
    try {
      const res = await fetch(`/chat/${roomId}/messages?after=${lastId()}`, { headers: { Accept: 'application/json' } });
      if (!res.ok) return;
      const d = await res.json();
      d.items.forEach((item) => addMessage(item.html, item.id));
      if (d.items.length) markRead();
    } catch (_) { /* 다음 재연결 때 다시 시도 */ }
  }

  async function refreshMembers() {
    try {
      const res = await fetch(`/chat/${roomId}/members`, { headers: { Accept: 'application/json' } });
      if (res.status === 403 || res.status === 404) { location.href = '/chat'; return; }
      if (!res.ok) return;
      const d = await res.json();
      document.getElementById('member-panel').innerHTML = d.html;
      members = d.members;
      readers = d.readers;
      updateReads();
    } catch (_) { /* 무시 */ }
  }

  // ---------- 실시간(SSE) ----------
  if (window.EventSource) {
    let connectedOnce = false;
    const es = new EventSource(`/chat/${roomId}/events`);
    es.addEventListener('ready', () => {
      live.classList.add('on');
      live.title = '실시간 연결됨';
      if (connectedOnce) fetchMissed(); // 재연결: 끊긴 동안 온 메시지 보충
      connectedOnce = true;
    });
    es.addEventListener('message', (e) => {
      const d = JSON.parse(e.data);
      addMessage(d.html, d.id);
      if (d.user_id !== me) markRead();
    });
    es.addEventListener('read', (e) => {
      const d = JSON.parse(e.data);
      readers[String(d.user_id)] = d.last_read;
      updateReads();
    });
    es.addEventListener('members', () => refreshMembers());
    es.onerror = () => { live.classList.remove('on'); live.title = '재연결 중...'; };
    window.addEventListener('beforeunload', () => es.close());
  }

  // ---------- 전송 ----------
  fileInput.addEventListener('change', () => {
    const f = fileInput.files[0];
    if (!f) { fileChip.hidden = true; return; }
    if (f.size > maxBytes) {
      toast(`파일은 최대 ${data.max_upload_mb}MB까지 올릴 수 있습니다.`);
      fileInput.value = '';
      fileChip.hidden = true;
      return;
    }
    fileChip.textContent = `📎 ${f.name} (${(f.size / 1024 / 1024).toFixed(2)}MB) — 전송 시 함께 올라갑니다`;
    fileChip.hidden = false;
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const hasFile = fileInput.files.length > 0;
    if (!input.value.trim() && !hasFile) return;
    if (form.dataset.busy) return;
    form.dataset.busy = '1';
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const res = await fetch(form.getAttribute('action'), {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' },
      });
      let d = {};
      try { d = await res.json(); } catch (_) { /* 무시 */ }
      if (!res.ok || !d.ok) { toast(d.error || `전송하지 못했습니다. (${res.status})`); return; }
      input.value = '';
      input.style.height = '';
      fileInput.value = '';
      fileChip.hidden = true;
      addMessage(d.html, d.id);
      scrollBottom();
    } catch (_) {
      toast('네트워크 오류로 전송하지 못했습니다.');
    } finally {
      delete form.dataset.busy;
      button.disabled = false;
      input.focus();
    }
  });

  // ---------- @멘션 자동완성 ----------
  let suggestions = [];
  let active = 0;
  let mentionStart = -1;

  function closeBox() { box.hidden = true; suggestions = []; }

  function renderBox() {
    box.innerHTML = suggestions
      .map((m, i) => `<button type="button" class="${i === active ? 'active' : ''}" data-i="${i}">@${esc(m.name)}</button>`)
      .join('');
    box.hidden = false;
  }

  function updateBox() {
    const pos = input.selectionStart;
    const match = input.value.slice(0, pos).match(/(^|\s)@([^\s@]{0,20})$/);
    if (!match) { closeBox(); return; }
    const q = match[2].toLowerCase();
    suggestions = members
      .filter((m) => m.id !== me && m.name.toLowerCase().includes(q))
      .sort((a, b) => a.name.toLowerCase().indexOf(q) - b.name.toLowerCase().indexOf(q))
      .slice(0, 8);
    if (!suggestions.length) { closeBox(); return; }
    mentionStart = pos - match[2].length - 1;
    active = 0;
    renderBox();
  }

  function pick(i) {
    const m = suggestions[i];
    if (!m) return;
    const pos = input.selectionStart;
    input.value = `${input.value.slice(0, mentionStart)}@${m.name} ${input.value.slice(pos)}`;
    const caret = mentionStart + m.name.length + 2;
    input.setSelectionRange(caret, caret);
    closeBox();
    input.focus();
  }

  input.addEventListener('input', updateBox);
  input.addEventListener('click', updateBox);
  input.addEventListener('blur', () => setTimeout(closeBox, 150));
  box.addEventListener('mousedown', (e) => {
    const btn = e.target.closest('button[data-i]');
    if (!btn) return;
    e.preventDefault();
    pick(Number(btn.dataset.i));
  });

  input.addEventListener('keydown', (e) => {
    if (!box.hidden && suggestions.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        active = (active + (e.key === 'ArrowDown' ? 1 : suggestions.length - 1)) % suggestions.length;
        renderBox();
        return;
      }
      if ((e.key === 'Enter' || e.key === 'Tab') && !e.isComposing) {
        e.preventDefault();
        pick(active);
        return;
      }
      if (e.key === 'Escape') { closeBox(); return; }
    }
    // Enter 전송 / Shift+Enter 줄바꿈 (한글 조합 중 Enter는 무시)
    if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // ---------- 초기화 ----------
  list.querySelectorAll('.msg[data-user]').forEach((li) => {
    if (Number(li.dataset.user) === me) li.classList.add('mine');
  });
  updateReads();
  if (!location.hash.startsWith('#msg-') && !new URLSearchParams(location.search).has('highlight')) scrollBottom();
})();
