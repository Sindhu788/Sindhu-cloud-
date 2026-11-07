/* master plan V2 LG4: moved out of concepts.html unchanged (the CSP allows no inline script) */
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
function renderSetupSteps(steps) {
  return '<ol>' + steps.map(s =>
    `<li><span class="step-title">${esc(s.title)}:</span> ${esc(s.text)}</li>`
  ).join('') + '</ol>';
}
function renderDetail(d) {
  // Defensive against a handful of concept entries whose detail object is
  // missing optional sections (Support & Resistance has no golden_rule/
  // long_setup/short_setup yet; Premium & Discount's why_location_matters
  // has no cases array yet) -- pre-existing content gaps, unrelated to the
  // Concepts Library cross-reference this file adds. Before this guard,
  // one crashing concept's renderDetail() call aborted the whole render
  // loop and wiped every already-rendered card (including the new
  // cross-reference section), since the loop has no per-card try/catch.
  // No content was added or changed here -- only "don't crash if a section
  // is absent."
  let html = '';
  html += `<h3>What it is</h3><p>${esc(d.what_it_is)}</p>`;
  if (d.types) {
    html += `<h3>Types</h3><ul>` + d.types.map(t =>
      `<li><span class="step-title">${esc(t.name)}:</span> ${esc(t.description)}</li>`
    ).join('') + `</ul>`;
  }
  if (d.why_location_matters) {
    html += `<h3>Why location matters</h3><p>${esc(d.why_location_matters.principle)}</p><ul>` +
      (d.why_location_matters.cases || []).map(c =>
        `<li><span class="step-title">${esc(c.location)}:</span> ${esc(c.meaning)}</li>`
      ).join('') + `</ul>`;
  }
  if (d.golden_rule) html += `<div class="golden-rule">${esc(d.golden_rule)}</div>`;
  if (d.long_setup || d.short_setup) {
    html += `<h3>Complete setups</h3><div class="setup-cols">
      <div><div class="step-title" style="margin-bottom:6px;">Long setup</div>${renderSetupSteps(d.long_setup || [])}</div>
      <div><div class="step-title" style="margin-bottom:6px;">Short setup</div>${renderSetupSteps(d.short_setup || [])}</div>
    </div>`;
  }
  if (d.thresholds) {
    html += `<h3>Thresholds used</h3><ul>` + d.thresholds.map(th =>
      `<li><span class="step-title">${esc(th.value)}</span> -- ${esc(th.note)}</li>`
    ).join('') + `</ul>`;
  }
  if (d.why_self_confirming) html += `<h3>Why no separate confirmation candle is needed</h3><p>${esc(d.why_self_confirming)}</p>`;
  if (d.engine_note) html += `<p>${esc(d.engine_note)}</p>`;
  html += `<div class="risk-note">${esc(d.risk_note)}</div>`;
  return html;
}
function renderRoadmap(data) {
  const root = document.getElementById('roadmap');
  const byCategory = data.categories.map(cat => ({
    name: cat.name,
    remaining: cat.concepts.filter(c => c.status !== 'defined'),
  })).filter(cat => cat.remaining.length);

  if (!byCategory.length) {
    root.innerHTML = '<h2>What\'s Next</h2><p style="color:var(--text-dim);font-size:13px;">All concepts are fully explained.</p>';
    return;
  }
  root.innerHTML = `<h2>What's Next -- ${byCategory.reduce((n, c) => n + c.remaining.length, 0)} Concepts Still To Detail</h2>` +
    byCategory.map(cat => `
      <div class="roadmap-cat">
        <div class="roadmap-cat-name">${esc(cat.name)}</div>
        <div class="roadmap-list">${cat.remaining.map(c => `<span class="pill pill-neutral">${esc(c.name)}</span>`).join('')}</div>
      </div>
    `).join('');
}
function renderLearningScore(data) {
  let total = 0, defined = 0;
  data.categories.forEach(cat => cat.concepts.forEach(c => {
    total++;
    if (c.status === 'defined' && c.detail) defined++;
  }));
  const pct = total ? Math.round((defined / total) * 100) : 0;
  document.getElementById('learningScore').innerHTML = `
    <div class="ls-label">Learning Score -- ${defined} of ${total} concepts fully explained (${pct}%)</div>
    <div class="ls-bar-track"><div class="ls-bar-fill" style="width:${pct}%;"></div></div>
  `;
}
function renderUsage(u) {
  if (!u) return '';
  const list = u.strategies.length
    ? `<div class="cu-list">${u.strategies.map(s => `<span class="pill pill-muted">${esc(s)}</span>`).join('')}</div>`
    : '';
  return `<div class="concept-usage"><span class="cu-count">${u.count}</span> ${u.count === 1 ? 'strategy' : 'strategies'} using this concept${list}</div>`;
}
Promise.all([
  fetch('/static/concepts_reference.json').then(r => r.json()),
  fetch('/api/concepts/usage').then(r => r.json()).catch(() => null),
])
  .then(([data, usageData]) => {
    const usageByName = (usageData && usageData.usage) || {};
    renderLearningScore(data);
    renderRoadmap(data);
    const root = document.getElementById('categories');
    data.categories.forEach(cat => {
      const section = document.createElement('div');
      section.className = 'concepts-category';
      const h2 = document.createElement('h2');
      h2.textContent = cat.name + ' (' + cat.concepts.length + ')';
      section.appendChild(h2);
      const grid = document.createElement('div');
      grid.className = 'concepts-grid';
      cat.concepts.forEach(c => {
        const isDefined = c.status === 'defined' && c.detail;
        const usage = usageByName[c.name];
        const card = document.createElement('div');
        card.className = 'concept-card card' + (isDefined ? ' defined' : '');
        card.innerHTML = `<div class="name">${c.name}</div>
          <div><span class="pill pill-muted">${cat.name}</span></div>
          <div><span class="pill ${isDefined ? 'pill-up' : 'pill-neutral'}">${c.status}</span></div>
          ${renderUsage(usage)}`;
        grid.appendChild(card);
        if (isDefined) {
          const detailBox = document.createElement('div');
          detailBox.className = 'concept-detail';
          detailBox.style.display = 'none';
          detailBox.innerHTML = renderDetail(c.detail);
          grid.appendChild(detailBox);
          card.addEventListener('click', (ev) => {
            if (ev.target.closest('.concept-usage')) return;
            detailBox.style.display = detailBox.style.display === 'none' ? 'block' : 'none';
          });
        }
      });
      section.appendChild(grid);
      root.appendChild(section);
    });
  })
  .catch(err => {
    document.getElementById('categories').textContent = 'Could not load concepts data: ' + err;
  });
