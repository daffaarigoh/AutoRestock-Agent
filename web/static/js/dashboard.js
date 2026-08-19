document.addEventListener('DOMContentLoaded', () => {
    // -------------------------------------------------------------
    // Tab Navigation
    // -------------------------------------------------------------
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.getAttribute('data-tab');
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanels.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const activePanel = document.getElementById(target);
            if (activePanel) activePanel.classList.add('active');
        });
    });

    // -------------------------------------------------------------
    // Initial Data Fetching
    // -------------------------------------------------------------
    loadInventory();
    loadPurchaseRequisitions();

    // -------------------------------------------------------------
    // Live Inventory Loader
    // -------------------------------------------------------------
    async function loadInventory() {
        try {
            const res = await fetch('/api/stream/inventory-summary');
            if (!res.ok) return;
            const data = await res.json();

            document.getElementById('stat-total-sku').textContent = data.total_sku || 0;
            document.getElementById('stat-critical').textContent = data.critical_count || 0;
            document.getElementById('stat-warning').textContent = data.warning_count || 0;

            const tbody = document.getElementById('inventory-table-body');
            tbody.innerHTML = '';

            data.items.forEach(item => {
                const tr = document.createElement('tr');
                let badgeClass = 'badge-healthy';
                if (item.health === 'CRITICAL') badgeClass = 'badge-critical';
                else if (item.health === 'WARNING') badgeClass = 'badge-warning';

                tr.innerHTML = `
                    <td><strong>${item.name}</strong><br><small style="color:var(--text-dim)">${item.item_id}</small></td>
                    <td>${item.category}</td>
                    <td><strong style="color:${item.health==='CRITICAL'?'#F87171':'#F9FAFB'}">${item.current_stock}</strong> ${item.unit}</td>
                    <td>${item.min_threshold} ${item.unit}</td>
                    <td>${item.avg_daily_usage} / day</td>
                    <td>${item.lead_time_days} days</td>
                    <td>Rp ${item.unit_price.toLocaleString('id-ID')}</td>
                    <td><span class="badge ${badgeClass}">${item.health}</span></td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error('Failed to load inventory:', err);
        }
    }

    // -------------------------------------------------------------
    // OCR Document Upload & Parsing
    // -------------------------------------------------------------
    const dropzone = document.getElementById('ocr-dropzone');
    const fileInput = document.getElementById('ocr-file-input');
    const ocrResultContainer = document.getElementById('ocr-result-container');

    if (dropzone && fileInput) {
        dropzone.addEventListener('click', () => fileInput.click());

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                handleFileUpload(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                handleFileUpload(e.target.files[0]);
            }
        });
    }

    async function handleFileUpload(file) {
        const docType = document.querySelector('input[name="doc_type"]:checked')?.value || 'delivery-note';
        const formData = new FormData();
        formData.append('file', file);

        dropzone.innerHTML = `<div class="dropzone-icon">⏳</div><p>Memproses ekstraksi dengan <strong>ocr-lighton</strong>...</p>`;

        try {
            const endpoint = docType === 'delivery-note' ? '/api/ingest/delivery-note' : '/api/ingest/stock-opname';
            const res = await fetch(endpoint, { method: 'POST', body: formData });
            const data = await res.json();

            dropzone.innerHTML = `<div class="dropzone-icon">✅</div><p>File <strong>${file.name}</strong> berhasil diekstrak!</p><small style="color:var(--accent)">Klik untuk upload dokumen lain</small>`;
            renderOCRResult(data);
        } catch (err) {
            dropzone.innerHTML = `<div class="dropzone-icon">❌</div><p>Gagal memproses dokumen: ${err.message}</p>`;
        }
    }

    function renderOCRResult(data) {
        ocrResultContainer.style.display = 'block';
        document.getElementById('ocr-doc-no').textContent = data.doc_number;
        document.getElementById('ocr-vendor').textContent = data.vendor_or_issuer;
        document.getElementById('ocr-summary').textContent = data.summary;

        const tbody = document.getElementById('ocr-table-body');
        tbody.innerHTML = '';
        data.items.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${item.item_name}</td>
                <td><strong>${item.qty_recorded}</strong> ${item.unit}</td>
                <td>Rp ${item.unit_price.toLocaleString('id-ID')}</td>
                <td><span style="color:var(--accent)">${item.condition_notes}</span></td>
            `;
            tbody.appendChild(tr);
        });
    }

    // -------------------------------------------------------------
    // Live Agent SSE Reasoning Stream
    // -------------------------------------------------------------
    const startAgentBtn = document.getElementById('btn-run-agent');
    const terminalBody = document.getElementById('terminal-logs');

    if (startAgentBtn) {
        startAgentBtn.addEventListener('click', () => {
            // Switch to Stream Tab
            document.querySelector('[data-tab="tab-stream"]').click();
            terminalBody.innerHTML = `<div class="log-entry"><span class="log-time">[Init]</span> <span class="log-msg">🚀 Memulai siklus otonom Multi-Agent Restock...</span></div>`;
            startAgentBtn.disabled = true;
            startAgentBtn.textContent = '⏳ Agent Running...';

            const eventSource = new EventSource('/api/stream/agent-run');

            eventSource.onmessage = (e) => {
                const data = JSON.parse(e.data);
                if (data.event === 'DONE') {
                    const doneEntry = document.createElement('div');
                    doneEntry.className = 'log-entry';
                    doneEntry.innerHTML = `<span class="log-time">[Complete]</span> <span class="log-msg" style="color:var(--success)">🎉 ${data.message}</span>`;
                    terminalBody.appendChild(doneEntry);
                    terminalBody.scrollTop = terminalBody.scrollHeight;
                    eventSource.close();
                    startAgentBtn.disabled = false;
                    startAgentBtn.textContent = '⚡ Run Autonomous Restock';
                    loadPurchaseRequisitions();
                    return;
                }

                const entry = document.createElement('div');
                entry.className = 'log-entry';
                entry.innerHTML = `
                    <span class="log-time">[${data.timestamp}]</span>
                    <span class="log-node">&lt;${data.node}&gt;</span>
                    <span class="log-msg">${data.message}</span>
                `;
                terminalBody.appendChild(entry);
                terminalBody.scrollTop = terminalBody.scrollHeight;
            };

            eventSource.onerror = (err) => {
                console.error('SSE Stream error:', err);
                eventSource.close();
                startAgentBtn.disabled = false;
                startAgentBtn.textContent = '⚡ Run Autonomous Restock';
            };
        });
    }

    // -------------------------------------------------------------
    // Purchase Requisitions & PDF Previewer
    // -------------------------------------------------------------
    async function loadPurchaseRequisitions() {
        try {
            const res = await fetch('/api/approval/list');
            if (!res.ok) return;
            const requisitions = await res.json();
            const container = document.getElementById('pr-list-tbody');
            if (!container) return;

            container.innerHTML = '';
            requisitions.forEach(pr => {
                const tr = document.createElement('tr');
                const isApproved = pr.status === 'APPROVED';
                const statusBadge = isApproved ? 'badge-healthy' : 'badge-warning';

                tr.innerHTML = `
                    <td><strong>${pr.pr_number}</strong></td>
                    <td>${pr.created_at}</td>
                    <td>${pr.items.length} Barang</td>
                    <td><strong style="color:var(--accent)">Rp ${pr.total_budget.toLocaleString('id-ID')}</strong></td>
                    <td><span class="badge badge-healthy">${pr.auditor_status}</span></td>
                    <td><span class="badge ${statusBadge}">${pr.status}</span></td>
                    <td>
                        <button class="btn btn-primary btn-sm" onclick="previewPDF('${pr.pr_number}')">📄 Lihat PDF</button>
                        ${!isApproved ? `<button class="btn btn-success btn-sm" onclick="approvePR('${pr.pr_number}')">✅ Approve</button>` : ''}
                    </td>
                `;
                container.appendChild(tr);
            });
        } catch (err) {
            console.error('Failed to load PR list:', err);
        }
    }

    window.previewPDF = function(prNumber) {
        const modal = document.getElementById('pdf-modal');
        const iframe = document.getElementById('pdf-iframe');
        iframe.src = `/storage/documents/${prNumber.replace(/-/g, '_')}.pdf`;
        modal.classList.add('active');
    };

    window.closeModal = function() {
        const modal = document.getElementById('pdf-modal');
        modal.classList.remove('active');
    };

    window.approvePR = async function(prNumber) {
        try {
            const res = await fetch('/api/approval/action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pr_number: prNumber, action: 'APPROVE', manager_name: 'Warehouse Lead' })
            });
            const data = await res.json();
            alert(`✅ ${data.message}`);
            loadPurchaseRequisitions();
        } catch (err) {
            alert(`Gagal approve: ${err.message}`);
        }
    };
});
