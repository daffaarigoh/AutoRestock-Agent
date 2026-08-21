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
                let stockColor = '#0f172a';
                if (item.health === 'CRITICAL') {
                    badgeClass = 'badge-critical';
                    stockColor = '#dc2626';
                } else if (item.health === 'WARNING') {
                    badgeClass = 'badge-warning';
                    stockColor = '#d97706';
                }

                tr.innerHTML = `
                    <td>
                        <div style="font-weight: 600; color: var(--text-main);">${item.name}</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono);">${item.item_id}</div>
                    </td>
                    <td>${item.category}</td>
                    <td><strong style="color:${stockColor}">${item.current_stock}</strong> <span style="color:var(--text-muted)">${item.unit}</span></td>
                    <td><strong>${item.min_threshold}</strong> <span style="color:var(--text-muted)">${item.unit}</span></td>
                    <td>${item.avg_daily_usage} / hari</td>
                    <td>${item.lead_time_days} hari</td>
                    <td>Rp ${Number(item.unit_price).toLocaleString('id-ID')}</td>
                    <td><span class="badge ${badgeClass}">${item.health}</span></td>
                    <td>
                        <button class="btn btn-secondary btn-sm" onclick="openThresholdModal('${item.item_id}', '${item.name.replace(/'/g, "\\'")}', ${item.current_stock}, ${item.min_threshold})">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 2px;">
                                <path d="M12 20h9"></path>
                                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
                            </svg>
                            Ubah Threshold
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            console.error('Failed to load inventory:', err);
        }
    }

    // -------------------------------------------------------------
    // Threshold Modal Management
    // -------------------------------------------------------------
    window.openThresholdModal = function(itemId, itemName, currentStock, minThreshold) {
        document.getElementById('edit-item-id').value = itemId;
        document.getElementById('edit-item-name').textContent = `${itemName} (${itemId})`;
        document.getElementById('edit-current-stock').value = currentStock;
        document.getElementById('edit-min-threshold').value = minThreshold;
        document.getElementById('threshold-modal').classList.add('active');
    };

    window.closeThresholdModal = function() {
        document.getElementById('threshold-modal').classList.remove('active');
    };

    const thresholdForm = document.getElementById('threshold-form');
    if (thresholdForm) {
        thresholdForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const itemId = document.getElementById('edit-item-id').value;
            const currentStock = parseInt(document.getElementById('edit-current-stock').value);
            const minThreshold = parseInt(document.getElementById('edit-min-threshold').value);

            try {
                const res = await fetch(`/api/inventory/items/${itemId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        current_stock: currentStock,
                        min_threshold: minThreshold
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    closeThresholdModal();
                    await loadInventory();
                } else {
                    alert(`Gagal update threshold: ${data.detail || data.message}`);
                }
            } catch (err) {
                alert(`Error: ${err.message}`);
            }
        });
    }

    // -------------------------------------------------------------
    // AI Workflow Assistant (Natural Language Prompt & Multi-Channel Handling)
    // -------------------------------------------------------------
    const promptForm = document.getElementById('custom-prompt-form');
    const promptInput = document.getElementById('custom-prompt-input');
    const btnSubmitPrompt = document.getElementById('btn-submit-prompt');
    const dynamicResultCard = document.getElementById('dynamic-result-card');
    const dynTitle = document.getElementById('dyn-title');
    const dynSubtitle = document.getElementById('dyn-subtitle');
    const dynSummary = document.getElementById('dyn-summary');
    const dynStepsContainer = document.getElementById('dyn-steps-container');
    const dynActions = document.getElementById('dyn-actions');
    const emailInputWrapper = document.getElementById('email-input-wrapper');
    const customRecipientEmail = document.getElementById('custom-recipient-email');

    // Channel Chip Interactions
    ['chk-db', 'chk-email', 'chk-tele', 'chk-n8n'].forEach(id => {
        const chk = document.getElementById(id);
        if (chk) {
            chk.addEventListener('change', () => {
                const parent = chk.closest('.channel-chip');
                if (parent) {
                    if (chk.checked) parent.classList.add('active');
                    else parent.classList.remove('active');
                }
                if (id === 'chk-email' && emailInputWrapper) {
                    if (chk.checked) emailInputWrapper.classList.add('show');
                    else emailInputWrapper.classList.remove('show');
                }
            });
        }
    });

    // Prompt chip suggestion handler
    document.querySelectorAll('.prompt-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const promptText = chip.getAttribute('data-prompt');
            if (promptInput && promptText) {
                promptInput.value = promptText;
                
                // Smart auto-select channel based on clicked chip
                const pLow = promptText.toLowerCase();
                const chkEmail = document.getElementById('chk-email');
                const chkTele = document.getElementById('chk-tele');
                const chkN8n = document.getElementById('chk-n8n');
                
                if (pLow.includes('email saja') || pLow.includes('hanya email')) {
                    if (chkEmail) { chkEmail.checked = true; chkEmail.dispatchEvent(new Event('change')); }
                    if (chkTele) { chkTele.checked = false; chkTele.dispatchEvent(new Event('change')); }
                    if (chkN8n) { chkN8n.checked = false; chkN8n.dispatchEvent(new Event('change')); }
                } else if (pLow.includes('telegram saja') || pLow.includes('hanya telegram')) {
                    if (chkEmail) { chkEmail.checked = false; chkEmail.dispatchEvent(new Event('change')); }
                    if (chkTele) { chkTele.checked = true; chkTele.dispatchEvent(new Event('change')); }
                    if (chkN8n) { chkN8n.checked = false; chkN8n.dispatchEvent(new Event('change')); }
                } else if (pLow.includes('database saja') || pLow.includes('hanya simpan') || pLow.includes('web dashboard & db saja')) {
                    if (chkEmail) { chkEmail.checked = false; chkEmail.dispatchEvent(new Event('change')); }
                    if (chkTele) { chkTele.checked = false; chkTele.dispatchEvent(new Event('change')); }
                    if (chkN8n) { chkN8n.checked = false; chkN8n.dispatchEvent(new Event('change')); }
                } else {
                    if (chkEmail) { chkEmail.checked = pLow.includes('email'); chkEmail.dispatchEvent(new Event('change')); }
                    if (chkTele) { chkTele.checked = pLow.includes('tele'); chkTele.dispatchEvent(new Event('change')); }
                    if (chkN8n) { chkN8n.checked = pLow.includes('n8n'); chkN8n.dispatchEvent(new Event('change')); }
                }

                if (promptForm) promptForm.dispatchEvent(new Event('submit'));
            }
        });
    });

    if (promptForm) {
        promptForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const prompt = promptInput.value.trim();
            if (!prompt) return;

            // Collect selected channel destinations
            const destinations = [];
            const chkEmail = document.getElementById('chk-email');
            const chkTele = document.getElementById('chk-tele');
            const chkN8n = document.getElementById('chk-n8n');

            if (chkEmail && chkEmail.checked) destinations.push('email');
            if (chkTele && chkTele.checked) destinations.push('telegram');
            if (chkN8n && chkN8n.checked) destinations.push('n8n');

            const recipientEmail = customRecipientEmail ? customRecipientEmail.value.trim() : 'manager@company.com';

            btnSubmitPrompt.disabled = true;
            btnSubmitPrompt.innerHTML = `<span>AI Memproses...</span>`;

            dynamicResultCard.style.display = 'block';
            dynTitle.textContent = 'Menyusun Alur Kerja Dinamis...';
            dynSubtitle.textContent = `Prompt: "${prompt}"`;
            dynSummary.innerHTML = `<em>Sedang menganalisis intent, memeriksa database DuckDB, dan menyusun langkah eksekusi...</em>`;
            dynStepsContainer.innerHTML = '';
            dynActions.innerHTML = '';

            try {
                const res = await fetch('/api/agent/custom-prompt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt: prompt,
                        destinations: destinations,
                        recipient_email: recipientEmail
                    })
                });
                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.detail || 'Gagal mengeksekusi prompt.');
                }

                dynTitle.textContent = data.workflow_title || 'Dynamic Workflow Result';
                dynSubtitle.textContent = `Prompt: "${data.prompt}"`;
                dynSummary.innerHTML = `<strong>Ringkasan Eksekusi:</strong> ${data.summary}`;

                // Render dynamic steps
                dynStepsContainer.innerHTML = '';
                (data.execution_steps || []).forEach(step => {
                    const stepDiv = document.createElement('div');
                    stepDiv.className = 'dyn-step-item';
                    stepDiv.innerHTML = `
                        <div class="dyn-step-num">${step.step_number}</div>
                        <div class="dyn-step-content">
                            <div class="dyn-step-title">${step.title}</div>
                            <div class="dyn-step-desc">${step.details}</div>
                        </div>
                    `;
                    dynStepsContainer.appendChild(stepDiv);
                });

                // Render action buttons (e.g. Preview PDF, View PR list)
                dynActions.innerHTML = '';
                if (data.pr_number) {
                    const btnPreview = document.createElement('button');
                    btnPreview.className = 'btn btn-primary btn-sm';
                    btnPreview.textContent = '📄 Lihat Dokumen PDF';
                    btnPreview.onclick = () => previewPDF(data.pr_number);
                    dynActions.appendChild(btnPreview);
                }

                const btnViewPR = document.createElement('button');
                btnViewPR.className = 'btn btn-secondary btn-sm';
                btnViewPR.textContent = 'Daftar Purchase Requisitions';
                btnViewPR.onclick = () => {
                    document.querySelector('[data-tab="tab-pr"]').click();
                };
                dynActions.appendChild(btnViewPR);

                // Refresh inventory and PR table in background
                await loadInventory();
                await loadPurchaseRequisitions();
            } catch (err) {
                dynSummary.innerHTML = `<span style="color: var(--danger); font-weight: 600;">Terjadi Kesalahan: ${err.message}</span>`;
            } finally {
                btnSubmitPrompt.disabled = false;
                btnSubmitPrompt.innerHTML = `
                    <span>Jalankan Workflow</span>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                        <polyline points="12 5 19 12 12 19"></polyline>
                    </svg>
                `;
            }
        });
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

        dropzone.innerHTML = `
            <div class="dropzone-text" style="font-weight: 600; color: var(--primary);">Memproses ekstraksi dengan model OCR LightOn...</div>
            <div class="dropzone-sub">Mohon tunggu beberapa saat</div>
        `;

        try {
            let endpoint = '/api/ingest/delivery-note';
            if (docType === 'stock-opname') endpoint = '/api/ingest/stock-opname';
            else if (docType === 'invoice') endpoint = '/api/ingest/invoice';

            const res = await fetch(endpoint, { method: 'POST', body: formData });
            const data = await res.json();

            dropzone.innerHTML = `
                <div class="dropzone-text" style="font-weight: 600; color: var(--success);">File <strong>${file.name}</strong> berhasil diekstrak!</div>
                <div class="dropzone-sub" style="color: var(--primary); margin-top: 4px;">Klik untuk mengunggah dokumen lain</div>
            `;
            renderOCRResult(data);
            await loadInventory();
        } catch (err) {

            dropzone.innerHTML = `
                <div class="dropzone-text" style="font-weight: 600; color: var(--danger);">Gagal memproses dokumen: ${err.message}</div>
                <div class="dropzone-sub">Klik untuk mencoba kembali</div>
            `;
        }
    }

    function renderOCRResult(data) {
        ocrResultContainer.style.display = 'block';
        document.getElementById('ocr-doc-no').textContent = data.doc_number || '-';
        document.getElementById('ocr-vendor').textContent = data.vendor_or_issuer || data.vendor_name || '-';
        document.getElementById('ocr-summary').textContent = data.summary || '-';

        const tbody = document.getElementById('ocr-table-body');
        tbody.innerHTML = '';
        (data.items || []).forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${item.item_name}</strong></td>
                <td><strong>${item.qty_recorded || item.qty_received || 0}</strong> ${item.unit}</td>
                <td>Rp ${(item.unit_price || 0).toLocaleString('id-ID')}</td>
                <td><span style="color:var(--text-secondary)">${item.condition_notes || '-'}</span></td>
            `;
            tbody.appendChild(tr);
        });
    }

    const ocrGeneratePrBtn = document.getElementById('btn-ocr-generate-pr');
    if (ocrGeneratePrBtn) {
        ocrGeneratePrBtn.addEventListener('click', async () => {
            try {
                ocrGeneratePrBtn.disabled = true;
                ocrGeneratePrBtn.textContent = 'Memproses AI Restock...';
                
                const res = await fetch('/api/agent/run-cycle', { method: 'POST' });
                const prData = await res.json();
                
                // Refresh PR list and switch to PR tab
                await loadPurchaseRequisitions();
                await loadInventory();
                
                if (prData && prData.items && prData.items.length > 0) {
                    document.querySelector('[data-tab="tab-pr"]').click();
                    if (prData.pr_number) {
                        previewPDF(prData.pr_number);
                    }
                } else {
                    alert('Seluruh stok inventaris saat ini dalam kondisi AMAN (HEALTHY). Tidak ada barang yang memerlukan restock.');
                    document.querySelector('[data-tab="tab-inventory"]').click();
                }
            } catch (err) {
                alert(`Gagal membuat Purchase Requisition: ${err.message}`);
            } finally {
                ocrGeneratePrBtn.disabled = false;
                ocrGeneratePrBtn.textContent = 'Proses Restock & Buat Dokumen PR (PDF)';
            }
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
            terminalBody.innerHTML = `<div class="log-entry"><span class="log-time">[Init]</span> <span class="log-msg">Memulai siklus otonom Multi-Agent Restock...</span></div>`;
            startAgentBtn.disabled = true;
            startAgentBtn.textContent = 'Agent Running...';

            const eventSource = new EventSource('/api/stream/agent-run');

            eventSource.onmessage = (e) => {
                const data = JSON.parse(e.data);
                if (data.event === 'DONE') {
                    const doneEntry = document.createElement('div');
                    doneEntry.className = 'log-entry';
                    doneEntry.innerHTML = `<span class="log-time">[Complete]</span> <span class="log-msg" style="color:#10b981; font-weight:600;">${data.message}</span>`;
                    terminalBody.appendChild(doneEntry);
                    terminalBody.scrollTop = terminalBody.scrollHeight;
                    eventSource.close();
                    startAgentBtn.disabled = false;
                    startAgentBtn.textContent = 'Run Autonomous Restock';
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
                startAgentBtn.textContent = 'Run Autonomous Restock';
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
                const isRejected = pr.status === 'REJECTED';

                let statusBadge = 'badge-pending';
                if (isApproved) statusBadge = 'badge-healthy';
                else if (isRejected) statusBadge = 'badge-critical';

                tr.innerHTML = `
                    <td><strong style="font-family: var(--font-mono);">${pr.pr_number}</strong></td>
                    <td>${pr.created_at}</td>
                    <td>${pr.items.length} Barang</td>
                    <td><strong style="color:var(--text-main)">Rp ${Number(pr.total_budget).toLocaleString('id-ID')}</strong></td>
                    <td><span class="badge badge-healthy">${pr.auditor_status}</span></td>
                    <td><span class="badge ${statusBadge}">${pr.status}</span></td>
                    <td>
                        <div style="display: flex; gap: 0.4rem; align-items: center;">
                            <button class="btn btn-secondary btn-sm" onclick="previewPDF('${pr.pr_number}')">Lihat PDF</button>
                            ${(!isApproved && !isRejected) ? `
                                <button class="btn btn-success btn-sm" onclick="executeApproval('${pr.pr_number}', 'APPROVE')">Approve</button>
                                <button class="btn btn-danger btn-sm" onclick="executeApproval('${pr.pr_number}', 'REJECT')">Reject</button>
                            ` : ''}
                        </div>
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
        // Use the robust download endpoint which automatically checks approved, pending, rejected, and documents folders
        iframe.src = `/api/documents/pr/${encodeURIComponent(prNumber)}/download?t=${Date.now()}`;
        modal.classList.add('active');
    };

    window.closeModal = function() {
        const modal = document.getElementById('pdf-modal');
        modal.classList.remove('active');
    };

    window.executeApproval = async function(prNumber, action) {
        try {
            const res = await fetch('/api/approval/action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pr_number: prNumber,
                    action: action,
                    manager_name: 'Warehouse Operations Manager'
                })
            });
            const data = await res.json();
            await loadPurchaseRequisitions();
            await loadInventory();
            // Automatically update and preview the freshly updated PDF
            previewPDF(prNumber);
        } catch (err) {
            alert(`Gagal memproses keputusan: ${err.message}`);
        }
    };

    window.resetSamplePR = async function() {
        try {
            await fetch('/api/approval/reset', { method: 'POST' });
            await loadPurchaseRequisitions();
            await loadInventory();
        } catch (err) {
            console.error('Failed to reset PR:', err);
        }
    };


});

