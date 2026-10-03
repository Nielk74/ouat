/* This progressive enhancement is embedded only in the explorer gallery. */
(() => {
  const root = document.documentElement;
  const demos = [...document.querySelectorAll('.showcase-demo')];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const canMove = () => !document.getElementById('motion-pause').checked &&
    (document.getElementById('motion-play').checked || !reduced.matches);
  const restart = demo => {
    if (!canMove()) return;
    demo.classList.add('replaying');
    requestAnimationFrame(() => requestAnimationFrame(() => demo.classList.remove('replaying')));
  };
  const syncControls = () => {
    for (const button of document.querySelectorAll('.demo-replay')) {
      button.disabled = !canMove();
      button.title = canMove() ? 'Restart this example from the beginning' : 'Select Play to enable replay';
    }
  };
  if ('IntersectionObserver' in window) {
    root.classList.add('showcase-enhanced');
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        entry.target.classList.toggle('in-view', entry.isIntersecting);
        if (entry.isIntersecting && !entry.target.dataset.motionSeen && canMove()) {
          entry.target.dataset.motionSeen = 'true';
          restart(entry.target);
        }
      }
    }, { rootMargin: '-115px 0px 0px 0px', threshold: 0.02 });
    for (const demo of demos) observer.observe(demo);
  }
  for (const button of document.querySelectorAll('.demo-replay')) {
    button.addEventListener('click', () => restart(button.closest('.showcase-demo')));
  }
  for (const control of document.querySelectorAll('[name="diagram-motion"]')) {
    control.addEventListener('change', syncControls);
  }
  reduced.addEventListener('change', syncControls);
  syncControls();

  const search = document.getElementById('icon-search');
  const category = document.getElementById('icon-category');
  const cards = [...document.querySelectorAll('[data-icon-id]')];
  const filterIcons = () => {
    const terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let count = 0;
    for (const card of cards) {
      card.hidden = !(terms.every(term => card.dataset.search.includes(term)) &&
        (!category.value || card.dataset.category === category.value));
      if (!card.hidden) count++;
    }
    document.getElementById('icon-count').textContent = `${count} of ${cards.length} icons`;
    document.getElementById('icon-empty').hidden = count !== 0;
  };
  search.addEventListener('input', filterIcons);
  category.addEventListener('change', filterIcons);
  document.getElementById('icon-reset').addEventListener('click', () => {
    search.value = '';
    category.value = '';
    filterIcons();
    search.focus();
  });
  filterIcons();

  for (const button of document.querySelectorAll('[data-copy-json]')) {
    button.addEventListener('click', async () => {
      const details = button.closest('.demo-recipe');
      const code = details.querySelector('.recipe-json code');
      const state = details.querySelector('.copy-status');
      try {
        if (!navigator.clipboard) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(code.textContent);
        state.textContent = 'JSON copied.';
      } catch {
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        state.textContent = 'JSON selected. Press Ctrl+C (or Command+C) to copy.';
      }
    });
  }
})();
