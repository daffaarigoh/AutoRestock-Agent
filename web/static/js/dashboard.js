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

document.addEventListener('DOMContentLoaded', () => {
  const uName = sessionStorage.getItem('username');
  const uTenant = sessionStorage.getItem('tenant_id');
  const uRole = sessionStorage.getItem('role');

  if (uName) {
    const el = document.getElementById('displayUsername');
    if (el) el.textContent = uName;
  }
  if (uTenant) {
    const el = document.getElementById('displayTenant');
    if (el) el.textContent = uTenant;
  }
  if (uRole === 'ADMIN') {
    const adminNav = document.getElementById('btnAdminNav');
    if (adminNav) adminNav.style.display = 'inline-flex';
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
  loadAllData();
  
  // Real-time synchronization (2s interval + instant refresh on window focus)
  setInterval(loadAllData, 2000);
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

  // Restore saved width from localStorage
  const savedWidth = localStorage.getItem('ar_sidebar_width');
  if (savedWidth && !isNaN(Number(savedWidth))) {
    const w = Math.max(320, Math.min(window.innerWidth * 0.8, Number(savedWidth)));
    document.documentElement.style.setProperty('--sidebar-width', `${w}px`);
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
    if (newWidth < 220) {
      closeDataSidebar();
      return;
    }

    // Constraints: min 320px, max 80% of screen width (max 1000px)
    newWidth = Math.max(320, Math.min(window.innerWidth * 0.8, Math.min(1000, newWidth)));

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

// --- Tab Switching ---
function switchCanvasTab(tabId) {
  document.querySelectorAll('.sidebar-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-target') === tabId);
  });

  document.querySelectorAll('.canvas-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === tabId);
  });

  if (tabId === 'canvas-inventory') {
    loadInventoryItems();
  } else if (tabId === 'canvas-prs') {
    loadApprovals();
  }
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

// --- Data Fetching ---
async function loadAllData() {
  await Promise.allSettled([
    loadInventoryItems(),
    loadApprovals(),
    loadDashboardStats()
  ]);
  await loadCategories();
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
    const res = await fetch(`/api/inventory/items?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const rawItems = await res.json();
      state.items = (rawItems || []).map(it => ({
        sku: it.item_id || it.sku || '',
        name: it.name || '',
        supplier_name: it.supplier_name || '-',
        category: it.category || 'General',
        current_stock: Number(it.current_stock) || 0,
        unit: it.unit || 'pcs',
        min_stock: Number(it.min_threshold) || 0,
        max_stock: Number(it.max_threshold) || 0,
        unit_price: Number(it.unit_price) || 0
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
        <td class="text-right" style="font-weight: 700; color: #0F172A;">${it.current_stock} <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">${it.unit}</span></td>
        <td class="text-right" style="font-size: 11px; color: var(--text-muted);">${it.min_stock} / ${it.max_stock}</td>
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

// --- Quick Action Chip Handler ---
function quickFillPrompt(promptText) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = promptText;
    input.focus();
    submitPrompt();
  }
}

// --- Interactive Prompt Submission ---
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    submitPrompt();
  }
}

async function submitPrompt() {
  const input = document.getElementById('promptInput');
  if (!input) return;

  const promptText = input.value.trim();
  if (!promptText) return;

  input.value = '';
  input.style.height = 'auto';

  appendUserMessage(promptText);

  const loadingId = appendAgentLoadingBubble();
  const btn = document.getElementById('btnSendPrompt');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/agent/custom-prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: promptText, destinations: [] })
    });

    const data = await res.json();
    removeLoadingBubble(loadingId);

    if (res.ok) {
      appendAgentResponseCard(data);
      await loadAllData();
      saveCopilotFeed();
    } else {
      appendAgentErrorMessage(data.detail || "Gagal memproses instruksi.");
      saveCopilotFeed();
    }
  } catch (e) {
    removeLoadingBubble(loadingId);
    appendAgentErrorMessage(e.message || "Terjadi kesalahan koneksi ke server backend.");
    saveCopilotFeed();
  } finally {
    if (btn) btn.disabled = false;
  }
}

function appendUserMessage(text) {
  const container = document.getElementById('geminiChatContainer');
  if (container) container.classList.remove('is-empty-state');

  const feed = document.getElementById('copilotFeed');
  if (!feed) return;

  const userBox = document.createElement('div');
  userBox.className = 'user-query-bubble';
  userBox.textContent = text;
  feed.appendChild(userBox);
  feed.scrollTop = feed.scrollHeight;
}

function appendAgentLoadingBubble() {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return null;

  const id = 'loading_' + Date.now();
  const box = document.createElement('div');
  box.id = id;
  box.className = 'agent-response-box';
  box.innerHTML = `
    <div class="agent-plan-box" style="display: flex; align-items: center; gap: 8px; color: #2563EB;">
      <svg class="spin-icon" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
      </svg>
      <span style="font-weight: 600; font-size: 12.5px;">Menganalisis instruksi & menjalankan proses...</span>
    </div>
  `;
  feed.appendChild(box);
  feed.scrollTop = feed.scrollHeight;
  return id;
}

function removeLoadingBubble(id) {
  if (!id) return;
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendAgentErrorMessage(errorText) {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return;

  const box = document.createElement('div');
  box.className = 'agent-response-box';
  box.innerHTML = `
    <div class="agent-plan-box" style="border-left: 4px solid #DC2626; background: #FEF2F2;">
      <div class="agent-plan-title" style="color: #DC2626;">TERJADI KESALAHAN</div>
      <div style="font-size: 13px; color: #991B1B;">${escapeHtml(errorText)}</div>
    </div>
  `;
  feed.appendChild(box);
  feed.scrollTop = feed.scrollHeight;
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

  // Scenario 1: General message / greeting / simple response
  if (actionType === 'general' && prs.length === 0 && items.length === 0 && actionType !== 'update_threshold') {
    container.innerHTML = `
      <div class="agent-plan-box">
        <div style="font-size: 13.5px; color: #0F172A; line-height: 1.6;">
          ${escapeHtml(data.message || intent.reasoning || 'Instruksi telah diproses.')}
        </div>
      </div>
    `;
    feed.appendChild(container);
    feed.scrollTop = feed.scrollHeight;
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
    feed.scrollTop = feed.scrollHeight;
    return;
  }

  // Scenario 3: Threshold Updated
  if (actionType === 'update_threshold') {
    container.innerHTML = `
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
    feed.scrollTop = feed.scrollHeight;
    return;
  }

  // Scenario 3b: Product Registration
  if (actionType === 'register_product') {
    const isError = data.message && (data.message.includes('ditolak') || data.message.includes('kurang') || data.message.includes('gagal'));
    container.innerHTML = `
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
    feed.scrollTop = feed.scrollHeight;
    return;
  }

  // Scenario 4: Email / Telegram Notification
  if (actionType === 'notify_email') {
    container.innerHTML = `
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
    feed.scrollTop = feed.scrollHeight;
    return;
  }

  // Scenario 5: General with affected items
  container.innerHTML = `
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
  feed.scrollTop = feed.scrollHeight;
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
