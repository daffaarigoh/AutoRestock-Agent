/**
 * AutoRestock-V2 Enterprise Prompt-First Operations Center
 * Orchestrates dynamic prompt execution, in-app modal preview, live data canvas updates, and WebSocket streaming.
 */

const state = {
  stats: {},
  items: [],
  categories: [],
  prs: [],
  attachedFile: null,
  currentModalPrNumber: null,
  socket: null,
  socketConnected: false
};

document.addEventListener('DOMContentLoaded', () => {
  const uName = localStorage.getItem('username');
  const uTenant = localStorage.getItem('tenant_id');
  if (uName) document.getElementById('displayUsername').textContent = uName;
  if (uTenant) document.getElementById('displayTenant').textContent = uTenant;

  restoreUiCustomizations();
  restoreCopilotFeed();
  // initWebSocket(); // Disabled to prevent 403 Forbidden backend log spam
  loadAllData();
  setInterval(loadDashboardStats, 15000);
});

// Override fetch to inject Auth Headers automatically
const originalFetch = window.fetch;
window.fetch = async function() {
    let [resource, config] = arguments;
    if(config === undefined) {
        config = {};
    }
    if(config.headers === undefined) {
        config.headers = {};
    }
    // Convert Headers object to literal if necessary, simplified approach:
    const token = localStorage.getItem('access_token');
    if (token) {
        if (config.headers instanceof Headers) {
            config.headers.append('Authorization', `Bearer ${token}`);
        } else {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
    }
    return await originalFetch(resource, config);
};

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

// --- Chat History Persistence & Gemini Empty State in LocalStorage ---
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
    // Sanitize legacy dark colors from older versions
    saved = saved
      .replace(/#0f172a/gi, '#FFFFFF')
      .replace(/#334155/gi, '#E2E8F0')
      .replace(/#1e293b/gi, '#FFFFFF')
      .replace(/#000000/gi, '#FFFFFF');
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
  showToast("Riwayat chat dibersihkan", "success");
}

// --- Collapsible Data Sidebar Controls (Gemini Chat-First) ---
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

// --- Tab Switching in Data Sidebar ---
function switchCanvasTab(tabId) {
  document.querySelectorAll('.sidebar-tab-btn, .canvas-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-target') === tabId);
  });

  document.querySelectorAll('.canvas-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === tabId);
  });
}

// --- Visual Refresh Button Animation ---
async function triggerVisualRefresh(btnId, callback) {
  const btn = document.getElementById(btnId);
  const icon = btn ? btn.querySelector('svg') : null;

  if (icon) icon.classList.add('spin-icon');
  if (btn) btn.disabled = true;

  try {
    await callback();
    showToast("Data berhasil diperbarui!", "success");
  } catch (e) {
    showToast("Gagal memperbarui data", "error");
  } finally {
    if (icon) icon.classList.remove('spin-icon');
    if (btn) btn.disabled = false;
  }
}

// --- Dynamic Categories ---
async function loadCategories() {
  try {
    // Dynamically extract unique categories from loaded items
    if (state.items && state.items.length > 0) {
      const cats = new Set(state.items.map(it => it.category));
      state.categories = Array.from(cats).filter(c => c);
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
  // Use sequential awaits to prevent DuckDB connection lock contention
  // when multiple endpoints try to open the database file concurrently.
  await loadDashboardStats();
  await loadInventoryItems();
  await loadApprovals();
  // Load categories after items are loaded
  await loadCategories();
}

async function loadDashboardStats() {
  try {
    const res = await fetch('/api/stream/inventory-summary');
    if (res.ok) {
      state.stats = await res.json();
      renderStats();
    }
  } catch (e) {
    console.error("Failed to fetch stats:", e);
  }
}

function renderStats() {
  const s = state.stats;
  const elTotal = document.getElementById('kpiTotalItems');
  if (elTotal) elTotal.textContent = s.total_items || 0;
  const elLow = document.getElementById('kpiLowStock');
  if (elLow) elLow.textContent = s.low_stock_items || 0;
  const elPending = document.getElementById('kpiPendingPrs');
  if (elPending) elPending.textContent = s.pending_prs || 0;
  const elVal = document.getElementById('kpiInventoryValue');
  if (elVal) elVal.textContent = formatCurrency(s.total_inventory_value_idr || 0);
}

// --- Inventory Catalog ---
async function loadInventoryItems() {
  try {
    const res = await fetch('/api/inventory/items');
    if (res.ok) {
      const rawItems = await res.json();
      state.items = rawItems.map(it => ({
        sku: it.item_id,
        name: it.name,
        supplier_name: '-', 
        category: it.category,
        current_stock: it.current_stock,
        unit: it.unit,
        min_stock: it.min_threshold,
        max_stock: (it.min_threshold || 1) * 3, 
        unit_price: it.unit_price || 0 
      }));
      filterCatalogTable();
    }
  } catch (e) {
    console.error("Failed to load inventory:", e);
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
        <td style="font-family: var(--font-mono); font-weight: 700; color: #60A5FA; font-size: 11.5px;">${it.sku}</td>
        <td>
          <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(it.name)}</div>
          <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(it.supplier_name || it.supplier_id)}</div>
        </td>
        <td><span style="font-size: 11px; background: rgba(255, 255, 255, 0.06); color: #94A3B8; border: 1px solid var(--border-color); padding: 2px 7px; border-radius: 4px;">${escapeHtml(it.category)}</span></td>
        <td class="text-right" style="font-weight: 700;">${it.current_stock} <span style="font-size: 10px; font-weight: 400; color: var(--text-muted);">${it.unit}</span></td>
        <td class="text-right" style="font-size: 11px; color: var(--text-muted);">${it.min_stock} / ${it.max_stock}</td>
        <td class="text-right" style="font-weight: 600;">${formatCurrency(it.unit_price)}</td>
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

// --- Purchase Requisitions (Pending on Top, Approved at Bottom) ---
async function loadApprovals() {
  try {
    const res = await fetch('/api/approval/list');
    if (res.ok) {
      const allPrs = await res.json();
      
      // Sort PRs: Pending approvals on TOP, Approved/Rejected at the bottom
      state.prs = allPrs.sort((a, b) => {
        const aPending = a.status === 'pending_approval' ? 1 : 0;
        const bPending = b.status === 'pending_approval' ? 1 : 0;
        if (aPending !== bPending) {
          return bPending - aPending; // 1 (pending) comes before 0 (approved)
        }
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
    const isApproved = pr.status === 'approved';
    const escapedSupplier = escapeHtml(pr.supplier_name).replace(/'/g, "\\'");
    return `
      <tr id="row-pr-${pr.pr_number}">
        <td style="font-family: var(--font-mono); font-weight: 700; color: #60A5FA; font-size: 11.5px;">${pr.pr_number}</td>
        <td style="font-weight: 600; color: var(--text-main);">${escapeHtml(pr.supplier_name)}</td>
        <td class="text-center" style="color: var(--text-secondary);">${pr.items?.length || 0} item</td>
        <td class="text-right" style="font-weight: 700; color: var(--text-main);">${formatCurrency(pr.grand_total)}</td>
        <td class="text-center" id="badge-container-${pr.pr_number}">
          <span class="badge ${isApproved ? 'badge-approved' : 'badge-pending'}">${isApproved ? 'DISETUJUI' : 'PENDING'}</span>
        </td>
        <td class="text-center">
          <div style="display: inline-flex; gap: 4px;" id="actions-container-${pr.pr_number}">
            <button class="btn btn-secondary btn-sm" onclick="openPdfModal('${pr.pr_number}', '${escapedSupplier}', ${pr.grand_total}, '${pr.status}')">
              📄 Lihat PDF
            </button>
            ${!isApproved ? `
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

  document.getElementById('modalPrNumber').textContent = prNumber;
  document.getElementById('modalSupplierName').textContent = supplierName ? `| ${supplierName}` : '';
  document.getElementById('modalGrandTotal').textContent = `Total Estimasi: ${formatCurrency(grandTotal || 0)}`;

  const isApproved = status === 'approved';
  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    statusBadge.className = `badge ${isApproved ? 'badge-approved' : 'badge-pending'}`;
    statusBadge.textContent = isApproved ? 'DISETUJUI' : 'PENDING APPROVAL';
  }

  // Set download button href with ?download=true
  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/pr/${prNumber}/download?download=true`;
    downloadBtn.setAttribute('download', `${prNumber}.pdf`);
  }

  // Set approve button visibility
  const approveBtn = document.getElementById('modalApproveBtn');
  if (approveBtn) {
    approveBtn.style.display = isApproved ? 'none' : 'inline-flex';
  }

  // Load iframe with inline preview
  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/pr/${prNumber}/download?inline=true`;
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

async function approvePrFromModal() {
  if (state.currentModalPrNumber) {
    await approvePrQuick(state.currentModalPrNumber);
    // Update modal UI state
    const approveBtn = document.getElementById('modalApproveBtn');
    if (approveBtn) approveBtn.style.display = 'none';
    const statusBadge = document.getElementById('modalPrStatusBadge');
    if (statusBadge) {
      statusBadge.className = 'badge badge-approved';
      statusBadge.textContent = 'DISETUJUI';
    }
  }
}

// --- Quick Approve Handler with Immediate Visual Feedback ---
async function approvePrQuick(prNumber) {
  // 1. Immediately disable buttons in UI and show loading feedback
  const allActionButtons = document.querySelectorAll(`[data-pr="${prNumber}"]`);
  allActionButtons.forEach(btn => {
    btn.disabled = true;
    btn.textContent = "Menyetujui...";
  });

  try {
    const res = await fetch('/api/approvals/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pr_number: prNumber,
        action: 'approve',
        approver_name: 'Manager Pengadaan'
      })
    });

    if (res.ok) {
      showToast(`Purchase Order ${prNumber} berhasil disetujui!`, 'success');

      // Update all buttons and badges across the feed and table immediately
      allActionButtons.forEach(btn => {
        const approvedBadge = document.createElement('span');
        approvedBadge.className = 'badge badge-approved';
        approvedBadge.textContent = 'DISETUJUI';
        btn.replaceWith(approvedBadge);
      });

      // Update table badge if exists
      const tableBadge = document.getElementById(`badge-container-${prNumber}`);
      if (tableBadge) {
        tableBadge.innerHTML = `<span class="badge badge-approved">DISETUJUI</span>`;
      }

      // Reload fresh data from backend
      await loadAllData();
      saveCopilotFeed();
    } else {
      showToast("Gagal menyetujui Purchase Requisition", "error");
      allActionButtons.forEach(btn => {
        btn.disabled = false;
        btn.textContent = "Setujui";
      });
    }
  } catch (e) {
    showToast("Terjadi kesalahan jaringan", "error");
    allActionButtons.forEach(btn => {
      btn.disabled = false;
      btn.textContent = "Setujui";
    });
  }
}

// --- Prompt Copilot Execution ---
function handleKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    submitPrompt();
  }
}

async function submitPrompt(customText) {
  const input = document.getElementById('promptInput');
  const promptText = customText || (input ? input.value.trim() : '');
  const hasFile = state.attachedFile != null;

  if (!promptText && !hasFile) return;

  if (input && !customText) input.value = '';

  // 1. Append User Message
  appendUserMessage(promptText);

  // 2. Append Loading Placeholder
  const loadingId = appendAgentLoadingBubble();

  const btn = document.getElementById('btnSendPrompt');
  if (btn) btn.disabled = true;

  // Reset catalog search box so user immediately sees affected items
  const searchBox = document.getElementById('searchCatalog');
  if (searchBox) searchBox.value = '';
  const filterCat = document.getElementById('filterCategory');
  if (filterCat) filterCat.value = '';

    try {
      const destinations = [];

      let res = await fetch('/api/agent/custom-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: promptText, auto_execute: true, destinations: destinations })
      });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Terjadi kesalahan pada agent.");
    }

    if (res.ok) {
      removeLoadingBubble(loadingId);
      appendAgentResponseCard(data);
      // Auto refresh catalog, categories, and approvals instantly
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
  const userBox = document.createElement('div');
  userBox.className = 'user-query-bubble';
  userBox.textContent = text;
  feed.appendChild(userBox);
  feed.scrollTop = feed.scrollHeight;
}

function appendAgentLoadingBubble() {
  const feed = document.getElementById('copilotFeed');
  const id = 'loading_' + Date.now();
  const box = document.createElement('div');
  box.id = id;
  box.className = 'agent-response-box';
  box.innerHTML = `
    <div class="agent-plan-box" style="display: flex; align-items: center; gap: 8px; color: var(--primary);">
      <span style="font-weight: 600; font-size: 12.5px;">Menganalisis instruksi & menjalankan proses...</span>
    </div>
  `;
  feed.appendChild(box);
  feed.scrollTop = feed.scrollHeight;
  return id;
}

function removeLoadingBubble(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendAgentErrorMessage(errorText) {
  const feed = document.getElementById('copilotFeed');
  const box = document.createElement('div');
  box.className = 'agent-response-box';
  box.innerHTML = `
    <div class="agent-plan-box" style="border-left: 4px solid var(--danger);">
      <div class="agent-plan-title" style="color: var(--danger);">TERJADI KESALAHAN</div>
      <div style="font-size: 13px; color: #7f1d1d;">${escapeHtml(errorText)}</div>
    </div>
  `;
  feed.appendChild(box);
  feed.scrollTop = feed.scrollHeight;
}

function appendAgentResponseCard(data) {
  const feed = document.getElementById('copilotFeed');
  const intent = data.parsed_intent || {};
  const actionType = data.action_type || 'general';
  const prs = data.generated_prs || [];
  const items = data.affected_items || [];

  const container = document.createElement('div');
  container.className = 'agent-response-box';

  let actionHtml = '';

  // SCENARIO 1: Added New Item
  if (actionType === 'add_item' && items.length > 0) {
    const it = items[0];
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #10B981; background: rgba(16, 185, 129, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #34D399;">BARANG BARU DIDAFTARKAN KE KATALOG</span>
          <span class="badge badge-approved">SUKSES</span>
        </div>
        <div class="action-card-body">
          <div style="font-size: 14.5px; font-weight: 700; color: #FFFFFF;">${escapeHtml(it.name)}</div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; font-size: 12.5px; color: #CBD5E1;">
            <div>SKU: <strong style="font-family: var(--font-mono); color: #60A5FA;">${it.sku}</strong></div>
            <div>Kategori: <strong style="color: #F8FAFC;">${escapeHtml(it.category)}</strong></div>
            <div>Stok Awal: <strong style="color: #34D399;">${it.current_stock} ${it.unit}</strong></div>
            <div>Harga Satuan: <strong style="color: #F8FAFC;">${formatCurrency(it.unit_price)}</strong></div>
            <div>Supplier: <strong style="color: #F8FAFC;">${escapeHtml(it.supplier_name || it.supplier_id)}</strong></div>
            <div>Lokasi Gudang: <strong style="color: #F8FAFC;">${escapeHtml(it.location_bin)}</strong></div>
          </div>
        </div>
      </div>
    `;
    switchCanvasTab('canvas-inventory');
  }

  // SCENARIO 2: Stock Updated / Restocked Directly
  else if ((actionType === 'update_stock' || actionType === 'restock') && items.length > 0) {
    const it = items[0];
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #10B981; background: rgba(16, 185, 129, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #34D399;">RESTOCK / SALDO STOK DIPERBARUI</span>
          <span class="badge badge-approved">SUKSES</span>
        </div>
        <div class="action-card-body">
          <div style="font-size: 14.5px; font-weight: 700; color: #FFFFFF;">${escapeHtml(it.name)}</div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; font-size: 12.5px; color: #CBD5E1;">
            <div>SKU: <strong style="font-family: var(--font-mono); color: #60A5FA;">${it.sku}</strong></div>
            <div>Kategori: <strong style="color: #F8FAFC;">${escapeHtml(it.category)}</strong></div>
            <div>Saldo Stok di Katalog: <strong style="color: #34D399; font-size: 14px;">${it.current_stock} ${it.unit}</strong></div>
            <div>Batas Min / Max: <strong style="color: #F8FAFC;">${it.min_stock} / ${it.max_stock}</strong></div>
          </div>
          ${prs.length > 0 ? `
            <div style="margin-top: 10px; font-size: 11.5px; color: #94A3B8; padding-top: 8px; border-top: 1px dashed rgba(255, 255, 255, 0.1);">
              Dokumen pengadaan: <strong style="font-family: var(--font-mono); color: #60A5FA;">${prs[0].pr_number}</strong> (Supplier: ${escapeHtml(prs[0].supplier_name)})
            </div>
          ` : ''}
        </div>
      </div>
    `;
    switchCanvasTab('canvas-inventory');
  }

  // SCENARIO 3: Threshold Updated
  else if (actionType === 'update_threshold') {
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #3B82F6; background: rgba(59, 130, 246, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #60A5FA;">THRESHOLD BATAS STOK DIPERBARUI</span>
          <span class="badge badge-approved">TERSIMPAN</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #E2E8F0; line-height: 1.6;">
          ${escapeHtml(data.message)}
        </div>
      </div>
    `;
    switchCanvasTab('canvas-inventory');
  }

  // SCENARIO 4: PR Review / Pending Inquiries
  else if (actionType === 'review_prs' && prs.length > 0) {
    const prCards = prs.map(pr => {
      const isApproved = pr.status === 'approved';
      const escapedSupplier = escapeHtml(pr.supplier_name).replace(/'/g, "\\'");
      return `
        <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: var(--radius-sm); padding: 12px; margin-top: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div>
              <span style="font-family: var(--font-mono); font-weight: 700; color: #60A5FA; font-size: 12.5px;">${pr.pr_number}</span>
              <span style="font-size: 12px; margin-left: 6px; color: #94A3B8;">${escapeHtml(pr.supplier_name)}</span>
            </div>
            <span style="font-weight: 800; font-size: 14px; color: #FFFFFF;">${formatCurrency(pr.grand_total)}</span>
          </div>
          <div style="font-size: 12px; color: #CBD5E1; margin-bottom: 10px;">
            ${(pr.items || []).map(it => `• ${escapeHtml(it.item_name)} (${it.quantity} ${it.unit})`).join('<br>')}
          </div>
          <div style="display: flex; gap: 6px; justify-content: flex-end; align-items: center;" id="feed-actions-${pr.pr_number}">
            <button class="btn btn-secondary btn-sm" onclick="openPdfModal('${pr.pr_number}', '${escapedSupplier}', ${pr.grand_total}, '${pr.status}')">
              📄 Lihat Dokumen PDF
            </button>
            ${!isApproved ? `
              <button class="btn btn-success btn-sm btn-approve-action" data-pr="${pr.pr_number}" onclick="approvePrQuick('${pr.pr_number}')">
                Setujui Sekarang
              </button>
            ` : `<span class="badge badge-approved">DISETUJUI</span>`}
          </div>
        </div>
      `;
    }).join('');

    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #F59E0B; background: rgba(245, 158, 11, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #FBBF24;">DAFTAR PR MENUNGGU PERSETUJUAN (${prs.length})</span>
          <span class="badge badge-pending">PERLU TINJAUAN</span>
        </div>
        <div class="action-card-body">
          ${prCards}
        </div>
      </div>
    `;
    switchCanvasTab('canvas-prs');
  }

  // SCENARIO 5: Product Details / Metadata Edited (Single or Batch)
  else if (actionType === 'edit_item' && items.length > 0) {
    const listHtml = items.map(it => `
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px dashed rgba(255, 255, 255, 0.1); font-size: 13px;">
        <div>
          <span style="font-weight: 700; color: #FFFFFF;">${escapeHtml(it.name)}</span>
          <span style="font-family: var(--font-mono); color: #60A5FA; font-size: 11.5px; margin-left: 6px;">(${it.sku})</span>
        </div>
        <div style="text-align: right; display: flex; align-items: center; gap: 8px;">
          <span class="badge badge-approved" style="font-size: 11px;">${escapeHtml(it.category || 'General')}</span>
          <span style="font-weight: 700; color: #F8FAFC;">${formatCurrency(it.unit_price)}</span>
        </div>
      </div>
    `).join('');

    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #3B82F6; background: rgba(59, 130, 246, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #60A5FA;">DATA ${items.length} PRODUK BERHASIL DIUBAH</span>
          <span class="badge badge-approved">TERSIMPAN</span>
        </div>
        <div class="action-card-body">
          <div style="font-size: 13px; color: #E2E8F0; margin-bottom: 10px; line-height: 1.5;">
            ${escapeHtml(data.message)}
          </div>
          <div style="max-height: 200px; overflow-y: auto;">
            ${listHtml}
          </div>
        </div>
      </div>
    `;
    loadAllData();
    openDataSidebar('canvas-inventory');
  }

  // SCENARIO 5.5: Product Deleted from Catalog
  else if (actionType === 'delete_item') {
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #EF4444; background: rgba(239, 68, 68, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #F87171;">PRODUK DIHAPUS DARI KATALOG</span>
          <span class="badge badge-out_of_stock">TERHAPUS</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #E2E8F0;">
          ${escapeHtml(data.message)}
        </div>
      </div>
    `;
    switchCanvasTab('canvas-inventory');
  }

  // SCENARIO 5.6: Dynamic Category Added or Deleted
  else if (actionType === 'add_category' || actionType === 'delete_category') {
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #10B981; background: rgba(16, 185, 129, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #34D399;">KATEGORI INVENTARIS DIPERBARUI</span>
          <span class="badge badge-approved">SUKSES</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #E2E8F0;">
          ${escapeHtml(data.message)}
        </div>
      </div>
    `;
    loadAllData();
    openDataSidebar('canvas-inventory');
  }

  // SCENARIO 5.8: Export Catalog Data
  else if (actionType === 'export_data') {
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #6366F1; background: rgba(99, 102, 241, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #818CF8;">EKSPOR DATA INVENTARIS</span>
          <span class="badge badge-approved">SIAP DIUNDUH</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #E2E8F0;">
          ${escapeHtml(data.message)}
          <div style="margin-top: 10px;">
            <a href="/api/inventory/export/csv" class="btn btn-primary btn-sm" download style="text-decoration: none; display: inline-flex; align-items: center; gap: 6px;">
              📥 Unduh Berkas CSV Sekarang
            </a>
          </div>
        </div>
      </div>
    `;
  }

  // SCENARIO 5.9: UI Dynamic Customization (e.g. rename columns)
  else if (actionType === 'ui_action') {
    const targetEl = document.getElementById('th-minmax');
    if (targetEl) targetEl.textContent = 'THRESHOLD';
    try {
      const customUi = JSON.parse(localStorage.getItem('ar_ui_custom') || '{}');
      customUi['th-minmax'] = 'THRESHOLD';
      localStorage.setItem('ar_ui_custom', JSON.stringify(customUi));
    } catch (e) {}
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #8B5CF6; background: rgba(139, 92, 246, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #A78BFA;">TAMPILAN UI DIPERBARUI</span>
          <span class="badge badge-approved">TERAPLIKASI</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #E2E8F0;">
          ${escapeHtml(data.message)}
        </div>
      </div>
    `;
    openDataSidebar('canvas-inventory');
  }

  // SCENARIO 6: External Notification / Sync
  else if (actionType === 'notify_email') {
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #3B82F6; background: rgba(59, 130, 246, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #60A5FA;">OTOMATISASI & NOTIFIKASI</span>
          <span class="badge badge-approved">TERKIRIM</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #E2E8F0;">
          ${escapeHtml(data.message)}
          ${items.length > 0 ? `
            <div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed rgba(255, 255, 255, 0.1); display: flex; flex-wrap: wrap; gap: 6px;">
              ${items.map(it => `
                <span class="badge ${it.current_stock <= 0 ? 'badge-out_of_stock' : (it.current_stock <= it.min_stock ? 'badge-low_stock' : 'badge-approved')}">
                  ${escapeHtml(it.name)}: ${it.current_stock} ${it.unit}
                </span>
              `).join('')}
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  // SCENARIO 7: General Summary / Inquiry Report
  else {
    actionHtml = `
      <div class="action-card" style="border-left: 4px solid #0284C7; background: rgba(2, 132, 199, 0.05);">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 13px; color: #38BDF8;">INFORMASI & LAPORAN INVENTARIS</span>
          <span class="badge badge-pending">STATUS REAL-TIME</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #E2E8F0; line-height: 1.6;">
          ${escapeHtml(data.message)}
          ${items.length > 0 ? `
            <div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed rgba(255, 255, 255, 0.1); display: flex; flex-wrap: wrap; gap: 6px;">
              ${items.map(it => `
                <span class="badge ${it.current_stock <= 0 ? 'badge-out_of_stock' : (it.current_stock <= it.min_stock ? 'badge-low_stock' : 'badge-approved')}">
                  ${escapeHtml(it.name)}: ${it.current_stock} ${it.unit}
                </span>
              `).join('')}
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="agent-plan-box">
      <div class="agent-plan-title">RENCANA & AKSI:</div>
      <div style="font-size: 13px; font-weight: 600; color: #F1F5F9; margin-bottom: 8px; line-height: 1.5;">
        ${escapeHtml(intent.reasoning || data.message)}
      </div>
      ${actionHtml}
    </div>
  `;

  feed.appendChild(container);
  feed.scrollTop = feed.scrollHeight;
}

// --- WebSocket Live Stream ---
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/logs`;

  state.socket = new WebSocket(wsUrl);

  state.socket.onopen = () => {
    state.socketConnected = true;
    const dot = document.getElementById('wsStatusDot');
    const label = document.getElementById('wsStatusLabel');
    if (dot) dot.style.backgroundColor = '#10b981';
    if (label) label.textContent = 'Online';
  };

  state.socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'pong') return;
      appendTerminalLog(data);

      // Auto reload data if there's any state-changing event
      if (['PR Generation', 'Catalog Creation', 'Stock Correction', 'Human Approval Decision'].includes(data.step_name)) {
        loadAllData();
      }
    } catch (e) {}
  };

  state.socket.onclose = () => {
    state.socketConnected = false;
    const dot = document.getElementById('wsStatusDot');
    const label = document.getElementById('wsStatusLabel');
    if (dot) dot.style.backgroundColor = '#f59e0b';
    if (label) label.textContent = 'Offline (WebSocket Disabled)';
    // setTimeout(initWebSocket, 3000); // Disabled reconnect to prevent backend log spam
  };
}

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
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    maximumFractionDigits: 0
  }).format(num);
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
  toast.className = 'toast';
  if (type === 'success') toast.style.borderLeft = '4px solid #16a34a';
  if (type === 'error') toast.style.borderLeft = '4px solid #dc2626';

  toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// --- API Health Checker ---
async function checkApiHealth() {
  const dot = document.getElementById('apiHealthDot');
  const text = document.getElementById('apiHealthText');
  if (!dot || !text) return;
  
  try {
    const res = await fetch('/health', { method: 'GET' });
    if (res.ok) {
      dot.style.backgroundColor = '#10b981'; // Green
      dot.style.boxShadow = '0 0 8px #10b981';
      text.textContent = 'API Connected';
      text.style.color = '#e2e8f0';
    } else {
      throw new Error("Not OK");
    }
  } catch (e) {
    dot.style.backgroundColor = '#ef4444'; // Red
    dot.style.boxShadow = '0 0 8px #ef4444';
    text.textContent = 'API Disconnected';
    text.style.color = '#ef4444';
  }
}

// Initial check and set interval
checkApiHealth();
setInterval(checkApiHealth, 5000);
