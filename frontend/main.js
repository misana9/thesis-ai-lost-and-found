/* ─────────────────────────────────────────────
   FindIt — app.js
   All view logic, state, and API calls.
   No inline event handlers — everything is
   wired via addEventListener after DOM ready.
───────────────────────────────────────────── */

const API_BASE = 'http://localhost:8000';

const CATEGORIES = [
  { name: 'Backpack / Bag',  emoji: '🎒' },
  { name: 'Electronics',     emoji: '📱' },
  { name: 'Wallet / Purse',  emoji: '👛' },
  { name: 'Keys',            emoji: '🔑' },
  { name: 'Umbrella',        emoji: '☂️' },
  { name: 'Glasses',         emoji: '👓' },
  { name: 'Water Bottle',    emoji: '💧' },
  { name: 'Clothing',        emoji: '👕' },
  { name: 'Other',           emoji: '📦' },
];

/* ── STATE ── */
let currentFlow = 'lost';

const state = {
  lost: {
    step: 'photo',
    imageFile: null,
    imagePreview: null,
    category: null,
    predictionScores: null,
    predictionLoading: false,
    description: '',
    location: '',
    dateLost: '',
    email: '',
  },
  found: {
    step: 'photo',
    imageFile: null,
    imagePreview: null,
    category: null,
    predictionScores: null,
    predictionLoading: false,
    description: '',
    location: '',
    dateFound: '',
    email: '',
    successMessage: null,
  },
  match: {
    response: null,
    lostForm: null,
    lostItemId: null,
    expandAll: false,
    selectedIndex: 0,
    claimMessage: null,
  },
  register: {
    successEmail: null,
    verifyUrl: null,
  },
};

/* ── AUTH ──
   Token lives in localStorage for prototype convenience.
   Known limitation: XSS can steal a localStorage JWT; prefer httpOnly cookies in production.
*/
const auth = {
  token: null,
  user: null,
  verified: false,
};

const TOKEN_KEY = 'findit_token';
const PROTECTED_VIEWS = ['landing', 'lost', 'found', 'match', 'admin'];

const loginAttempts = {
  count: 0,
  lockedUntil: null,
};

let lockoutTimer = null;

function decodeJWT(token) {
  try {
    const payload = token.split('.')[1];
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  return headers;
}

function accountEmail() {
  return (auth.user?.email || '').trim().toLowerCase();
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((value || '').trim());
}

function saveToken(token) {
  auth.token = token;
  auth.user = decodeJWT(token);
  auth.verified = auth.user?.email_verified ?? false;
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  auth.token = null;
  auth.user = null;
  auth.verified = false;
  localStorage.removeItem(TOKEN_KEY);
}

function loadToken() {
  const saved = localStorage.getItem(TOKEN_KEY);
  if (!saved) return;
  try {
    const payload = decodeJWT(saved);
    if (!payload) {
      localStorage.removeItem(TOKEN_KEY);
      return;
    }
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      localStorage.removeItem(TOKEN_KEY);
      return;
    }
    auth.token = saved;
    auth.user = payload;
    auth.verified = payload.email_verified ?? false;
  } catch {
    localStorage.removeItem(TOKEN_KEY);
  }
}

function renderNav() {
  const isAuthed = !!auth.token;
  const firstName = auth.user?.name?.split(' ')[0]
    || auth.user?.full_name?.split(' ')[0]
    || auth.user?.email?.split('@')[0]
    || '';

  document.querySelectorAll('.nav-right').forEach(navRight => {
    if (isAuthed) {
      navRight.innerHTML = `
        <span class="nav-user-name">${firstName}</span>
        <button type="button" class="nav-btn btn-signout">Sign out</button>
      `;
      navRight.querySelector('.btn-signout')?.addEventListener('click', () => {
        clearToken();
        renderNav();
        showView('login');
      });
    } else {
      navRight.innerHTML = `<button type="button" class="nav-btn btn-nav-signin">Sign in</button>`;
      navRight.querySelector('.btn-nav-signin')?.addEventListener('click', () => showView('login'));
    }
  });
}

function showView(name) {
  renderNav();

  if (PROTECTED_VIEWS.includes(name) && !auth.token) {
    renderLogin();
    name = 'login';
  }

  if (name === 'login') renderLogin();
  if (name === 'register') renderRegister();

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const ids = {
    landing: 'view-landing',
    lost: 'view-lost',
    found: 'view-found',
    match: 'view-match',
    admin: 'view-admin',
    login: 'view-login',
    register: 'view-register',
  };
  const el = document.getElementById(ids[name]);
  if (!el) return;
  el.classList.remove('active');
  void el.offsetWidth;
  el.classList.add('active');
  window.scrollTo(0, 0);
}

/* ── HELPERS ── */
function getCategoryEmoji(name) {
  const cat = CATEGORIES.find(c => c.name === name);
  return cat ? cat.emoji : '📦';
}

function backpackArtHTML() {
  return `<div class="backpack-art">
    <div class="bp-top"></div>
    <div class="bp-strap-l"></div>
    <div class="bp-strap-r"></div>
    <div class="bp-body"></div>
    <div class="bp-pocket"></div>
    <div class="bp-zipper"></div>
    <div class="bp-zipper-pull"></div>
    <div class="bp-pocket-zipper"></div>
  </div>`;
}

function stepsHTML(steps, current) {
  return `<div class="steps-indicator">
    ${steps.map((label, i) => {
      const cls   = i < current ? 'done' : i === current ? 'active' : '';
      const num   = i < current ? '✓' : i + 1;
      const line  = i < steps.length - 1 ? '<div class="step-line"></div>' : '';
      return `<div class="step-ind ${cls}">
        <div class="step-num">${num}</div>${label}
      </div>${line}`;
    }).join('')}
  </div>`;
}

function categoryPillsHTML(selected, scores) {
  const list = scores
    ? [...CATEGORIES].sort((a, b) => (scores[b.name] || 0) - (scores[a.name] || 0))
    : CATEGORIES;
  return list.map(c => {
    const sel   = c.name === selected ? 'selected' : '';
    const check = c.name === selected ? '✓' : '';
    return `<button type="button" class="category-pill ${sel}" data-cat="${c.name}">
      <span class="pill-emoji">${c.emoji}</span>
      <span>${c.name}</span>
      <span class="pill-check">${check}</span>
    </button>`;
  }).join('');
}

function fixButtonTypes() {
  document.querySelectorAll('button:not([type])').forEach(b => {
    b.type = 'button';
  });
}

/* Delegate category pill clicks inside a container */
function bindCategoryPills(container) {
  container.querySelectorAll('.category-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.cat;
      state[currentFlow].category = name;
      container.querySelectorAll('.category-pill').forEach(p => {
        const isSel = p.dataset.cat === name;
        p.classList.toggle('selected', isSel);
        p.querySelector('.pill-check').textContent = isSel ? '✓' : '';
      });
      // enable continue button if present
      const continueBtn = container.querySelector('#btn-category-continue');
      if (continueBtn) continueBtn.disabled = false;
    });
  });
}

/* ─────────────────────── LOST FLOW ─────────────────────── */

function startLostFlow() {
  currentFlow = 'lost';
  Object.assign(state.lost, {
    step: 'photo', imageFile: null, imagePreview: null,
    category: null, predictionScores: null, predictionLoading: false,
    description: '', location: '', dateLost: '', email: accountEmail(),
  });
  renderLostStep();
  showView('lost');
}

function renderLostStep() {
  fixButtonTypes();
  const s   = state.lost;
  const el  = document.getElementById('lost-flow-container');
  el.innerHTML = buildLostHTML(s);
  bindLostEvents(s);
}

function buildLostHTML(s) {
  if (s.step === 'photo') {
    return `
      <button class="back-link" id="lost-back-landing">← Back</button>
      <div class="flow-header">
        <div class="flow-eyebrow">Lost something?</div>
        <div class="flow-title">Report a <span>lost item</span></div>
        <p class="flow-subtitle">Upload a photo and we'll search every found item on campus for a match.</p>
      </div>
      ${stepsHTML(['Photo', 'Details', 'Submit'], 0)}
      <div class="upload-zone" id="lost-upload-zone">
        <input type="file" id="lost-file-input" accept="image/*"/>
        <div class="upload-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
        </div>
        <div class="upload-label">Upload a photo of your item</div>
        <div class="upload-sub">optional but improves match accuracy</div>
      </div>
      ${s.imagePreview
        ? `<div class="preview-card">
             <div class="preview-img-wrap">
               <img src="${s.imagePreview}" alt="Preview"/>
               <div class="img-badge">Photo uploaded</div>
             </div>
           </div>`
        : `<button class="skip-link" id="lost-skip-photo">Skip photo — select category manually</button>`
      }`;
  }

  if (s.step === 'category') {
    return `
      <button class="back-link" id="lost-back-photo">← Back</button>
      <div class="flow-header">
        <div class="flow-eyebrow">Lost something?</div>
        <div class="flow-title">What did you <span>lose?</span></div>
      </div>
      ${stepsHTML(['Photo', 'Details', 'Submit'], 0)}
      <div id="lost-category-content">
        ${s.predictionLoading
          ? `<div class="category-loading">
               <div class="spinner"></div>
               <div class="category-loading-text">Analysing your item…</div>
             </div>`
          : `<div class="category-card">
               <div class="category-card-title">🧠 AI predicted category</div>
               <div class="category-pills">${categoryPillsHTML(s.category, s.predictionScores)}</div>
               <div class="category-hint">Tap to change if this looks wrong</div>
             </div>
             <button class="btn-primary" id="btn-category-continue" ${s.category ? '' : 'disabled'}>
               Looks right, continue →
             </button>`
        }
      </div>`;
  }

  if (s.step === 'details') {
    return `
      <button class="back-link" id="lost-back-category">← Back</button>
      <div class="flow-header">
        <div class="flow-eyebrow">Lost something?</div>
        <div class="flow-title">Item <span>details</span></div>
      </div>
      ${stepsHTML(['Photo', 'Details', 'Submit'], 1)}
      <div class="locked-category">
        <span>${getCategoryEmoji(s.category)} ${s.category}</span>
        <button class="edit-btn" id="lost-edit-category" title="Edit category">✏️</button>
      </div>
      <div class="form-card">
        <div class="form-section-label">Tell us more</div>
        <div class="field">
          <label for="lost-desc">Description</label>
          <textarea id="lost-desc" placeholder="e.g. Black backpack with red zipper…">${s.description}</textarea>
        </div>
        <div class="field">
          <label for="lost-location">Where lost</label>
          <input type="text" id="lost-location" placeholder="e.g. Main Library, Floor 2" value="${s.location}"/>
        </div>
        <div class="row-2">
          <div class="field">
            <label for="lost-date">Date lost</label>
            <input type="text" id="lost-date" placeholder="e.g. June 10, 2026" value="${s.dateLost}"/>
          </div>
          <div class="field">
            <label for="lost-email">Your email</label>
            <input type="email" id="lost-email" placeholder="you@university.edu" value="${s.email}" required/>
          </div>
        </div>
      </div>
      <button class="btn-primary" id="lost-next-btn">Next →</button>`;
  }

  if (s.step === 'review') {
    return `
      <button class="back-link" id="lost-back-details">← Back</button>
      <div class="flow-header">
        <div class="flow-eyebrow">Almost done</div>
        <div class="flow-title">Review &amp; <span>submit</span></div>
      </div>
      ${stepsHTML(['Photo', 'Details', 'Submit'], 2)}
      <div class="review-card">
        ${s.imagePreview ? `<div class="review-thumb"><img src="${s.imagePreview}" alt="Your item"/></div>` : ''}
        <div class="review-body">
          <div class="review-row"><div class="review-key">Category</div><div class="review-val">${getCategoryEmoji(s.category)} ${s.category}</div></div>
          <div class="review-row"><div class="review-key">Description</div><div class="review-val">${s.description || '—'}</div></div>
          <div class="review-row"><div class="review-key">Where lost</div><div class="review-val">${s.location || '—'}</div></div>
          <div class="review-row"><div class="review-key">Date lost</div><div class="review-val">${s.dateLost || '—'}</div></div>
          <div class="review-row"><div class="review-key">Email</div><div class="review-val">${s.email || '—'}</div></div>
        </div>
      </div>
      <button class="btn-primary" id="lost-submit-btn">Submit lost report →</button>
      <div class="error-banner" id="lost-error">Something went wrong. Please try again.</div>`;
  }

  return '';
}

function bindLostEvents(s) {
  const el = document.getElementById('lost-flow-container');

  el.querySelector('#lost-back-landing')?.addEventListener('click', () => showView('landing'));
  el.querySelector('#lost-back-photo')?.addEventListener('click', () => { state.lost.step = 'photo'; renderLostStep(); });
  el.querySelector('#lost-back-category')?.addEventListener('click', () => { state.lost.step = 'category'; state.lost.predictionLoading = false; renderLostStep(); });
  el.querySelector('#lost-back-details')?.addEventListener('click', () => { state.lost.step = 'details'; renderLostStep(); });
  el.querySelector('#lost-edit-category')?.addEventListener('click', () => { state.lost.step = 'category'; state.lost.predictionLoading = false; renderLostStep(); });

  const uploadZone = el.querySelector('#lost-upload-zone');
  const fileInput  = el.querySelector('#lost-file-input');
  if (uploadZone && fileInput) {
    uploadZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', e => handleLostUpload(e));
  }

  el.querySelector('#lost-skip-photo')?.addEventListener('click', () => {
    state.lost.step = 'category';
    state.lost.predictionLoading = false;
    state.lost.category = null;
    state.lost.predictionScores = null;
    renderLostStep();
  });

  bindCategoryPills(el);

  el.querySelector('#btn-category-continue')?.addEventListener('click', () => {
    if (!state.lost.category) return;
    state.lost.step = 'details';
    renderLostStep();
  });

  el.querySelector('#lost-next-btn')?.addEventListener('click', () => {
    state.lost.description = document.getElementById('lost-desc').value.trim();
    state.lost.location    = document.getElementById('lost-location').value.trim();
    state.lost.dateLost    = document.getElementById('lost-date').value.trim();
    state.lost.email       = document.getElementById('lost-email').value.trim().toLowerCase();
    if (!state.lost.description) { alert('Please enter a description.'); return; }
    if (!isValidEmail(state.lost.email)) { alert('Please enter a valid email so we can notify you.'); return; }
    state.lost.step = 'review';
    renderLostStep();
  });

  el.querySelector('#lost-submit-btn')?.addEventListener('click', () => submitLostReport());
}

function handleLostUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  if (state.lost.imagePreview) URL.revokeObjectURL(state.lost.imagePreview);
  state.lost.imageFile    = file;
  state.lost.imagePreview = URL.createObjectURL(file);
  state.lost.step         = 'category';
  state.lost.predictionLoading = true;
  renderLostStep();
  predictCategory('lost');
}

/* ─────────────────────── FOUND FLOW ─────────────────────── */

function startFoundFlow() {
  currentFlow = 'found';
  const today = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  Object.assign(state.found, {
    step: 'photo', imageFile: null, imagePreview: null,
    category: null, predictionScores: null, predictionLoading: false,
    description: '', location: '', dateFound: today, email: accountEmail(),
    successMessage: null,
  });
  renderFoundStep();
  showView('found');
}

function renderFoundStep() {
  fixButtonTypes();
  const s  = state.found;
  const el = document.getElementById('found-flow-container');
  el.innerHTML = buildFoundHTML(s);
  bindFoundEvents(s);
}

function buildFoundHTML(s) {
  if (s.step === 'photo') {
    return `
      <button class="back-link" id="found-back-landing">← Back</button>
      <div class="flow-header">
        <div class="flow-eyebrow">Found something?</div>
        <div class="flow-title">Report a <span>found item</span></div>
        <p class="flow-subtitle">Upload a photo and we'll automatically match it with people who reported it missing.</p>
      </div>
      <div class="upload-zone" id="found-upload-zone">
        <input type="file" id="found-file-input" accept="image/*"/>
        <div class="upload-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
        </div>
        <div class="upload-label">Upload a photo of the found item</div>
        <div class="upload-sub">required — photo powers the AI matching</div>
      </div>
      ${s.imagePreview
        ? `<div class="preview-card">
             <div class="preview-img-wrap">
               <img src="${s.imagePreview}" alt="Preview"/>
               <div class="img-badge">Photo uploaded</div>
             </div>
           </div>`
        : ''
      }`;
  }

  if (s.step === 'category') {
    return `
      <button class="back-link" id="found-back-photo">← Back</button>
      <div class="flow-header">
        <div class="flow-eyebrow">Found something?</div>
        <div class="flow-title">What did you <span>find?</span></div>
      </div>
      ${s.predictionLoading
        ? `<div class="category-loading">
             <div class="spinner"></div>
             <div class="category-loading-text">Analysing your item…</div>
           </div>`
        : `<div class="category-card">
             <div class="category-card-title">🧠 AI predicted category</div>
             <div class="category-pills">${categoryPillsHTML(s.category, s.predictionScores)}</div>
             <div class="category-hint">Tap to change if this looks wrong</div>
           </div>
           <button class="btn-primary" id="btn-category-continue" ${s.category ? '' : 'disabled'}>
             Looks right, continue →
           </button>`
      }`;
  }

  if (s.step === 'details') {
    return `
      <button class="back-link" id="found-back-category">← Back</button>
      <div class="flow-header">
        <div class="flow-eyebrow">Found something?</div>
        <div class="flow-title">Item <span>details</span></div>
      </div>
      <div class="locked-category">
        <span>${getCategoryEmoji(s.category)} ${s.category}</span>
        <button class="edit-btn" id="found-edit-category" title="Edit category">✏️</button>
      </div>
      <div class="form-card">
        <div class="form-section-label">Item details</div>
        <div class="field">
          <label for="found-desc">Description <span style="color:#94A3B8;font-weight:400">(optional)</span></label>
          <textarea id="found-desc" placeholder="e.g. Black backpack with red zipper…">${s.description}</textarea>
        </div>
        <div class="row-2">
          <div class="field">
            <label for="found-location">Where found</label>
            <input type="text" id="found-location" placeholder="e.g. Main Library, Floor 2" value="${s.location}"/>
          </div>
          <div class="field">
            <label for="found-date">Date found</label>
            <input type="text" id="found-date" value="${s.dateFound}"/>
          </div>
        </div>
      </div>
      <div class="form-card">
        <div class="form-section-label">Your contact</div>
        <div class="field">
          <label for="found-email">Your email</label>
          <input type="email" id="found-email" placeholder="finder@university.edu" value="${s.email}" required/>
        </div>
      </div>
      <button class="btn-primary" id="found-submit-btn">Submit found item →</button>
      <div class="error-banner" id="found-error">Something went wrong. Please try again.</div>
      <p class="bottom-note">Your photo is processed locally. We never share your contact without consent.</p>`;
  }

  if (s.step === 'success') {
    return `
      <div class="success-state">
        <div class="success-check">✓</div>
        <div class="success-title">Your report is live.</div>
        <div class="success-sub">${s.successMessage || "We'll notify you by email if we find the owner."}</div>
        <button class="btn-primary" id="found-report-another">Report another item</button>
      </div>`;
  }

  return '';
}

function bindFoundEvents(s) {
  const el = document.getElementById('found-flow-container');

  el.querySelector('#found-back-landing')?.addEventListener('click', () => showView('landing'));
  el.querySelector('#found-back-photo')?.addEventListener('click', () => { state.found.step = 'photo'; renderFoundStep(); });
  el.querySelector('#found-back-category')?.addEventListener('click', () => { state.found.step = 'category'; state.found.predictionLoading = false; renderFoundStep(); });
  el.querySelector('#found-edit-category')?.addEventListener('click', () => { state.found.step = 'category'; state.found.predictionLoading = false; renderFoundStep(); });
  el.querySelector('#found-report-another')?.addEventListener('click', () => showView('landing'));

  const uploadZone = el.querySelector('#found-upload-zone');
  const fileInput  = el.querySelector('#found-file-input');
  if (uploadZone && fileInput) {
    uploadZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', e => handleFoundUpload(e));
  }

  bindCategoryPills(el);

  el.querySelector('#btn-category-continue')?.addEventListener('click', () => {
    if (!state.found.category) return;
    state.found.step = 'details';
    renderFoundStep();
  });

  el.querySelector('#found-submit-btn')?.addEventListener('click', () => submitFoundReport());
}

function handleFoundUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  if (state.found.imagePreview) URL.revokeObjectURL(state.found.imagePreview);
  state.found.imageFile    = file;
  state.found.imagePreview = URL.createObjectURL(file);
  state.found.step         = 'category';
  state.found.predictionLoading = true;
  renderFoundStep();
  predictCategory('found');
}

/* ─────────────────────── CATEGORY PREDICTION ─────────────────────── */

async function predictCategory(flow) {
  const s = state[flow];
  if (!s.imageFile) {
    s.predictionLoading = false;
    flow === 'lost' ? renderLostStep() : renderFoundStep();
    return;
  }
  try {
    const fd = new FormData();
    fd.append('image', s.imageFile);
    const res  = await fetch(`${API_BASE}/predict-category`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error('Prediction failed');
    const data = await res.json();
    s.category        = data.predicted;
    s.predictionScores = data.all_scores;
  } catch {
    s.category        = s.category || 'Other';
    s.predictionScores = null;
  } finally {
    s.predictionLoading = false;
    flow === 'lost' ? renderLostStep() : renderFoundStep();
  }
}

/* ─────────────────────── SUBMIT LOST ─────────────────────── */

async function submitLostReport(expandAll = false) {
  const btn   = document.getElementById('lost-submit-btn');
  const errEl = document.getElementById('lost-error');
  if (btn)   { btn.disabled = true; btn.textContent = 'Searching for matches…'; }
  if (errEl) errEl.classList.remove('visible');

  const s  = state.lost;
  if (!isValidEmail(s.email)) {
    if (btn)   { btn.disabled = false; btn.textContent = 'Submit lost report →'; }
    if (errEl) {
      errEl.textContent = 'A valid email is required so we can notify you.';
      errEl.classList.add('visible');
    }
    return;
  }

  const fd = new FormData();
  if (s.imageFile) fd.append('image', s.imageFile);
  fd.append('description', s.description);
  fd.append('category', expandAll ? 'All' : s.category);
  if (expandAll) fd.append('original_category', s.category);
  if (s.location) fd.append('location', s.location);
  if (s.dateLost) fd.append('date_lost', s.dateLost);
  fd.append('email', s.email);

  try {
    const res  = await fetch(`${API_BASE}/lost`, {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(typeof err.detail === 'string' ? err.detail : 'Submit failed');
    }
    const data = await res.json();
    state.match.response      = data;
    state.match.lostForm      = { ...s };
    state.match.lostItemId    = data.id || null;
    state.match.expandAll     = expandAll;
    state.match.selectedIndex = 0;
    state.match.claimMessage  = null;
    renderMatchView();
    showView('match');
  } catch (err) {
    if (btn)   { btn.disabled = false; btn.textContent = 'Submit lost report →'; }
    if (errEl) {
      errEl.textContent = err.message || 'Something went wrong. Please try again.';
      errEl.classList.add('visible');
    }
  }
}

/* ─────────────────────── SUBMIT FOUND ─────────────────────── */

async function submitFoundReport() {
  const s     = state.found;
  s.description = (document.getElementById('found-desc')?.value || '').trim();
  s.location    = (document.getElementById('found-location')?.value || '').trim();
  s.dateFound   = (document.getElementById('found-date')?.value || '').trim();
  s.email       = (document.getElementById('found-email')?.value || '').trim().toLowerCase();

  const btn   = document.getElementById('found-submit-btn');
  const errEl = document.getElementById('found-error');
  if (btn)   { btn.disabled = true; btn.textContent = 'Submitting…'; }
  if (errEl) errEl.classList.remove('visible');

  if (!isValidEmail(s.email)) {
    if (btn)   { btn.disabled = false; btn.textContent = 'Submit found item →'; }
    if (errEl) {
      errEl.textContent = 'A valid email is required so we can notify you.';
      errEl.classList.add('visible');
    }
    return;
  }

  const fd = new FormData();
  fd.append('image', s.imageFile);
  if (s.description) fd.append('description', s.description);
  fd.append('category', s.category);
  if (s.location)  fd.append('location', s.location);
  if (s.dateFound) fd.append('date_found', s.dateFound);
  fd.append('finder_email', s.email);

  try {
    const res = await fetch(`${API_BASE}/found`, {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail;
      const message = typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map(d => d.msg || JSON.stringify(d)).join('; ')
          : 'Submit failed';
      throw new Error(message);
    }
    const data = await res.json().catch(() => ({}));
    state.found.successMessage = data.message || null;
    state.found.step = 'success';
    renderFoundStep();
  } catch (err) {
    if (btn)   { btn.disabled = false; btn.textContent = 'Submit found item →'; }
    if (errEl) {
      errEl.textContent = err.message || 'Something went wrong. Please try again.';
      errEl.classList.add('visible');
    }
  }
}

/* ─────────────────────── MATCH VIEW ─────────────────────── */

function tierLabel(match) {
  const tier = match.tier;
  if (tier === 'strong') return { text: 'Strong match', cls: 'strong', color: 'emerald' };
  if (tier === 'possible') return { text: 'Possible match', cls: 'possible', color: 'amber' };
  if (tier === 'weak') return { text: 'Weak match', cls: 'weak', color: 'red' };
  return null;
}

function filterMatches(matches) {
  // Keep every backend match that passed the score threshold, ranked highest first.
  return (matches || [])
    .filter(m => m && m.tier && typeof m.score === 'number')
    .slice()
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return (a.rank || 0) - (b.rank || 0);
    });
}

function scoreRowHTML(label, value, colorClass) {
  const isNull = value == null;
  const pctW   = isNull ? 0 : Math.round(value * 100);
  return `<div class="score-row">
    <div class="score-label">${label}</div>
    <div class="score-track">
      <div class="score-fill ${isNull ? 'gray' : colorClass}" style="width:${pctW}%"></div>
    </div>
    <div class="score-val ${isNull ? 'na' : ''}">${isNull ? 'n/a' : value.toFixed(2)}</div>
  </div>`;
}

function renderMatchView() {
  const { response, lostForm, selectedIndex, claimMessage } = state.match;
  const container   = document.getElementById('match-container');
  const matches     = filterMatches(response.matches);
  const category    = response.category_searched || lostForm.category;
  const total       = response.total_compared || 0;

  if (matches.length === 0) {
    container.innerHTML = buildEmptyMatchHTML(category, total);
    bindEmptyMatchEvents();
    return;
  }

  // Clamp selection so rank #1 shows first by default.
  const safeIndex = Math.min(Math.max(selectedIndex || 0, 0), matches.length - 1);
  if (safeIndex !== selectedIndex) state.match.selectedIndex = safeIndex;

  const selected     = matches[safeIndex];
  const conf         = tierLabel(selected);
  const pct          = Math.round(selected.score * 100);
  const fillColor    = conf ? conf.color : 'emerald';
  const rankLabel    = selected.rank || (safeIndex + 1);
  const imgSrc       = selected.image_url ? `${API_BASE}${selected.image_url}` : null;
  const initials     = (selected.reported_by || 'U').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  const sameCategory = typeof selected.same_category === 'boolean'
    ? selected.same_category
    : selected.category === lostForm.category;
  const breakdown    = selected.scores_breakdown || response.scores_breakdown || {};
  const bannerTitle  = matches.length === 1
    ? (conf ? `${conf.text} found!` : 'Possible match found!')
    : `${matches.length} ranked matches found`;

  const lostPreview = lostForm?.imagePreview
    || (response.lost_image_url ? `${API_BASE}${response.lost_image_url}` : null);
  const lostCategory = response.lost_category || lostForm?.category || '—';
  const lostDesc = response.lost_description || lostForm?.description || '—';
  const lostLocation = response.lost_location || lostForm?.location || '—';
  const lostDate = response.lost_date || lostForm?.dateLost || '—';

  container.innerHTML = `
    <button class="back-link" id="match-back-landing">← Back</button>

    ${claimMessage ? `
      <div class="claim-success-banner">
        <div class="claim-success-title">✓ Claim submitted</div>
        <div class="claim-success-sub">${claimMessage}</div>
      </div>
    ` : ''}

    <div class="match-banner">
      <div class="match-banner-header">
        <div class="match-banner-dot"></div>
        <div class="match-banner-title">${bannerTitle}</div>
      </div>
      <div class="match-banner-sub">
        ${matches.length} above threshold · Compared ${total} found items · Scope: ${category}
      </div>
      <div class="confidence-row">
        <div class="confidence-label">Rank #${rankLabel} confidence</div>
        <div class="confidence-track">
          <div class="confidence-fill ${fillColor}" style="width:${pct}%"></div>
        </div>
        <div class="confidence-pct">${pct}%</div>
      </div>
    </div>

    <div class="candidates-title" style="margin-top:0">Compare your lost item with this match</div>
    <div class="compare-panel">
      <div class="compare-card lost">
        <div class="compare-card-head">
          <div class="compare-card-title">Your lost report</div>
          <span class="pill pill-lost">Lost</span>
        </div>
        <div class="compare-img">
          ${lostPreview
            ? `<img src="${lostPreview}" alt="Your lost item"/>`
            : `<div class="compare-placeholder">${getCategoryEmoji(lostCategory)}<br/>No photo uploaded</div>`
          }
        </div>
        <div class="compare-meta">
          <div class="compare-meta-name">${getCategoryEmoji(lostCategory)} ${lostCategory}</div>
          <div class="compare-meta-desc">${lostDesc}</div>
          <div class="compare-meta-line">Where: ${lostLocation}</div>
          <div class="compare-meta-line">Date: ${lostDate}</div>
        </div>
      </div>

      <div class="compare-card found">
        <div class="compare-card-head">
          <div class="compare-card-title">Rank #${rankLabel} match</div>
          <span class="pill pill-found">Found</span>
        </div>
        <div class="compare-img">
          ${imgSrc
            ? `<img src="${imgSrc}" alt="Found match"/>`
            : `<div class="compare-placeholder">${getCategoryEmoji(selected.category)}<br/>No photo</div>`
          }
        </div>
        <div class="compare-meta">
          <div class="compare-meta-name">${getCategoryEmoji(selected.category)} ${selected.category}</div>
          <div class="compare-meta-desc">${selected.description || '—'}</div>
          <div class="compare-meta-line">Where: ${selected.location || '—'}</div>
          <div class="compare-meta-line">Date: ${selected.date_found || '—'}</div>
        </div>
      </div>
    </div>

    ${matches.length > 1 ? `
      <div class="rank-nav">
        <button type="button" class="rank-nav-btn" id="btn-prev-rank" ${safeIndex === 0 ? 'disabled' : ''}>← Previous</button>
        <div class="rank-nav-status">Viewing rank #${rankLabel} of ${matches.length}</div>
        <button type="button" class="rank-nav-btn" id="btn-next-rank" ${safeIndex >= matches.length - 1 ? 'disabled' : ''}>Next →</button>
      </div>
    ` : ''}

    <div class="best-match-card">
      <div class="best-match-header">
        <div class="best-match-label">Rank #${rankLabel} details · ${safeIndex + 1} of ${matches.length}</div>
        ${conf ? `<span class="confidence-tag ${conf.cls}">${conf.text}</span>` : ''}
      </div>
      <div class="match-img-area">
        ${imgSrc ? `<img src="${imgSrc}" alt="Found item"/>` : backpackArtHTML()}
      </div>
      <div class="detail-rows">
        <div class="detail-row"><div class="detail-key">Category</div><div class="detail-val">${getCategoryEmoji(selected.category)} ${selected.category}</div></div>
        <div class="detail-row"><div class="detail-key">Description</div><div class="detail-val">${selected.description || '—'}</div></div>
        <div class="detail-row"><div class="detail-key">Found at</div><div class="detail-val emerald">${selected.location || '—'}</div></div>
        <div class="detail-row"><div class="detail-key">Date found</div><div class="detail-val">${selected.date_found || '—'}</div></div>
        <div class="detail-row"><div class="detail-key">Time found</div><div class="detail-val">${selected.time_found || '—'}</div></div>
        <div class="detail-row"><div class="detail-key">Currently held at</div><div class="detail-val">Library Information Desk</div></div>
        <div class="detail-row"><div class="detail-key">Reported by</div><div class="detail-val">${selected.reported_by || '—'}</div></div>
      </div>
      <div class="similarity-section">
        <div class="similarity-title">Similarity breakdown</div>
        ${scoreRowHTML('Text → image',              breakdown.text_to_image,             'indigo')}
        ${scoreRowHTML('Image → image',             breakdown.image_to_image,            'emerald')}
        ${scoreRowHTML('Found text → lost image',   breakdown.found_text_to_lost_image,  'amber')}
      </div>
      <div class="category-match-row">
        <div class="category-match-label">Category match</div>
        <span class="cat-match-pill ${sameCategory ? 'same' : 'diff'}">
          ${sameCategory ? '✓ Same category' : '⚠ Different category'}
        </span>
      </div>
      <div class="finder-strip">
        <div class="finder-avatar">${initials}</div>
        <div class="finder-info">
          <div class="finder-name">${selected.reported_by || 'Anonymous'}</div>
          <div class="finder-verified">Verified user</div>
        </div>
        <button class="btn-contact" id="btn-contact-finder">Contact</button>
      </div>
    </div>

    <div class="action-btns">
      <button class="btn-emerald" id="btn-this-is-mine" ${claimMessage ? 'disabled' : ''}>
        ${claimMessage ? 'Claim submitted' : '✓ This is mine — claim rank #' + rankLabel}
      </button>
      <button class="btn-secondary" id="btn-not-mine" ${claimMessage ? 'disabled' : ''}>
        ${safeIndex < matches.length - 1 ? 'Not this one — next ranked →' : 'None of these are mine'}
      </button>
      <div class="error-banner" id="claim-error">Something went wrong. Please try again.</div>
    </div>

    <div class="candidates-title">All ranked matches (${matches.length})</div>
    ${matches.map((m, idx) => {
      const mPct  = Math.round(m.score * 100);
      const mTier = tierLabel(m);
      const mRank = m.rank || (idx + 1);
      const mImg  = m.image_url ? `${API_BASE}${m.image_url}` : null;
      const active = idx === safeIndex ? 'selected' : '';
      return `<div class="candidate-card ${active}" data-idx="${idx}" role="button" tabindex="0">
        <div class="candidate-rank">#${mRank}</div>
        ${mImg
          ? `<img class="candidate-thumb" src="${mImg}" alt=""/>`
          : `<div class="candidate-emoji">${getCategoryEmoji(m.category)}</div>`
        }
        <div class="candidate-body">
          <div class="candidate-name">${m.description || m.category}</div>
          <div class="candidate-loc">${m.location || '—'} · ${mTier ? mTier.text : ''}</div>
        </div>
        <span class="pill pill-category" style="font-size:10px;">${m.category}</span>
        <div class="candidate-score">${mPct}%</div>
      </div>`;
    }).join('')}

    <div class="match-footer-note">
      Showing all ${matches.length} matches above the 0.55 threshold · ${total} reports compared · Ranked by weighted CLIP similarity
    </div>`;

  bindMatchEvents(selected, matches);
  fixButtonTypes();
}

function buildEmptyMatchHTML(category, total) {
  return `
    <button class="back-link" id="match-back-landing">← Back</button>
    <div class="empty-state">
      <div class="radar-wrap" style="position:relative;width:200px;height:200px;margin:0 auto 24px;transform:none;">
        <div class="radar-ring"></div>
        <div class="radar-ring"></div>
        <div class="radar-ring"></div>
        <div class="radar-center"></div>
      </div>
      <div class="empty-title">No matches found in ${category}</div>
      <div class="empty-sub">We searched ${total} found items. We'll notify you by email when something comes in.</div>
      ${!state.match.expandAll
        ? `<button class="btn-text" id="btn-expand-search">Expand search to all categories</button>`
        : ''
      }
    </div>
    <div class="match-footer-note">
      Searched ${total} reports · Scope: ${category} · Ranked by weighted CLIP similarity
    </div>`;
}

function bindMatchEvents(selectedMatch, matches) {
  const container = document.getElementById('match-container');
  container.querySelector('#match-back-landing')?.addEventListener('click', () => showView('landing'));

  container.querySelector('#btn-this-is-mine')?.addEventListener('click', () => claimCurrentMatch(selectedMatch));

  container.querySelector('#btn-not-mine')?.addEventListener('click', () => {
    const next = (state.match.selectedIndex || 0) + 1;
    if (next < matches.length) {
      state.match.selectedIndex = next;
      renderMatchView();
      container.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    showView('landing');
  });

  container.querySelector('#btn-prev-rank')?.addEventListener('click', () => {
    if (state.match.selectedIndex > 0) {
      state.match.selectedIndex -= 1;
      renderMatchView();
    }
  });

  container.querySelector('#btn-next-rank')?.addEventListener('click', () => {
    if (state.match.selectedIndex < matches.length - 1) {
      state.match.selectedIndex += 1;
      renderMatchView();
    }
  });

  container.querySelectorAll('.candidate-card').forEach(card => {
    const select = () => {
      state.match.selectedIndex = parseInt(card.dataset.idx, 10);
      renderMatchView();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    card.addEventListener('click', select);
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        select();
      }
    });
  });
}

async function claimCurrentMatch(topMatch) {
  const btn = document.getElementById('btn-this-is-mine');
  const errEl = document.getElementById('claim-error');
  if (!topMatch || !state.match.lostItemId) {
    if (errEl) {
      errEl.textContent = 'Missing report id. Please re-submit the lost report.';
      errEl.classList.add('visible');
    }
    return;
  }
  if (btn) { btn.disabled = true; btn.textContent = 'Claiming…'; }
  if (errEl) errEl.classList.remove('visible');

  try {
    const res = await fetch(`${API_BASE}/claim`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        found_item_id: topMatch.id,
        lost_item_id: state.match.lostItemId,
        email: state.match.lostForm?.email || accountEmail() || null,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Claim failed');
    state.match.claimMessage = data.message || data.notify_message || 'Claim recorded.';
    renderMatchView();
  } catch (err) {
    const rank = topMatch?.rank || ((state.match.selectedIndex || 0) + 1);
    if (btn) { btn.disabled = false; btn.textContent = `✓ This is mine — claim rank #${rank}`; }
    if (errEl) {
      errEl.textContent = err.message || 'Something went wrong. Please try again.';
      errEl.classList.add('visible');
    }
  }
}

function bindEmptyMatchEvents() {
  const container = document.getElementById('match-container');
  container.querySelector('#match-back-landing')?.addEventListener('click', () => showView('landing'));
  container.querySelector('#btn-expand-search')?.addEventListener('click', () => expandSearch());
}

async function expandSearch() {
  const container = document.getElementById('match-container');
  container.innerHTML = `
    <div class="category-loading" style="margin-top:40px">
      <div class="spinner"></div>
      <div class="category-loading-text">Searching all categories…</div>
    </div>`;
  state.match.expandAll = true;
  await submitLostReport(true);
}

/* ─────────────────────── ADMIN QUEUE ─────────────────────── */

async function openAdminQueue() {
  showView('admin');
  const container = document.getElementById('admin-container');
  container.innerHTML = `
    <div class="category-loading" style="margin-top:24px">
      <div class="spinner"></div>
      <div class="category-loading-text">Loading queue…</div>
    </div>`;

  try {
    const res = await fetch(`${API_BASE}/queue`);
    if (!res.ok) throw new Error('Failed to load queue');
    const data = await res.json();
    container.innerHTML = `
      <button class="back-link" id="admin-back">← Back</button>
      <div class="flow-header">
        <div class="flow-eyebrow">Desk view</div>
        <div class="flow-title">Campus <span>queue</span></div>
        <p class="flow-subtitle">Found reports, lost reports, and claims currently in the system.</p>
      </div>
      <div class="admin-grid">
        ${renderAdminColumn('Found items', data.found_items || [], item => `
          <div class="admin-card">
            <div class="admin-card-title">${getCategoryEmoji(item.category)} ${item.category}</div>
            <div class="admin-card-body">${item.description || 'No description'}</div>
            <div class="admin-card-meta">${item.location || '—'} · ${item.status}</div>
          </div>`)}
        ${renderAdminColumn('Lost items', data.lost_items || [], item => `
          <div class="admin-card">
            <div class="admin-card-title">${getCategoryEmoji(item.category)} ${item.category}</div>
            <div class="admin-card-body">${item.description || 'No description'}</div>
            <div class="admin-card-meta">${item.location || '—'} · ${item.status}</div>
          </div>`)}
        ${renderAdminColumn('Claims', data.claims || [], item => `
          <div class="admin-card">
            <div class="admin-card-title">Claim ${item.status}</div>
            <div class="admin-card-body">${item.notify_message || 'No message'}</div>
            <div class="admin-card-meta">${item.claimed_by_email || '—'}</div>
          </div>`)}
      </div>`;
    document.getElementById('admin-back')?.addEventListener('click', () => showView('landing'));
  } catch {
    container.innerHTML = `
      <button class="back-link" id="admin-back">← Back</button>
      <div class="error-banner visible">Could not load the queue. Is the API running?</div>`;
    document.getElementById('admin-back')?.addEventListener('click', () => showView('landing'));
  }
}

function renderAdminColumn(title, items, renderItem) {
  return `<div class="admin-column">
    <div class="admin-column-title">${title} (${items.length})</div>
    ${items.length ? items.map(renderItem).join('') : '<div class="admin-empty">None yet</div>'}
  </div>`;
}

/* ─────────────────────── AUTH: LOGIN ─────────────────────── */

function isLoginLocked() {
  return !!(loginAttempts.lockedUntil && Date.now() < loginAttempts.lockedUntil);
}

function clearLockoutTimer() {
  if (lockoutTimer) {
    clearInterval(lockoutTimer);
    lockoutTimer = null;
  }
}

function startLockout() {
  loginAttempts.lockedUntil = Date.now() + 60000;
  renderLogin();
  clearLockoutTimer();
  lockoutTimer = setInterval(() => {
    if (!isLoginLocked()) {
      clearLockoutTimer();
      loginAttempts.count = 0;
      loginAttempts.lockedUntil = null;
      renderLogin();
      return;
    }
    const banner = document.getElementById('login-lockout');
    if (!banner) return;
    const remaining = Math.ceil((loginAttempts.lockedUntil - Date.now()) / 1000);
    banner.textContent = `Too many attempts. Try again in ${remaining} seconds.`;
  }, 1000);
}

function getPasswordStrength(password) {
  if (password.length === 0) return { level: 0, label: '', color: 'gray', width: '0%' };
  if (password.length < 8) return { level: 1, label: 'Weak', color: 'red', width: '33%' };
  const hasMix = /[A-Z]/.test(password) && /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  if (hasMix && hasNumber) return { level: 3, label: 'Strong', color: 'emerald', width: '100%' };
  return { level: 2, label: 'Fair', color: 'amber', width: '66%' };
}

function clearFieldErrors(container) {
  container.querySelectorAll('.field-error').forEach(el => el.classList.remove('field-error'));
  container.querySelectorAll('.field-error-msg').forEach(el => el.remove());
}

function setFieldError(input, message) {
  if (!input) return;
  input.classList.add('field-error');
  const msg = document.createElement('div');
  msg.className = 'field-error-msg';
  msg.textContent = message;
  input.parentElement.appendChild(msg);
}

function apiErrorMessage(data, fallback) {
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(d => d.msg || JSON.stringify(d)).join('; ');
  if (typeof data?.message === 'string') return data.message;
  return fallback;
}

function buildLoginHTML() {
  const locked = isLoginLocked();
  const remaining = locked ? Math.ceil((loginAttempts.lockedUntil - Date.now()) / 1000) : 0;

  return `
    <div class="auth-logo" id="login-brand-logo">Find<span>It</span></div>
    <div class="form-card">
      <div class="flow-eyebrow">Welcome back</div>
      <div class="flow-title" style="margin-bottom:18px">Sign in to FindIt</div>
      <div class="field">
        <label for="login-email">Email</label>
        <input type="email" id="login-email" placeholder="you@university.edu" autocomplete="email"/>
      </div>
      <div class="field">
        <label for="login-password">Password</label>
        <input type="password" id="login-password" placeholder="Your password" autocomplete="current-password"/>
      </div>
    </div>
    <button type="button" class="btn-primary" id="btn-login-submit" ${locked ? 'disabled' : ''}>Sign in →</button>
    <div class="error-banner" id="login-error">Something went wrong. Please try again.</div>
    <div class="lockout-banner ${locked ? 'visible' : ''}" id="login-lockout">
      Too many attempts. Try again in ${remaining} seconds.
    </div>
    <div class="auth-switch">Don't have an account? <button type="button" id="btn-goto-register">Register</button></div>
    <button type="button" class="auth-forgot" id="btn-forgot-password">Forgot password?</button>
  `;
}

function renderLogin() {
  const el = document.getElementById('login-container');
  if (!el) return;
  el.innerHTML = buildLoginHTML();
  bindLoginEvents();
  fixButtonTypes();
}

function bindLoginEvents() {
  const el = document.getElementById('login-container');
  el.querySelector('#login-brand-logo')?.addEventListener('click', () => {
    if (auth.token) showView('landing');
  });
  el.querySelector('#btn-goto-register')?.addEventListener('click', () => showView('register'));
  el.querySelector('#btn-forgot-password')?.addEventListener('click', () => {});
  el.querySelector('#btn-login-submit')?.addEventListener('click', () => submitLogin());

  el.querySelector('#login-password')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') submitLogin();
  });
  el.querySelector('#login-email')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') submitLogin();
  });
}

async function submitLogin() {
  if (isLoginLocked()) return;

  const el = document.getElementById('login-container');
  const emailInput = document.getElementById('login-email');
  const passwordInput = document.getElementById('login-password');
  const errEl = document.getElementById('login-error');
  const btn = document.getElementById('btn-login-submit');

  clearFieldErrors(el);
  errEl?.classList.remove('visible');

  const email = (emailInput?.value || '').trim();
  const password = passwordInput?.value || '';
  let valid = true;

  if (!email) {
    setFieldError(emailInput, 'Email is required');
    valid = false;
  }
  if (!password) {
    setFieldError(passwordInput, 'Password is required');
    valid = false;
  }
  if (!valid) return;

  if (btn) { btn.disabled = true; btn.textContent = 'Signing in…'; }

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorMessage(data, 'Invalid email or password'));

    saveToken(data.access_token);
    if (!auth.verified) {
      clearToken();
      if (btn) { btn.disabled = false; btn.textContent = 'Sign in →'; }
      if (errEl) {
        errEl.textContent = 'Please verify your email before signing in.';
        errEl.classList.add('visible');
      }
      return;
    }

    loginAttempts.count = 0;
    loginAttempts.lockedUntil = null;
    clearLockoutTimer();
    renderNav();
    showView('landing');
  } catch (err) {
    loginAttempts.count += 1;
    if (loginAttempts.count >= 5) {
      startLockout();
      return;
    }
    if (btn) { btn.disabled = false; btn.textContent = 'Sign in →'; }
    if (errEl) {
      errEl.textContent = err.message || 'Something went wrong. Please try again.';
      errEl.classList.add('visible');
    }
  }
}

/* ─────────────────────── AUTH: REGISTER ─────────────────────── */

function buildRegisterHTML() {
  if (state.register.successEmail) {
    return `
      <div class="auth-logo" id="register-brand-logo">Find<span>It</span></div>
      <div class="success-state">
        <div class="success-check">✓</div>
        <div class="success-title">Check your email</div>
        <div class="success-sub">We sent a verification link to ${state.register.successEmail}. You must verify before signing in.</div>
        <p class="bottom-note" style="margin-bottom:20px">Didn't get it? Check your spam folder.</p>
        ${state.register.verifyUrl ? `
          <p class="bottom-note" style="margin-bottom:12px">Prototype: open this verify link</p>
          <button type="button" class="btn-primary" id="btn-open-verify" style="margin-bottom:16px">Verify email →</button>
        ` : ''}
        <button type="button" class="btn-text" id="btn-register-to-login">Back to sign in</button>
      </div>
    `;
  }

  return `
    <div class="auth-logo" id="register-brand-logo">Find<span>It</span></div>
    <div class="form-card">
      <div class="flow-eyebrow">Join FindIt</div>
      <div class="flow-title" style="margin-bottom:18px">Create your account</div>
      <div class="field">
        <label for="register-name">Full name</label>
        <input type="text" id="register-name" placeholder="Juan Dela Cruz" autocomplete="name"/>
      </div>
      <div class="field">
        <label for="register-email">Email</label>
        <input type="email" id="register-email" placeholder="you@university.edu" autocomplete="email"/>
      </div>
      <div class="field">
        <label for="register-password">Password</label>
        <input type="password" id="register-password" placeholder="At least 8 characters" autocomplete="new-password"/>
        <div class="strength-bar-wrap">
          <div class="strength-bar-track">
            <div class="strength-bar-fill gray" id="strength-fill" style="width:0%"></div>
          </div>
          <div class="strength-label gray" id="strength-label"></div>
        </div>
      </div>
      <div class="field">
        <label for="register-confirm">Confirm password</label>
        <input type="password" id="register-confirm" placeholder="Repeat your password" autocomplete="new-password"/>
      </div>
    </div>
    <button type="button" class="btn-primary" id="btn-register-submit">Create account →</button>
    <div class="error-banner" id="register-error">Something went wrong. Please try again.</div>
    <div class="auth-switch">Already have an account? <button type="button" id="btn-goto-login">Sign in</button></div>
  `;
}

function renderRegister() {
  const el = document.getElementById('register-container');
  if (!el) return;
  el.innerHTML = buildRegisterHTML();
  bindRegisterEvents();
  fixButtonTypes();
}

function bindRegisterEvents() {
  const el = document.getElementById('register-container');
  el.querySelector('#register-brand-logo')?.addEventListener('click', () => {
    if (auth.token) showView('landing');
  });
  el.querySelector('#btn-goto-login')?.addEventListener('click', () => {
    state.register.successEmail = null;
    state.register.verifyUrl = null;
    showView('login');
  });
  el.querySelector('#btn-register-to-login')?.addEventListener('click', () => {
    state.register.successEmail = null;
    state.register.verifyUrl = null;
    showView('login');
  });
  el.querySelector('#btn-open-verify')?.addEventListener('click', () => {
    if (state.register.verifyUrl) window.open(state.register.verifyUrl, '_blank');
  });
  el.querySelector('#btn-register-submit')?.addEventListener('click', () => submitRegister());

  const passwordInput = el.querySelector('#register-password');
  passwordInput?.addEventListener('input', () => {
    const strength = getPasswordStrength(passwordInput.value);
    const fill = document.getElementById('strength-fill');
    const label = document.getElementById('strength-label');
    if (fill) {
      fill.style.width = strength.width;
      fill.className = `strength-bar-fill ${strength.color}`;
    }
    if (label) {
      label.textContent = strength.label;
      label.className = `strength-label ${strength.color}`;
    }
  });
}

async function submitRegister() {
  const el = document.getElementById('register-container');
  const nameInput = document.getElementById('register-name');
  const emailInput = document.getElementById('register-email');
  const passwordInput = document.getElementById('register-password');
  const confirmInput = document.getElementById('register-confirm');
  const errEl = document.getElementById('register-error');
  const btn = document.getElementById('btn-register-submit');

  clearFieldErrors(el);
  errEl?.classList.remove('visible');

  const name = (nameInput?.value || '').trim();
  const email = (emailInput?.value || '').trim();
  const password = passwordInput?.value || '';
  const confirm = confirmInput?.value || '';
  const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  let valid = true;

  if (!name) {
    setFieldError(nameInput, 'Full name is required');
    valid = false;
  }
  if (!email) {
    setFieldError(emailInput, 'Email is required');
    valid = false;
  } else if (!emailOk) {
    setFieldError(emailInput, 'Enter a valid email address');
    valid = false;
  }
  if (!password) {
    setFieldError(passwordInput, 'Password is required');
    valid = false;
  } else if (password.length < 8) {
    setFieldError(passwordInput, 'Password must be at least 8 characters');
    valid = false;
  }
  if (!confirm) {
    setFieldError(confirmInput, 'Confirm your password');
    valid = false;
  } else if (confirm !== password) {
    setFieldError(confirmInput, 'Passwords do not match');
    valid = false;
  }
  if (!valid) return;

  if (btn) { btn.disabled = true; btn.textContent = 'Creating account…'; }

  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorMessage(data, 'Registration failed'));

    state.register.successEmail = email;
    state.register.verifyUrl = data.dev_verify_url || null;
    renderRegister();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Create account →'; }
    if (errEl) {
      errEl.textContent = err.message || 'Something went wrong. Please try again.';
      errEl.classList.add('visible');
    }
  }
}

/* ─────────────────────── BOOT ─────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  loadToken();
  fixButtonTypes();
  renderNav();

  document.getElementById('btn-start-lost')?.addEventListener('click', startLostFlow);
  document.getElementById('btn-start-found')?.addEventListener('click', startFoundFlow);
  document.getElementById('btn-cta-lost')?.addEventListener('click', startLostFlow);
  document.getElementById('btn-cta-found')?.addEventListener('click', startFoundFlow);
  document.getElementById('nav-logo-landing')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-lost')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-found')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-match')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-admin')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-login')?.addEventListener('click', () => {
    if (auth.token) showView('landing');
  });
  document.getElementById('nav-logo-register')?.addEventListener('click', () => {
    if (auth.token) showView('landing');
  });

  if (auth.token) {
    showView('landing');
  } else {
    showView('login');
  }
});
