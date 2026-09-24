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

  function formatMarkdownResponse(text) {
    if (!text) return '';

    const stripEmojis = (str) => (str || '').replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F1E0}-\u{1F1FF}\u{1F900}-\u{1F9FF}\u{1F004}\u{1F0CF}\u{1F170}-\u{1F251}\u{2300}-\u{23FF}\u{2B50}\u{2B55}\u{2934}\u{2935}\u{2B05}\u{2B06}\u{2B07}]/gu, '').trim();
    const cleanText = (str) => escapeHtml(stripEmojis(String(str || '')).replace(/\*\*/g, '').replace(/`/g, '').trim());
    const lines = String(text).split('\n');
    let inTable = false;
    let html = '';
    let tableRows = [];

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('```')) continue;

      if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
        if (trimmed.includes('---')) continue;
        inTable = true;
        tableRows.push(trimmed.split('|').slice(1, -1).map(cleanText));
        continue;
      }

      if (inTable && tableRows.length > 0) {
        html += `<div style="overflow-x:auto; margin: 10px 0;"><table class="data-table" style="font-size: 11.5px; width: 100%;"><thead><tr>` +
          tableRows[0].map(c => `<th style="padding: 6px 8px;">${c}</th>`).join('') +
          `</tr></thead><tbody>` +
          tableRows.slice(1).map(row => `<tr>` + row.map(c => `<td style="padding: 6px 8px;">${c}</td>`).join('') + `</tr>`).join('') +
          `</tbody></table></div>`;
        inTable = false;
        tableRows = [];
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
      if (content.startsWith('- ')) html += `<div style="margin: 3px 0 3px 12px; font-size: 12.5px;">- ${content.substring(2)}</div>`;
      else if (content) html += `<div style="margin: 4px 0; font-size: 13px; line-height: 1.5;">${content}</div>`;
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

  return { escapeHtml, formatMarkdownResponse };
});