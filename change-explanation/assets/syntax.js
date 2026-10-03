/* Offline progressive enhancement. Plain source and diff gutters survive without JS. */
(() => {
  const hljs = globalThis.ChangeExplanationHLJS?.default;
  if (!hljs) return;
  const canonicalNames = new Map();
  for (const name of hljs.listLanguages()) {
    const grammar = hljs.getLanguage(name);
    for (const alias of grammar.aliases || []) canonicalNames.set(alias.toLowerCase(), name);
  }
  for (const name of hljs.listLanguages()) canonicalNames.set(name, name);
  const aliases = {'c#':'csharp', 'c++':'cpp', 'f#':'fsharp', 'shell':'bash', 'jsx':'javascript', 'tsx':'typescript', 'plain text':'plaintext'};
  const extensions = {
    mjs:'javascript', cjs:'javascript', mts:'typescript', cts:'typescript',
    vue:'xml', svelte:'xml', astro:'xml', svg:'xml', xhtml:'xml',
    h:'cpp', hh:'cpp', hpp:'cpp', hxx:'cpp', cc:'cpp', cxx:'cpp', ino:'cpp',
    csx:'csharp', kt:'kotlin', kts:'kotlin', rs:'rust', pyw:'python', pyi:'python',
    psm1:'powershell', psd1:'powershell', bash:'bash', zsh:'bash',
    rbw:'ruby', rmd:'markdown', mdx:'markdown', ipynb:'json', jsonl:'json',
    tf:'hcl', tfvars:'hcl', yml:'yaml', toml:'ini', cfg:'ini', properties:'properties',
    proto:'protobuf', graphql:'graphql', gql:'graphql', ex:'elixir', exs:'elixir',
    clj:'clojure', cljs:'clojure', cljc:'clojure', edn:'clojure', hrl:'erlang',
    pl:'perl', pm:'perl', tex:'latex', cls:'latex', sty:'latex', vb:'vbnet'
  };
  const specialFiles = {
    dockerfile:'dockerfile', containerfile:'dockerfile', makefile:'makefile', gnumakefile:'makefile',
    'cmakelists.txt':'cmake', '.bashrc':'bash', '.zshrc':'bash', '.profile':'bash',
    gemfile:'ruby', rakefile:'ruby', vagrantfile:'ruby', justfile:'makefile'
  };
  // Exclude obscure grammars from content guesses; explicit names and filenames use the full registry.
  const candidates = ['bash','c','cpp','csharp','css','dart','diff','dockerfile','elixir','erlang',
    'go','graphql','groovy','haskell','terraform','ini','java','javascript','json','julia','kotlin',
    'latex','less','lua','makefile','markdown','nginx','objectivec','perl','php','powershell',
    'protobuf','python','r','ruby','rust','scala','scss','sql','swift','typescript','vbnet','xml','yaml']
    .filter(name => hljs.getLanguage(name));
  const normalize = value => {
    const key = (value || '').trim().toLowerCase().replace(/^language-/, '');
    return canonicalNames.get(aliases[key] || key);
  };
  const fromFile = value => {
    const name = (value || '').split(/[\\/]/).pop().toLowerCase();
    if (specialFiles[name]) return specialFiles[name];
    if (/^(dockerfile|containerfile)\./.test(name)) return 'dockerfile';
    const extension = name.includes('.') ? name.split('.').pop() : '';
    return normalize(extensions[extension] || extension);
  };
  const selectLanguage = (explicit, file, source) => {
    if (explicit.trim()) return {language:normalize(explicit) || 'plaintext', origin:'Specified language'};
    const inferred = fromFile(file);
    if (inferred) return {language:inferred, origin:'Detected from filename'};
    // Strong syntax cues prevent higher-scoring, incompatible guesses on small excerpts.
    const signatures = [
      ['python', /^\s*(?:async\s+)?def\s+\w+\s*\([^\n]*\)\s*(?:->[^\n]+)?\s*:/m],
      ['sql', /^\s*(?:select\b[\s\S]+?\bfrom\b|insert\s+into\b|delete\s+from\b|create\s+(?:table|index|view)\b|alter\s+table\b)/i],
      ['go', /^\s*package\s+\w+[\s\S]*\bfunc\s+/m],
      ['rust', /^\s*(?:pub\s+)?(?:async\s+)?fn\s+\w+\s*\(/m],
      ['php', /^\s*<\?php\b/],
      ['terraform', /^\s*(?:resource|data)\s+"[^"\n]+"\s+"[^"\n]+"\s*\{/m],
      ['typescript', /^\s*(?:export\s+)?(?:interface\s+\w+\s*\{|type\s+\w+\s*=)/m],
      ['javascript', /^\s*(?:export\s+)?(?:const|let)\s+[\w$]+\s*=/m],
      ['bash', /^#![^\n]*\b(?:bash|sh|zsh)\b/]
    ];
    for (const [language, signature] of signatures) {
      if (signature.test(source)) return {language, origin:'Detected from content'};
    }
    if (/^\s*[\[{]/.test(source)) {
      try { JSON.parse(source); return {language:'json', origin:'Detected from content'}; } catch { /* Continue inference. */ }
    }
    // Content guesses are a fallback for substantive excerpts, not arbitrary prose.
    const result = hljs.highlightAuto(source.slice(0, 12000), candidates);
    return result.language && result.relevance >= 3 && result.relevance > (result.secondBest?.relevance || 0)
      ? {language:result.language, origin:'Detected from content'}
      : {language:'plaintext', origin:'Plain text'};
  };
  const paint = (source, language) => hljs.highlight(source, {language, ignoreIllegals:true}).value;
  const paintLines = (lines, language) => {
    const original = lines.map(line => line.textContent);
    const template = document.createElement('template');
    template.innerHTML = paint(original.join('\n'), language);
    const fragments = [document.createDocumentFragment()];
    // Split emitted tokens at newlines, retaining ancestor scopes for multiline strings/comments.
    const visit = (node, scopes = []) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const parts = node.textContent.split('\n');
        parts.forEach((part, index) => {
          if (index) fragments.push(document.createDocumentFragment());
          if (!part) return;
          let painted = document.createTextNode(part);
          for (const scope of [...scopes].reverse()) {
            const span = document.createElement('span');
            span.className = scope;
            span.append(painted);
            painted = span;
          }
          fragments.at(-1).append(painted);
        });
      } else {
        const next = node.nodeType === Node.ELEMENT_NODE && node.className ? [...scopes, node.className] : scopes;
        for (const child of node.childNodes) visit(child, next);
      }
    };
    visit(template.content);
    if (fragments.length !== lines.length || fragments.some((fragment, i) => fragment.textContent !== original[i])) return;
    lines.forEach((line, i) => line.replaceChildren(fragments[i]));
  };
  for (const block of document.querySelectorAll('.code-change:not([data-highlighted])')) {
    try {
      const sides = [...block.querySelectorAll('.code-excerpt')].map(side => [...side.querySelectorAll('.code-text')]);
      const source = sides.map(lines => lines.map(line => line.textContent).join('\n')).sort((a,b) => b.length-a.length)[0] || '';
      const chosen = selectLanguage(block.dataset.language || '', block.dataset.file || '', source);
      for (const lines of sides) if (lines.length) paintLines(lines, chosen.language);
      const badge = block.querySelector('.code-language');
      if (badge) {
        badge.textContent = chosen.language === 'plaintext' && !block.dataset.language ? '' : hljs.getLanguage(chosen.language).name || chosen.language;
        badge.title = chosen.origin;
      }
      block.dataset.resolvedLanguage = chosen.language;
      block.dataset.highlighted = 'true';
    } catch { /* Keep the already escaped, readable source if a grammar fails. */ }
  }
  for (const code of document.querySelectorAll('.recipe-json code:not([data-highlighted])')) {
    try {
      const original = code.textContent;
      const template = document.createElement('template');
      template.innerHTML = paint(original, 'json');
      if (template.content.textContent !== original) continue;
      code.replaceChildren(template.content);
      code.dataset.highlighted = 'true';
    } catch { /* Copy still works with plain JSON. */ }
  }
})();
