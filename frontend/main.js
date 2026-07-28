/* ─────────────────────────────────────────────
   AMAlost — app.js
   All view logic, state, and API calls.
   No inline event handlers — everything is
   wired via addEventListener after DOM ready.
───────────────────────────────────────────── */

const API_BASE = 'http://localhost:8000';

const CATEGORIES = [
  { name: 'Backpack / Bag',     emoji: '🎒' },
  { name: 'Gadgets',            emoji: '📱' },
  { name: 'Gadget Accessories', emoji: '🎧' },
  { name: 'Electronics',        emoji: '🔌' },
  { name: 'School Supplies',    emoji: '✏️' },
  { name: 'Wallet / Purse',     emoji: '👛' },
  { name: 'Umbrella',           emoji: '☂️' },
  { name: 'Glasses',            emoji: '👓' },
  { name: 'Water Bottle',       emoji: '💧' },
  { name: 'Clothing',           emoji: '👕' },
  { name: 'Other',              emoji: '📦' },
];

/** Where an item was discovered (found) or places visited that day (lost). */
const CAMPUS_LOCATIONS = [
  'Registrar Office',
  'Faculty',
  'Library',
  'Room 401',
  'Room 402',
  'Room 403',
  'Room 404',
  'Room 405',
  'Room 406',
  'Room 407',
  'Room 408',
  'Room 409',
  'Room 410',
];

function todayISODate() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function formatLocationsLabel(locations) {
  if (Array.isArray(locations)) {
    return locations.length ? locations.join(' · ') : '—';
  }
  return locations || '—';
}

function locationCheckboxesHTML(selected, namePrefix) {
  const selectedSet = new Set(Array.isArray(selected) ? selected : []);
  return `<div class="location-grid">
    ${CAMPUS_LOCATIONS.map(loc => {
      const id = `${namePrefix}-${loc.replace(/\s+/g, '-').toLowerCase()}`;
      const checked = selectedSet.has(loc) ? 'checked' : '';
      return `<label class="location-chip" for="${id}">
        <input type="checkbox" id="${id}" name="${namePrefix}" value="${loc}" ${checked}/>
        <span>${loc}</span>
      </label>`;
    }).join('')}
  </div>`;
}

function locationSelectHTML(selected, selectId) {
  const opts = CAMPUS_LOCATIONS.map(loc => {
    const sel = loc === selected ? 'selected' : '';
    return `<option value="${loc}" ${sel}>${loc}</option>`;
  }).join('');
  return `<select id="${selectId}" required>
    <option value="">Select where it was found…</option>
    ${opts}
  </select>`;
}

function readCheckedLocations(namePrefix) {
  return Array.from(document.querySelectorAll(`input[name="${namePrefix}"]:checked`))
    .map(el => el.value);
}

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
    location: [],
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
    foundItemId: null,
    foundForm: null,
    direction: 'lost_to_found', // 'lost_to_found' | 'found_to_lost'
    expandAll: false,
    searchAllLocations: false,
    selectedIndex: 0,
    claimMessage: null,
    contact: null,
  },
  register: {
    successEmail: null,
    verifyUrl: null,
    mailMode: null,
    mailSent: false,
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

const TOKEN_KEY = 'amalost_token';
const PROTECTED_VIEWS = ['landing', 'lost', 'found', 'match', 'admin', 'dashboard'];

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

function isAdminUser() {
  return !!(auth.token && auth.user?.is_admin);
}

function goHome() {
  if (isAdminUser()) openAdminQueue();
  else showView('landing');
}

function renderNav() {
  const isAuthed = !!auth.token;
  const isAdmin = isAdminUser();
  const firstName = auth.user?.name?.split(' ')[0]
    || auth.user?.full_name?.split(' ')[0]
    || auth.user?.email?.split('@')[0]
    || '';

  document.querySelectorAll('.nav-right').forEach(navRight => {
    if (isAuthed) {
      navRight.innerHTML = `
        ${isAdmin ? '<button type="button" class="nav-btn btn-admin">Admin</button>' : ''}
        <button type="button" class="nav-btn btn-my-items">My items</button>
        <span class="nav-user-name">${firstName}</span>
        <button type="button" class="nav-btn btn-signout">Sign out</button>
      `;
      navRight.querySelector('.btn-admin')?.addEventListener('click', () => openAdminQueue());
      navRight.querySelector('.btn-my-items')?.addEventListener('click', () => openDashboard());
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
    dashboard: 'view-dashboard',
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

const VAGUE_DESC_WORDS = new Set([
  'item', 'items', 'thing', 'things', 'stuff', 'object', 'objects',
  'lost', 'found', 'something', 'someone', 'misc', 'miscellaneous',
  'n/a', 'na', 'none', 'test', 'asdf', 'xxx',
]);

function descriptionValidationError(text) {
  const cleaned = (text || '').trim().replace(/\s+/g, ' ');
  if (!cleaned) {
    return 'Please add a short description (color, brand, marks, or other details).';
  }
  const tokens = cleaned.toLowerCase().match(/[a-z0-9]+/g) || [];
  if (cleaned.length < 8 || tokens.length < 2) {
    return 'Description is too short. Add a couple of details (e.g. “black Casio calculator with cracked case”).';
  }
  const meaningful = tokens.filter(t => !VAGUE_DESC_WORDS.has(t));
  if (!meaningful.length || tokens.every(t => VAGUE_DESC_WORDS.has(t))) {
    return 'Description is too vague. Add distinctive details (color, brand, model, scratches, stickers…).';
  }
  return null;
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
  // Rank by AI confidence when available, but always keep Other at the bottom.
  const list = scores
    ? [...CATEGORIES].sort((a, b) => {
        if (a.name === 'Other') return 1;
        if (b.name === 'Other') return -1;
        return (scores[b.name] || 0) - (scores[a.name] || 0);
      })
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
    description: '', location: [], dateLost: todayISODate(), email: accountEmail(),
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
          <label>Places you visited that day</label>
          <p class="bottom-note" style="margin:0 0 10px">Select every spot you went — matching prefers found items from these places (soft boost, not a hard filter).</p>
          ${locationCheckboxesHTML(s.location, 'lost-loc')}
        </div>
        <div class="row-2">
          <div class="field">
            <label for="lost-date">Date lost</label>
            <input type="date" id="lost-date" value="${s.dateLost || todayISODate()}" required/>
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
          <div class="review-row"><div class="review-key">Places visited</div><div class="review-val">${formatLocationsLabel(s.location)}</div></div>
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
    state.lost.location    = readCheckedLocations('lost-loc');
    state.lost.dateLost    = document.getElementById('lost-date').value.trim();
    state.lost.email       = document.getElementById('lost-email').value.trim().toLowerCase();
    const descErr = descriptionValidationError(state.lost.description);
    if (descErr) { alert(descErr); return; }
    if (!state.lost.location.length) {
      alert('Select at least one place you visited the day the item was lost.');
      return;
    }
    if (!state.lost.dateLost) { alert('Please select the date lost.'); return; }
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
  Object.assign(state.found, {
    step: 'photo', imageFile: null, imagePreview: null,
    category: null, predictionScores: null, predictionLoading: false,
    description: '', location: '', dateFound: todayISODate(), email: accountEmail(),
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
          <label for="found-desc">Description</label>
          <textarea id="found-desc" placeholder="e.g. Black iPhone 13 with cracked screen protector…">${s.description}</textarea>
          <p class="bottom-note" style="margin-top:6px">Required — color, brand, marks, or other details (anti-fraud matching).</p>
        </div>
        <div class="row-2">
          <div class="field">
            <label for="found-location">Where found</label>
            ${locationSelectHTML(s.location, 'found-location')}
            <p class="bottom-note" style="margin-top:6px">Discovery spot — where you picked it up, not a holding desk.</p>
          </div>
          <div class="field">
            <label for="found-date">Date found</label>
            <input type="date" id="found-date" value="${s.dateFound || todayISODate()}" required/>
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
        <div class="success-sub">${s.successMessage || "No open lost reports matched yet. Your found item is live for owners to discover."}</div>
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

async function submitLostReport(expandAll = false, searchAllLocations = false) {
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

  const locations = Array.isArray(s.location) ? s.location : (s.location ? [s.location] : []);
  if (!locations.length) {
    if (btn)   { btn.disabled = false; btn.textContent = 'Submit lost report →'; }
    if (errEl) {
      errEl.textContent = 'Select at least one place you visited that day.';
      errEl.classList.add('visible');
    }
    return;
  }

  const applyAllLocations = searchAllLocations || state.match.searchAllLocations;
  const fd = new FormData();
  if (s.imageFile) fd.append('image', s.imageFile);
  fd.append('description', s.description);
  fd.append('category', expandAll ? 'All' : s.category);
  if (expandAll) fd.append('original_category', s.category);
  fd.append('location', locations.join(' | '));
  if (s.dateLost) fd.append('date_lost', s.dateLost);
  fd.append('email', s.email);
  if (applyAllLocations) fd.append('search_all_locations', 'true');

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
    state.match.lostForm      = { ...s, location: locations };
    state.match.lostItemId    = data.id || null;
    state.match.foundItemId   = null;
    state.match.foundForm     = null;
    state.match.direction     = 'lost_to_found';
    state.match.expandAll     = expandAll;
    state.match.searchAllLocations = !!data.search_all_locations || applyAllLocations;
    state.match.selectedIndex = 0;
    state.match.claimMessage  = null;
    state.match.contact       = null;
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

  const descErr = descriptionValidationError(s.description);
  if (descErr) {
    if (btn)   { btn.disabled = false; btn.textContent = 'Submit found item →'; }
    if (errEl) {
      errEl.textContent = descErr;
      errEl.classList.add('visible');
    }
    return;
  }

  if (!s.location) {
    if (btn)   { btn.disabled = false; btn.textContent = 'Submit found item →'; }
    if (errEl) {
      errEl.textContent = 'Select where the item was found.';
      errEl.classList.add('visible');
    }
    return;
  }
  if (!s.dateFound) {
    if (btn)   { btn.disabled = false; btn.textContent = 'Submit found item →'; }
    if (errEl) {
      errEl.textContent = 'Select the date found.';
      errEl.classList.add('visible');
    }
    return;
  }

  const fd = new FormData();
  fd.append('image', s.imageFile);
  fd.append('description', s.description);
  fd.append('category', s.category);
  fd.append('location', s.location);
  fd.append('date_found', s.dateFound);
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

    const matches = filterMatches(data.matches);
    if (matches.length > 0) {
      state.match.response = data;
      state.match.foundForm = { ...s };
      state.match.foundItemId = data.id || null;
      state.match.lostItemId = null;
      state.match.lostForm = null;
      state.match.direction = 'found_to_lost';
      state.match.expandAll = false;
      state.match.searchAllLocations = false;
      state.match.selectedIndex = 0;
      state.match.claimMessage = null;
      state.match.contact = null;
      renderMatchView();
      showView('match');
      return;
    }

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
  const { response, lostForm, foundForm, selectedIndex, claimMessage, direction } = state.match;
  const isReverse   = direction === 'found_to_lost';
  const container   = document.getElementById('match-container');
  const matches     = filterMatches(response?.matches);
  const category    = isReverse
    ? (response.category || foundForm?.category || '—')
    : (response.category_searched || lostForm?.category || '—');
  const total       = response?.total_compared || 0;

  if (matches.length === 0) {
    container.innerHTML = buildEmptyMatchHTML(category, total);
    bindEmptyMatchEvents();
    return;
  }

  const safeIndex = Math.min(Math.max(selectedIndex || 0, 0), matches.length - 1);
  if (safeIndex !== selectedIndex) state.match.selectedIndex = safeIndex;

  const selected     = matches[safeIndex];
  const conf         = tierLabel(selected);
  const pct          = Math.round(selected.score * 100);
  const fillColor    = conf ? conf.color : 'emerald';
  const rankLabel    = selected.rank || (safeIndex + 1);
  const imgSrc       = selected.image_url ? `${API_BASE}${selected.image_url}` : null;
  const mineCategory = isReverse ? (foundForm?.category || response.category) : (lostForm?.category || response.lost_category);
  const sameCategory = typeof selected.same_category === 'boolean'
    ? selected.same_category
    : selected.category === mineCategory;
  const breakdown    = selected.scores_breakdown || response.scores_breakdown || {};
  const bannerTitle  = matches.length === 1
    ? (conf ? `${conf.text} found!` : 'Possible match found!')
    : `${matches.length} ranked matches found`;

  const leftPreview = isReverse
    ? (foundForm?.imagePreview || (response.found_image_url ? `${API_BASE}${response.found_image_url}` : null))
    : (lostForm?.imagePreview || (response.lost_image_url ? `${API_BASE}${response.lost_image_url}` : null));
  const leftCategory = isReverse
    ? (response.category || foundForm?.category || '—')
    : (response.lost_category || lostForm?.category || '—');
  const leftDesc = isReverse
    ? (response.found_description || foundForm?.description || '—')
    : (response.lost_description || lostForm?.description || '—');
  const leftLocation = isReverse
    ? (response.found_location || foundForm?.location || '—')
    : formatLocationsLabel(response.lost_location || lostForm?.location);
  const leftDate = isReverse
    ? (response.found_date || foundForm?.dateFound || '—')
    : (response.lost_date || lostForm?.dateLost || '—');

  const sameLocation = !!selected.same_location;
  const locationScope = response.location_scope
    || (state.match.searchAllLocations ? 'All locations (no location boost)' : null);
  const rightDate = isReverse ? (selected.date_lost || '—') : (selected.date_found || '—');
  const primaryBtn = claimMessage
    ? (isReverse ? 'Match accepted' : 'Claim submitted')
    : (isReverse
      ? `✓ Accept match — notify owner (rank #${rankLabel})`
      : `✓ This is mine — claim rank #${rankLabel}`);
  const secondaryBtn = safeIndex < matches.length - 1
    ? 'Not this one — next ranked →'
    : (isReverse ? 'None of these match' : 'None of these are mine');
  const compareTitle = isReverse
    ? 'Compare your found item with this open lost report'
    : 'Compare your lost item with this match';
  const scopeLine = isReverse
    ? `${matches.length} above threshold · Compared ${total} open lost reports`
    : `${matches.length} above threshold · Compared ${total} found items · Scope: ${category}${locationScope ? ` · ${locationScope}` : ''}`;

  container.innerHTML = `
    <button class="back-link" id="match-back-landing">← Back</button>

    ${claimMessage ? `
      <div class="claim-success-banner">
        <div class="claim-success-title">✓ ${isReverse ? 'Match accepted' : 'Claim submitted'}</div>
        <div class="claim-success-sub">${claimMessage}</div>
        <div class="claim-success-actions">
          <button type="button" class="btn-emerald" id="btn-open-contact" style="width:auto;padding:10px 16px;font-size:13px">
            View exchange / confirm →
          </button>
        </div>
      </div>
    ` : ''}

    <div class="match-banner">
      <div class="match-banner-header">
        <div class="match-banner-dot"></div>
        <div class="match-banner-title">${bannerTitle}</div>
      </div>
      <div class="match-banner-sub">${scopeLine}</div>
      <div class="confidence-row">
        <div class="confidence-label">Rank #${rankLabel} confidence</div>
        <div class="confidence-track">
          <div class="confidence-fill ${fillColor}" style="width:${pct}%"></div>
        </div>
        <div class="confidence-pct">${pct}%</div>
      </div>
    </div>

    <div class="candidates-title" style="margin-top:0">${compareTitle}</div>
    <div class="compare-panel">
      <div class="compare-card ${isReverse ? 'found' : 'lost'}">
        <div class="compare-card-head">
          <div class="compare-card-title">${isReverse ? 'Your found report' : 'Your lost report'}</div>
          <span class="pill ${isReverse ? 'pill-found' : 'pill-lost'}">${isReverse ? 'Found' : 'Lost'}</span>
        </div>
        <div class="compare-img">
          ${leftPreview
            ? `<img src="${leftPreview}" alt="Your item"/>`
            : `<div class="compare-placeholder">${getCategoryEmoji(leftCategory)}<br/>No photo uploaded</div>`
          }
        </div>
        <div class="compare-meta">
          <div class="compare-meta-name">${getCategoryEmoji(leftCategory)} ${leftCategory}</div>
          <div class="compare-meta-desc">${leftDesc}</div>
          <div class="compare-meta-line">Where: ${leftLocation}</div>
          <div class="compare-meta-line">Date: ${leftDate}</div>
        </div>
      </div>

      <div class="compare-card ${isReverse ? 'lost' : 'found'}">
        <div class="compare-card-head">
          <div class="compare-card-title">Rank #${rankLabel} match</div>
          <span class="pill ${isReverse ? 'pill-lost' : 'pill-found'}">${isReverse ? 'Lost' : 'Found'}</span>
        </div>
        <div class="compare-img">
          ${imgSrc
            ? `<img src="${imgSrc}" alt="Match"/>`
            : `<div class="compare-placeholder">${getCategoryEmoji(selected.category)}<br/>No photo</div>`
          }
        </div>
        <div class="compare-meta">
          <div class="compare-meta-name">${getCategoryEmoji(selected.category)} ${selected.category}</div>
          <div class="compare-meta-desc">${selected.description || '—'}</div>
          <div class="compare-meta-line">Where: ${selected.location || '—'}</div>
          <div class="compare-meta-line">Date: ${rightDate}</div>
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
        ${imgSrc ? `<img src="${imgSrc}" alt="Match item"/>` : backpackArtHTML()}
      </div>
      <div class="detail-rows">
        <div class="detail-row"><div class="detail-key">Category</div><div class="detail-val">${getCategoryEmoji(selected.category)} ${selected.category}</div></div>
        <div class="detail-row"><div class="detail-key">Description</div><div class="detail-val">${selected.description || '—'}</div></div>
        <div class="detail-row"><div class="detail-key">${isReverse ? 'Lost at' : 'Found at'}</div><div class="detail-val emerald">${selected.location || '—'}</div></div>
        <div class="detail-row"><div class="detail-key">${isReverse ? 'Date lost' : 'Date found'}</div><div class="detail-val">${rightDate}</div></div>
        ${!isReverse ? `<div class="detail-row"><div class="detail-key">Time found</div><div class="detail-val">${selected.time_found || '—'}</div></div>` : ''}
        <div class="detail-row"><div class="detail-key">Meetup</div><div class="detail-val">Coordinate directly (public campus spot)</div></div>
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
      <div class="category-match-row">
        <div class="category-match-label">Location overlap</div>
        <span class="cat-match-pill ${sameLocation ? 'same' : 'diff'}">
          ${sameLocation ? '✓ Found spot in your places' : '○ Different / unknown place'}
        </span>
      </div>
      ${!isReverse && !state.match.searchAllLocations ? `
        <button type="button" class="btn-text" id="btn-expand-locations" style="margin-top:12px">
          Search all locations (ignore place boost) →
        </button>
      ` : ''}
    </div>

    <div class="action-btns">
      <button class="btn-emerald" id="btn-this-is-mine" ${claimMessage ? 'disabled' : ''}>${primaryBtn}</button>
      <button class="btn-secondary" id="btn-not-mine" ${claimMessage ? 'disabled' : ''}>${secondaryBtn}</button>
      ${!isReverse ? '' : '<p class="bottom-note">Accepting notifies the lost owner with your contact. No email is sent until you accept.</p>'}
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
  const locScope = state.match.response?.location_scope || '';
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
      <div style="display:flex;flex-direction:column;gap:8px;align-items:center;margin-top:8px">
        ${!state.match.expandAll
          ? `<button class="btn-text" id="btn-expand-search">Expand search to all categories</button>`
          : ''
        }
        ${!state.match.searchAllLocations
          ? `<button class="btn-text" id="btn-expand-locations">Search all locations (ignore place boost)</button>`
          : ''
        }
      </div>
    </div>
    <div class="match-footer-note">
      Searched ${total} reports · Scope: ${category}${locScope ? ` · ${locScope}` : ''} · Ranked by weighted CLIP similarity
    </div>`;
}

function buildClaimEmailTemplate(contact) {
  const category = contact.category || 'item';
  const pickup = contact.pickup_point
    || 'Agree a public campus meetup — coordinate directly';
  const foundLoc = contact.found_location || 'n/a';
  const lostLoc = contact.lost_location || 'n/a';
  const owner = contact.owner_email || accountEmail() || 'me';
  return {
    subject: `AMAlost match accepted — contact for ${category}`,
    body: [
      `Match accepted. Status: IN PROCESS.`,
      '',
      `Finder: ${contact.finder_name || 'Anonymous'} <${contact.finder_email}>`,
      `Owner: ${owner}`,
      `Found at (discovery): ${foundLoc}`,
      `Lost places visited: ${lostLoc}`,
      `Meetup: ${pickup}`,
      '',
      'Coordinate pickup with each other — AMAlost does not hold items.',
      'Both parties must confirm after a successful exchange.',
      'Anti-fraud: public meetup, verify identity, never send money.',
    ].join('\n'),
  };
}

function openFinderContactModal(contactOverride = null) {
  const contact = contactOverride || state.match.contact;
  const root = document.getElementById('contact-modal-root');
  if (!root) return;

  if (!contact || !contact.finder_email) {
    root.classList.remove('hidden');
    root.innerHTML = `
      <div class="contact-modal-backdrop" id="contact-modal-backdrop">
        <div class="contact-modal" role="dialog" aria-modal="true" aria-labelledby="contact-modal-title">
          <div class="contact-modal-title" id="contact-modal-title">Finder contact unavailable</div>
          <div class="contact-modal-sub">This found item has no email on file. Coordinate a public campus meetup if you still pursue the claim.</div>
          <div class="contact-modal-actions">
            <button type="button" class="btn-secondary" id="btn-close-contact-modal">Close</button>
          </div>
        </div>
      </div>`;
    root.querySelector('#btn-close-contact-modal')?.addEventListener('click', closeFinderContactModal);
    root.querySelector('#contact-modal-backdrop')?.addEventListener('click', e => {
      if (e.target.id === 'contact-modal-backdrop') closeFinderContactModal();
    });
    return;
  }

  const template = buildClaimEmailTemplate(contact);
  const viaSmtp = contact.mail_mode === 'smtp';
  const ownerOk = !!contact.owner_mail_sent;
  const finderOk = !!contact.finder_mail_sent;
  const statusLine = viaSmtp
    ? 'Match accepted emails were sent automatically. Status is now in process.'
    : 'Match accepted emails were saved to the server outbox (add SMTP for live inbox delivery). Status is now in process.';

  root.classList.remove('hidden');
  root.innerHTML = `
    <div class="contact-modal-backdrop" id="contact-modal-backdrop">
      <div class="contact-modal" role="dialog" aria-modal="true" aria-labelledby="contact-modal-title">
        <div class="contact-modal-title" id="contact-modal-title">Match accepted — in process</div>
        <div class="contact-modal-sub">${statusLine}</div>

        <div class="contact-detail">
          <div class="contact-detail-label">Exchange status</div>
          <div class="contact-detail-value">in_process · waiting for both confirmations</div>
        </div>
        <div class="contact-detail">
          <div class="contact-detail-label">Finder</div>
          <div class="contact-detail-value">${contact.finder_name || 'Anonymous'} · ${contact.finder_email}</div>
        </div>
        <div class="contact-detail">
          <div class="contact-detail-label">Owner (you)</div>
          <div class="contact-detail-value">${contact.owner_email || accountEmail() || '—'}</div>
        </div>
        <div class="contact-detail">
          <div class="contact-detail-label">Pickup point</div>
          <div class="contact-detail-value">${contact.pickup_point || 'Coordinate a public campus meetup'}</div>
        </div>
        <div class="contact-detail">
          <div class="contact-detail-label">Email delivery</div>
          <div class="contact-detail-value">${viaSmtp ? 'SMTP' : 'Outbox'} · owner ${ownerOk ? 'sent' : 'failed'} · finder ${finderOk ? 'sent' : 'failed'}</div>
        </div>

        <div class="contact-detail-label" style="margin-top:12px">What was emailed</div>
        <div class="contact-template-preview"><strong>Subject:</strong> ${template.subject}\n\n${template.body}</div>
        <div class="contact-modal-sub" style="margin-top:8px">
          Safety tip: meet in public, verify the rightful owner, and never send money. AMAlost does not hold items.
        </div>
        <div id="contact-send-status" class="contact-modal-sub" style="margin:0 0 10px"></div>

        <div class="contact-modal-actions">
          ${contact.owner_confirm_url || contact.finder_confirm_url
            ? `<button type="button" class="btn-emerald" id="btn-owner-confirm-exchange">I completed the exchange ✓</button>`
            : ''
          }
          <button type="button" class="btn-secondary" id="btn-send-finder-email">Resend notification emails</button>
          <button type="button" class="btn-secondary" id="btn-close-contact-modal">Close</button>
        </div>
      </div>
    </div>`;

  root.querySelector('#btn-close-contact-modal')?.addEventListener('click', closeFinderContactModal);
  root.querySelector('#contact-modal-backdrop')?.addEventListener('click', e => {
    if (e.target.id === 'contact-modal-backdrop') closeFinderContactModal();
  });
  root.querySelector('#btn-send-finder-email')?.addEventListener('click', () => resendCoordinationEmails(contact));
  root.querySelector('#btn-owner-confirm-exchange')?.addEventListener('click', async () => {
    const confirmUrl = contact.owner_confirm_url || contact.finder_confirm_url;
    const token = confirmUrl
      ? (new URL(confirmUrl, window.location.origin).searchParams.get('confirm')
        || confirmUrl.split('confirm=')[1])
      : null;
    if (!token) return;
    const statusEl = document.getElementById('contact-send-status');
    try {
      const data = await confirmExchangeToken(token);
      closeFinderContactModal();
      showExchangeConfirmResult(data);
      if (data.processed) {
        state.match.claimMessage = data.message;
        renderMatchView();
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = err.message || 'Confirm failed.';
    }
  });
}

async function confirmExchangeToken(token) {
  const res = await fetch(`${API_BASE}/claim/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Confirm failed');
  return data;
}

async function handleVerifyQueryParam() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('verify_token');
  if (!token) return;

  showView('login');
  const root = document.getElementById('contact-modal-root');
  if (root) {
    root.classList.remove('hidden');
    root.innerHTML = `
      <div class="contact-modal-backdrop">
        <div class="contact-modal">
          <div class="contact-modal-title">Verifying your email…</div>
          <div class="contact-modal-sub">One moment while we activate your account.</div>
        </div>
      </div>`;
  }

  try {
    const res = await fetch(`${API_BASE}/auth/verify?token=${encodeURIComponent(token)}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Verification failed');
    if (root) {
      root.innerHTML = `
        <div class="contact-modal-backdrop">
          <div class="contact-modal">
            <div class="contact-modal-title">Email verified</div>
            <div class="contact-modal-sub">${escapeHTML(data.message || 'You can sign in now.')}</div>
            <button type="button" class="btn-primary" id="verify-modal-close">Continue to sign in</button>
          </div>
        </div>`;
      root.querySelector('#verify-modal-close')?.addEventListener('click', () => {
        root.classList.add('hidden');
        root.innerHTML = '';
        showView('login');
      });
    } else {
      window.alert(data.message || 'Email verified. You can sign in now.');
    }
  } catch (err) {
    if (root) {
      root.innerHTML = `
        <div class="contact-modal-backdrop">
          <div class="contact-modal">
            <div class="contact-modal-title">Verification failed</div>
            <div class="contact-modal-sub">${escapeHTML(err.message || 'Invalid or expired link.')}</div>
            <button type="button" class="btn-primary" id="verify-modal-close">Close</button>
          </div>
        </div>`;
      root.querySelector('#verify-modal-close')?.addEventListener('click', () => {
        root.classList.add('hidden');
        root.innerHTML = '';
      });
    } else {
      window.alert(err.message || 'Verification failed.');
    }
  } finally {
    const url = new URL(window.location.href);
    url.searchParams.delete('verify_token');
    const clean = url.pathname.endsWith('amalost.html')
      ? `${url.pathname}${url.search}${url.hash}`
      : `/amalost.html${url.search}${url.hash}`;
    window.history.replaceState({}, '', clean);
  }
}

async function handleConfirmQueryParam() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('confirm');
  if (!token) return;

  // Land on the main site immediately, then show exchange status popup.
  if (auth.token) showView('landing');
  else showView('login');

  const root = document.getElementById('contact-modal-root');
  if (root) {
    root.classList.remove('hidden');
    root.innerHTML = `
      <div class="contact-modal-backdrop">
        <div class="contact-modal">
          <div class="contact-modal-title">Confirming your exchange…</div>
          <div class="contact-modal-sub">One moment while we update the claim status.</div>
        </div>
      </div>`;
  }

  try {
    const data = await confirmExchangeToken(token);
    showExchangeConfirmResult(data);
  } catch (err) {
    showExchangeConfirmResult({
      error: true,
      message: err.message || 'Invalid confirmation link.',
    });
  } finally {
    const url = new URL(window.location.href);
    url.searchParams.delete('confirm');
    // Keep users on amalost.html without the token sticking in the URL.
    const clean = url.pathname.endsWith('amalost.html')
      ? `${url.pathname}${url.search}${url.hash}`
      : `/amalost.html${url.search}${url.hash}`;
    window.history.replaceState({}, '', clean);
  }
}

function showExchangeConfirmResult(data) {
  const root = document.getElementById('contact-modal-root');
  if (!root) return;

  if (data.error) {
    root.classList.remove('hidden');
    root.innerHTML = `
      <div class="contact-modal-backdrop" id="contact-modal-backdrop">
        <div class="contact-modal" role="dialog" aria-modal="true">
          <div class="contact-modal-title">Could not confirm</div>
          <div class="contact-modal-sub">${data.message}</div>
          <div class="contact-modal-actions">
            <button type="button" class="btn-secondary" id="btn-close-contact-modal">Back to AMAlost</button>
          </div>
        </div>
      </div>`;
    root.querySelector('#btn-close-contact-modal')?.addEventListener('click', () => {
      closeFinderContactModal();
      showView(auth.token ? 'landing' : 'login');
    });
    return;
  }

  const processed = !!data.processed;
  const ownerDone = !!data.owner_confirmed;
  const finderDone = !!data.finder_confirmed;
  const title = processed ? 'Exchange complete' : 'Confirmation saved';
  const badge = processed
    ? '<span class="pill pill-found">Processed</span>'
    : '<span class="pill pill-category">In process</span>';
  const subtitle = processed
    ? 'Both parties confirmed. This item is marked processed and will no longer appear in open lost/found matching.'
    : (data.message || 'Thanks — we recorded your confirmation. Waiting for the other party.');

  root.classList.remove('hidden');
  root.innerHTML = `
    <div class="contact-modal-backdrop" id="contact-modal-backdrop">
      <div class="contact-modal" role="dialog" aria-modal="true">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px;">
          <div class="contact-modal-title" style="margin:0">${title}</div>
          ${badge}
        </div>
        <div class="contact-modal-sub">${subtitle}</div>

        <div class="contact-detail">
          <div class="contact-detail-label">You confirmed as</div>
          <div class="contact-detail-value">${data.role || 'participant'}</div>
        </div>
        <div class="contact-detail">
          <div class="contact-detail-label">Item</div>
          <div class="contact-detail-value">${data.category || '—'}</div>
        </div>
        <div class="contact-detail">
          <div class="contact-detail-label">Owner confirmation</div>
          <div class="contact-detail-value">${ownerDone ? '✓ Confirmed' : '⏳ Waiting'}</div>
        </div>
        <div class="contact-detail">
          <div class="contact-detail-label">Finder confirmation</div>
          <div class="contact-detail-value">${finderDone ? '✓ Confirmed' : '⏳ Waiting'}</div>
        </div>
        <div class="contact-detail">
          <div class="contact-detail-label">Exchange status</div>
          <div class="contact-detail-value">${data.status || (processed ? 'processed' : 'in_process')}</div>
        </div>

        <div class="contact-modal-actions">
          <button type="button" class="btn-emerald" id="btn-close-contact-modal">
            ${processed ? 'Done — back to AMAlost' : 'Got it — waiting for the other party'}
          </button>
        </div>
      </div>
    </div>`;

  root.querySelector('#btn-close-contact-modal')?.addEventListener('click', () => {
    closeFinderContactModal();
    showView(auth.token ? 'landing' : 'login');
  });
  root.querySelector('#contact-modal-backdrop')?.addEventListener('click', e => {
    if (e.target.id === 'contact-modal-backdrop') {
      closeFinderContactModal();
      showView(auth.token ? 'landing' : 'login');
    }
  });
}

async function resendCoordinationEmails(contact) {
  const btn = document.getElementById('btn-send-finder-email');
  const statusEl = document.getElementById('contact-send-status');
  if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
  if (statusEl) statusEl.textContent = '';

  try {
    const res = await fetch(`${API_BASE}/claim/contact`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        found_item_id: state.match.contact?.found_item_id || contact.found_item_id,
        lost_item_id: state.match.lostItemId,
        email: contact.owner_email || accountEmail() || null,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Failed to send email');

    state.match.contact = {
      ...state.match.contact,
      ...contact,
      mail_mode: data.mail_mode,
      owner_mail_sent: data.owner_mail_sent,
      finder_mail_sent: data.finder_mail_sent,
      owner_email: data.owner_email || contact.owner_email,
      finder_email: data.finder_email || contact.finder_email,
      finder_name: data.finder_name || contact.finder_name,
    };
    if (statusEl) {
      statusEl.textContent = data.mail_mode === 'smtp'
        ? 'Notification emails resent.'
        : 'Saved to server outbox — configure SMTP_HOST for live delivery.';
    }
    openFinderContactModal(state.match.contact);
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Resend notification emails'; }
    if (statusEl) statusEl.textContent = err.message || 'Send failed.';
  }
}

function closeFinderContactModal() {
  const root = document.getElementById('contact-modal-root');
  if (!root) return;
  root.classList.add('hidden');
  root.innerHTML = '';
}

function bindMatchEvents(selectedMatch, matches) {
  const container = document.getElementById('match-container');
  container.querySelector('#match-back-landing')?.addEventListener('click', () => showView('landing'));

  container.querySelector('#btn-this-is-mine')?.addEventListener('click', () => claimCurrentMatch(selectedMatch));
  container.querySelector('#btn-open-contact')?.addEventListener('click', () => openFinderContactModal());
  container.querySelector('#btn-contact-finder')?.addEventListener('click', () => {
    if (state.match.claimMessage && state.match.contact) openFinderContactModal();
  });

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

  container.querySelector('#btn-expand-locations')?.addEventListener('click', () => expandLocationSearch());
}

async function claimCurrentMatch(selectedMatch) {
  const btn = document.getElementById('btn-this-is-mine');
  const errEl = document.getElementById('claim-error');
  const isReverse = state.match.direction === 'found_to_lost';

  const foundItemId = isReverse ? state.match.foundItemId : selectedMatch?.id;
  const lostItemId = isReverse ? selectedMatch?.id : state.match.lostItemId;

  if (!foundItemId || !lostItemId) {
    if (errEl) {
      errEl.textContent = 'Missing report id. Please re-submit the report.';
      errEl.classList.add('visible');
    }
    return;
  }
  if (btn) { btn.disabled = true; btn.textContent = isReverse ? 'Accepting match…' : 'Claiming…'; }
  if (errEl) errEl.classList.remove('visible');

  try {
    const res = await fetch(`${API_BASE}/claim`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        found_item_id: foundItemId,
        lost_item_id: lostItemId,
        email: isReverse
          ? (state.match.foundForm?.email || accountEmail() || null)
          : (state.match.lostForm?.email || accountEmail() || null),
        initiated_by: isReverse ? 'finder' : 'owner',
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : (isReverse ? 'Accept failed' : 'Claim failed'));

    state.match.claimMessage = data.message || data.notify_message || 'Match accepted — in process.';
    state.match.lostItemId = lostItemId;
    state.match.foundItemId = foundItemId;
    state.match.contact = {
      found_item_id: foundItemId,
      claim_id: data.id,
      owner_email: data.owner_email || null,
      finder_email: data.finder_email || null,
      finder_name: data.finder_name || null,
      category: data.category || selectedMatch.category || null,
      found_location: data.found_location || null,
      lost_location: data.lost_location || null,
      pickup_point: data.pickup_point || 'Coordinate a public campus meetup',
      mail_mode: data.mail_mode || 'outbox',
      owner_mail_sent: !!data.owner_mail_sent,
      finder_mail_sent: !!data.finder_mail_sent,
      owner_confirm_url: data.owner_confirm_url || null,
      finder_confirm_url: data.finder_confirm_url || null,
      owner_confirmed: !!data.owner_confirmed,
      finder_confirmed: !!data.finder_confirmed,
      exchange_status: data.exchange_status || data.status || 'in_process',
    };
    renderMatchView();
    openFinderContactModal(state.match.contact);
  } catch (err) {
    const rank = selectedMatch?.rank || ((state.match.selectedIndex || 0) + 1);
    if (btn) {
      btn.disabled = false;
      btn.textContent = isReverse
        ? `✓ Accept match — notify owner (rank #${rank})`
        : `✓ This is mine — claim rank #${rank}`;
    }
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
  container.querySelector('#btn-expand-locations')?.addEventListener('click', () => expandLocationSearch());
}

async function expandSearch() {
  const container = document.getElementById('match-container');
  container.innerHTML = `
    <div class="category-loading" style="margin-top:40px">
      <div class="spinner"></div>
      <div class="category-loading-text">Searching all categories…</div>
    </div>`;
  state.match.expandAll = true;
  await submitLostReport(true, state.match.searchAllLocations);
}

async function expandLocationSearch() {
  const container = document.getElementById('match-container');
  container.innerHTML = `
    <div class="category-loading" style="margin-top:40px">
      <div class="spinner"></div>
      <div class="category-loading-text">Searching all locations…</div>
    </div>`;
  state.match.searchAllLocations = true;
  await submitLostReport(state.match.expandAll, true);
}

/* ─────────────────────── ADMIN QUEUE ─────────────────────── */

const ADMIN_TABS = [
  { id: 'lost', label: 'Lost' },
  { id: 'found', label: 'Found' },
  { id: 'in_process', label: 'In process' },
  { id: 'matched', label: 'Matched' },
];

let adminQueueData = null;
let adminActiveTab = 'lost';

function filterAdminTab(data, tabId) {
  const lost = data.lost_items || [];
  const found = data.found_items || [];
  const claims = data.claims || [];

  if (tabId === 'lost') {
    return lost
      .filter(item => item.status === 'open' || item.status === 'available')
      .map(item => ({ kind: 'lost', ...item }));
  }
  if (tabId === 'found') {
    return found
      .filter(item => item.status === 'available' || item.status === 'open')
      .map(item => ({ kind: 'found', ...item }));
  }
  if (tabId === 'in_process') {
    return [
      ...lost.filter(item => item.status === 'in_process').map(item => ({ kind: 'lost', ...item })),
      ...found.filter(item => item.status === 'in_process').map(item => ({ kind: 'found', ...item })),
      ...claims.filter(c => c.status === 'in_process').map(c => ({ kind: 'claim', ...c })),
    ];
  }
  // matched / completed
  return [
    ...lost.filter(item => item.status === 'processed').map(item => ({ kind: 'lost', ...item })),
    ...found.filter(item => item.status === 'processed').map(item => ({ kind: 'found', ...item })),
    ...claims.filter(c => c.status === 'processed').map(c => ({ kind: 'claim', ...c })),
  ];
}

function adminTabCounts(data) {
  return Object.fromEntries(ADMIN_TABS.map(tab => [tab.id, filterAdminTab(data, tab.id).length]));
}

function renderAdminItemCard(item) {
  const canCancel = item.status === 'in_process';
  const actions = `
    <div class="dash-actions">
      ${canCancel
        ? `<button type="button" class="btn-secondary btn-admin-action" data-admin-cancel="${escapeHTML(item.kind)}" data-id="${escapeHTML(item.id)}">Cancel exchange</button>`
        : ''}
      <button type="button" class="btn-cancel btn-admin-action" data-admin-delete="${escapeHTML(item.kind)}" data-id="${escapeHTML(item.id)}">Delete</button>
    </div>`;

  if (item.kind === 'claim') {
    return `
      <div class="dash-card">
        <div class="dash-thumb">🔗</div>
        <div class="dash-body">
          <div class="dash-card-title">Claim #${escapeHTML(item.id)}</div>
          <div class="dash-card-desc">${escapeHTML(item.notify_message || 'No message')}</div>
          <div class="dash-card-meta">${escapeHTML(item.claimed_by_email || '—')} · lost #${escapeHTML(item.lost_item_id || '—')} · found #${escapeHTML(item.found_item_id || '—')}</div>
          <div class="dash-pills">
            ${statusPill(item.status)}
            <span class="status-pill status-open">owner ${item.owner_confirmed ? '✓' : '…'}</span>
            <span class="status-pill status-open">finder ${item.finder_confirmed ? '✓' : '…'}</span>
          </div>
          ${actions}
        </div>
      </div>`;
  }

  const isLost = item.kind === 'lost';
  const dateLabel = isLost ? (item.date_lost || '—') : (item.date_found || '—');
  const who = isLost ? (item.email || '—') : (item.finder_email || item.reported_by || '—');
  return `
    <div class="dash-card">
      <div class="dash-thumb">${item.image_url
        ? `<img src="${API_BASE}${item.image_url}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:10px"/>`
        : getCategoryEmoji(item.category)}</div>
      <div class="dash-body">
        <div class="dash-card-title">${getCategoryEmoji(item.category)} ${escapeHTML(item.category)} · ${isLost ? 'Lost' : 'Found'} #${escapeHTML(item.id)}</div>
        <div class="dash-card-desc">${escapeHTML(item.description || 'No description')}</div>
        <div class="dash-card-meta">${escapeHTML(item.location || 'Location n/a')} · ${escapeHTML(dateLabel)} · ${escapeHTML(who)}</div>
        <div class="dash-pills">${statusPill(item.status)}</div>
        ${actions}
      </div>
    </div>`;
}

function renderAdminDashboard(data, tabId = adminActiveTab) {
  const container = document.getElementById('admin-container');
  if (!container) return;

  adminQueueData = data;
  adminActiveTab = tabId;
  const counts = adminTabCounts(data);
  const items = filterAdminTab(data, tabId);

  container.innerHTML = `
    <button class="back-link" id="admin-back">← Landing</button>
    <div class="flow-header">
      <div class="flow-eyebrow">Admin</div>
      <div class="flow-title">Campus <span>dashboard</span></div>
      <p class="flow-subtitle">All uploaded items across campus — filter by status. Cancel reopens an exchange; Delete removes the entry.</p>
    </div>
    <div class="admin-tabs" role="tablist">
      ${ADMIN_TABS.map(tab => `
        <button type="button" class="admin-tab ${tab.id === tabId ? 'active' : ''}" data-tab="${tab.id}" role="tab" aria-selected="${tab.id === tabId}">
          ${tab.label}
          <span class="admin-tab-count">${counts[tab.id]}</span>
        </button>`).join('')}
    </div>
    <div class="admin-tab-panel">
      ${items.length
        ? items.map(renderAdminItemCard).join('')
        : '<div class="admin-empty">Nothing in this tab yet.</div>'}
    </div>`;

  document.getElementById('admin-back')?.addEventListener('click', () => showView('landing'));
  container.querySelectorAll('.admin-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const next = btn.getAttribute('data-tab');
      if (next && adminQueueData) renderAdminDashboard(adminQueueData, next);
    });
  });
  container.querySelectorAll('[data-admin-cancel]').forEach(btn => {
    btn.addEventListener('click', () => adminCancelEntry(btn));
  });
  container.querySelectorAll('[data-admin-delete]').forEach(btn => {
    btn.addEventListener('click', () => adminDeleteEntry(btn));
  });
}

async function adminCancelEntry(btn) {
  const kind = btn?.dataset?.adminCancel;
  const id = btn?.dataset?.id;
  if (!kind || !id) return;
  if (!window.confirm('Cancel this in-process exchange? Both linked items will reopen for matching.')) return;

  const body = kind === 'claim'
    ? { claim_id: id }
    : kind === 'lost'
      ? { lost_item_id: id }
      : { found_item_id: id };

  if (btn) { btn.disabled = true; btn.textContent = 'Cancelling…'; }
  try {
    const res = await fetch(`${API_BASE}/admin/claim/cancel`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) { showView('login'); return; }
    if (res.status === 403) { alert('Admin access required.'); return; }
    if (!res.ok) throw new Error(apiErrorMessage(data, 'Could not cancel exchange'));
    await openAdminQueue();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Cancel exchange'; }
    alert(err.message || 'Could not cancel exchange');
  }
}

async function adminDeleteEntry(btn) {
  const kind = btn?.dataset?.adminDelete;
  const id = btn?.dataset?.id;
  if (!kind || !id) return;
  const label = kind === 'claim' ? 'claim' : `${kind} item`;
  if (!window.confirm(`Delete this ${label}? This cannot be undone.`)) return;

  if (btn) { btn.disabled = true; btn.textContent = 'Deleting…'; }
  try {
    const res = await fetch(`${API_BASE}/admin/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) { showView('login'); return; }
    if (res.status === 403) { alert('Admin access required.'); return; }
    if (!res.ok) throw new Error(apiErrorMessage(data, 'Could not delete entry'));
    await openAdminQueue();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Delete'; }
    alert(err.message || 'Could not delete entry');
  }
}

async function openAdminQueue() {
  if (!auth.token) {
    showView('login');
    return;
  }
  if (!isAdminUser()) {
    showView('landing');
    return;
  }

  showView('admin');
  const container = document.getElementById('admin-container');
  if (!container) return;
  container.innerHTML = `
    <div class="category-loading" style="margin-top:24px">
      <div class="spinner"></div>
      <div class="category-loading-text">Loading admin queue…</div>
    </div>`;

  try {
    const res = await fetch(`${API_BASE}/admin/queue`, { headers: authHeaders() });
    if (res.status === 401) { showView('login'); return; }
    if (res.status === 403) {
      container.innerHTML = `
        <button class="back-link" id="admin-back">← Landing</button>
        <div class="error-banner visible">Admin access required.</div>`;
      document.getElementById('admin-back')?.addEventListener('click', () => showView('landing'));
      return;
    }
    if (!res.ok) throw new Error('Failed to load queue');
    const data = await res.json();
    renderAdminDashboard(data, adminActiveTab);
  } catch {
    container.innerHTML = `
      <button class="back-link" id="admin-back">← Landing</button>
      <div class="error-banner visible">Could not load the admin queue. Is the API running?</div>`;
    document.getElementById('admin-back')?.addEventListener('click', () => showView('landing'));
  }
}

/* ─────────────────────── MY DASHBOARD ─────────────────────── */

function escapeHTML(str) {
  return String(str ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function statusPill(status) {
  const label = (status || 'unknown').replace(/_/g, ' ');
  return `<span class="status-pill status-${status || 'unknown'}">${escapeHTML(label)}</span>`;
}

async function openDashboard() {
  showView('dashboard');
  const container = document.getElementById('dashboard-container');
  if (!container) return;
  container.innerHTML = `
    <div class="category-loading" style="margin-top:24px">
      <div class="spinner"></div>
      <div class="category-loading-text">Loading your items…</div>
    </div>`;

  try {
    const res = await fetch(`${API_BASE}/me/dashboard`, { headers: authHeaders() });
    if (res.status === 401) { showView('login'); return; }
    if (!res.ok) throw new Error('Failed to load dashboard');
    const data = await res.json();
    renderDashboard(data);
  } catch {
    container.innerHTML = `
      <button class="back-link" id="dash-back">← Back</button>
      <div class="error-banner visible">Could not load your items. Is the API running?</div>`;
    document.getElementById('dash-back')?.addEventListener('click', () => showView('landing'));
  }
}

function renderDashboard(data) {
  const container = document.getElementById('dashboard-container');
  if (!container) return;

  const lost = data.lost_items || [];
  const found = data.found_items || [];
  const claims = data.claims || [];

  const lostCards = lost.length ? lost.map(item => `
    <div class="dash-card">
      <div class="dash-thumb">${item.image_url
        ? `<img src="${API_BASE}${item.image_url}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:10px"/>`
        : getCategoryEmoji(item.category)}</div>
      <div class="dash-body">
        <div class="dash-card-title">${getCategoryEmoji(item.category)} ${escapeHTML(item.category)}</div>
        <div class="dash-card-desc">${escapeHTML(item.description || 'No description')}</div>
        <div class="dash-card-meta">${escapeHTML(item.location || 'Location n/a')} · ${escapeHTML(item.date_lost || '—')}</div>
        <div class="dash-pills">${statusPill(item.status)}</div>
      </div>
    </div>`).join('') : '<div class="admin-empty">You haven\'t reported any lost items yet.</div>';

  const foundCards = found.length ? found.map(item => `
    <div class="dash-card">
      <div class="dash-thumb">${item.image_url
        ? `<img src="${API_BASE}${item.image_url}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:10px"/>`
        : getCategoryEmoji(item.category)}</div>
      <div class="dash-body">
        <div class="dash-card-title">${getCategoryEmoji(item.category)} ${escapeHTML(item.category)}</div>
        <div class="dash-card-desc">${escapeHTML(item.description || 'No description')}</div>
        <div class="dash-card-meta">${escapeHTML(item.location || 'Location n/a')} · ${escapeHTML(item.date_found || '—')}</div>
        <div class="dash-pills">${statusPill(item.status)}</div>
      </div>
    </div>`).join('') : '<div class="admin-empty">You haven\'t reported any found items yet.</div>';

  const claimCards = claims.length ? claims.map(claim => {
    const confirmFlags = `
      <span class="confirm-flag">Owner ${claim.owner_confirmed ? '<span class="yes">✓</span>' : '<span class="no">pending</span>'}</span>
      <span class="confirm-flag">Finder ${claim.finder_confirmed ? '<span class="yes">✓</span>' : '<span class="no">pending</span>'}</span>`;
    const youConfirmed = claim.role === 'owner' ? claim.owner_confirmed : claim.finder_confirmed;
    const actions = claim.can_cancel ? `
      <div class="dash-actions">
        ${!youConfirmed ? `<button type="button" class="btn-confirm-exchange" data-claim-confirm="${claim.id}" data-role="${claim.role}">Confirm exchange done</button>` : ''}
        <button type="button" class="btn-cancel" data-claim-cancel="${claim.id}">Cancel exchange</button>
      </div>` : '';
    return `
    <div class="dash-card">
      <div class="dash-thumb">${getCategoryEmoji(claim.category)}</div>
      <div class="dash-body">
        <div class="dash-card-title">${getCategoryEmoji(claim.category)} ${escapeHTML(claim.category || 'Item')}</div>
        <div class="dash-card-meta">You are the <strong>${escapeHTML(claim.role)}</strong> · with ${escapeHTML(claim.counterpart_email || 'unknown')}</div>
        <div class="dash-pills">${statusPill(claim.status)} ${confirmFlags}</div>
        ${actions}
      </div>
    </div>`;
  }).join('') : '<div class="admin-empty">No active or past matches yet.</div>';

  container.innerHTML = `
    <button class="back-link" id="dash-back">← Back</button>
    <div class="flow-header">
      <div class="flow-eyebrow">Signed in as ${escapeHTML(data.email || '')}</div>
      <div class="flow-title">My <span>items</span></div>
      <p class="flow-subtitle">Your reports and matches. You can cancel an in-process exchange to reopen both items.</p>
    </div>

    <div class="dash-section">
      <div class="dash-section-head"><div class="dash-section-title">Active & past matches</div><div class="dash-section-count">${claims.length}</div></div>
      ${claimCards}
    </div>
    <div class="dash-section">
      <div class="dash-section-head"><div class="dash-section-title">My lost reports</div><div class="dash-section-count">${lost.length}</div></div>
      ${lostCards}
    </div>
    <div class="dash-section">
      <div class="dash-section-head"><div class="dash-section-title">My found reports</div><div class="dash-section-count">${found.length}</div></div>
      ${foundCards}
    </div>`;

  document.getElementById('dash-back')?.addEventListener('click', () => showView('landing'));
  container.querySelectorAll('[data-claim-cancel]').forEach(btn => {
    btn.addEventListener('click', () => cancelClaimFromDashboard(btn.dataset.claimCancel, btn));
  });
  container.querySelectorAll('[data-claim-confirm]').forEach(btn => {
    btn.addEventListener('click', () => confirmFromDashboard(btn.dataset.claimConfirm, btn));
  });
}

async function cancelClaimFromDashboard(claimId, btn) {
  if (!claimId) return;
  if (!window.confirm('Cancel this exchange? Both items will reopen for matching and both parties will be emailed.')) return;
  if (btn) { btn.disabled = true; btn.textContent = 'Cancelling…'; }
  try {
    const res = await fetch(`${API_BASE}/claim/cancel`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ claim_id: claimId }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Cancel failed');
    openDashboard();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Cancel exchange'; }
    window.alert(err.message || 'Could not cancel this exchange.');
  }
}

async function confirmFromDashboard(claimId, btn) {
  if (!claimId) return;
  if (!window.confirm('Confirm that you completed this exchange? The item is marked processed once both parties confirm.')) return;
  if (btn) { btn.disabled = true; btn.textContent = 'Confirming…'; }
  try {
    const res = await fetch(`${API_BASE}/claim/confirm-auth`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ claim_id: claimId }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Confirm failed');
    window.alert(data.message || 'Confirmation recorded.');
    openDashboard();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Confirm exchange done'; }
    window.alert(err.message || 'Could not confirm this exchange.');
  }
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
    <div class="auth-logo" id="login-brand-logo">AMA<span>lost</span></div>
    <div class="form-card">
      <div class="flow-eyebrow">Welcome back</div>
      <div class="flow-title" style="margin-bottom:18px">Sign in to AMAlost</div>
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
    goHome();
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
    const modeNote = state.register.mailMode === 'outbox'
      ? 'Dev mode: email was written to the server outbox (SMTP not used).'
      : state.register.mailSent
        ? 'A verification email is on its way — check inbox and spam.'
        : 'We tried to send a verification email. If it does not arrive, use the link below or resend.';
    return `
      <div class="auth-logo" id="register-brand-logo">AMA<span>lost</span></div>
      <div class="success-state">
        <div class="success-check">✓</div>
        <div class="success-title">Check your email</div>
        <div class="success-sub">We sent a verification link to <strong>${escapeHTML(state.register.successEmail)}</strong>. You must verify before signing in.</div>
        <p class="bottom-note" style="margin-bottom:16px">${modeNote}</p>
        <button type="button" class="btn-primary" id="btn-resend-verify" style="margin-bottom:12px">Resend verification email</button>
        ${state.register.verifyUrl ? `
          <p class="bottom-note" style="margin-bottom:12px">Demo fallback — open verify link directly:</p>
          <button type="button" class="btn-text" id="btn-open-verify" style="margin-bottom:16px">Verify email →</button>
        ` : ''}
        <button type="button" class="btn-text" id="btn-register-to-login">Back to sign in</button>
        <div class="error-banner" id="register-error" style="margin-top:14px"></div>
      </div>
    `;
  }

  return `
    <div class="auth-logo" id="register-brand-logo">AMA<span>lost</span></div>
    <div class="form-card">
      <div class="flow-eyebrow">Join AMAlost</div>
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
    state.register.mailMode = null;
    state.register.mailSent = false;
    showView('login');
  });
  el.querySelector('#btn-register-to-login')?.addEventListener('click', () => {
    state.register.successEmail = null;
    state.register.verifyUrl = null;
    state.register.mailMode = null;
    state.register.mailSent = false;
    showView('login');
  });
  el.querySelector('#btn-open-verify')?.addEventListener('click', () => {
    if (state.register.verifyUrl) window.open(state.register.verifyUrl, '_blank');
  });
  el.querySelector('#btn-resend-verify')?.addEventListener('click', () => resendVerificationEmail());
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

async function resendVerificationEmail() {
  const email = state.register.successEmail;
  const errEl = document.getElementById('register-error');
  const btn = document.getElementById('btn-resend-verify');
  if (!email) return;
  if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
  errEl?.classList.remove('visible');
  try {
    const res = await fetch(`${API_BASE}/auth/resend-verification`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorMessage(data, 'Could not resend verification'));
    state.register.verifyUrl = data.dev_verify_url || state.register.verifyUrl;
    state.register.mailMode = data.mail_mode || state.register.mailMode;
    state.register.mailSent = !!data.mail_sent;
    renderRegister();
    window.alert(data.message || 'Verification email resent.');
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Resend verification email'; }
    if (errEl) {
      errEl.textContent = err.message || 'Could not resend verification.';
      errEl.classList.add('visible');
    }
  }
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
    state.register.mailMode = data.mail_mode || null;
    state.register.mailSent = !!data.mail_sent;
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
  handleVerifyQueryParam();
  handleConfirmQueryParam();

  document.getElementById('btn-start-lost')?.addEventListener('click', startLostFlow);
  document.getElementById('btn-start-found')?.addEventListener('click', startFoundFlow);
  document.getElementById('btn-cta-lost')?.addEventListener('click', startLostFlow);
  document.getElementById('btn-cta-found')?.addEventListener('click', startFoundFlow);
  document.getElementById('nav-logo-landing')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-lost')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-found')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-match')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-admin')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-dashboard')?.addEventListener('click', () => showView('landing'));
  document.getElementById('nav-logo-login')?.addEventListener('click', () => {
    if (auth.token) showView('landing');
  });
  document.getElementById('nav-logo-register')?.addEventListener('click', () => {
    if (auth.token) showView('landing');
  });

  if (auth.token) goHome();
  else showView('login');
});
