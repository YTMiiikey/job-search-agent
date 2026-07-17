// Content script: runs on every LinkedIn job page as it loads.
// Captures the job description and stashes it in sessionStorage so the
// popup can read it later (even if the tab is frozen in the background).

(function () {
  const KEY = '__jsa_desc';

  function extractDescription() {
    // 1. JSON-LD structured data (most reliable when present)
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

    // 2. CSS selectors — LinkedIn 2025/2026 class names
    const selectors = [
      '.show-more-less-html__markup',           // expanded description HTML area
      '#job-details',                            // id-based container
      '.jobs-description__content',             // content area
      '.jobs-description-content__text',        // alternate name
      '.jobs-description',                      // broader wrapper
      '[class*="job-description"]',             // any class containing job-description
      '[class*="description__text"]',           // alternate LinkedIn naming
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      const text = el?.innerText?.trim();
      if (text && text.length > 300) return text;
    }

    // 3. Find the element that immediately follows an "About the job" heading
    for (const heading of document.querySelectorAll('h2, h3, [class*="heading"]')) {
      if (/about the job/i.test(heading.innerText)) {
        // Try next sibling, then parent's next sibling
        let candidate = heading.nextElementSibling || heading.parentElement?.nextElementSibling;
        const text = candidate?.innerText?.trim();
        if (text && text.length > 200) return text;
      }
    }

    return null;
  }

  function tryStore() {
    const text = extractDescription();
    if (text) {
      try { sessionStorage.setItem(KEY, text); } catch (_) {}
      return true;
    }
    return false;
  }

  // Try immediately (page may already be rendered)
  if (tryStore()) return;

  // Otherwise observe DOM mutations until the description appears (or 10 s pass)
  const observer = new MutationObserver(() => {
    if (tryStore()) observer.disconnect();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  setTimeout(() => observer.disconnect(), 10000);
})();
