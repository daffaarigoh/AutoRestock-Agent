const assert = require('node:assert/strict');
const { formatMarkdownResponse } = require('../web/static/js/safe_rendering.js');

const payload = '<img src=x onerror=alert(1)>';
const cases = [
  payload,
  `# ${payload}`,
  `> ${payload}`,
  `- ${payload}`,
  `| value |\n| --- |\n| ${payload} |`,
];

for (const input of cases) {
  const rendered = formatMarkdownResponse(input);
  assert.ok(!rendered.includes(payload), `raw HTML payload escaped for ${input}`);
  assert.ok(rendered.includes('&lt;img'), `payload remains readable as text for ${input}`);
}

console.log('Markdown rendering escapes untrusted HTML in text and table contexts.');