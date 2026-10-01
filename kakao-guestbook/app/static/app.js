/* 공통 스크립트: AJAX 폼 처리(스크롤 위치 유지), 강조 이동, 댓글 접기/펴기, 글쓰기 버튼.
   JS가 꺼져 있으면 폼은 일반 POST로 제출되고 서버가 리다이렉트로 응답합니다. */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function toast(message, type = 'error') {
    const el = $('#toast');
    if (!el) { alert(message); return; }
    el.textContent = message;
    el.className = `toast show ${type}`;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { el.className = 'toast'; }, 2600);
  }

  function openAncestors(el) {
    let d = el.closest('details');
    while (d) {
      d.open = true;
      d = d.parentElement ? d.parentElement.closest('details') : null;
    }
  }

  function highlight(id, scroll = true) {
    const el = document.getElementById(id);
    if (!el) return false;
    openAncestors(el);
    if (scroll) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.remove('highlight');
    void el.offsetWidth; // 애니메이션 재시작
    el.classList.add('highlight');
    return true;
  }

  function htmlToElement(html) {
    const tpl = document.createElement('template');
    tpl.innerHTML = html.trim();
    return tpl.content.firstElementChild;
  }

  /* 요소를 새 HTML로 교체할 때 열린 접기 상태와 작성 중인 글을 보존합니다. */
  function captureState(root, submittedForm) {
    const open = {};
    $$('details[data-key]', root).forEach((d) => { open[d.dataset.key] = d.open; });
    if (submittedForm) {
      const wrapper = submittedForm.closest('details.inline-form[data-key]');
      if (wrapper) open[wrapper.dataset.key] = false; // 수정/답글 폼은 제출 후 닫기
    }
    const drafts = {};
    $$('textarea[data-key]', root).forEach((t) => {
      if (submittedForm && submittedForm.contains(t)) return;
      if (t.value.trim()) drafts[t.dataset.key] = t.value;
    });
    return { open, drafts };
  }

  function restoreState(root, state) {
    $$('details[data-key]', root).forEach((d) => {
      if (d.dataset.key in state.open) d.open = state.open[d.dataset.key];
    });
    $$('textarea[data-key]', root).forEach((t) => {
      if (state.drafts[t.dataset.key]) t.value = state.drafts[t.dataset.key];
    });
  }

  function replaceElement(id, html, submittedForm) {
    const old = document.getElementById(id);
    if (!old) return null;
    const fresh = htmlToElement(html);
    const state = captureState(old, submittedForm);
    old.replaceWith(fresh);
    restoreState(fresh, state);
    return fresh;
  }

  function applyResult(form, data) {
    if (data.redirect) { location.href = data.redirect; return; }
    if (data.reload) { location.reload(); return; }

    if (data.removed) {
      const el = document.getElementById(data.removed);
      if (el) {
        el.classList.add('fade-out');
        setTimeout(() => el.remove(), 250);
      }
    }

    if (data.html && data.post_id) {
      const id = `post-${data.post_id}`;
      if (!replaceElement(id, data.html, form)) {
        // 새 글: 1페이지를 보고 있으면 맨 위에 끼워 넣고, 아니면 1페이지로 이동
        const list = $('#post-list');
        if (list && list.dataset.page === '1') {
          list.prepend(htmlToElement(data.html));
          const empty = $('#empty-msg');
          if (empty) empty.remove();
        } else if (data.url) {
          location.href = data.url;
          return;
        }
      }
    }

    if (data.total !== undefined && $('#post-total')) $('#post-total').textContent = data.total;

    // 범용 부분 교체: [{id, html}, ...]
    (data.replace || []).forEach((r) => replaceElement(r.id, r.html, form));

    if (form.hasAttribute('data-reset') && document.body.contains(form)) form.reset();
    // 스크롤 위치 유지: AJAX 결과는 스크롤 이동 없이 강조만 합니다.
    if (data.focus) highlight(data.focus, false);
    if (data.message) toast(data.message, 'success');
    document.dispatchEvent(new CustomEvent('gb:updated', { detail: data }));
  }

  async function submitAjax(form) {
    if (form.dataset.busy) return;
    form.dataset.busy = '1';
    const buttons = $$('button', form);
    buttons.forEach((b) => { b.disabled = true; });
    try {
      const res = await fetch(form.getAttribute('action'), {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' },
        credentials: 'same-origin',
      });
      let data = {};
      try { data = await res.json(); } catch (_) { /* JSON이 아닌 응답 */ }
      if (res.status === 401 && data.login) { location.href = data.login; return; }
      if (!res.ok || !data.ok) {
        toast(data.error || `요청을 처리하지 못했습니다. (${res.status})`);
        return;
      }
      applyResult(form, data);
    } catch (err) {
      toast('네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      delete form.dataset.busy;
      buttons.forEach((b) => { b.disabled = false; });
    }
  }

  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.confirm && !confirm(form.dataset.confirm)) {
      e.preventDefault();
      return;
    }
    if (!form.hasAttribute('data-ajax')) return;
    e.preventDefault();
    submitAjax(form);
  });

  // Ctrl/Cmd + Enter로 제출, 입력에 맞춰 높이 자동 조절
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && e.target.matches('textarea')) {
      const form = e.target.form;
      if (form) { e.preventDefault(); form.requestSubmit(); }
    }
  });
  document.addEventListener('input', (e) => {
    const t = e.target;
    if (t.matches && t.matches('textarea')) {
      t.style.height = 'auto';
      t.style.height = `${Math.min(t.scrollHeight + 2, 400)}px`;
    }
  });

  // 댓글 전체 접기·펴기
  const toggleAll = $('#toggle-all-comments');
  if (toggleAll) {
    toggleAll.hidden = false;
    toggleAll.addEventListener('click', () => {
      const anyOpen = $$('#post-list details.comments').some((d) => d.open);
      const open = !anyOpen;
      $$('#post-list details.comments, #post-list details.replies').forEach((d) => { d.open = open; });
      toggleAll.textContent = open ? '댓글 모두 접기' : '댓글 모두 펴기';
    });
  }

  // 글쓰기 플로팅 버튼: 맨 위로 + 입력창 포커스
  const fab = $('#fab-write');
  if (fab) {
    fab.addEventListener('click', (e) => {
      const input = $('#post-content');
      if (!input) return; // 비로그인: 로그인 페이지로 이동
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      setTimeout(() => input.focus({ preventScroll: true }), 350);
    });
  }

  // ?highlight=대상id 또는 #대상id 로 들어오면 해당 요소를 펼치고 강조
  const params = new URLSearchParams(location.search);
  const target = params.get('highlight');
  const hashTarget = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
  if (target) {
    requestAnimationFrame(() => highlight(target, true));
  } else if (hashTarget) {
    openAncestors(hashTarget); // 접힌 댓글 안의 앵커도 보이도록
    requestAnimationFrame(() => hashTarget.scrollIntoView({ block: 'center' }));
  }
  if (params.has('highlight')) {
    params.delete('highlight');
    const qs = params.toString();
    history.replaceState(null, '', location.pathname + (qs ? `?${qs}` : '') + location.hash);
  }

  // 안 읽은 알림 배지 주기적 갱신(탭이 보일 때만)
  const badge = $('#notif-badge');
  function setBadge(count) {
    if (!badge) return;
    badge.textContent = count > 99 ? '99+' : String(count);
    badge.hidden = count <= 0;
  }
  async function refreshBadge() {
    if (!badge || document.hidden) return;
    try {
      const res = await fetch('/notifications/unread-count', { headers: { Accept: 'application/json' } });
      if (res.ok) setBadge((await res.json()).count);
    } catch (_) { /* 무시 */ }
  }
  if (badge) {
    setInterval(refreshBadge, 30000);
    document.addEventListener('visibilitychange', refreshBadge);
  }

  window.GB = { toast, highlight, replaceElement, applyResult, setBadge, refreshBadge };
})();
