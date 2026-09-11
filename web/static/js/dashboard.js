/**
 * AutoRestock-V2 Enterprise Minimalist Operations Center
 * Features: Left-Sided Resizable Data Sidebar, Interactive AI Command Center, In-App PDF Previewer, Real-Time DuckDB Sync.
 */

const state = {
  stats: {},
  items: [],
  categories: [],
  prs: [],
  currentModalPrNumber: null,
  isResizing: false
};

function getEffectiveTenant() {
  const rawTenant = (sessionStorage.getItem('tenant_id') || '').toUpperCase().trim();
  const rawUsername = (sessionStorage.getItem('username') || '').toLowerCase().trim();

  if (rawUsername === 'usera' || rawTenant === 'INVENTORY' || rawTenant === 'TENANT_A') {
    return 'INVENTORY';
  }
  if (rawUsername === 'userb' || rawTenant === 'HR' || rawTenant === 'TENANT_B') {
    return 'HR';
  }
  if (rawUsername === 'userc' || rawTenant === 'FINANCE' || rawTenant === 'TENANT_C') {
    return 'FINANCE';
  }
  return 'ALL';
}

document.addEventListener('DOMContentLoaded', () => {
  const uName = sessionStorage.getItem('username');
  const uRole = sessionStorage.getItem('role');
  const effectiveTenant = getEffectiveTenant();

  if (uName) {
    const el = document.getElementById('displayUsername');
    if (el) el.textContent = uName;
  }
  const elTenant = document.getElementById('displayTenant');
  if (elTenant) {
    elTenant.textContent = effectiveTenant;
  }
  if (uRole === 'ADMIN' || (uName && uName.toLowerCase() === 'admin')) {
    window.location.href = '/static/admin.html';
    return;
  }

  // Set initial sidebar toggle button text
  const isCollapsed = document.body.classList.contains('sidebar-collapsed');
  const btnText = document.getElementById('toggleSidebarText');
  if (btnText) {
    btnText.textContent = isCollapsed ? 'Katalog & Data' : 'Tutup Sidebar';
  }

  initSidebarResizer();
  restoreUiCustomizations();
  restoreCopilotFeed();
  applyTenantSecurityAndPersonalization();
  initPromptInputAutoResize();
  loadAllData();
  
  // Real-time synchronization (10s interval + instant refresh on window focus)
  setInterval(loadAllData, 10000);
  window.addEventListener('focus', () => loadAllData());
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) loadAllData();
  });
});

// Logout Helper
function logoutSession() {
  sessionStorage.clear();
  localStorage.clear();
  window.location.href = '/static/login.html';
}

// Override fetch to inject Auth Headers automatically
const originalFetch = window.fetch;
window.fetch = async function(resource, config = {}) {
  const token = sessionStorage.getItem('access_token');
  let headers = {};

  if (resource instanceof Request) {
    resource.headers.forEach((val, key) => { headers[key] = val; });
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const newReq = new Request(resource, { headers });
    return await originalFetch(newReq);
  }

  if (config.headers instanceof Headers) {
    headers = new Headers(config.headers);
    if (token) headers.set('Authorization', `Bearer ${token}`);
  } else if (config.headers && typeof config.headers === 'object') {
    headers = { ...config.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
  } else {
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  const newConfig = { ...config, headers };
  const res = await originalFetch(resource, newConfig);
  if (res.status === 401 && !window.location.pathname.includes('login.html')) {
    sessionStorage.clear();
    localStorage.clear();
    window.location.href = '/static/login.html';
  }
  return res;
};

// --- Left-Sided Resizable Sidebar Splitter Logic (Drag to Resize / Slide to Left) ---
function initSidebarResizer() {
  const resizer = document.getElementById('sidebarResizer');
  const sidebar = document.getElementById('dataSidebar');
  if (!resizer || !sidebar) return;

  // Restore saved width from localStorage (defaulting comfortably to 580px for multi-column data)
  const savedWidth = localStorage.getItem('ar_sidebar_width');
  if (savedWidth && !isNaN(Number(savedWidth))) {
    const w = Math.max(520, Math.min(window.innerWidth * 0.85, Number(savedWidth)));
    document.documentElement.style.setProperty('--sidebar-width', `${w}px`);
  } else {
    document.documentElement.style.setProperty('--sidebar-width', '580px');
  }

  let startX = 0;
  let startWidth = 0;

  const onMouseDown = (e) => {
    state.isResizing = true;
    startX = e.clientX;
    startWidth = sidebar.getBoundingClientRect().width;
    resizer.classList.add('is-dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const onMouseMove = (e) => {
    if (!state.isResizing) return;
    // Since sidebar is on the LEFT, dragging mouse right increases width, dragging left decreases width
    const deltaX = e.clientX - startX;
    let newWidth = startWidth + deltaX;

    // Minimum collapse threshold (slide left into hidden state)
    if (newWidth < 240) {
      closeDataSidebar();
      return;
    }

    // Constraints: min 360px, max 85% of screen width (max 1100px)
    newWidth = Math.max(360, Math.min(window.innerWidth * 0.85, Math.min(1100, newWidth)));

    document.body.classList.remove('sidebar-collapsed');
    const btnText = document.getElementById('toggleSidebarText');
    if (btnText) btnText.textContent = 'Tutup Sidebar';

    document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
    localStorage.setItem('ar_sidebar_width', newWidth);
  };

  const onMouseUp = () => {
    if (!state.isResizing) return;
    state.isResizing = false;
    resizer.classList.remove('is-dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';

    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
  };

  resizer.addEventListener('mousedown', onMouseDown);
}

function toggleExpandSidebar() {
  const sidebar = document.getElementById('dataSidebar');
  const btn = document.getElementById('btnExpandSidebar');
  if (!sidebar) return;

  const isExpanded = sidebar.classList.contains('sidebar-maximized');
  if (isExpanded) {
    sidebar.classList.remove('sidebar-maximized');
    const prevWidth = localStorage.getItem('ar_sidebar_prev_width') || '580';
    document.documentElement.style.setProperty('--sidebar-width', `${prevWidth}px`);
    if (btn) btn.title = 'Perlebar / Maksimalkan Panel';
  } else {
    const currentWidth = sidebar.getBoundingClientRect().width;
    localStorage.setItem('ar_sidebar_prev_width', currentWidth);
    sidebar.classList.add('sidebar-maximized');
    const targetWidth = Math.min(window.innerWidth * 0.75, 920);
    document.documentElement.style.setProperty('--sidebar-width', `${targetWidth}px`);
    if (btn) btn.title = 'Kembalikan Ukuran Panel';
  }
}

function restoreUiCustomizations() {
  try {
    const customUi = JSON.parse(localStorage.getItem('ar_ui_custom') || '{}');
    for (const [id, label] of Object.entries(customUi)) {
      const el = document.getElementById(id);
      if (el) el.textContent = label;
    }
  } catch (e) {
    console.error("Failed to restore UI customizations:", e);
  }
}

// --- Chat History Persistence in LocalStorage ---
function saveCopilotFeed() {
  const feed = document.getElementById('copilotFeed');
  const container = document.getElementById('geminiChatContainer');
  if (feed) {
    localStorage.setItem('ar_copilot_feed', feed.innerHTML);
    if (container) {
      if (feed.children.length === 0) {
        container.classList.add('is-empty-state');
      } else {
        container.classList.remove('is-empty-state');
      }
    }
  }
}

function restoreCopilotFeed() {
  let saved = localStorage.getItem('ar_copilot_feed');
  const feed = document.getElementById('copilotFeed');
  const container = document.getElementById('geminiChatContainer');
  if (saved && feed && saved.trim().length > 0) {
    feed.innerHTML = saved;
    feed.scrollTop = feed.scrollHeight;
    if (container) container.classList.remove('is-empty-state');
  } else {
    if (container) container.classList.add('is-empty-state');
  }
}

function clearCopilotFeed() {
  const feed = document.getElementById('copilotFeed');
  const container = document.getElementById('geminiChatContainer');
  if (feed) {
    feed.innerHTML = '';
    localStorage.removeItem('ar_copilot_feed');
  }
  if (container) {
    container.classList.add('is-empty-state');
  }
  showToast("Riwayat aktivitas telah dibersihkan", "info");
}

// --- Left Sidebar Controls ---
function toggleDataSidebar() {
  const isCollapsed = document.body.classList.toggle('sidebar-collapsed');
  const btnText = document.getElementById('toggleSidebarText');
  if (btnText) {
    btnText.textContent = isCollapsed ? 'Katalog & Data' : 'Tutup Sidebar';
  }
}

function openDataSidebar(tabId) {
  document.body.classList.remove('sidebar-collapsed');
  const btnText = document.getElementById('toggleSidebarText');
  if (btnText) btnText.textContent = 'Tutup Sidebar';
  if (tabId) switchCanvasTab(tabId);
}

function closeDataSidebar() {
  document.body.classList.add('sidebar-collapsed');
  const btnText = document.getElementById('toggleSidebarText');
  if (btnText) btnText.textContent = 'Katalog & Data';
}

// --- Tenant Security & UI Personalization ---
function applyTenantSecurityAndPersonalization() {
  const tenant = getEffectiveTenant();
  const username = sessionStorage.getItem('username') || 'User';

  const pillInv = document.getElementById('modPillInventory');
  const pillHr = document.getElementById('modPillHr');
  const pillFin = document.getElementById('modPillFinance');

  const tabInv = document.getElementById('sidebarTabInventory');
  const tabHr = document.getElementById('sidebarTabHr');
  const tabFin = document.getElementById('sidebarTabFinance');
  const tabPrs = document.getElementById('sidebarTabPrs');
  const tabPos = document.getElementById('sidebarTabPos');
  const tabTerminal = document.getElementById('sidebarTabTerminal');

  const heroTitle = document.getElementById('heroTitle');
  const heroSubtitle = document.getElementById('heroSubtitle');
  const promptInput = document.getElementById('promptInput');
  const inputHint = document.getElementById('inputHintText');

  if (tenant === 'INVENTORY') {
    // Hide HR & Finance from header and sidebar
    if (pillHr) pillHr.style.display = 'none';
    if (pillFin) pillFin.style.display = 'none';
    if (pillInv) pillInv.style.display = 'inline-flex';

    if (tabHr) tabHr.style.display = 'none';
    if (tabFin) tabFin.style.display = 'none';
    if (tabInv) tabInv.style.display = 'inline-flex';
    if (tabPrs) tabPrs.style.display = 'inline-flex';
    if (tabPos) tabPos.style.display = 'inline-flex';
    if (tabTerminal) tabTerminal.style.display = 'inline-flex';

    if (heroTitle) heroTitle.textContent = 'Inventory & Logistics Command Center';
    if (heroSubtitle) heroSubtitle.textContent = `Selamat datang, ${username}. Panel operasional terisolasi material menara telekomunikasi, kabel fiber optic, monitoring saldo gudang regional, serta alur pengadaan barang PT Bali Towerindo Sentra Tbk.`;
    if (promptInput) promptInput.placeholder = 'Tanyakan stok material menara, catat penerimaan PO tiba (contoh: PO-2026-006 sudah sampai di Bandung), atau buat PR...';
    if (inputHint) inputHint.textContent = 'Akses Terisolasi: Divisi Inventory & Logistik Material Menara/FO (DuckDB Live Sync)';

    switchCanvasTab('canvas-inventory');
  } else if (tenant === 'HR') {
    // Hide Inventory & Finance from header and sidebar
    if (pillInv) pillInv.style.display = 'none';
    if (pillFin) pillFin.style.display = 'none';
    if (pillHr) pillHr.style.display = 'inline-flex';

    if (tabInv) tabInv.style.display = 'none';
    if (tabFin) tabFin.style.display = 'none';
    if (tabPrs) tabPrs.style.display = 'none';
    if (tabPos) tabPos.style.display = 'none';
    if (tabHr) tabHr.style.display = 'inline-flex';
    if (tabTerminal) tabTerminal.style.display = 'inline-flex';

    if (heroTitle) heroTitle.textContent = 'HR & Field Workforce Command Center';
    if (heroSubtitle) heroSubtitle.textContent = `Selamat datang, ${username}. Panel manajemen ketenagakerjaan teknisi lapangan, kualifikasi sertifikat K3 TKPK rigger, rekap jam lembur, dan pengajuan cuti PT Bali Towerindo Sentra Tbk.`;
    if (promptInput) promptInput.placeholder = 'Ajukan cuti teknisi, cari personil bersertifikat K3 TKPK, atau cek lowongan kerja...';
    if (inputHint) inputHint.textContent = 'Akses Terisolasi: Divisi Human Resources & Field Operations';

    switchCanvasTab('canvas-hr');
  } else if (tenant === 'FINANCE') {
    // Hide Inventory & HR from header and sidebar
    if (pillInv) pillInv.style.display = 'none';
    if (pillHr) pillHr.style.display = 'none';
    if (pillFin) pillFin.style.display = 'inline-flex';

    if (tabInv) tabInv.style.display = 'none';
    if (tabHr) tabHr.style.display = 'none';
    if (tabPrs) tabPrs.style.display = 'none';
    if (tabPos) tabPos.style.display = 'none';
    if (tabFin) tabFin.style.display = 'inline-flex';
    if (tabTerminal) tabTerminal.style.display = 'inline-flex';

    if (heroTitle) heroTitle.textContent = 'Finance & Telecom Billing Command Center';
    if (heroSubtitle) heroSubtitle.textContent = `Selamat datang, ${username}. Panel rekonsiliasi keuangan, penagihan invoice sewa menara ke operator telekomunikasi, kontrak MLA, sewa lahan site, dan utilitas listrik PT Bali Towerindo Sentra Tbk.`;
    if (promptInput) promptInput.placeholder = 'Cek invoice jatuh tempo operator, rincian biaya PLN site, atau mutasi kas...';
    if (inputHint) inputHint.textContent = 'Akses Terisolasi: Divisi Finance, Billing & Accounting';

    switchCanvasTab('canvas-finance');
  } else {
    // Admin or Multi-Tenant (ALL)
    if (pillInv) pillInv.style.display = 'inline-flex';
    if (pillHr) pillHr.style.display = 'inline-flex';
    if (pillFin) pillFin.style.display = 'inline-flex';

    if (tabInv) tabInv.style.display = 'inline-flex';
    if (tabHr) tabHr.style.display = 'inline-flex';
    if (tabFin) tabFin.style.display = 'inline-flex';
    if (tabPrs) tabPrs.style.display = 'inline-flex';
    if (tabPos) tabPos.style.display = 'inline-flex';
    if (tabTerminal) tabTerminal.style.display = 'inline-flex';

    if (heroTitle) heroTitle.textContent = 'Bali Tower Operations Command Center';
    if (heroSubtitle) heroSubtitle.textContent = 'Pusat komando terpadu PT Bali Towerindo Sentra Tbk. Akses komprehensif ke seluruh 18 basis data operasional: Inventaris Menara & FO, Ketenagakerjaan & K3 Lapangan, serta Keuangan & Billing Operator.';
    if (promptInput) promptInput.placeholder = 'Ketik instruksi atau pertanyaan analisis operasional enterprise...';
    if (inputHint) inputHint.textContent = 'Hak Akses Administrator Enterprise: Terhubung ke seluruh 18 basis data operasional DuckDB';

    switchCanvasTab('canvas-inventory');
  }
}

// --- Tab Switching ---
function switchCanvasTab(tabId) {
  const tenant = getEffectiveTenant();

  // Strict guard against navigating to unauthorized tabs for tenant-specific users
  if (tenant === 'INVENTORY' && ['canvas-hr', 'canvas-finance'].includes(tabId)) {
    tabId = 'canvas-inventory';
  } else if (tenant === 'HR' && ['canvas-inventory', 'canvas-finance', 'canvas-prs', 'canvas-pos'].includes(tabId)) {
    tabId = 'canvas-hr';
  } else if (tenant === 'FINANCE' && ['canvas-inventory', 'canvas-hr', 'canvas-prs', 'canvas-pos'].includes(tabId)) {
    tabId = 'canvas-finance';
  }

  document.querySelectorAll('.sidebar-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-target') === tabId);
  });

  document.querySelectorAll('.canvas-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === tabId);
  });

  // Update header quick pills
  document.querySelectorAll('.mod-pill').forEach(pill => {
    const fn = pill.getAttribute('onclick') || '';
    pill.classList.toggle('active', fn.includes(tabId));
  });

  if (tabId === 'canvas-inventory') {
    loadInventoryItems();
    loadStockBalances();
  } else if (tabId === 'canvas-hr') {
    loadHrData();
    loadEmployees();
  } else if (tabId === 'canvas-finance') {
    loadFinanceData();
    loadClients();
  } else if (tabId === 'canvas-prs') {
    loadApprovals();
  } else if (tabId === 'canvas-pos') {
    loadPurchaseOrders();
  }
}

// --- Sub-Tab Switching ---
function switchInvSubTab(subTabId) {
  document.querySelectorAll('#canvas-inventory .sub-tab-btn').forEach(btn => {
    btn.classList.toggle('active', (btn.getAttribute('onclick') || '').includes(subTabId));
  });
  document.querySelectorAll('#canvas-inventory .sub-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === subTabId);
  });

  if (subTabId === 'sub-inv-items') loadInventoryItems();
  else if (subTabId === 'sub-inv-balances') loadStockBalances();
  else if (subTabId === 'sub-inv-warehouses') loadWarehouses();
  else if (subTabId === 'sub-inv-suppliers') loadSuppliers();
}

function switchHrSubTab(subTabId) {
  document.querySelectorAll('#canvas-hr .sub-tab-btn').forEach(btn => {
    btn.classList.toggle('active', (btn.getAttribute('onclick') || '').includes(subTabId));
  });
  document.querySelectorAll('#canvas-hr .sub-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === subTabId);
  });

  if (subTabId === 'sub-hr-employees') loadEmployees();
  else if (subTabId === 'sub-hr-leaves') loadHrData();
  else if (subTabId === 'sub-hr-candidates') loadHrData();
  else if (subTabId === 'sub-hr-jobs') loadJobPostings();
}

function switchFinSubTab(subTabId) {
  document.querySelectorAll('#canvas-finance .sub-tab-btn').forEach(btn => {
    btn.classList.toggle('active', (btn.getAttribute('onclick') || '').includes(subTabId));
  });
  document.querySelectorAll('#canvas-finance .sub-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === subTabId);
  });

  if (subTabId === 'sub-fin-invoices') loadFinanceData();
  else if (subTabId === 'sub-fin-clients') loadClients();
  else if (subTabId === 'sub-fin-mla') loadMlaContracts();
  else if (subTabId === 'sub-fin-leases') loadLandLeases();
  else if (subTabId === 'sub-fin-utilities') loadSiteUtilities();
}

// --- Visual Refresh Button Animation ---
async function triggerVisualRefresh(btnId, callback) {
  const btn = document.getElementById(btnId);
  const icon = btn ? btn.querySelector('.refresh-icon, svg') : null;

  if (icon) icon.classList.add('spin-icon');
  if (btn) btn.disabled = true;

  try {
    await callback();
    showToast("Data berhasil diperbarui", "success");
  } catch (e) {
    showToast("Gagal memperbarui data", "error");
  } finally {
    if (icon) icon.classList.remove('spin-icon');
    if (btn) btn.disabled = false;
  }
}

// --- Categories ---
async function loadCategories() {
  try {
    if (state.items && state.items.length > 0) {
      const cats = new Set(state.items.map(it => it.category));
      state.categories = Array.from(cats).filter(Boolean);
      renderCategoryOptions();
    }
  } catch (e) {
    console.error("Failed to load categories:", e);
  }
}

function renderCategoryOptions() {
  const select = document.getElementById('filterCategory');
  if (!select) return;
  const currentVal = select.value;

  select.innerHTML = `<option value="">Semua Kategori</option>` + (state.categories || []).map(c => {
    return `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`;
  }).join('');

  if (currentVal && state.categories.includes(currentVal)) {
    select.value = currentVal;
  }
}

// --- Data Fetching (Multi-Domain & Tenant Isolated) ---
async function loadAllData() {
  const tenant = getEffectiveTenant();

  if (tenant === 'INVENTORY') {
    await Promise.allSettled([
      loadInventoryItems(),
      loadStockBalances(),
      loadWarehouses(),
      loadSuppliers(),
      loadPurchaseOrders(),
      loadApprovals(),
      loadDashboardStats()
    ]);
    await loadCategories();
  } else if (tenant === 'HR') {
    await Promise.allSettled([
      loadHrData(),
      loadEmployees(),
      loadJobPostings(),
      loadSites()
    ]);
  } else if (tenant === 'FINANCE') {
    await Promise.allSettled([
      loadFinanceData(),
      loadClients(),
      loadMlaContracts(),
      loadLandLeases(),
      loadSiteUtilities(),
      loadCoa()
    ]);
  } else {
    // Admin / Multi-Tenant: load all 18 tables across all domains!
    await Promise.allSettled([
      loadInventoryItems(),
      loadStockBalances(),
      loadWarehouses(),
      loadSuppliers(),
      loadPurchaseOrders(),
      loadApprovals(),
      loadDashboardStats(),
      loadHrData(),
      loadEmployees(),
      loadJobPostings(),
      loadSites(),
      loadFinanceData(),
      loadClients(),
      loadMlaContracts(),
      loadLandLeases(),
      loadSiteUtilities(),
      loadCoa()
    ]);
    await loadCategories();
  }
}

// ==============================================================================
// DOMAIN 1: INVENTORY & LOGISTICS LOADERS
// ==============================================================================

function updateSidebarRowCount(count, label) {
  const el = document.getElementById('sidebarRowCountInfo');
  if (el) {
    el.textContent = `${count} ${label}`;
  }
}

async function loadStockBalances() {
  const tbody = document.getElementById('invBalancesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/inventory/stock-balances?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      state.stockBalances = data || [];
      filterBalancesTable();
    }
  } catch (e) {
    console.error("Failed to load stock balances:", e);
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 24px; color: #DC2626;">Gagal memuat saldo gudang.</td></tr>`;
    }
  }
}

function renderStockBalancesTable(data) {
  const tbody = document.getElementById('invBalancesTableBody');
  if (!tbody) return;
  updateSidebarRowCount(data ? data.length : 0, 'Data Saldo Gudang');
  if (!data || data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 24px; color: var(--text-muted);">Tidak ada data saldo gudang yang cocok.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.map(b => {
    let statusBadge = 'badge-normal';
    let statusText = 'NORMAL';
    if (b.stock_status === 'CRITICAL') {
      statusBadge = 'badge-out_of_stock';
      statusText = 'KRITIS';
    } else if (b.stock_status === 'LOW_STOCK') {
      statusBadge = 'badge-low_stock';
      statusText = 'MENIPIS';
    }
    return `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(b.balance_id)}</td>
        <td><strong>${escapeHtml(b.item_name)}</strong><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${escapeHtml(b.item_code)}</span></td>
        <td><strong>${escapeHtml(b.warehouse_name)}</strong></td>
        <td><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(b.region)}</span></td>
        <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #0F172A;">${Number(b.quantity_on_hand).toLocaleString('id-ID')} <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">${escapeHtml(b.unit || 'pcs')}</span></td>
        <td class="text-right" style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${Number(b.quantity_reserved || 0).toLocaleString('id-ID')}</td>
        <td class="text-right" style="font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: #D97706;">${Number(b.reorder_point).toLocaleString('id-ID')}</td>
        <td class="text-center"><span class="badge ${statusBadge}">${statusText}</span></td>
        <td class="text-center" style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(b.last_stock_take_date || '-')}</td>
      </tr>
    `;
  }).join('');
}

function filterBalancesTable() {
  const search = (document.getElementById('searchBalances')?.value || '').toLowerCase().trim();
  const status = document.getElementById('filterBalanceStatus')?.value || '';

  const list = state.stockBalances || [];
  const filtered = list.filter(b => {
    const matchSearch = !search ||
      (b.item_name || '').toLowerCase().includes(search) ||
      (b.item_code || '').toLowerCase().includes(search) ||
      (b.warehouse_name || '').toLowerCase().includes(search) ||
      (b.region || '').toLowerCase().includes(search) ||
      (b.balance_id || '').toLowerCase().includes(search);

    let matchStatus = true;
    if (status === 'CRITICAL') matchStatus = (b.stock_status === 'CRITICAL');
    else if (status === 'LOW') matchStatus = (b.stock_status === 'LOW_STOCK');
    else if (status === 'NORMAL') matchStatus = (b.stock_status === 'NORMAL');

    return matchSearch && matchStatus;
  });

  renderStockBalancesTable(filtered);
}

async function loadWarehouses() {
  const tbody = document.getElementById('invWarehousesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/inventory/warehouses?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--text-muted);">Belum ada data gudang logistik.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(w => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11.5px; font-weight: 700; color: #2563EB;">${escapeHtml(w.warehouse_id)}</td>
          <td><strong>${escapeHtml(w.warehouse_name)}</strong></td>
          <td><span style="font-size: 11px; background: #EFF6FF; color: #1E40AF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${escapeHtml(w.warehouse_type)}</span></td>
          <td>${escapeHtml(w.region)}</td>
          <td style="font-size: 11px; color: #334155; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(w.address)}">${escapeHtml(w.address)}</td>
          <td class="text-right" style="font-family: var(--font-mono); font-weight: 700;">${Number(w.capacity_sqm).toLocaleString('id-ID')} m²</td>
          <td class="text-center"><span class="badge ${w.status === 'ACTIVE' ? 'badge-approved' : 'badge-pending'}">${escapeHtml(w.status)}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load warehouses:", e);
  }
}

async function loadSuppliers() {
  const tbody = document.getElementById('invSuppliersTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/inventory/suppliers?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--text-muted);">Belum ada rekanan supplier.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(s => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(s.supplier_id)}</td>
          <td><strong>${escapeHtml(s.supplier_name)}</strong></td>
          <td><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(s.category)}</span></td>
          <td>${escapeHtml(s.contact_person || '-')}</td>
          <td style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">${escapeHtml(s.phone || '-')}<br>${escapeHtml(s.email || '-')}</td>
          <td class="text-center"><span style="font-weight: 800; color: #D97706; font-family: var(--font-mono);">${s.rating}</span> / 5.0</td>
          <td class="text-center"><span style="font-size: 11px; background: #EFF6FF; color: #1E40AF; padding: 2px 6px; border-radius: 4px;">${escapeHtml(s.payment_terms)}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load suppliers:", e);
  }
}

async function loadPurchaseOrders() {
  const tbodyTop = document.getElementById('topPosTableBody');
  const badgeTop = document.getElementById('topPoCountBadge');
  if (!tbodyTop) return;
  try {
    const res = await fetch(`/api/balitower/inventory/purchase-orders?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (badgeTop) badgeTop.textContent = `${data ? data.length : 0} PO`;
      if (!data || data.length === 0) {
        tbodyTop.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 24px; color: var(--text-muted);">Belum ada Purchase Order terbit.</td></tr>`;
        return;
      }
      const rowsHtml = data.map(po => {
        let statusBadge = 'badge-pending';
        if (po.po_status === 'DELIVERED') statusBadge = 'badge-approved';
        else statusBadge = 'badge-pending';
        return `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 11.5px; font-weight: 700; color: #2563EB;">${escapeHtml(po.po_number)}</td>
            <td><strong>${escapeHtml(po.supplier_name)}</strong></td>
            <td>${escapeHtml(po.item_name)}</td>
            <td class="text-right" style="font-weight: 700; font-family: var(--font-mono);">${Number(po.order_quantity).toLocaleString('id-ID')}</td>
            <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #0F172A;">${formatCurrency(po.total_amount)}</td>
            <td class="text-center" style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(po.order_date)}</td>
            <td class="text-center" style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(po.expected_delivery || '-')}</td>
            <td class="text-center"><span class="badge ${statusBadge}">${escapeHtml(po.po_status)}</span></td>
            <td class="text-center" style="white-space: nowrap;">
              ${po.po_status === 'ORDERED' ? `
              <button class="btn btn-primary btn-xs" style="padding: 3px 8px; font-size: 11px; background: #16A34A; border-color: #15803D; margin-right: 4px; display: inline-flex; align-items: center; gap: 4px;" onclick="confirmGoodsReceiptQuick('${escapeHtml(po.po_id)}', '${escapeHtml(po.po_number)}')">
                <svg width="11" height="11" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                <span>Terima Barang</span>
              </button>
              ` : ''}
              <button class="btn btn-secondary btn-xs" style="padding: 3px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;" onclick="openPoPdfModal('${escapeHtml(po.po_id)}', '${escapeHtml(po.po_number)}', '${escapeHtml(po.supplier_name)}', ${po.total_amount}, '${escapeHtml(po.po_status)}')">
                <svg width="11" height="11" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span>PDF</span>
              </button>
            </td>
          </tr>
        `;
      }).join('');
      tbodyTop.innerHTML = rowsHtml;
    }
  } catch (e) {
    console.error("Failed to load POs:", e);
  }
}

function confirmGoodsReceiptQuick(poId, poNumber) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = `Barang untuk ${poId} sudah sampai di gudang, tolong catat penerimaannya`;
    input.focus();
    submitPrompt();
  }
}

// ==============================================================================
// DOMAIN 2: HR & FIELD WORKFORCE LOADERS
// ==============================================================================

async function loadEmployees() {
  const tbody = document.getElementById('hrEmployeesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/hr/employees?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      state.employees = data || [];
      filterEmployeesTable();
    } else {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">Akses dibatasi atau data tidak tersedia untuk sesi ini.</td></tr>`;
    }
  } catch (e) {
    console.error("Failed to load employees:", e);
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">Gagal mengambil data karyawan.</td></tr>`;
  }
}

function renderEmployeesTable(data) {
  const tbody = document.getElementById('hrEmployeesTableBody');
  if (!tbody) return;
  updateSidebarRowCount(data ? data.length : 0, 'Data Karyawan');
  if (!data || data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">Tidak ada data karyawan yang cocok.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.map(e => `
    <tr>
      <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(e.employee_id)}</td>
      <td><strong>${escapeHtml(e.full_name)}</strong></td>
      <td><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(e.department)}</span></td>
      <td>${escapeHtml(e.job_title)}</td>
      <td class="text-center"><span class="badge ${e.employment_status === 'PERMANENT' ? 'badge-approved' : 'badge-pending'}">${escapeHtml(e.employment_status)}</span></td>
      <td class="text-center"><span class="badge ${e.k3_certification !== 'NON_CERTIFIED' ? 'badge-tkpk' : 'badge-pending'}">${escapeHtml(e.k3_certification)}</span></td>
      <td class="text-center" style="font-family: var(--font-mono); font-weight: 700; color: #0F172A;">${e.leave_balance_days} hari</td>
    </tr>
  `).join('');
}

function filterEmployeesTable() {
  const search = (document.getElementById('searchEmployees')?.value || '').toLowerCase().trim();
  const list = state.employees || [];
  const filtered = list.filter(e => {
    return !search ||
      (e.full_name || '').toLowerCase().includes(search) ||
      (e.employee_id || '').toLowerCase().includes(search) ||
      (e.department || '').toLowerCase().includes(search) ||
      (e.job_title || '').toLowerCase().includes(search);
  });
  renderEmployeesTable(filtered);
}

async function loadJobPostings() {
  const tbody = document.getElementById('hrJobsTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/hr/job-postings?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada lowongan pekerjaan dibuka.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(j => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(j.job_id)}</td>
          <td><strong>${escapeHtml(j.job_title)}</strong></td>
          <td>${escapeHtml(j.department)}</td>
          <td class="text-center"><span class="badge badge-tkpk">${escapeHtml(j.required_k3_cert)}</span></td>
          <td class="text-center" style="font-family: var(--font-mono);">${j.min_experience_years} th</td>
          <td class="text-center" style="font-weight: 700; color: #2563EB;">${j.open_positions} org</td>
          <td>${escapeHtml(j.work_location)}</td>
          <td class="text-center"><span class="badge ${j.status === 'OPEN' ? 'badge-approved' : 'badge-rejected'}">${escapeHtml(j.status)}</span></td>
        </tr>
      `).join('');
    } else {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Akses dibatasi atau data tidak tersedia untuk sesi ini.</td></tr>`;
    }
  } catch (e) {
    console.error("Failed to load job postings:", e);
    tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Gagal mengambil data lowongan.</td></tr>`;
  }
}

async function loadSites() {
  const tbody = document.getElementById('hrSitesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/hr/sites?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada titik site menara.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(s => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(s.site_id)}</td>
          <td><strong>${escapeHtml(s.site_name)}</strong></td>
          <td><span style="font-size: 11px; background: #EFF6FF; color: #1E40AF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${escapeHtml(s.site_type)}</span></td>
          <td>${escapeHtml(s.region)}</td>
          <td class="text-center" style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${Number(s.latitude).toFixed(4)}, ${Number(s.longitude).toFixed(4)}</td>
          <td class="text-right" style="font-family: var(--font-mono); font-weight: 700;">${s.height_meters} m</td>
          <td>${escapeHtml(s.structure_type)}</td>
          <td class="text-center"><span class="badge" style="background:#F1F5F9; color:#475569;">${s.tenant_count} Operator</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load sites:", e);
  }
}

// --- HR & Field Workforce Data Loader ---
async function loadHrData() {
  try {
    // 1. HR Summary KPIs
    const sumRes = await fetch(`/api/balitower/hr/summary?t=${Date.now()}`, { cache: 'no-store' });
    if (sumRes.ok) {
      const s = await sumRes.json();
      const el1 = document.getElementById('kpiHrTotalEmp');
      if (el1) el1.textContent = s.total_employees;
      const el2 = document.getElementById('kpiHrFieldTech');
      if (el2) el2.textContent = s.field_technicians;
      const el3 = document.getElementById('kpiHrK3Cert');
      if (el3) el3.textContent = s.certified_k3_tkpk;
      const el4 = document.getElementById('kpiHrOvertime');
      if (el4) el4.textContent = s.total_overtime_hours + ' Jam';
    }

    // 2. Attendance & Geofencing Logs
    const attRes = await fetch(`/api/balitower/hr/attendances?limit=30&t=${Date.now()}`, { cache: 'no-store' });
    const tbodyAtt = document.getElementById('hrAttendanceTableBody');
    if (attRes.ok && tbodyAtt) {
      const atts = await attRes.json();
      if (!atts || atts.length === 0) {
        tbodyAtt.innerHTML = `<tr><td colspan="6" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada catatan absensi.</td></tr>`;
      } else {
        tbodyAtt.innerHTML = atts.map(a => `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 11.5px;">${escapeHtml(a.date)}</td>
            <td><strong>${escapeHtml(a.employee_name)}</strong><br><span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(a.job_title)}</span></td>
            <td><span style="font-weight: 600;">${escapeHtml(a.site_name)}</span><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: #64748B;">${escapeHtml(a.site_id || '-')}</span></td>
            <td class="text-center"><span class="badge" style="background:#F1F5F9; color:#475569;">${a.distance_to_site_m}m</span></td>
            <td class="text-right" style="font-weight: 700; color: ${a.overtime_hours > 0 ? '#D97706' : '#64748B'}; font-family: var(--font-mono);">${a.overtime_hours > 0 ? a.overtime_hours + ' jam' : '-'}</td>
            <td class="text-center"><span class="badge ${a.status.includes('OVERTIME') ? 'badge-approved' : 'badge-pending'}">${escapeHtml(a.status)}</span></td>
          </tr>
        `).join('');
      }
    }

    // 3. Candidates Filter & Screening
    const candRes = await fetch(`/api/balitower/hr/candidates?t=${Date.now()}`, { cache: 'no-store' });
    const tbodyCand = document.getElementById('hrCandidatesTableBody');
    if (candRes.ok && tbodyCand) {
      const cands = await candRes.json();
      tbodyCand.innerHTML = cands.map(c => `
        <tr>
          <td><strong>${escapeHtml(c.full_name)}</strong><br><span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(c.current_city)}</span></td>
          <td>${escapeHtml(c.job_title)}<br><span style="font-size: 11px; color: var(--text-muted);">${c.years_of_experience} th pengalaman</span></td>
          <td class="text-center"><span class="badge badge-tkpk">${escapeHtml(c.k3_cert_held)}</span></td>
          <td class="text-center"><span class="badge ${c.medical_checkup_status.includes('FIT_FOR_HEIGHT') ? 'badge-paid' : 'badge-unpaid'}">${escapeHtml(c.medical_checkup_status)}</span></td>
          <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #2563EB;">${c.technical_score}</td>
          <td class="text-center"><span class="badge badge-pending">${escapeHtml(c.recruitment_stage)}</span></td>
        </tr>
      `).join('');
    }

    // 4. Leave Requests
    const leaveRes = await fetch(`/api/balitower/hr/leave-requests?t=${Date.now()}`, { cache: 'no-store' });
    const tbodyLeave = document.getElementById('hrLeavesTableBody');
    if (leaveRes.ok && tbodyLeave) {
      const leaves = await leaveRes.json();
      tbodyLeave.innerHTML = leaves.map(l => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(l.leave_id)}</td>
          <td><strong>${escapeHtml(l.applicant_name)}</strong><br><span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(l.job_title)}</span></td>
          <td>${escapeHtml(l.leave_type)}</td>
          <td class="text-center" style="font-weight: 700;">${l.days_requested}</td>
          <td style="font-size: 11.5px;">${escapeHtml(l.reason)}<br><span style="color: var(--text-muted); font-size: 10.5px;">Mulai: ${l.start_date}</span></td>
          <td>${escapeHtml(l.substitute_name)}</td>
          <td class="text-center"><span class="badge ${l.approval_status === 'APPROVED' ? 'badge-approved' : 'badge-pending'}">${escapeHtml(l.approval_status)}</span></td>
          <td class="text-center" style="white-space: nowrap;">
            <button class="btn btn-secondary btn-sm" onclick="openLeavePdfModal('${l.leave_id}', '${escapeHtml(l.applicant_name)}', '${escapeHtml(l.leave_type)}', ${l.days_requested}, '${escapeHtml(l.approval_status)}')" style="padding: 3px 10px; font-size: 11.5px;" title="Lihat Berkas PDF">
              PDF
            </button>
          </td>
        </tr>
      `).join('');
    }
    // Also keep employees table synchronized
    loadEmployees();
  } catch (e) {
    console.error("Failed to load HR data:", e);
  }
}

async function approveLeaveQuick(leaveId) {
  try {
    const res = await fetch(`/api/balitower/hr/leave-requests/${leaveId}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'APPROVE' })
    });
    if (res.ok) {
      showToast("Pengajuan cuti berhasil disetujui", "success");
      loadHrData();
      loadEmployees();
    }
  } catch (e) {
    showToast("Gagal menyetujui cuti", "error");
  }
}

// ==============================================================================
// DOMAIN 3: FINANCE & TELECOM BILLING LOADERS
// ==============================================================================

async function loadClients() {
  const tbody = document.getElementById('finClientsTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/clients?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada data operator klien.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(c => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(c.client_id)}</td>
          <td><strong>${escapeHtml(c.client_name)}</strong></td>
          <td><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(c.client_type)}</span></td>
          <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(c.npwp || '-')}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${escapeHtml(c.billing_email || '-')}<br>${escapeHtml(c.phone || '-')}</td>
          <td class="text-center" style="font-weight: 700; font-family: var(--font-mono);">${c.active_lease_sites} Site</td>
          <td class="text-right" style="font-weight: 700; font-family: var(--font-mono);">${formatCurrency(c.credit_limit_idr)}</td>
          <td class="text-center" style="font-family: var(--font-mono);">${c.payment_terms_days} hari</td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load clients:", e);
  }
}

async function loadMlaContracts() {
  const tbody = document.getElementById('finMlaTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/mla-contracts?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada kontrak MLA.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(m => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(m.contract_id)}</td>
          <td><strong>${escapeHtml(m.client_name)}</strong></td>
          <td><strong>${escapeHtml(m.site_name)}</strong><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${escapeHtml(m.site_id)}</span></td>
          <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #0F172A;">${formatCurrency(m.monthly_rate)}</td>
          <td class="text-center"><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(m.billing_frequency)}</span></td>
          <td class="text-center" style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(m.start_date)} s/d ${escapeHtml(m.end_date)}</td>
          <td class="text-center"><span class="badge ${m.electricity_included ? 'badge-approved' : 'badge-pending'}">${m.electricity_included ? 'Termasuk PLN' : 'Terpisah'}</span></td>
          <td class="text-center"><span class="badge ${m.status === 'ACTIVE' ? 'badge-approved' : 'badge-rejected'}">${escapeHtml(m.status)}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load MLA contracts:", e);
  }
}

async function loadLandLeases() {
  const tbody = document.getElementById('finLandLeasesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/land-leases?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada data sewa lahan.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(l => {
        const isPaidActive = l.status === 'ACTIVE_PAID' || l.status === 'ACTIVE' || l.status === 'PAID';
        return `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(l.lease_id)}</td>
          <td><strong>${escapeHtml(l.site_name)}</strong><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${escapeHtml(l.site_id)}</span></td>
          <td>${escapeHtml(l.region)}</td>
          <td>${escapeHtml(l.landowner_name)}</td>
          <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #DC2626;">${formatCurrency(l.annual_lease_cost)}</td>
          <td class="text-center" style="font-family: var(--font-mono);">${l.lease_duration_years} th</td>
          <td class="text-center" style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(l.end_date)}</td>
          <td class="text-center"><span class="badge ${isPaidActive ? 'badge-active_paid' : 'badge-pending'}">${escapeHtml(l.status)}</span></td>
        </tr>
      `;
      }).join('');
    }
  } catch (e) {
    console.error("Failed to load land leases:", e);
  }
}

async function loadSiteUtilities() {
  const tbody = document.getElementById('finUtilitiesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/site-utilities?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada data utilitas site.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(u => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(u.utility_id)}</td>
          <td><strong>${escapeHtml(u.site_name)}</strong><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${escapeHtml(u.site_id)}</span></td>
          <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(u.billing_period)}</td>
          <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(u.pln_meter_id || '-')}</td>
          <td class="text-right" style="font-family: var(--font-mono); font-weight: 600;">${formatCurrency(u.pln_cost)}</td>
          <td class="text-right" style="font-family: var(--font-mono); font-weight: 600;">${formatCurrency(u.genset_fuel_cost)}</td>
          <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #DC2626;">${formatCurrency(u.total_utility_cost)}</td>
          <td class="text-center"><span class="badge ${u.paid_status === 'PAID' ? 'badge-paid' : 'badge-unpaid'}">${escapeHtml(u.paid_status)}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load site utilities:", e);
  }
}

async function loadCoa() {
  const tbody = document.getElementById('finCoaTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/chart-of-accounts?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada bagan akun COA.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(a => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11.5px; font-weight: 800; color: #2563EB;">${escapeHtml(a.account_code)}</td>
          <td><strong>${escapeHtml(a.account_name)}</strong></td>
          <td class="text-center"><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(a.account_type)}</span></td>
          <td class="text-center"><span class="badge ${a.normal_balance === 'DEBIT' ? 'badge-approved' : 'badge-pending'}">${escapeHtml(a.normal_balance)}</span></td>
          <td style="font-size: 11.5px; color: #334155;">${escapeHtml(a.description || '-')}</td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load COA:", e);
  }
}

// --- Finance & Accounting Data Loader ---
async function loadFinanceData() {
  try {
    // 1. Finance Summary KPIs
    const sumRes = await fetch(`/api/balitower/finance/summary?t=${Date.now()}`, { cache: 'no-store' });
    if (sumRes.ok) {
      const s = await sumRes.json();
      const el1 = document.getElementById('kpiFinRevenue');
      if (el1) el1.textContent = 'Rp ' + (s.total_revenue_billed_idr / 1000000).toFixed(1) + 'M';
      const el2 = document.getElementById('kpiFinPaid');
      if (el2) el2.textContent = 'Rp ' + (s.total_revenue_collected_idr / 1000000).toFixed(1) + 'M';
      const el3 = document.getElementById('kpiFinUnpaid');
      if (el3) el3.textContent = 'Rp ' + (s.outstanding_accounts_receivable_idr / 1000000).toFixed(1) + 'M';
      const el4 = document.getElementById('kpiFinNetCash');
      if (el4) el4.textContent = '+Rp ' + (s.net_cash_flow_idr / 1000000).toFixed(1) + 'M';
    }

    // 2. Revenue Invoices
    const invRes = await fetch(`/api/balitower/finance/invoices?t=${Date.now()}`, { cache: 'no-store' });
    if (invRes.ok) {
      const invs = await invRes.json();
      state.invoices = invs || [];
      filterInvoicesTable();
    }

    // 3. Transactions / General Ledger
    const trxRes = await fetch(`/api/balitower/finance/transactions?limit=25&t=${Date.now()}`, { cache: 'no-store' });
    const tbodyTrx = document.getElementById('finTrxTableBody');
    if (trxRes.ok && tbodyTrx) {
      const trxs = await trxRes.json();
      if (!trxs || trxs.length === 0) {
        tbodyTrx.innerHTML = `<tr><td colspan="6" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada transaksi jurnal kas.</td></tr>`;
      } else {
        tbodyTrx.innerHTML = trxs.map(t => `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(t.trx_id)}</td>
            <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(t.trx_date)}</td>
            <td><span style="font-weight: 600;">${escapeHtml(t.account_name)}</span></td>
            <td class="text-center"><span class="${t.trx_type === 'INFLOW' ? 'badge-inflow' : 'badge-outflow'}">${t.trx_type === 'INFLOW' ? '+ INFLOW' : '- OUTFLOW'}</span></td>
            <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: ${t.trx_type === 'INFLOW' ? '#059669' : '#DC2626'};">Rp ${Number(t.amount).toLocaleString('id-ID')}</td>
            <td style="font-size: 11.5px; color: #334155;">${escapeHtml(t.description || '-')}</td>
          </tr>
        `).join('');
      }
    }
  } catch (e) {
    console.error("Failed to load Finance data:", e);
  }
}

function renderInvoicesTable(data) {
  const tbodyInv = document.getElementById('finInvoicesTableBody');
  if (!tbodyInv) return;
  updateSidebarRowCount(data ? data.length : 0, 'Data Invoice');
  if (!data || data.length === 0) {
    tbodyInv.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">Tidak ada invoice yang sesuai.</td></tr>`;
    return;
  }
  tbodyInv.innerHTML = data.map(i => {
    const isPaid = (i.payment_status || '').toUpperCase() === 'PAID' || (i.payment_status || '').toUpperCase() === 'ACTIVE_PAID';
    const displayStatus = isPaid ? 'PAID' : 'PENDING';
    const badgeClass = isPaid ? 'badge-paid' : 'badge-pending';
    const invId = i.invoice_id || '';
    const invNum = i.invoice_number || '';
    const clientName = i.client_name || '';
    const totalBilled = Number(i.total_billed || 0);

    return `
    <tr>
      <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(invNum)}</td>
      <td><strong>${escapeHtml(clientName)}</strong></td>
      <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(i.period_covered || '-')}</td>
      <td class="text-right" style="font-weight: 800; font-family: var(--font-mono);">Rp ${totalBilled.toLocaleString('id-ID')}</td>
      <td class="text-center" style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(i.due_date || '-')}</td>
      <td class="text-center"><span class="badge ${badgeClass}">${displayStatus}</span></td>
      <td class="text-center">
        <button class="btn btn-secondary btn-sm" style="padding: 3px 9px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;" onclick="openInvoicePdfModal('${escapeHtml(invId)}', '${escapeHtml(invNum)}', '${escapeHtml(clientName)}', ${totalBilled}, '${displayStatus}')" title="Buka Dokumen PDF Resmi">
          <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          <span>PDF</span>
        </button>
      </td>
    </tr>
  `;
  }).join('');
}

function filterInvoicesTable() {
  const search = (document.getElementById('searchInvoices')?.value || '').toLowerCase().trim();
  const list = state.invoices || [];
  const filtered = list.filter(i => {
    return !search ||
      (i.invoice_number || '').toLowerCase().includes(search) ||
      (i.client_name || '').toLowerCase().includes(search);
  });
  renderInvoicesTable(filtered);
}

async function loadDashboardStats() {
  try {
    const res = await fetch(`/api/stream/inventory-summary?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      state.stats = await res.json();
    }
  } catch (e) {
    console.error("Failed to fetch stats:", e);
  }
}

// --- Inventory Catalog ---
async function loadInventoryItems() {
  const tbody = document.getElementById('catalogTableBody');
  try {
    let res = await fetch(`/api/balitower/inventory/items?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) {
      res = await fetch(`/api/inventory/items?t=${Date.now()}`, { cache: 'no-store' });
    }
    if (res.ok) {
      const rawItems = await res.json();
      state.items = (rawItems || []).map(it => ({
        sku: it.item_code || it.item_id || it.sku || '',
        name: it.name || it.item_name || '',
        supplier_name: it.supplier_name || '-',
        category: it.category || 'General',
        current_stock: Number(it.total_stock !== undefined ? it.total_stock : it.current_stock) || 0,
        unit: it.unit || 'pcs',
        min_stock: Number(it.min_stock !== undefined ? it.min_stock : it.min_threshold) || 0,
        max_stock: Number(it.max_stock !== undefined ? it.max_stock : (it.max_threshold !== undefined ? it.max_threshold : (it.min_stock * 3))) || 0,
        unit_price: Number(it.unit_price) || 0,
        stock_status: it.stock_status || ''
      }));
      filterCatalogTable();
    } else {
      const err = await res.json().catch(() => ({}));
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: #DC2626; font-weight: 500;">Gagal memuat data inventaris (${escapeHtml(err.detail || 'HTTP ' + res.status)}). Silakan login ulang.</td></tr>`;
      }
    }
  } catch (e) {
    console.error("Failed to load inventory:", e);
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: #DC2626; font-weight: 500;">Terjadi gangguan koneksi saat mengambil katalog.</td></tr>`;
    }
  }
}

function renderCatalogTable(items) {
  const tbody = document.getElementById('catalogTableBody');
  if (!tbody) return;
  updateSidebarRowCount(items ? items.length : 0, 'Item Katalog');

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">Katalog kosong atau tidak ada data yang cocok.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(it => {
    let badgeClass = 'badge-normal';
    let statusLabel = 'Normal';
    if (it.current_stock === 0) {
      badgeClass = 'badge-out_of_stock';
      statusLabel = 'Habis';
    } else if (it.current_stock <= it.min_stock * 0.5) {
      badgeClass = 'badge-out_of_stock';
      statusLabel = 'Kritis';
    } else if (it.current_stock <= it.min_stock) {
      badgeClass = 'badge-low_stock';
      statusLabel = 'Menipis';
    }

    return `
      <tr>
        <td>
          <span style="font-family: var(--font-mono); font-weight: 700; color: #2563EB; font-size: 11.5px; background: #EFF6FF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${it.sku}</span>
        </td>
        <td>
          <div style="font-weight: 600; color: #0F172A;">${escapeHtml(it.name)}</div>
        </td>
        <td>
          <span style="font-size: 11px; background: #F1F5F9; color: #475569; border: 1px solid #E2E8F0; padding: 2px 6px; border-radius: 4px;">${escapeHtml(it.category)}</span>
        </td>
        <td class="text-right" style="font-weight: 700; color: #0F172A;">${it.current_stock.toLocaleString('id-ID')} <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">${it.unit}</span></td>
        <td class="text-right" style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">${it.min_stock.toLocaleString('id-ID')} / ${it.max_stock.toLocaleString('id-ID')}</td>
        <td class="text-right" style="font-weight: 600; color: #0F172A;">${formatCurrency(it.unit_price)}</td>
        <td class="text-center"><span class="badge ${badgeClass}">${statusLabel}</span></td>
      </tr>
    `;
  }).join('');
}

function filterCatalogTable() {
  const search = document.getElementById('searchCatalog')?.value.toLowerCase() || '';
  const category = document.getElementById('filterCategory')?.value || '';

  const filtered = state.items.filter(it => {
    const matchSearch = it.name.toLowerCase().includes(search) || it.sku.toLowerCase().includes(search);
    const matchCat = !category || it.category.toLowerCase() === category.toLowerCase();
    return matchSearch && matchCat;
  });

  renderCatalogTable(filtered);
}

// --- Purchase Requisitions ---
async function loadApprovals() {
  try {
    const res = await fetch(`/api/approval/list?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const allPrs = await res.json();

      state.prs = allPrs.sort((a, b) => {
        const aPending = String(a.status).toUpperCase() === 'PENDING' ? 1 : 0;
        const bPending = String(b.status).toUpperCase() === 'PENDING' ? 1 : 0;
        if (aPending !== bPending) return bPending - aPending;
        return (b.pr_number || '').localeCompare(a.pr_number || '');
      });

      renderPrsTable(state.prs);
    }
  } catch (e) {
    console.error("Failed to load PRs:", e);
  }
}

function renderPrsTable(prs) {
  const tbody = document.getElementById('prsTableBody');
  if (!tbody) return;

  if (!prs || prs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="padding: 20px; color: var(--text-muted);">Belum ada Purchase Requisition terbit.</td></tr>`;
    return;
  }

  tbody.innerHTML = prs.map(pr => {
    const rawStatus = String(pr.status || '').toUpperCase();
    const isApproved = rawStatus === 'APPROVED';
    const isRejected = rawStatus === 'REJECTED';

    let supplierName = pr.supplier_name;
    if (!supplierName && pr.items && pr.items.length > 0) {
      const vendors = Array.from(new Set(pr.items.map(it => it.vendor_name).filter(Boolean)));
      if (vendors.length === 1) supplierName = vendors[0];
      else if (vendors.length > 1) supplierName = `Multi-Vendor (${vendors.length})`;
    }
    supplierName = supplierName || 'Vendor Terdaftar';
    const escapedSupplier = escapeHtml(supplierName).replace(/'/g, "\\'");

    const grandTotal = Number(pr.total_budget ?? pr.grand_total ?? 0);

    let badgeClass = 'badge-pending';
    let statusLabel = 'PENDING';
    if (isApproved) {
      badgeClass = 'badge-approved';
      statusLabel = 'DISETUJUI';
    } else if (isRejected) {
      badgeClass = 'badge-rejected';
      statusLabel = 'DITOLAK';
    }

    const isAdmin = sessionStorage.getItem('role') === 'ADMIN';

    return `
      <tr id="row-pr-${pr.pr_number}">
        <td style="white-space: nowrap;">
          <span style="font-family: var(--font-mono); font-weight: 700; color: #2563EB; font-size: 11.5px; background: #EFF6FF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${pr.pr_number}</span>
        </td>
        <td style="font-weight: 600; color: #0F172A; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(supplierName)}">
          ${escapeHtml(supplierName)}
        </td>
        <td class="text-center" style="color: var(--text-secondary); white-space: nowrap;">${pr.items?.length || 0} item</td>
        <td class="text-right" style="font-weight: 700; color: #0F172A; white-space: nowrap;">${formatCurrency(grandTotal)}</td>
        <td class="text-center" id="badge-container-${pr.pr_number}" style="white-space: nowrap;">
          <span class="badge ${badgeClass}">${statusLabel}</span>
        </td>
        <td class="text-center" style="white-space: nowrap;">
          <div style="display: inline-flex; gap: 4px;" id="actions-container-${pr.pr_number}">
            <button class="btn btn-secondary btn-sm" onclick="openPdfModal('${pr.pr_number}', '${escapedSupplier}', ${grandTotal}, '${rawStatus}')">
              Lihat PDF
            </button>
            ${!isApproved && !isRejected && isAdmin ? `
              <button class="btn btn-success btn-sm btn-approve-action" data-pr="${pr.pr_number}" onclick="approvePrQuick('${pr.pr_number}')">
                Setujui
              </button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// --- In-App PDF Preview Modal ---
function openPdfModal(prNumber, supplierName, grandTotal, status) {
  state.currentModalPrNumber = prNumber;
  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;

  // Resolve current status from state.prs if available to avoid stale feed status
  const foundPr = state.prs?.find(p => p.pr_number === prNumber);
  const effectiveStatus = foundPr ? foundPr.status : status;

  const rawStatus = String(effectiveStatus || '').toUpperCase();
  const isApproved = rawStatus === 'APPROVED';
  const isRejected = rawStatus === 'REJECTED';
  const isAdmin = sessionStorage.getItem('role') === 'ADMIN';

  document.getElementById('modalPrNumber').textContent = prNumber;
  document.getElementById('modalSupplierName').textContent = supplierName ? `| ${supplierName}` : '';
  document.getElementById('modalGrandTotal').textContent = `Total Anggaran: ${formatCurrency(grandTotal || 0)}`;

  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    if (isApproved) {
      statusBadge.className = 'badge badge-approved';
      statusBadge.textContent = 'DISETUJUI';
    } else if (isRejected) {
      statusBadge.className = 'badge badge-rejected';
      statusBadge.textContent = 'DITOLAK';
    } else {
      statusBadge.className = 'badge badge-pending';
      statusBadge.textContent = 'PENDING APPROVAL';
    }
  }

  // Setujui button in modal: ONLY for ADMIN and ONLY when status is PENDING
  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) {
    if (isAdmin && !isApproved && !isRejected) {
      modalApproveBtn.style.display = 'inline-flex';
      modalApproveBtn.disabled = false;
      modalApproveBtn.innerHTML = `
        <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
        </svg>
        <span>Setujui Dokumen PR</span>
      `;
    } else {
      modalApproveBtn.style.display = 'none';
    }
  }

  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/pr/${prNumber}/download?download=true&t=${Date.now()}`;
    downloadBtn.setAttribute('download', `${prNumber}.pdf`);
  }

  const openTabBtn = document.getElementById('modalOpenTabBtn');
  if (openTabBtn) {
    openTabBtn.href = `/api/documents/pr/${prNumber}/download?inline=true&t=${Date.now()}`;
  }

  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/pr/${prNumber}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
  }

  modal.classList.add('open');
}

function closePdfModal() {
  const modal = document.getElementById('pdfPreviewModal');
  if (modal) {
    modal.classList.remove('open');
    const iframe = document.getElementById('pdfPreviewIframe');
    if (iframe) iframe.src = 'about:blank';
  }
}

// --- Open Official Purchase Order (PO) Typst PDF In-App Preview Modal ---
function openPoPdfModal(poId, poNumber, supplierName, grandTotal, poStatus) {
  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;

  const prNumberEl = document.getElementById('modalPrNumber');
  if (prNumberEl) prNumberEl.textContent = poNumber || poId;

  const supplierNameEl = document.getElementById('modalSupplierName');
  if (supplierNameEl) supplierNameEl.textContent = supplierName || "Surat Pesanan Resmi";

  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    const rawStatus = (poStatus || "ORDERED").toUpperCase();
    if (rawStatus === 'DELIVERED') statusBadge.className = 'badge badge-approved';
    else statusBadge.className = 'badge badge-pending';
    statusBadge.textContent = rawStatus;
  }

  const grandTotalEl = document.getElementById('modalGrandTotal');
  if (grandTotalEl) grandTotalEl.textContent = grandTotal ? `Total Anggaran PO: ${formatCurrency(grandTotal)}` : "Surat Pesanan Resmi PT Bali Towerindo Sentra Tbk";

  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) modalApproveBtn.style.display = 'none';

  const cleanPoId = encodeURIComponent(poId);
  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/po/${cleanPoId}/download?download=true&t=${Date.now()}`;
    downloadBtn.setAttribute('download', `${poId}.pdf`);
  }

  const openTabBtn = document.getElementById('modalOpenTabBtn');
  if (openTabBtn) {
    openTabBtn.href = `/api/documents/po/${cleanPoId}/download?inline=true&t=${Date.now()}`;
  }

  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/po/${cleanPoId}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
  }

  modal.classList.add('open');
}

// --- Open Official Leave Request Typst PDF In-App Preview Modal ---
function openLeavePdfModal(leaveId, applicantName, leaveType, daysRequested, status) {
  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;

  const prNumberEl = document.getElementById('modalPrNumber');
  if (prNumberEl) prNumberEl.textContent = leaveId;

  const supplierNameEl = document.getElementById('modalSupplierName');
  if (supplierNameEl) supplierNameEl.textContent = `${applicantName} - ${leaveType}`;

  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    const rawStatus = (status || "PENDING_APPROVAL").toUpperCase();
    if (rawStatus === 'APPROVED') statusBadge.className = 'badge badge-approved';
    else if (rawStatus === 'REJECTED') statusBadge.className = 'badge badge-rejected';
    else statusBadge.className = 'badge badge-pending';
    statusBadge.textContent = rawStatus;
  }

  const grandTotalEl = document.getElementById('modalGrandTotal');
  if (grandTotalEl) grandTotalEl.textContent = `Durasi Cuti: ${daysRequested} Hari Kerja`;

  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) modalApproveBtn.style.display = 'none';

  const cleanLeaveId = encodeURIComponent(leaveId);
  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/leave/${cleanLeaveId}/download?download=true&t=${Date.now()}`;
    downloadBtn.setAttribute('download', `${leaveId}.pdf`);
  }

  const openTabBtn = document.getElementById('modalOpenTabBtn');
  if (openTabBtn) {
    openTabBtn.href = `/api/documents/leave/${cleanLeaveId}/download?inline=true&t=${Date.now()}`;
  }

  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/leave/${cleanLeaveId}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
  }

  modal.classList.add('open');
}

// --- Open Official Tower Lease Invoice Typst PDF In-App Preview Modal ---
function openInvoicePdfModal(invoiceId, invoiceNumber, clientName, totalBilled, status) {
  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;

  const prNumberEl = document.getElementById('modalPrNumber');
  if (prNumberEl) prNumberEl.textContent = invoiceNumber || invoiceId;

  const supplierNameEl = document.getElementById('modalSupplierName');
  if (supplierNameEl) supplierNameEl.textContent = clientName || "Surat Perjanjian Sewa & Tagihan Invoice";

  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    const rawStatus = (status || "PENDING").toUpperCase();
    if (rawStatus === 'PAID' || rawStatus === 'ACTIVE_PAID') {
      statusBadge.className = 'badge badge-paid';
      statusBadge.textContent = 'PAID';
    } else {
      statusBadge.className = 'badge badge-pending';
      statusBadge.textContent = 'PENDING';
    }
  }

  const grandTotalEl = document.getElementById('modalGrandTotal');
  if (grandTotalEl) grandTotalEl.textContent = totalBilled ? `Total Tagihan: ${formatCurrency(totalBilled)}` : "Surat Perjanjian Sewa & Tagihan Invoice PT Bali Towerindo Sentra Tbk";

  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) modalApproveBtn.style.display = 'none';

  const cleanInvId = encodeURIComponent(invoiceId);
  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/invoice/${cleanInvId}/download?download=true&t=${Date.now()}`;
    downloadBtn.setAttribute('download', `${invoiceId}.pdf`);
  }

  const openTabBtn = document.getElementById('modalOpenTabBtn');
  if (openTabBtn) {
    openTabBtn.href = `/api/documents/invoice/${cleanInvId}/download?inline=true&t=${Date.now()}`;
  }

  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/invoice/${cleanInvId}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
  }

  modal.classList.add('open');
}

// --- Approve Action From Inside Modal ---
async function approvePrFromModal() {
  const prNumber = state.currentModalPrNumber;
  if (!prNumber) return;

  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) {
    modalApproveBtn.disabled = true;
    modalApproveBtn.textContent = "Menyetujui...";
  }

  await approvePrQuick(prNumber);

  // If still in modal, ensure view is refreshed to APPROVED
  if (state.currentModalPrNumber === prNumber) {
    const statusBadge = document.getElementById('modalPrStatusBadge');
    if (statusBadge) {
      statusBadge.className = 'badge badge-approved';
      statusBadge.textContent = 'DISETUJUI';
    }
    if (modalApproveBtn) {
      modalApproveBtn.style.display = 'none';
    }
    const iframe = document.getElementById('pdfPreviewIframe');
    if (iframe) {
      iframe.src = `/api/documents/pr/${prNumber}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
    }
  }
}

// --- Quick Approve Action ---
async function approvePrQuick(prNumber) {
  const allActionButtons = document.querySelectorAll(`[data-pr="${prNumber}"]`);
  allActionButtons.forEach(btn => {
    btn.disabled = true;
    btn.textContent = "Menyetujui...";
  });

  try {
    const res = await fetch('/api/approval/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pr_number: prNumber,
        action: 'APPROVE',
        manager_name: sessionStorage.getItem('username') || 'Warehouse Manager'
      })
    });

    if (res.ok) {
      showToast(`Purchase Requisition ${prNumber} berhasil disetujui`, 'success');

      // Update PR status in local state
      if (state.prs) {
        const p = state.prs.find(item => item.pr_number === prNumber);
        if (p) p.status = 'APPROVED';
      }

      allActionButtons.forEach(btn => {
        const approvedBadge = document.createElement('span');
        approvedBadge.className = 'badge badge-approved';
        approvedBadge.textContent = 'DISETUJUI';
        btn.replaceWith(approvedBadge);
      });

      const tableBadgeContainer = document.getElementById(`badge-container-${prNumber}`);
      if (tableBadgeContainer) {
        tableBadgeContainer.innerHTML = `<span class="badge badge-approved">DISETUJUI</span>`;
      }

      // If the modal is currently open for this PR, update modal header & refresh iframe
      if (state.currentModalPrNumber === prNumber) {
        const statusBadge = document.getElementById('modalPrStatusBadge');
        if (statusBadge) {
          statusBadge.className = 'badge badge-approved';
          statusBadge.textContent = 'DISETUJUI';
        }
        const modalApproveBtn = document.getElementById('modalApproveBtn');
        if (modalApproveBtn) {
          modalApproveBtn.style.display = 'none';
        }
        const iframe = document.getElementById('pdfPreviewIframe');
        if (iframe) {
          iframe.src = `/api/documents/pr/${prNumber}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
        }
      }

      await loadAllData();
      saveCopilotFeed();
    } else {
      throw new Error("Gagal menyetujui dokumen.");
    }
  } catch (e) {
    showToast(e.message || "Gagal menyetujui PR", "error");
    allActionButtons.forEach(btn => {
      btn.disabled = false;
      btn.textContent = "Setujui";
    });
  }
}

// --- Interactive Prompt Auto-Resizing & Submission ---
function autoResizePromptInput() {
  const textarea = document.getElementById('promptInput');
  if (!textarea) return;
  textarea.style.height = 'auto';
  const newHeight = Math.min(Math.max(textarea.scrollHeight, 24), 220);
  textarea.style.height = newHeight + 'px';
  
  const container = textarea.closest('.input-bar-container');
  if (container) {
    if (newHeight > 34) {
      container.classList.add('is-multiline');
    } else {
      container.classList.remove('is-multiline');
    }
  }
}

function initPromptInputAutoResize() {
  const textarea = document.getElementById('promptInput');
  if (!textarea) return;
  textarea.addEventListener('input', autoResizePromptInput);
  textarea.addEventListener('paste', () => setTimeout(autoResizePromptInput, 0));
  textarea.addEventListener('focus', autoResizePromptInput);
  autoResizePromptInput();
}

// --- Quick Action Chip Handler ---
function quickFillPrompt(promptText) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = promptText;
    autoResizePromptInput();
    input.focus();
    submitPrompt();
  }
}

// --- Global Prompt Execution & Abort Controller (Gemini Style Stop Action) ---
let activePromptAbortController = null;
let isAgentPromptRunning = false;

function setAgentPromptRunning(isRunning) {
  isAgentPromptRunning = isRunning;
  const btn = document.getElementById('btnSendPrompt');
  if (!btn) return;

  if (isRunning) {
    btn.classList.add('btn-stop-state');
    btn.disabled = false;
    btn.setAttribute('title', 'Hentikan respon (Stop)');
    btn.setAttribute('aria-label', 'Hentikan respon');
    btn.innerHTML = `
      <span>Stop</span>
      <svg class="stop-icon" width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
        <rect x="5" y="5" width="14" height="14" rx="2" />
      </svg>
    `;
  } else {
    btn.classList.remove('btn-stop-state');
    btn.disabled = false;
    btn.setAttribute('title', 'Kirim instruksi');
    btn.setAttribute('aria-label', 'Kirim instruksi');
    btn.innerHTML = `
      <span>Kirim</span>
      <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/>
      </svg>
    `;
  }
}

function stopPromptExecution() {
  if (activePromptAbortController) {
    activePromptAbortController.abort();
    activePromptAbortController = null;
  }
  setAgentPromptRunning(false);
}

// Global keydown listener for Escape key to cancel ongoing prompt execution
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && isAgentPromptRunning) {
    e.preventDefault();
    stopPromptExecution();
  }
});

// --- Interactive Prompt Submission ---
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (isAgentPromptRunning) return; // Prevent duplicate submission while running
    submitPrompt();
  } else if (e.key === 'Enter' && e.shiftKey) {
    setTimeout(autoResizePromptInput, 0);
  }
}

function useClarificationHint(hintText) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = hintText;
    input.focus();
    submitPrompt();
  }
}

function handleStreamAborted(streamBubble, accumulatedText = '') {
  if (!streamBubble) return;

  const cursor = streamBubble.querySelector('.stream-cursor');
  if (cursor) cursor.remove();

  const inlineCancel = streamBubble.querySelector('.btn-cancel-inline');
  if (inlineCancel) inlineCancel.remove();

  const activeChips = streamBubble.querySelectorAll('.stage-chip.active');
  activeChips.forEach(c => {
    c.classList.remove('active');
    c.classList.add('done');
    const pulse = c.querySelector('.stage-pulse-dot');
    if (pulse) pulse.remove();
  });

  const stagesContainer = streamBubble.querySelector('.stage-chips-container');
  if (stagesContainer) {
    const stoppedChip = document.createElement('div');
    stoppedChip.className = 'stage-chip stopped';
    stoppedChip.innerHTML = `
      <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style="color: #64748B;"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
      <span>Dibatalkan oleh pengguna</span>
    `;
    stagesContainer.appendChild(stoppedChip);
  }

  const textSlot = streamBubble.querySelector('.stream-text-slot');
  if (textSlot) {
    if (accumulatedText) {
      textSlot.innerHTML = formatMarkdownResponse(accumulatedText) + `
        <div class="stream-stopped-hint">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
          <span>Proses pembuatan respon dihentikan.</span>
        </div>
      `;
    }
  }
  scrollChatToBottom();
}

async function submitPrompt() {
  // If agent is currently running and user clicks the Stop button:
  if (isAgentPromptRunning) {
    stopPromptExecution();
    return;
  }

  const input = document.getElementById('promptInput');
  if (!input) return;

  const promptText = input.value.trim();
  if (!promptText) return;

  input.value = '';
  input.style.height = 'auto';
  const barContainer = input.closest('.input-bar-container');
  if (barContainer) barContainer.classList.remove('is-multiline');

  appendUserMessage(promptText);

  const lower = promptText.toLowerCase();
  const isLeaveFormIntent = ["ajukan cuti", "input cuti", "form cuti", "formulir cuti", "permohonan cuti", "isi cuti", "minta cuti", "mau cuti", "input data cuti", "buat cuti"].some(k => lower.includes(k));

  if (isLeaveFormIntent && (getEffectiveTenant() === 'HR' || getEffectiveTenant() === 'ALL')) {
    renderLeaveRequestChatForm();
    saveCopilotFeed();
    return;
  }

  const streamBubble = appendAgentStreamBubble();
  activePromptAbortController = new AbortController();
  setAgentPromptRunning(true);

  try {
    const res = await fetch('/api/agent/stream-prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: promptText, destinations: [] }),
      signal: activePromptAbortController.signal
    });

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      if (streamBubble) streamBubble.remove();
      appendAgentErrorMessage(errJson.detail || "Gagal memproses instruksi.");
      saveCopilotFeed();
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let accumulatedText = '';
    let completedPayload = null;

    while (true) {
      if (activePromptAbortController?.signal?.aborted) break;

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (activePromptAbortController?.signal?.aborted) break;

        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const rawJson = trimmed.substring(5).trim();
        if (!rawJson) continue;

        try {
          const evt = JSON.parse(rawJson);
          if (evt.type === 'status') {
            updateStreamStage(streamBubble, evt.stage, evt.message);
          } else if (evt.type === 'clarification') {
            renderClarificationBox(streamBubble, evt.clarification);
          } else if (evt.type === 'token') {
            accumulatedText += evt.content;
            updateStreamText(streamBubble, accumulatedText);
          } else if (evt.type === 'complete') {
            completedPayload = evt.payload;
          } else if (evt.type === 'error') {
            throw new Error(evt.message || "Error saat streaming respon.");
          }
        } catch (err) {
          console.warn('Error parsing stream event:', err, rawJson);
        }
      }
    }

    // Check if aborted right after loop
    if (activePromptAbortController?.signal?.aborted) {
      handleStreamAborted(streamBubble, accumulatedText);
      saveCopilotFeed();
      return;
    }

    // Finalize stream bubble with complete response data
    finalizeStreamBubble(streamBubble, completedPayload, accumulatedText);
    await loadAllData();
    saveCopilotFeed();

  } catch (e) {
    const isAborted = e.name === 'AbortError' || activePromptAbortController?.signal?.aborted;
    if (isAborted) {
      handleStreamAborted(streamBubble);
      saveCopilotFeed();
      return;
    }

    if (streamBubble) streamBubble.remove();
    appendAgentErrorMessage(e.message || "Terjadi kesalahan koneksi ke server backend.");
    saveCopilotFeed();
  } finally {
    setAgentPromptRunning(false);
    activePromptAbortController = null;
  }
}

function scrollChatToBottom() {
  const wrapper = document.getElementById('copilotFeedWrapper');
  const feed = document.getElementById('copilotFeed');
  if (wrapper) wrapper.scrollTop = wrapper.scrollHeight;
  if (feed) feed.scrollTop = feed.scrollHeight;
}

function getAgentBubbleHeaderHtml(badgeText = 'Agent Aktif', isError = false) {
  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `
    <div class="agent-bubble-header">
      <div class="agent-avatar ${isError ? 'error-avatar' : ''}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/>
          <rect x="3" y="8" width="18" height="12" rx="3"/>
          <circle cx="8" cy="14" r="1.5" fill="currentColor"/>
          <circle cx="16" cy="14" r="1.5" fill="currentColor"/>
          <line x1="12" y1="13" x2="12" y2="15"/>
        </svg>
      </div>
      <div class="agent-header-info">
        <span class="agent-name">Bali Tower Copilot</span>
        <span class="agent-status-badge ${isError ? 'error-badge' : ''}">
          ${!isError ? '<span class="agent-online-dot"></span>' : ''}${escapeHtml(badgeText)}
        </span>
      </div>
      <span class="bubble-time">${timeStr}</span>
    </div>
  `;
}

function appendUserMessage(text) {
  const container = document.getElementById('geminiChatContainer');
  if (container) container.classList.remove('is-empty-state');

  const feed = document.getElementById('copilotFeed');
  if (!feed) return;

  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const userBox = document.createElement('div');
  userBox.className = 'user-query-bubble';
  userBox.innerHTML = `
    <div class="bubble-meta">
      <span class="bubble-sender">Anda</span>
      <span class="bubble-time">${timeStr}</span>
    </div>
    <div class="bubble-text">${escapeHtml(text)}</div>
  `;
  feed.appendChild(userBox);
  scrollChatToBottom();
}

function appendAgentStreamBubble() {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return null;

  const id = 'stream_' + Date.now();
  const box = document.createElement('div');
  box.id = id;
  box.className = 'agent-response-box';
  box.innerHTML = `
    ${getAgentBubbleHeaderHtml('Agent Aktif')}
    <div class="agent-plan-box">
      <div class="stage-chips-container">
        <div class="stage-chip active">
          <span class="stage-pulse-dot"></span>
          <span>Menganalisis instruksi dan wewenang...</span>
        </div>
        <button type="button" class="btn-cancel-inline" onclick="stopPromptExecution()" title="Hentikan respon (Stop)">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
          <span>Stop</span>
        </button>
      </div>
      <div class="clarification-slot"></div>
      <div class="stream-text-slot" style="font-size: 13.5px; color: #0F172A; line-height: 1.65;">
        <span class="stream-cursor"></span>
      </div>
      <div class="stream-artifacts-slot" style="margin-top: 8px;"></div>
    </div>
  `;
  feed.appendChild(box);
  scrollChatToBottom();
  return box;
}

function updateStreamStage(streamBubble, stage, message) {
  if (!streamBubble) return;
  const stagesContainer = streamBubble.querySelector('.stage-chips-container');
  if (!stagesContainer) return;

  const prevActive = stagesContainer.querySelector('.stage-chip.active');
  if (prevActive) {
    prevActive.classList.remove('active');
    prevActive.classList.add('done');
    const pulse = prevActive.querySelector('.stage-pulse-dot');
    if (pulse) pulse.remove();
  }

  const inlineCancel = stagesContainer.querySelector('.btn-cancel-inline');

  const chip = document.createElement('div');
  chip.className = 'stage-chip active';
  chip.innerHTML = `
    <span class="stage-pulse-dot"></span>
    <span>${escapeHtml(message)}</span>
  `;

  if (inlineCancel) {
    stagesContainer.insertBefore(chip, inlineCancel);
  } else {
    stagesContainer.appendChild(chip);
  }
  scrollChatToBottom();
}

function renderClarificationBox(streamBubble, clarification) {
  if (!streamBubble || !clarification) return;
  const slot = streamBubble.querySelector('.clarification-slot');
  if (!slot) return;

  const hint = clarification.hint || '';
  const escapedHint = escapeHtml(hint).replace(/'/g, "\\'");

  slot.innerHTML = `
    <div class="clarification-box">
      <div class="clarification-title">
        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>${escapeHtml(clarification.title || 'Klarifikasi Diperlukan')}</span>
      </div>
      <div class="clarification-message">${escapeHtml(clarification.message || '')}</div>
      ${hint ? `
        <button type="button" class="clarification-hint-btn" onclick="useClarificationHint('${escapedHint}')">
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span>Gunakan Saran: "<strong>${escapeHtml(hint)}</strong>"</span>
        </button>
      ` : ''}
    </div>
  `;
  scrollChatToBottom();
}

function updateStreamText(streamBubble, text) {
  if (!streamBubble) return;
  const textSlot = streamBubble.querySelector('.stream-text-slot');
  if (!textSlot) return;

  textSlot.innerHTML = formatMarkdownResponse(text) + '<span class="stream-cursor"></span>';
  scrollChatToBottom();
}

function finalizeStreamBubble(streamBubble, payload, streamedText) {
  if (!streamBubble) return;

  const cursor = streamBubble.querySelector('.stream-cursor');
  if (cursor) cursor.remove();

  const inlineCancel = streamBubble.querySelector('.btn-cancel-inline');
  if (inlineCancel) inlineCancel.remove();

  const activeChips = streamBubble.querySelectorAll('.stage-chip.active');
  activeChips.forEach(c => {
    c.classList.remove('active');
    c.classList.add('done');
    const pulse = c.querySelector('.stage-pulse-dot');
    if (pulse) pulse.remove();
  });

  if (!payload) return;

  const prs = payload.generated_prs || [];
  const items = payload.affected_items || [];
  const actionType = payload.action_type || 'general';

  if (actionType === 'hr_leave_form' || (payload.parsed_intent && payload.parsed_intent.workflow_id === 'hr_leave_form')) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      renderLeaveRequestChatForm(artifactsSlot);
    }
  } else if (prs.length > 0) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const prCards = prs.map(pr => {
        const rawStatus = String(pr.status || '').toUpperCase();
        const supplier = pr.supplier_name || 'Vendor Terdaftar';
        const grandTotal = Number(pr.grand_total || pr.total_budget || 0);
        const escapedSupplier = escapeHtml(supplier).replace(/'/g, "\\'");

        return `
          <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px; margin-top: 8px; box-shadow: var(--shadow-xs);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div>
                <span style="font-family: var(--font-mono); font-weight: 700; color: #2563EB; font-size: 12px; background: #EFF6FF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${pr.pr_number}</span>
                <span style="font-size: 12.5px; margin-left: 6px; color: #334155; font-weight: 600;">${escapeHtml(supplier)}</span>
              </div>
              <span style="font-weight: 800; font-size: 14px; color: #0F172A;">${formatCurrency(grandTotal)}</span>
            </div>
            <div style="font-size: 12.5px; color: #475569; margin-bottom: 10px; line-height: 1.6;">
              ${(pr.items || []).map(it => `• <strong>${escapeHtml(it.item_name || it.name)}</strong>: ${it.quantity || it.reorder_qty} ${it.unit || 'pcs'}`).join('<br>')}
            </div>
            <div style="background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #166534; display: flex; align-items: center; gap: 8px;">
              <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              <span>Dokumen PR resmi telah dikompilasi (PDF) dan notifikasi persetujuan telah otomatis dikirimkan ke email tujuan.</span>
            </div>
            <div style="display: flex; justify-content: flex-end;">
              <button class="btn btn-secondary btn-sm" onclick="openPdfModal('${pr.pr_number}', '${escapedSupplier}', ${grandTotal}, '${rawStatus}')">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span>Lihat Dokumen PDF</span>
              </button>
            </div>
          </div>
        `;
      }).join('');

      artifactsSlot.innerHTML = `
        <div class="action-card" style="border-left: 4px solid #16A34A; background: #F0FDF4; border: 1px solid #DCFCE7; margin-top: 10px;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #15803D;">DOKUMEN PR DITERBITKAN & TERKIRIM KE EMAIL (${prs.length})</span>
            <span class="badge badge-approved">TERKIRIM KE EMAIL</span>
          </div>
          <div class="action-card-body">
            ${prCards}
          </div>
        </div>
      `;
      openDataSidebar('canvas-prs');
    }
  }

  if (payload.onboarding_id) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const onbId = payload.onboarding_id;
      const clientName = payload.client_name || 'Klien Operator';
      const siteId = payload.site_id || '';
      const totalBilled = payload.total_billed || 0;
      artifactsSlot.innerHTML = `
        <div class="action-card" style="border-left: 4px solid #16A34A; background: #F0FDF4; border: 1px solid #DCFCE7; margin-top: 10px;">
          <div class="action-card-header" style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 700; font-size: 12.5px; color: #15803D;">PENGAJUAN SEWA MENARA OPERATOR BARU (${escapeHtml(onbId)})</span>
            <span class="badge badge-approved" style="background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D;">PENDING APPROVAL</span>
          </div>
          <div class="action-card-body" style="padding-top: 8px;">
            <div style="font-size: 12.5px; color: #334155; margin-bottom: 8px;">
              <strong>Klien:</strong> ${escapeHtml(clientName)} ${siteId ? `• <strong>Site:</strong> ${escapeHtml(siteId)}` : ''}
            </div>
            <div style="background: #FFFFFF; border: 1px solid #DCFCE7; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #166534; display: flex; align-items: center; gap: 8px;">
              <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              <span>Faktur tagihan sewa menara & berkas perjanjian telah dikompilasi (PDF) dan dikirimkan ke email untuk persetujuan.</span>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 8px;">
              <a href="/api/documents/invoice/${encodeURIComponent(onbId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                <span>Unduh Faktur PDF</span>
              </a>
              <button class="btn btn-primary btn-sm" onclick="openInvoicePdfModal('${escapeHtml(onbId)}', '${escapeHtml(onbId)}', '${escapeHtml(clientName)}', ${totalBilled}, 'PENDING')">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span>Lihat Dokumen PDF</span>
              </button>
            </div>
          </div>
        </div>
      `;
      openDataSidebar('canvas-finance');
      if (typeof loadFinanceData === 'function') loadFinanceData();
      if (typeof loadClients === 'function') loadClients();
      if (typeof loadMlaContracts === 'function') loadMlaContracts();
    }
  }

  if (payload.leave_id) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const lId = payload.leave_id;
      const appName = payload.applicant_name || 'Karyawan';
      const lType = payload.leave_type || 'Cuti';
      const days = payload.days_requested || 1;
      artifactsSlot.innerHTML = `
        <div style="display: flex; justify-content: flex-end; margin-top: 10px; gap: 8px;">
          <a href="/api/documents/leave/${encodeURIComponent(lId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
            <span>Unduh PDF Cuti</span>
          </a>
          <button class="btn btn-primary btn-sm" onclick="openLeavePdfModal('${escapeHtml(lId)}', '${escapeHtml(appName)}', '${escapeHtml(lType)}', ${days}, 'PENDING_APPROVAL')">
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            <span>Lihat Dokumen PDF</span>
          </button>
        </div>
      `;
    }
  } else if (items.length > 0 && actionType !== 'general') {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const isReg = actionType === 'register_product';
      const title = isReg ? 'PRODUK BARU BERHASIL DIDAFTARKAN' : 'PERUBAHAN AMBANG BATAS STOK';
      const badge = isReg ? '<span class="badge badge-approved">BERHASIL</span>' : '<span class="badge badge-updated">DIPERBARUI</span>';
      
      const rows = items.map(it => `
        <tr>
          <td><strong>${escapeHtml(it.name)}</strong></td>
          <td>${it.current_stock !== undefined ? it.current_stock : '-'} ${it.unit || ''}</td>
          <td><span style="color: #2563EB; font-weight: 600;">${it.min_stock !== undefined ? it.min_stock : '-'}</span> ${it.unit || ''}</td>
        </tr>
      `).join('');

      artifactsSlot.innerHTML = `
        <div class="action-card" style="border-left: 4px solid #2563EB; background: #F8FAFC; border: 1px solid #E2E8F0; margin-top: 10px;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #1E293B;">${title} (${items.length})</span>
            ${badge}
          </div>
          <div class="action-card-body" style="padding: 6px 10px;">
            <table class="data-table" style="font-size: 12px; margin: 4px 0;">
              <thead>
                <tr>
                  <th>Nama Barang</th>
                  <th>Stok Fisik</th>
                  <th>Batas Min</th>
                </tr>
              </thead>
              <tbody>
                ${rows}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }
  }

  if (payload.po_id || payload.pdf_download_url) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const poId = payload.po_id || (payload.parsed_intent && payload.parsed_intent.po_id);
      if (poId) {
        const poNum = payload.po_number || poId;
        const supplier = payload.supplier_name || 'Vendor Terdaftar';
        const total = payload.grand_total || 0;
        const st = payload.status || 'ORDERED';
        artifactsSlot.innerHTML = `
          <div style="display: flex; justify-content: flex-end; margin-top: 10px; gap: 8px;">
            <a href="/api/documents/po/${encodeURIComponent(poId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
              <span>Unduh PDF PO</span>
            </a>
            <button class="btn btn-primary btn-sm" onclick="openPoPdfModal('${escapeHtml(poId)}', '${escapeHtml(poNum)}', '${escapeHtml(supplier)}', ${total}, '${escapeHtml(st)}')">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
              <span>Lihat Dokumen PO (PDF)</span>
            </button>
          </div>
        `;
      }
    }
  }

  scrollChatToBottom();
}

function appendAgentErrorMessage(errorText) {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return;

  const box = document.createElement('div');
  box.className = 'agent-response-box';
  box.innerHTML = `
    ${getAgentBubbleHeaderHtml('Kendala Sistem', true)}
    <div class="agent-plan-box" style="border-left: 4px solid #DC2626; background: #FEF2F2; border-color: #FECACA;">
      <div class="agent-plan-title" style="color: #DC2626;">TERJADI KESALAHAN</div>
      <div style="font-size: 13px; color: #991B1B; line-height: 1.5;">${escapeHtml(errorText)}</div>
    </div>
  `;
  feed.appendChild(box);
  scrollChatToBottom();
}

function formatMarkdownResponse(text) {
  if (!text) return '';

  // Strip emojis across the board
  const stripEmojis = (str) => (str || '').replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F1E0}-\u{1F1FF}\u{1F900}-\u{1F9FF}\u{1F004}\u{1F0CF}\u{1F170}-\u{1F251}\u{2300}-\u{23FF}\u{2B50}\u{2B55}\u{2934}\u{2935}\u{2B05}\u{2B06}\u{2B07}]/gu, '').trim();

  const lines = text.split('\n');
  let inTable = false;
  let html = '';
  let tableRows = [];

  const cleanText = (str) => stripEmojis(str || '').replace(/\*\*/g, '').replace(/`/g, '').trim();

  for (let line of lines) {
    let trimmed = line.trim();

    // Strip markdown table rows
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      if (trimmed.includes('---')) continue; // skip header separator
      inTable = true;
      const cells = trimmed.split('|').slice(1, -1).map(c => {
        let val = cleanText(c);
        if (val.toUpperCase() === 'PENDING_APPROVAL' || val.toUpperCase() === 'PENDING') {
          return '<span class="badge badge-pending" style="font-weight: 700;">PENDING</span>';
        } else if (val.toUpperCase() === 'APPROVED' || val.toUpperCase() === 'PAID' || val.toUpperCase() === 'ACTIVE_PAID') {
          return '<span class="badge badge-paid" style="font-weight: 700;">PAID</span>';
        }
        return val;
      });
      tableRows.push(cells);
    } else {
      if (inTable && tableRows.length > 0) {
        html += `<div style="overflow-x:auto; margin: 10px 0;"><table class="data-table" style="font-size: 11.5px; width: 100%;"><thead><tr>` +
          tableRows[0].map(c => `<th style="padding: 6px 8px;">${c}</th>`).join('') +
          `</tr></thead><tbody>` +
          tableRows.slice(1).map(row => `<tr>` + row.map(c => `<td style="padding: 6px 8px;">${c}</td>`).join('') + `</tr>`).join('') +
          `</tbody></table></div>`;
        inTable = false;
        tableRows = [];
      }

      // Clean header lines (### or ## or #)
      if (trimmed.startsWith('#')) {
        const hTitle = cleanText(trimmed.replace(/^#+\s*/, ''));
        if (hTitle) {
          html += `<div style="font-size: 13.5px; font-weight: 700; color: #0F172A; margin: 8px 0 4px 0;">${hTitle}</div>`;
        }
        continue;
      }

      // Clean blockquote lines (> ...)
      if (trimmed.startsWith('>')) {
        const bQuote = cleanText(trimmed.replace(/^>\s*/, ''));
        if (bQuote) {
          html += `<div style="background: #F8FAFC; border-left: 3px solid #CBD5E1; padding: 7px 10px; margin: 6px 0; font-size: 12px; color: #475569; border-radius: 0 6px 6px 0; line-height: 1.5;">${bQuote}</div>`;
        }
        continue;
      }

      const cLine = cleanText(trimmed);
      if (cLine.startsWith('- ')) {
        html += `<div style="margin: 3px 0 3px 12px; font-size: 12.5px;">- ${cLine.substring(2)}</div>`;
      } else if (cLine.length > 0) {
        html += `<div style="margin: 4px 0; font-size: 13px; line-height: 1.5;">${cLine}</div>`;
      }
    }
  }
  if (inTable && tableRows.length > 0) {
    html += `<div style="overflow-x:auto; margin: 10px 0;"><table class="data-table" style="font-size: 11.5px; width: 100%;"><thead><tr>` +
      tableRows[0].map(c => `<th style="padding: 6px 8px;">${c}</th>`).join('') +
      `</tr></thead><tbody>` +
      tableRows.slice(1).map(row => `<tr>` + row.map(c => `<td style="padding: 6px 8px;">${c}</td>`).join('') + `</tr>`).join('') +
      `</tbody></table></div>`;
  }

  return html;
}

function appendAgentResponseCard(data) {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return;

  const intent = data.parsed_intent || {};
  const actionType = data.action_type || 'general';
  const prs = data.generated_prs || [];
  const items = data.affected_items || [];

  const container = document.createElement('div');
  container.className = 'agent-response-box';

  // Scenario 0: Safe Fallback / Anti-Halusinasi (Out of Scope / Unrecognized Intent)
  if (actionType === 'unrecognized_intent' || actionType === 'out_of_scope') {
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Di Luar Cakupan', true)}
      <div class="agent-plan-box" style="border-left: 4px solid #F59E0B; background: #FFFBEB; border: 1px solid #FDE68A;">
        <div style="font-size: 13.5px; color: #92400E; line-height: 1.6;">
          ${escapeHtml(data.message || 'Mohon maaf, instruksi yang Anda masukkan berada di luar cakupan wewenang operasional sistem PT Bali Towerindo Sentra Tbk.')}
        </div>
      </div>
    `;
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 1: Bali Tower Domain queries (HR, Finance, Inventory) & General responses
  if (['hr_query', 'finance_query', 'inventory_query', 'general'].includes(actionType) && prs.length === 0 && items.length === 0) {
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Laporan')}
      <div class="agent-plan-box">
        <div style="font-size: 13px; color: #0F172A; line-height: 1.6;">
          ${formatMarkdownResponse(data.message || intent.reasoning || 'Instruksi telah diproses.')}
        </div>
      </div>
    `;
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 1b: Goods Receipt Confirmation (Penerimaan Barang Fisik Gudang via Prompt Chat)
  if (actionType === 'goods_receipt') {
    const isAlreadyDelivered = intent.workflow_id === 'goods_receipt_already_delivered';
    const isClarification = intent.workflow_id === 'goods_receipt_clarification';
    const isNotFound = intent.workflow_id === 'goods_receipt_not_found';
    
    let headerTitle = "PENERIMAAN BARANG FISIK BERHASIL DIBUKUKAN";
    let badgeText = "DELIVERED";
    let badgeClass = "badge-approved";
    let borderStyle = "border-left: 4px solid #16A34A; background: #F0FDF4; border: 1px solid #DCFCE7;";
    let headerColor = "#15803D";
    
    if (isAlreadyDelivered) {
      headerTitle = "STATUS PENGIRIMAN: SUDAH PERNAH DITERIMA";
      badgeText = "SELESAI";
      badgeClass = "badge-approved";
      borderStyle = "border-left: 4px solid #2563EB; background: #EFF6FF; border: 1px solid #BFDBFE;";
      headerColor = "#1D4ED8";
    } else if (isClarification) {
      headerTitle = "PURCHASE ORDER AKTIF (ORDERED)";
      badgeText = "ORDERED";
      badgeClass = "badge-low_stock";
      borderStyle = "border-left: 4px solid #D97706; background: #FFFBEB; border: 1px solid #FDE68A;";
      headerColor = "#B45309";
    } else if (isNotFound) {
      headerTitle = "PURCHASE ORDER TIDAK DITEMUKAN";
      badgeText = "PERIKSA KEMBALI";
      badgeClass = "badge-rejected";
      borderStyle = "border-left: 4px solid #DC2626; background: #FEF2F2; border: 1px solid #FECACA;";
      headerColor = "#B91C1C";
    }

    const targetPoId = data.po_id || intent.po_id;
    const poBtnHtml = (targetPoId && !isNotFound && !isClarification) ? `
      <div style="display: flex; justify-content: flex-end; margin-top: 10px; gap: 8px;">
        <a href="/api/documents/po/${encodeURIComponent(targetPoId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
          <span>Unduh PDF PO</span>
        </a>
        <button class="btn btn-secondary btn-sm" onclick="openPoPdfModal('${escapeHtml(targetPoId)}', '${escapeHtml(data.po_number || intent.po_number || targetPoId)}')">
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          <span>Lihat Dokumen PO (PDF)</span>
        </button>
      </div>
    ` : '';

    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Penerimaan Logistik')}
      <div class="agent-plan-box">
        <div class="action-card" style="${borderStyle} margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: ${headerColor};">${headerTitle}</span>
            <span class="badge ${badgeClass}">${badgeText}</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: #0F172A; line-height: 1.6;">
            ${formatMarkdownResponse(data.message)}
            ${poBtnHtml}
          </div>
        </div>
      </div>
    `;
    if (!isNotFound && !isClarification) {
      openDataSidebar('canvas-pos');
    }
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 1c: View / Download PO Document via AI Prompt
  if (actionType === 'view_po_document') {
    const poId = data.po_id || intent.po_id;
    const poNum = data.po_number || intent.po_number || poId;
    const supplier = data.supplier_name || 'Vendor Terdaftar';
    const total = data.grand_total || 0;
    const st = data.status || 'ORDERED';

    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Dokumen PO (PDF)')}
      <div class="agent-plan-box">
        <div class="action-card" style="border-left: 4px solid #2563EB; background: #EFF6FF; border: 1px solid #BFDBFE; margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #1D4ED8;">DOKUMEN RESMI PURCHASE ORDER TERBIT (PDF)</span>
            <span class="badge badge-approved">${escapeHtml(st)}</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: #1E3A8A; line-height: 1.6;">
            ${formatMarkdownResponse(data.message)}
            <div style="display: flex; justify-content: flex-end; margin-top: 12px; gap: 8px;">
              <a href="/api/documents/po/${encodeURIComponent(poId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                <span>Unduh PDF</span>
              </a>
              <button class="btn btn-primary btn-sm" onclick="openPoPdfModal('${escapeHtml(poId)}', '${escapeHtml(poNum)}', '${escapeHtml(supplier)}', ${total}, '${escapeHtml(st)}')">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span>Lihat Dokumen PDF</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 2: PR Document(s) Generated
  if (prs.length > 0) {
    const prCards = prs.map(pr => {
      const rawStatus = String(pr.status || '').toUpperCase();
      const supplier = pr.supplier_name || 'Vendor Terdaftar';
      const grandTotal = Number(pr.grand_total || pr.total_budget || 0);
      const escapedSupplier = escapeHtml(supplier).replace(/'/g, "\\'");

      return `
        <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px; margin-top: 8px; box-shadow: var(--shadow-xs);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div>
              <span style="font-family: var(--font-mono); font-weight: 700; color: #2563EB; font-size: 12px; background: #EFF6FF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${pr.pr_number}</span>
              <span style="font-size: 12.5px; margin-left: 6px; color: #334155; font-weight: 600;">${escapeHtml(supplier)}</span>
            </div>
            <span style="font-weight: 800; font-size: 14px; color: #0F172A;">${formatCurrency(grandTotal)}</span>
          </div>
          <div style="font-size: 12.5px; color: #475569; margin-bottom: 10px; line-height: 1.6;">
            ${(pr.items || []).map(it => `• <strong>${escapeHtml(it.item_name || it.name)}</strong>: ${it.quantity || it.reorder_qty} ${it.unit || 'pcs'}`).join('<br>')}
          </div>
          <div style="background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #166534; display: flex; align-items: center; gap: 8px;">
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
            <span>Dokumen PR resmi telah dikompilasi (PDF) dan notifikasi persetujuan telah otomatis dikirimkan ke email manajer.</span>
          </div>
          <div style="display: flex; justify-content: flex-end;">
            <button class="btn btn-secondary btn-sm" onclick="openPdfModal('${pr.pr_number}', '${escapedSupplier}', ${grandTotal}, '${rawStatus}')">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
              <span>Lihat Dokumen PDF</span>
            </button>
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('PR Diterbitkan')}
      <div class="agent-plan-box">
        <div class="agent-plan-title">INFORMASI & STATUS PENGADAAN:</div>
        <div style="font-size: 13px; font-weight: 600; color: #0F172A; margin-bottom: 6px; line-height: 1.5;">
          ${escapeHtml(intent.reasoning || data.message || 'Dokumen pengadaan berhasil diterbitkan dan diproses.')}
        </div>
        <div class="action-card" style="border-left: 4px solid #16A34A; background: #F0FDF4; border: 1px solid #DCFCE7;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #15803D;">DOKUMEN PR DITERBITKAN & TERKIRIM KE EMAIL (${prs.length})</span>
            <span class="badge badge-approved">TERKIRIM KE EMAIL</span>
          </div>
          <div class="action-card-body">
            ${prCards}
          </div>
        </div>
      </div>
    `;
    openDataSidebar('canvas-prs');
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 3: Threshold Updated
  if (actionType === 'update_threshold') {
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Ambang Batas')}
      <div class="agent-plan-box">
        <div class="action-card" style="border-left: 4px solid #2563EB; background: #EFF6FF; border: 1px solid #DBEAFE; margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #1D4ED8;">BATAS STOK DIPERBARUI</span>
            <span class="badge badge-approved">TERSIMPAN</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: #1E3A8A; line-height: 1.5;">
            ${escapeHtml(data.message)}
          </div>
        </div>
      </div>
    `;
    openDataSidebar('canvas-inventory');
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 3b: Product Registration
  if (actionType === 'register_product') {
    const isError = data.message && (data.message.includes('ditolak') || data.message.includes('kurang') || data.message.includes('gagal'));
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml(isError ? 'Pendaftaran Ditolak' : 'Barang Terdaftar', isError)}
      <div class="agent-plan-box">
        <div class="action-card" style="border-left: 4px solid ${isError ? '#DC2626' : '#16A34A'}; background: ${isError ? '#FEF2F2' : '#F0FDF4'}; border: 1px solid ${isError ? '#FECACA' : '#DCFCE7'}; margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: ${isError ? '#B91C1C' : '#15803D'};">PENDAFTARAN BARANG BARU</span>
            <span class="badge ${isError ? 'badge-rejected' : 'badge-approved'}">${isError ? 'DITOLAK' : 'TERDAFTAR'}</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: ${isError ? '#991B1B' : '#166534'}; line-height: 1.5;">
            ${escapeHtml(data.message)}
            ${items.length > 0 ? `
              <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed ${isError ? '#FCA5A5' : '#BBF7D0'}; display: flex; flex-wrap: wrap; gap: 6px;">
                ${items.map(it => `
                  <span class="badge badge-normal">
                    ${escapeHtml(it.name)}: ${it.current_stock} ${it.unit} (Min: ${it.min_stock})
                  </span>
                `).join('')}
              </div>
            ` : ''}
          </div>
        </div>
      </div>
    `;
    if (!isError) {
      openDataSidebar('canvas-inventory');
    }
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 4: Email Notification
  if (actionType === 'notify_email') {
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Notifikasi Email')}
      <div class="agent-plan-box">
        <div class="action-card" style="border-left: 4px solid #16A34A; background: #F0FDF4; border: 1px solid #DCFCE7; margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #15803D;">OTOMATISASI & NOTIFIKASI</span>
            <span class="badge badge-approved">TERKIRIM</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: #166534;">
            ${escapeHtml(data.message)}
            ${items.length > 0 ? `
              <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #BBF7D0; display: flex; flex-wrap: wrap; gap: 6px;">
                ${items.map(it => `
                  <span class="badge ${it.current_stock <= 0 ? 'badge-out_of_stock' : (it.current_stock <= it.min_stock ? 'badge-low_stock' : 'badge-approved')}">
                    ${escapeHtml(it.name)}: ${it.current_stock} ${it.unit}
                  </span>
                `).join('')}
              </div>
            ` : ''}
          </div>
        </div>
      </div>
    `;
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 5: General with affected items
  container.innerHTML = `
    ${getAgentBubbleHeaderHtml('Laporan Inventaris')}
    <div class="agent-plan-box">
      <div class="action-card" style="border-left: 4px solid #2563EB; background: #F8FAFC; border: 1px solid #E2E8F0; margin-top: 0;">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 12.5px; color: #2563EB;">INFORMASI & LAPORAN INVENTARIS</span>
          <span class="badge badge-normal">STATUS REAL-TIME</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #334155; line-height: 1.5;">
          ${escapeHtml(data.message || 'Laporan inventaris berhasil disusun.')}
          ${items.length > 0 ? `
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #E2E8F0; display: flex; flex-wrap: wrap; gap: 6px;">
              ${items.map(it => `
                <span class="badge ${it.current_stock <= 0 ? 'badge-out_of_stock' : (it.current_stock <= it.min_stock ? 'badge-low_stock' : 'badge-approved')}">
                  ${escapeHtml(it.name)}: ${it.current_stock} ${it.unit}
                </span>
              `).join('')}
            </div>
          ` : ''}
        </div>
      </div>
    </div>
  `;

  feed.appendChild(container);
  scrollChatToBottom();
}

// --- Terminal Logs ---
function appendTerminalLog(log) {
  const terminal = document.getElementById('liveAgentTerminal');
  if (!terminal) return;

  const line = document.createElement('div');
  line.className = 'terminal-line';

  let msgClass = 'terminal-msg-info';
  if (log.status === 'success') msgClass = 'terminal-msg-success';
  if (log.status === 'warning') msgClass = 'terminal-msg-warning';
  if (log.status === 'error') msgClass = 'terminal-msg-error';

  line.innerHTML = `
    <span class="terminal-time">[${log.timestamp || '00:00:00'}]</span>
    <span class="terminal-agent">[${escapeHtml(log.agent_name || 'Agent')}]</span>
    <span class="terminal-step">${escapeHtml(log.step_name || 'Step')}:</span>
    <span class="${msgClass}">${escapeHtml(log.message || '')}</span>
  `;

  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

function clearTerminalLogs() {
  const terminal = document.getElementById('liveAgentTerminal');
  if (terminal) terminal.innerHTML = '';
}

// --- Utilities ---
function formatCurrency(num) {
  const n = Number(num);
  if (isNaN(n) || num === null || num === undefined) {
    return 'Rp 0';
  }
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    maximumFractionDigits: 0
  }).format(n);
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
    .replace(/\n/g, '<br>');
}

function showToast(message, type = 'info') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type === 'success' ? 'toast-success' : (type === 'error' ? 'toast-error' : '')}`;
  
  let iconSvg = `<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`;
  if (type === 'success') {
    iconSvg = `<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#10B981"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`;
  } else if (type === 'error') {
    iconSvg = `<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#EF4444"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>`;
  }

  toast.innerHTML = `${iconSvg}<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 250);
  }, 3000);
}

// --- API Health Checker ---
async function checkApiHealth() {
  const dot = document.getElementById('apiHealthDot');
  const text = document.getElementById('apiHealthText');
  if (!dot || !text) return;

  try {
    const res = await fetch('/health', { method: 'GET' });
    const data = await res.json().catch(() => ({}));

    if (res.ok && data.llm_connected) {
      dot.style.backgroundColor = '#10B981';
      dot.style.boxShadow = '0 0 6px rgba(16, 185, 129, 0.4)';
      text.textContent = 'API Connected';
      text.style.color = '#15803D';
    } else {
      dot.style.backgroundColor = '#EF4444';
      dot.style.boxShadow = '0 0 6px rgba(239, 68, 68, 0.4)';
      text.textContent = 'API Disconnected';
      text.style.color = '#DC2626';
    }
  } catch (e) {
    dot.style.backgroundColor = '#EF4444';
    dot.style.boxShadow = '0 0 6px rgba(239, 68, 68, 0.4)';
    text.textContent = 'API Disconnected';
    text.style.color = '#DC2626';
  }
}

checkApiHealth();
setInterval(checkApiHealth, 6000);

function useCopilotSuggestion(promptText) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = promptText;
    autoResizePromptInput();
    input.focus();
    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// ==============================================================================
// DOMAIN 2 (HR & WORKFORCE): INTERACTIVE CHAT LEAVE APPLICATION FORM
// ==============================================================================

async function renderLeaveRequestChatForm(targetContainer = null) {
  const container = document.getElementById('geminiChatContainer');
  if (container) container.classList.remove('is-empty-state');

  let parent = targetContainer;
  if (!parent) {
    const feed = document.getElementById('copilotFeed');
    if (!feed) return;
    const agentBox = document.createElement('div');
    agentBox.className = 'agent-response-box';
    agentBox.innerHTML = `
      ${getAgentBubbleHeaderHtml('HR Assistant')}
      <div class="stream-text-content" style="margin-bottom: 8px;">
        Silakan lengkapi formulir permohonan cuti teknisi di bawah ini. Setelah dikonfirmasi dan dikirim, data akan langsung tersimpan di basis data DuckDB dan berkas resmi PDF akan dikirimkan ke HR.
      </div>
      <div class="stream-artifacts-slot"></div>
    `;
    feed.appendChild(agentBox);
    parent = agentBox.querySelector('.stream-artifacts-slot');
  }

  // Fetch employees list if not already cached
  if (!state.employeesList || state.employeesList.length === 0) {
    try {
      const res = await fetch(`/api/balitower/hr/employees?t=${Date.now()}`);
      if (res.ok) {
        state.employeesList = await res.json();
      }
    } catch (e) {
      console.warn("Failed to load employees for leave form:", e);
    }
  }

  const emps = state.employeesList || [];
  const empOptions = emps.map(e => `
    <option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.full_name)} (${escapeHtml(e.employee_id)}) - ${escapeHtml(e.job_title)}</option>
  `).join('');

  const subOptions = `<option value="">-- Pilih Teknisi Pengganti (Opsional) --</option>` + emps.map(e => `
    <option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.full_name)} - ${escapeHtml(e.job_title)}</option>
  `).join('');

  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const defaultDate = tomorrow.toISOString().split('T')[0];

  const formId = 'leaveForm_' + Date.now();

  parent.innerHTML = `
    <div class="leave-form-card" id="${formId}">
      <div class="leave-form-header">
        <span class="leave-form-title">Formulir Permohonan Cuti Karyawan</span>
        <span class="badge badge-pending">DRAF BARU</span>
      </div>
      <div class="leave-form-body">
        <!-- Field 1: Karyawan Pemohon (Full Width) -->
        <div class="leave-form-group">
          <label class="leave-form-label">Karyawan Pemohon <span style="color: #DC2626;">*</span></label>
          <select class="leave-form-select" id="${formId}_emp">
            ${empOptions}
          </select>
        </div>

        <!-- Row 1: Jenis Cuti & Durasi Hari Kerja -->
        <div class="leave-form-row">
          <div class="leave-form-col">
            <label class="leave-form-label">Jenis Cuti <span style="color: #DC2626;">*</span></label>
            <select class="leave-form-select" id="${formId}_type">
              <option value="ANNUAL_LEAVE">Cuti Tahunan</option>
              <option value="SICK_LEAVE">Cuti Sakit</option>
              <option value="SPECIAL_LEAVE">Cuti Khusus / Alasan Penting</option>
              <option value="MATERNITY_LEAVE">Cuti Melahirkan</option>
            </select>
          </div>
          <div class="leave-form-col">
            <label class="leave-form-label">Durasi Hari Kerja <span style="color: #DC2626;">*</span></label>
            <input type="number" class="leave-form-input" id="${formId}_days" value="1" min="1" max="30" placeholder="Jumlah hari...">
          </div>
        </div>

        <!-- Row 2: Tanggal Mulai Cuti & Teknisi Pengganti -->
        <div class="leave-form-row">
          <div class="leave-form-col">
            <label class="leave-form-label">Tanggal Mulai Cuti <span style="color: #DC2626;">*</span></label>
            <input type="date" class="leave-form-input" id="${formId}_start" value="${defaultDate}">
          </div>
          <div class="leave-form-col">
            <label class="leave-form-label">Teknisi Pengganti / Backup</label>
            <select class="leave-form-select" id="${formId}_sub">
              ${subOptions}
            </select>
          </div>
        </div>

        <!-- Field 4: Alasan Pengajuan Cuti (Full Width) -->
        <div class="leave-form-group">
          <label class="leave-form-label">Alasan Pengajuan Cuti <span style="color: #DC2626;">*</span></label>
          <input type="text" class="leave-form-input" id="${formId}_reason" placeholder="Contoh: Keperluan keluarga mendesak ke luar kota..." value="">
        </div>
      </div>

      <div class="leave-form-footer">
        <span id="${formId}_error" style="color: #DC2626; font-size: 12px; display: none;"></span>
        <button class="btn btn-primary btn-sm" id="${formId}_btn" onclick="submitLeaveRequestForm('${formId}')">
          <span>Kirim Pengajuan Cuti</span>
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/>
          </svg>
        </button>
      </div>
    </div>
  `;

  scrollChatToBottom();
}

function triggerLeaveFormInChat() {
  const container = document.getElementById('geminiChatContainer');
  if (container) container.classList.remove('is-empty-state');
  renderLeaveRequestChatForm();
}

async function submitLeaveRequestForm(formId) {
  const empEl = document.getElementById(`${formId}_emp`);
  const typeEl = document.getElementById(`${formId}_type`);
  const startEl = document.getElementById(`${formId}_start`);
  const daysEl = document.getElementById(`${formId}_days`);
  const subEl = document.getElementById(`${formId}_sub`);
  const reasonEl = document.getElementById(`${formId}_reason`);
  const btn = document.getElementById(`${formId}_btn`);
  const errorEl = document.getElementById(`${formId}_error`);

  if (!empEl || !typeEl || !startEl || !daysEl || !reasonEl) return;

  const employeeId = empEl.value.trim();
  const leaveType = typeEl.value;
  const startDate = startEl.value.trim();
  const daysRequested = parseInt(daysEl.value, 10);
  const reason = reasonEl.value.trim();
  const substituteId = subEl ? subEl.value.trim() : null;

  if (errorEl) errorEl.style.display = 'none';

  if (!employeeId) {
    if (errorEl) { errorEl.textContent = 'Silakan pilih karyawan pemohon.'; errorEl.style.display = 'block'; }
    return;
  }
  if (!startDate) {
    if (errorEl) { errorEl.textContent = 'Silakan tentukan tanggal mulai cuti.'; errorEl.style.display = 'block'; }
    return;
  }
  if (!daysRequested || daysRequested < 1) {
    if (errorEl) { errorEl.textContent = 'Durasi hari cuti minimal 1 hari.'; errorEl.style.display = 'block'; }
    return;
  }
  if (!reason) {
    if (errorEl) { errorEl.textContent = 'Alasan pengajuan cuti wajib diisi.'; errorEl.style.display = 'block'; }
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>Menyimpan ke DB & Mengirim PDF...</span>`;
  }

  try {
    const res = await fetch('/api/balitower/hr/leave-requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        employee_id: employeeId,
        leave_type: leaveType,
        start_date: startDate,
        days_requested: daysRequested,
        reason: reason,
        substitute_employee_id: substituteId || null
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Gagal mencatat pengajuan cuti.");
    }

    const respData = await res.json();
    const d = respData.data || {};
    const leaveId = respData.leave_id || d.leave_id || 'LV-2026-NEW';
    const formCard = document.getElementById(formId);

    if (formCard) {
      // Update parent bubble stream text to avoid duplicate text
      const parentBox = formCard.closest('.agent-response-box');
      if (parentBox) {
        const streamText = parentBox.querySelector('.stream-text-content');
        if (streamText) {
          streamText.textContent = 'Permohonan cuti telah berhasil dicatat dan diajukan ke Divisi HR:';
        }
      }

      const typeLabelMap = {
        'ANNUAL_LEAVE': 'Cuti Tahunan',
        'SICK_LEAVE': 'Cuti Sakit',
        'SPECIAL_LEAVE': 'Cuti Khusus / Alasan Penting',
        'MATERNITY_LEAVE': 'Cuti Melahirkan'
      };
      const typeLabel = typeLabelMap[d.leave_type] || d.leave_type;

      formCard.className = 'leave-success-card';
      formCard.innerHTML = `
        <div class="leave-success-header">
          <span class="leave-success-title">Pengajuan Cuti Berhasil Dicatat</span>
          <span class="badge badge-approved">TERKIRIM KE HR</span>
        </div>
        <div class="leave-success-body">
          <div class="leave-info-grid">
            <div class="leave-info-item">
              <span class="leave-info-k">No. Pengajuan:</span>
              <span class="badge" style="background:#EFF6FF; color:#2563EB; font-family:var(--font-mono); font-weight:700;">${escapeHtml(leaveId)}</span>
            </div>
            <div class="leave-info-item">
              <span class="leave-info-k">Pemohon:</span>
              <span class="leave-info-v"><strong>${escapeHtml(d.applicant_name || '-')}</strong> (${escapeHtml(d.job_title || '-')})</span>
            </div>
            <div class="leave-info-item">
              <span class="leave-info-k">Periode Cuti:</span>
              <span class="leave-info-v">${escapeHtml(d.start_date)} s/d ${escapeHtml(d.end_date)} (<strong>${d.days_requested} hari kerja</strong>)</span>
            </div>
            <div class="leave-info-item">
              <span class="leave-info-k">Jenis Cuti:</span>
              <span class="leave-info-v">${escapeHtml(typeLabel)}</span>
            </div>
            <div class="leave-info-item" style="grid-column: 1 / -1;">
              <span class="leave-info-k">Alasan:</span>
              <span class="leave-info-v">${escapeHtml(d.reason || '-')}</span>
            </div>
          </div>
          <div class="leave-dispatch-notice">
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
            </svg>
            <span>Berkas permohonan resmi format PDF telah diterbitkan dan notifikasi telah dikirimkan ke HR.</span>
          </div>
          <div class="leave-action-row">
            <button class="btn btn-primary btn-sm" onclick="openLeavePdfModal('${leaveId}', '${escapeHtml(d.applicant_name || '')}', '${escapeHtml(typeLabel)}', ${d.days_requested}, 'PENDING_APPROVAL')">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
              </svg>
              <span>Lihat Dokumen PDF</span>
            </button>
            <a href="/api/documents/leave/${leaveId}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
              </svg>
              <span>Unduh PDF</span>
            </a>
          </div>
        </div>
      `;
    }

    showToast(`Pengajuan cuti ${leaveId} berhasil disimpan dan dikirim ke HR`, 'success');
    loadHrData();
    loadEmployees();
    saveCopilotFeed();
  } catch (err) {
    if (errorEl) {
      errorEl.textContent = err.message || "Gagal menyimpan pengajuan cuti.";
      errorEl.style.display = 'block';
    }
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>Kirim Pengajuan Cuti</span>`;
    }
    showToast(err.message || "Gagal memproses pengajuan cuti", 'error');
  }
}

// --- Auto-Refresh on Window Focus / Tab Activation (e.g., returning from Email Quick Approval) ---
window.addEventListener('focus', () => {
  const hrCanvas = document.getElementById('canvas-hr');
  if (hrCanvas && hrCanvas.classList.contains('active')) {
    loadHrData();
    loadEmployees();
  }
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    const hrCanvas = document.getElementById('canvas-hr');
    if (hrCanvas && hrCanvas.classList.contains('active')) {
      loadHrData();
      loadEmployees();
    }
  }
});
