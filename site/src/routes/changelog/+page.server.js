import changelogSource from '../../../../CHANGELOG.md?raw';

const SOURCE_BASE = 'https://github.com/Autonomy-Data-Unit/annual-deprivation-index/blob/main/';
const RELEASE_HEADING = /^##\s+(\d{4}-\d{2}-\d{2})\s+(?:\u2014|-)\s+(.+?)\s*$/gm;

function escapeHtml(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function normalisePunctuation(value) {
  if (value.trim() === '\u2014') return 'None';
  return value
    .replace(/\s*\u2014\s*/g, ', ')
    .replaceAll('\u2013', '-')
    .trim();
}

function safeLink(value) {
  const href = value.trim();
  if (/^https?:\/\//i.test(href) || href.startsWith('/') || href.startsWith('#')) return href;
  if (/^[a-z][a-z\d+.-]*:/i.test(href)) return '#';
  return `${SOURCE_BASE}${href.replace(/^\.\//, '')}`;
}

function renderInline(source) {
  const tokens = [];
  const stash = (html) => {
    const token = `\uE000${tokens.length}\uE001`;
    tokens.push(html);
    return token;
  };

  let value = normalisePunctuation(source);
  value = value.replace(/`([^`]+)`/g, (_, code) => stash(`<code>${escapeHtml(normalisePunctuation(code))}</code>`));
  value = value.replace(/\[([^\]]+)]\(([^)]+)\)/g, (_, label, href) => {
    const target = escapeHtml(safeLink(href));
    return stash(`<a href="${target}">${escapeHtml(normalisePunctuation(label))}</a>`);
  });

  value = escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');

  return value.replace(/\uE000(\d+)\uE001/g, (_, index) => tokens[Number(index)]);
}

function headingId(prefix, heading, usedIds) {
  const stem = normalisePunctuation(heading)
    .toLowerCase()
    .replace(/`/g, '')
    .replace(/[^a-z\d]+/g, '-')
    .replace(/^-|-$/g, '') || 'section';
  const base = `${prefix}-${stem}`;
  const count = usedIds.get(base) ?? 0;
  usedIds.set(base, count + 1);
  return count ? `${base}-${count + 1}` : base;
}

function tableCells(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim());
}

function isTableDivider(line) {
  const cells = tableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isBlockStart(lines, index) {
  const line = lines[index] ?? '';
  if (!line.trim()) return true;
  if (/^```/.test(line) || /^#{2,6}\s+/.test(line) || /^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) return true;
  return line.includes('|') && isTableDivider(lines[index + 1] ?? '');
}

function renderBlocks(markdown, prefix) {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const usedIds = new Map();
  const headingLevels = new Map([[1, 2]]);
  const html = [];

  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    const fence = line.match(/^```\s*([\w-]*)\s*$/);
    if (fence) {
      const code = [];
      i += 1;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) {
        code.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      const language = fence[1] ? ` class="language-${escapeHtml(fence[1])}"` : '';
      html.push(`<pre><code${language}>${escapeHtml(code.join('\n'))}</code></pre>`);
      continue;
    }

    const heading = line.match(/^(#{2,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      const sourceLevel = heading[1].length;
      let parentLevel = sourceLevel - 1;
      while (parentLevel > 1 && !headingLevels.has(parentLevel)) parentLevel -= 1;
      const level = Math.min(6, (headingLevels.get(parentLevel) ?? 2) + 1);
      for (const knownLevel of headingLevels.keys()) {
        if (knownLevel >= sourceLevel) headingLevels.delete(knownLevel);
      }
      headingLevels.set(sourceLevel, level);
      const id = headingId(prefix, heading[2], usedIds);
      html.push(`<h${level} id="${id}">${renderInline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    if (line.includes('|') && isTableDivider(lines[i + 1] ?? '')) {
      const headers = tableCells(line);
      const alignments = tableCells(lines[i + 1]).map((cell) => cell.endsWith(':') ? ' class="num"' : '');
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
        rows.push(tableCells(lines[i]));
        i += 1;
      }
      const head = headers.map((cell, index) => `<th scope="col"${alignments[index] ?? ''}>${renderInline(cell)}</th>`).join('');
      const body = rows.map((row) => `<tr>${row.map((cell, index) => `<td${alignments[index] ?? ''}>${renderInline(cell)}</td>`).join('')}</tr>`).join('');
      html.push(`<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`);
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (unordered || ordered) {
      const tag = unordered ? 'ul' : 'ol';
      const pattern = unordered ? /^\s*[-*]\s+(.+)$/ : /^\s*\d+\.\s+(.+)$/;
      const items = [];
      while (i < lines.length) {
        const item = lines[i].match(pattern);
        if (!item) break;
        items.push(`<li>${renderInline(item[1])}</li>`);
        i += 1;
      }
      html.push(`<${tag}>${items.join('')}</${tag}>`);
      continue;
    }

    const paragraph = [line.trim()];
    i += 1;
    while (i < lines.length && !isBlockStart(lines, i)) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    html.push(`<p>${renderInline(paragraph.join(' '))}</p>`);
  }

  return html.join('\n');
}

function paragraphs(markdown) {
  return markdown
    .trim()
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.replace(/\s*\n\s*/g, ' ').trim())
    .filter(Boolean);
}

function sentences(paragraph) {
  return paragraph.match(/.*?[.!?](?:\s+|$)|.+$/g)?.map((sentence) => sentence.trim()).filter(Boolean) ?? [];
}

function releaseDateLabel(isoDate) {
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC'
  }).format(new Date(`${isoDate}T00:00:00Z`));
}

function sentenceCase(value) {
  return value ? value[0].toUpperCase() + value.slice(1) : value;
}

function parseRelease(match, body) {
  const id = match[1];
  const lines = body.replace(/\r\n?/g, '\n').split('\n');
  const impactStart = lines.findIndex((line) => /^###\s+The decisions that can change an existing result\s*$/.test(line));
  if (impactStart < 0) throw new Error(`Release ${id} needs a "decisions that can change an existing result" section`);

  const impactEndOffset = lines.slice(impactStart + 1).findIndex((line) => /^#{2,3}\s+/.test(line));
  const impactEnd = impactEndOffset < 0 ? lines.length : impactStart + 1 + impactEndOffset;
  const intro = paragraphs(lines.slice(0, impactStart).join('\n'));
  if (!intro[0]) throw new Error(`Release ${id} needs a reader-facing opening paragraph`);

  const introSentences = sentences(intro[0]);
  const decisions = introSentences.filter((sentence) =>
    /(replace|rerun|remains? valid|still (?:holds?|valid)|no need to|do not need|must be rebuilt)/i.test(sentence)
  );
  const answer = (decisions.length ? decisions : introSentences.slice(0, 2)).join(' ');
  const identification = sentences((intro[1] ?? '').replace(/^\*\*How to identify the corrected release\.\*\*\s*/, ''));
  const usefulIdentification = identification.filter((sentence) => /\barchive\b/i.test(sentence) && /(contains|without|superseded)/i.test(sentence));
  const identificationText = (usefulIdentification.length ? usefulIdentification : identification).join(' ');

  return {
    id,
    date: id,
    dateLabel: releaseDateLabel(id),
    title: sentenceCase(normalisePunctuation(match[2])),
    answerHtml: `<p>${renderInline(answer)}</p>`,
    identificationHtml: identificationText ? `<p>${renderInline(identificationText)}</p>` : '',
    impactsHtml: renderBlocks(lines.slice(impactStart + 1, impactEnd).join('\n'), `release-${id}-impact`),
    detailsHtml: renderBlocks(lines.slice(impactEnd).join('\n'), `release-${id}`)
  };
}

function parseChangelog(source) {
  const matches = [...source.matchAll(RELEASE_HEADING)];
  if (!matches.length) throw new Error('CHANGELOG.md contains no dated release headings');

  return matches.map((match, index) => {
    const start = match.index + match[0].length;
    const end = matches[index + 1]?.index ?? source.length;
    return parseRelease(match, source.slice(start, end));
  });
}

export function load() {
  return { releases: parseChangelog(changelogSource) };
}
