const JOB_PATTERNS = [
  /linkedin\.com\/(jobs\/view|comm\/jobs\/view)\//,
  /boards\.greenhouse\.io\//,
  /jobs\.lever\.co\//,
  /jobs\.ashbyhq\.com\//,
  /myworkdayjobs\.com\//,
  /\/jobs\//,
  /\/careers\//,
];

function looksLikeJob(url) {
  return JOB_PATTERNS.some(p => p.test(url));
}

// Split "Job Title | Company | LinkedIn" on | and – (en-dash) only.
// Does NOT split on regular hyphens so titles like
// "Senior Scientist - Protein Design" stay intact.
function parseTabTitle(raw) {
  const parts = raw.split(/\s*[|–]\s*/);
  const noise = new Set(['linkedin', 'indeed', 'glassdoor', 'lever', 'greenhouse', 'workday']);
  const meaningful = parts.filter(p => p && !noise.has(p.toLowerCase().trim()));
  return {
    title:   meaningful[0]?.trim() || raw,
    company: meaningful[1]?.trim() || '',
  };
}

// ─── Functions injected into each tab ────────────────────────────────────────

// Injected FIRST: scroll the job description into view and expand collapsed sections.
function scrollAndExpand() {
  // Scroll to the bottom of the page first to trigger lazy loading
  window.scrollTo(0, document.body.scrollHeight);

  const target = document.querySelector(
    '#job-details, .jobs-description__content, .show-more-less-html__markup, .jobs-description'
  );
  if (target) {
    target.scrollIntoView({ behavior: 'instant', block: 'center' });
  }

  // Click any "See more" / "Show more" buttons in the description area
  document.querySelectorAll(
    'button.show-more-less-html__button, ' +
    'button[aria-label="Click to see more description"], ' +
    'button[aria-label*="more description"]'
  ).forEach(btn => { try { btn.click(); } catch (_) {} });

  return !!target;
}

// Injected SECOND (after waiting): read the description.
// Checks sessionStorage set by the content script first, then falls back to
// DOM selectors with polling.
async function grabPageText() {
  const KEY = '__jsa_desc';

  // 1. Content script may have stored the description when the page first loaded
  try {
    const stored = sessionStorage.getItem(KEY);
    if (stored && stored.length > 300) return stored;
  } catch (_) {}

  // 2. JSON-LD structured data
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const d = JSON.parse(s.textContent);
      const raw = d.description || d.jobDescription;
      if (raw) {
        const tmp = document.createElement('div');
        tmp.innerHTML = raw;
        const text = tmp.innerText.trim();
        if (text.length > 200) return text;
      }
    } catch (_) {}
  }

  // 3. CSS selectors with polling (up to 4 seconds)
  const selectors = [
    '.show-more-less-html__markup',
    '#job-details',
    '.jobs-description__content',
    '.jobs-description-content__text',
    '.jobs-description',
    '[class*="job-description"]',
    '[class*="description__text"]',
  ];

  function tryGet() {
    // Try each selector
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      const text = el?.innerText?.trim();
      if (text && text.length > 300) return text;
    }
    // Try "About the job" heading landmark
    for (const h of document.querySelectorAll('h2, h3, [class*="heading"]')) {
      if (/about the job/i.test(h.innerText)) {
        const candidate = h.nextElementSibling || h.parentElement?.nextElementSibling;
        const text = candidate?.innerText?.trim();
        if (text && text.length > 200) return text;
      }
    }
    return null;
  }

  for (let i = 0; i < 8; i++) {
    const text = tryGet();
    if (text) return text;
    await new Promise(r => setTimeout(r, 500));
  }

  // 4. Full body fallback (always has something, may include UI chrome)
  return document.body?.innerText?.trim() || '';
}

function grabCompanyLocation() {
  function t(sels) {
    for (const sel of sels) {
      const el = document.querySelector(sel);
      const text = el?.innerText?.trim();
      if (text) return text;
    }
    return '';
  }
  return {
    company: t([
      '.job-details-jobs-unified-top-card__company-name a',
      '.job-details-jobs-unified-top-card__company-name',
      '.topcard__org-name-link',
      '.jobs-unified-top-card__company-name',
      '[class*="company-name"]',
    ]),
    location: t([
      '.job-details-jobs-unified-top-card__primary-description-without-url',
      '.topcard__flavor--bullet',
      '.jobs-unified-top-card__bullet',
      '[class*="job-location"]',
    ]),
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function injectScript(tabId, func) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId },
    func,
  });
  return res?.result ?? null;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─── Main collector ───────────────────────────────────────────────────────────

document.getElementById('collect').addEventListener('click', async () => {
  const statusEl = document.getElementById('status');
  statusEl.className = '';
  statusEl.textContent = 'Scanning tabs...';

  try {
    const allTabs = await chrome.tabs.query({});
    const jobTabs = allTabs.filter(tab => tab.url && looksLikeJob(tab.url));

    if (jobTabs.length === 0) {
      statusEl.className = 'error';
      statusEl.textContent = 'No job tabs found. Make sure your job posting tabs are open.';
      return;
    }

    statusEl.textContent = `Found ${jobTabs.length} job tab(s). Collecting...`;

    const results = [];
    const errors  = [];

    for (let i = 0; i < jobTabs.length; i++) {
      const tab = jobTabs[i];
      statusEl.textContent = `[${i + 1}/${jobTabs.length}] ${tab.title?.slice(0, 60) || tab.url}`;

      const { title, company: titleCompany } = parseTabTitle(tab.title || tab.url);
      let description = '';
      let company = titleCompany;
      let location = '';

      // Step 1: scroll into view + expand collapsed sections
      try { await injectScript(tab.id, scrollAndExpand); } catch (_) {}

      // Step 2: short wait for LinkedIn to render after scroll/click
      await sleep(800);

      // Step 3: grab description (async function with internal polling)
      try {
        description = await injectScript(tab.id, grabPageText) || '';
      } catch (e) {
        errors.push(`${title}: ${e.message}`);
      }

      // Step 4: grab company + location from page if possible
      try {
        const cl = await injectScript(tab.id, grabCompanyLocation);
        if (cl) {
          company  = cl.company  || company;
          location = cl.location || '';
        }
      } catch (_) {}

      results.push({ url: tab.url, title, company, location, description });
    }

    if (results.length === 0) {
      statusEl.className = 'error';
      statusEl.textContent = 'No results. Errors: ' + (errors.join('; ') || 'unknown');
      return;
    }

    // Save to jobs_scraped.json
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
    await chrome.downloads.download({
      url: URL.createObjectURL(blob),
      filename: 'jobs_scraped.json',
      saveAs: false,
    });

    const descOk = results.filter(r => r.description.length > 500).length;
    statusEl.className = 'ok';
    statusEl.textContent =
      `Saved ${results.length} job(s) — ${descOk} with full description. ` +
      (errors.length ? `⚠ ${errors.length} error(s). ` : '') +
      'Run: python3 scripts/import_scraped_jobs.py';
  } catch (e) {
    statusEl.className = 'error';
    statusEl.textContent = `Fatal error: ${e.message}`;
  }
});
