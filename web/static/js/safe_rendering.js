(function (root, factory) {
  const helpers = factory();
  root.escapeHtml = helpers.escapeHtml;
  root.formatMarkdownResponse = helpers.formatMarkdownResponse;
  if (typeof module === 'object' && module.exports) module.exports = helpers;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')
      .replace(/\n/g, '<br>');
  }

  function formatTableCell(rawCell, colIdx, headerText) {
    if (rawCell === null || rawCell === undefined || rawCell === '') {
      return '-';
    }
    const clean = String(rawCell).trim();
    const escaped = escapeHtml(clean);
    const upper = clean.toUpperCase();

    // 1. Purchase Requisition ID with quick action download buttons
    const prMatch = clean.match(/^PR-\d{4}-[A-Za-z0-9_-]+$/i) || clean.match(/^PR-[A-Za-z0-9_-]{4,30}$/i);
    if (prMatch) {
      const prNum = prMatch[0];
      const safePr = escapeHtml(prNum);
      return `<div class="table-pr-cell">` +
        `<span class="table-badge-pr">${safePr}</span>` +
        `<div class="table-doc-actions">` +
          `<a href="/api/documents/pr/${encodeURIComponent(prNum)}/download?download=true" target="_blank" class="table-doc-pill" title="Unduh PDF (Typst)" download="${safePr}.pdf">` +
            `<svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>` +
            `<span>PDF</span>` +
          `</a>` +
          `<a href="/api/documents/pr/${encodeURIComponent(prNum)}/download-typst" target="_blank" class="table-doc-pill table-doc-pill-typst" title="Unduh Source Typst (.typ)" download="${safePr}.typ">` +
            `<svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>` +
            `<span>.typ</span>` +
          `</a>` +
        `</div>` +
      `</div>`;
    }

    // 2. Status Badges
    if (/^(CRITICAL|KRITIS|HABIS|OUT OF STOCK|OUT_OF_STOCK|REJECTED|DANGER|EXPIRED)$/i.test(upper)) {
      return `<span class="table-badge table-badge-critical">${escaped}</span>`;
    }
    if (/^(LOW|LOW STOCK|LOW_STOCK|RENDAH|WARNING|PENDING|PENDING_APPROVAL|NEED RESTOCK|PERLU RESTOCK|RESTOCK NEEDED)$/i.test(upper)) {
      return `<span class="table-badge table-badge-warning">${escaped}</span>`;
    }
    if (/^(SAFE|AMAN|NORMAL|OK|APPROVED|ACTIVE|COMPLETED|PAID|LUNAS|TERPENUHI)$/i.test(upper)) {
      return `<span class="table-badge table-badge-success">${escaped}</span>`;
    }
    if (/^(IN PROGRESS|IN_PROGRESS|PROCESS|SUBMITTED|DRAFT|PARTIAL)$/i.test(upper)) {
      return `<span class="table-badge table-badge-info">${escaped}</span>`;
    }

    // 3. SKU / Material / Inventory Code badges
    if (/^(MAT|SKU|INV|ITEM|TWR|EMP|TRX|WO|PO)-[A-Za-z0-9_-]+$/i.test(clean)) {
      return `<span class="table-badge-sku">${escaped}</span>`;
    }

    // 4. Currency formatting
    if (/^Rp\s*[\d\.,]+$/i.test(clean)) {
      return `<span class="table-cell-currency">${escaped}</span>`;
    }

    return escaped;
  }

  function formatPrMentions(escapedText) {
    if (!escapedText || typeof escapedText !== 'string') return '';
    return escapedText.replace(/\b(PR-\d{4}-[A-Za-z0-9_-]+)\b/g, (match) => {
      const safePr = escapeHtml(match);
      return `<span class="chat-pr-inline-group">` +
        `<span class="chat-pr-code">${safePr}</span>` +
        `<a href="/api/documents/pr/${encodeURIComponent(match)}/download?download=true" target="_blank" class="chat-pr-doc-link" title="Unduh PDF (Typst)" download="${safePr}.pdf">` +
          `<svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>` +
          `<span>PDF</span>` +
        `</a>` +
        `<a href="/api/documents/pr/${encodeURIComponent(match)}/download-typst" target="_blank" class="chat-pr-doc-link chat-pr-doc-link-typ" title="Unduh Source Typst (.typ)" download="${safePr}.typ">` +
          `<svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>` +
          `<span>.typ</span>` +
        `</a>` +
      `</span>`;
    });
  }

  function formatMarkdownResponse(text) {
    if (!text) return '';

    const stripEmojis = (str) => (str || '').replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F1E0}-\u{1F1FF}\u{1F900}-\u{1F9FF}\u{1F004}\u{1F0CF}\u{1F170}-\u{1F251}\u{2300}-\u{23FF}\u{2B50}\u{2B55}\u{2934}\u{2935}\u{2B05}\u{2B06}\u{2B07}]/gu, '').trim();
    const cleanText = (str) => escapeHtml(stripEmojis(String(str || '')).replace(/\*\*/g, '').replace(/`/g, '').trim());
    const lines = String(text).split('\n');
    let inTable = false;
    let html = '';
    let tableRows = [];
    let tableAlignments = [];

    function renderTableHtml() {
      if (!tableRows.length) return '';
      let tHtml = `<div class="table-responsive-wrapper chat-table-wrapper"><table class="data-table chat-markdown-table"><thead><tr>`;
      tHtml += tableRows[0].map((c, idx) => {
        const align = (tableAlignments && tableAlignments[idx]) || '';
        const cls = align === 'right' ? ' class="text-right"' : (align === 'center' ? ' class="text-center"' : '');
        return `<th${cls}>${escapeHtml(c)}</th>`;
      }).join('');
      tHtml += `</tr></thead><tbody>`;
      tHtml += tableRows.slice(1).map(row => `<tr>` +
        row.map((c, idx) => {
          const align = (tableAlignments && tableAlignments[idx]) || '';
          let cls = align === 'right' ? 'text-right' : (align === 'center' ? 'text-center' : '');
          if (!cls && (/^Rp\s*[\d\.,]+$/i.test(c) || /^-?\d+(\.\d+)?$/.test(c))) {
            cls = 'text-right';
          }
          return `<td${cls ? ` class="${cls}"` : ''}>${formatTableCell(c, idx, tableRows[0] ? tableRows[0][idx] : '')}</td>`;
        }).join('') +
      `</tr>`).join('');
      tHtml += `</tbody></table></div>`;
      return tHtml;
    }

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('```')) continue;

      if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
        if (trimmed.includes('---')) {
          tableAlignments = trimmed.split('|').slice(1, -1).map(col => {
            const c = col.trim();
            if (c.startsWith(':') && c.endsWith(':')) return 'center';
            if (c.endsWith(':')) return 'right';
            if (c.startsWith(':')) return 'left';
            return '';
          });
          continue;
        }
        inTable = true;
        tableRows.push(trimmed.split('|').slice(1, -1).map(c => stripEmojis(String(c || '')).replace(/\*\*/g, '').replace(/`/g, '').trim()));
        continue;
      }

      if (inTable && tableRows.length > 0) {
        html += renderTableHtml();
        inTable = false;
        tableRows = [];
        tableAlignments = [];
      }

      if (trimmed.startsWith('#')) {
        const heading = cleanText(trimmed.replace(/^#+\s*/, ''));
        if (heading) html += `<div style="font-size: 13.5px; font-weight: 700; color: #0F172A; margin: 8px 0 4px 0;">${heading}</div>`;
        continue;
      }
      if (trimmed.startsWith('>')) {
        const quote = cleanText(trimmed.replace(/^>\s*/, ''));
        if (quote) html += `<div style="background: #F8FAFC; border-left: 3px solid #CBD5E1; padding: 7px 10px; margin: 6px 0; font-size: 12px; color: #475569; border-radius: 0 6px 6px 0; line-height: 1.5;">${quote}</div>`;
        continue;
      }

      const content = cleanText(trimmed);
      if (content.startsWith('- ')) {
        html += `<div style="margin: 3px 0 3px 12px; font-size: 12.5px;">- ${formatPrMentions(content.substring(2))}</div>`;
      } else if (content) {
        html += `<div style="margin: 4px 0; font-size: 13px; line-height: 1.5;">${formatPrMentions(content)}</div>`;
      }
    }

    if (inTable && tableRows.length > 0) {
      html += renderTableHtml();
    }
    return html;
  }

  return { escapeHtml, formatMarkdownResponse };
});