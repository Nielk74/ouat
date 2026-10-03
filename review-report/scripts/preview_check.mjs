// Optional visual verification: Node 22+ and a local Chromium browser, no packages.
// node preview_check.mjs report.html output-directory browser-executable
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join, dirname, basename } from 'node:path';
import { pathToFileURL } from 'node:url';

const [source, destination, executable] = process.argv.slice(2);
if (!source || !destination || !executable) {
  throw new Error('Usage: node preview_check.mjs report.html output-directory browser-executable');
}
const reportName = basename(source, '.html');
const profile = mkdtempSync(join(tmpdir(), 'review-preview-'));
const temporaryRoot = realpathSync(tmpdir());
const checkedProfile = realpathSync(profile);
if (dirname(checkedProfile) !== temporaryRoot || !basename(checkedProfile).startsWith('review-preview-')) {
  throw new Error('Temporary browser profile must be inside the system temporary directory.');
}
const browser = spawn(executable, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--remote-debugging-port=0',
  '--user-data-dir=' + checkedProfile, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
let browserError = '';
browser.stderr.on('data', data => { browserError = (browserError + data.toString()).slice(-2000); });
const sleep = milliseconds => new Promise(resolveSleep => setTimeout(resolveSleep, milliseconds));
let socket;
try {
  const activePort = join(checkedProfile, 'DevToolsActivePort');
  for (let attempt = 0; !existsSync(activePort); attempt++) {
    if (attempt > 100 || browser.exitCode !== null) throw new Error('Browser did not start: ' + browserError);
    await sleep(100);
  }
  const port = readFileSync(activePort, 'utf8').split('\n')[0];
  const targets = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
  const target = targets.find(item => item.type === 'page');
  if (!target) throw new Error('Browser page target was not created.');
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolveOpen, reject) => {
    socket.addEventListener('open', resolveOpen, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  let serial = 0;
  const pending = new Map();
  const pageErrors = [];
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') pageErrors.push(message.params.exceptionDetails.text);
    if (!pending.has(message.id)) return;
    const request = pending.get(message.id);
    pending.delete(message.id);
    clearTimeout(request.timer);
    if (message.error) request.reject(new Error(JSON.stringify(message.error)));
    else request.resolve(message.result);
  });
  function cdp(method, params = {}) {
    return new Promise((resolveCall, reject) => {
      const id = ++serial;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('Timed out: ' + method)); }, 15000);
      pending.set(id, { resolve: resolveCall, reject, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const response = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.text);
    return response.result.value;
  }
  await cdp('Page.enable');
  await cdp('Runtime.enable');
  const url = pathToFileURL(resolve(source)).href;
  const results = [];
  mkdirSync(resolve(destination), { recursive: true });
  for (const width of [1440, 768, 375]) {
    await cdp('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: width < 600 });
    await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
    await cdp('Page.navigate', { url });
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      ready = await evaluate('location.href === ' + JSON.stringify(url) + ' && document.readyState === "complete"');
      if (ready) break;
      await sleep(50);
    }
    if (!ready) throw new Error('Report did not finish loading.');
    const layout = await evaluate(`({
      width: innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      sections: [...document.querySelectorAll('main section')].map(node => node.id),
      hidden: [...document.querySelectorAll('main section, main article, main figure')].filter(node => {
        const style = getComputedStyle(node);
        return style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0;
      }).length,
      animations: document.getAnimations().map(animation => ({
        name: animation.animationName,
        className: animation.effect.target.getAttribute('class') || '',
        duration: animation.effect.getTiming().duration,
        iterations: animation.effect.getTiming().iterations === Infinity ? 'infinite' : animation.effect.getTiming().iterations
      }))
    })`);
    if (layout.scrollWidth > layout.width + 1) throw new Error('Page overflows horizontally at ' + width + 'px.');
    if (layout.hidden) throw new Error('Report hides essential content.');
    const diagramText = await evaluate(`(() => {
      const failures = [];
      let checked = 0;
      for (const graph of document.querySelectorAll('.graph')) {
        if (!graph.getClientRects().length) continue;
        for (const box of graph.querySelectorAll('.node-box')) {
          const bounds = box.getBBox();
          for (const label of box.parentElement.querySelectorAll('text')) {
            const text = label.getBBox();
            checked++;
            if (text.x < bounds.x + 3 || text.x + text.width > bounds.x + bounds.width - 3 ||
                text.y < bounds.y + 3 || text.y + text.height > bounds.y + bounds.height - 3) {
              failures.push(label.textContent);
            }
          }
        }
      }
      return { checked, failures };
    })()`);
    if (diagramText.failures.length) throw new Error('Diagram text exceeds its node: ' + JSON.stringify(diagramText.failures));
    const brandArtwork = await evaluate(`(() => {
      const failures = [];
      let checked = 0, contrastChecked = 0, multicolor = 0, minimum = Infinity;
      const rgba = color => (color.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
      const luminance = rgb => {
        const linear = rgb.map(channel => {
          const value = channel/255;
          return value <= .04045 ? value/12.92 : ((value+.055)/1.055)**2.4;
        });
        return linear.reduce((sum, value, index) => sum+value*[.2126, .7152, .0722][index], 0);
      };
      const ratio = (a, b) => (Math.max(luminance(a), luminance(b))+.05)/(Math.min(luminance(a), luminance(b))+.05);
      for (const mark of document.querySelectorAll('use[href^="#brand-"]')) {
        if (!mark.getClientRects().length) continue;
        checked++;
        const id = mark.getAttribute('href').slice(1), symbol = document.getElementById(id);
        const box = mark.getBBox();
        if (!symbol || symbol.tagName.toLowerCase() !== 'symbol' || box.width <= 0 || box.height <= 0) {
          failures.push('Missing/empty brand artwork: ' + id);
          continue;
        }
        // A single brand color cannot audit multicolor artwork. Those official
        // marks retain curated tiles and are checked visually instead.
        if (!/^#[a-f0-9]{6}$/i.test(symbol.getAttribute('fill') || '')) {
          multicolor++;
          continue;
        }
        const foreground = rgba(getComputedStyle(symbol).fill);
        const host = mark.closest('[data-node]');
        const tile = host?.querySelector('.node-art-bg') || mark.closest('.brand-art, .icon-tile');
        if (!tile) { failures.push('Brand has no controlled contrast tile: ' + id); continue; }
        const inspect = status => {
          const style = getComputedStyle(tile);
          const background = rgba(host ? style.fill : style.backgroundColor);
          const contrast = ratio(foreground, background);
          contrastChecked++;
          minimum = Math.min(minimum, contrast);
          if (!Number.isFinite(contrast) || contrast < 3) failures.push(id + ' icon contrast below 3:1 (' + status + '): ' + contrast.toFixed(2));
        };
        inspect('rendered');
        if (host) {
          const original = host.getAttribute('class');
          for (const status of ['new', 'changed', 'removed', 'unchanged']) {
            host.setAttribute('class', original.replace(/status-(new|changed|removed|unchanged)/, 'status-' + status));
            inspect(status);
            host.classList.add('has-issue');
            inspect(status + '/issue');
          }
          host.setAttribute('class', original);
        }
      }
      return { checked, contrastChecked, multicolor, minimum: Number.isFinite(minimum) ? Number(minimum.toFixed(2)) : null, failures: [...new Set(failures)] };
    })()`);
    if (brandArtwork.failures.length) throw new Error('Invalid local logo: ' + JSON.stringify(brandArtwork.failures));
    const diagramRouting = await evaluate(`(() => {
      const failures = [];
      let checked = 0;
      const bounds = node => {
        const box = node.getBBox();
        return [box.x, box.y, box.width, box.height];
      };
      const overlaps = (a, b) => a[0] < b[0]+b[2] && a[0]+a[2] > b[0] && a[1] < b[1]+b[3] && a[1]+a[3] > b[1];
      const hits = (a, b, box) => a[0] === b[0]
        ? box[0] < a[0] && a[0] < box[0]+box[2] && Math.max(a[1], b[1]) > box[1] && Math.min(a[1], b[1]) < box[1]+box[3]
        : box[1] < a[1] && a[1] < box[1]+box[3] && Math.max(a[0], b[0]) > box[0] && Math.min(a[0], b[0]) < box[0]+box[2];
      const shared = (a, b, c, d) => {
        if (a[1] === b[1] && b[1] === c[1] && c[1] === d[1]) {
          return Math.min(Math.max(a[0], b[0]), Math.max(c[0], d[0])) > Math.max(Math.min(a[0], b[0]), Math.min(c[0], d[0]));
        }
        if (a[0] === b[0] && b[0] === c[0] && c[0] === d[0]) {
          return Math.min(Math.max(a[1], b[1]), Math.max(c[1], d[1])) > Math.max(Math.min(a[1], b[1]), Math.min(c[1], d[1]));
        }
        return false;
      };
      for (const graph of document.querySelectorAll('.graph')) {
        if (!graph.getClientRects().length) continue;
        const nodes = new Map([...graph.querySelectorAll('[data-node]')].map(node => [node.dataset.node, bounds(node.querySelector('.node-box'))]));
        const headers = [...graph.querySelectorAll('.group-heading-bg')].map(bounds);
        const routes = [...graph.querySelectorAll('.edge')].map(edge => ({
          index: edge.dataset.edge, target: edge.dataset.to,
          path: edge.querySelector('.connector'),
          points: edge.querySelector('.connector').dataset.points.split(';').map(point => point.split(',').map(Number))
        }));
        const labels = [...graph.querySelectorAll('.edge-number-box')].map(bounds);
        for (const heading of graph.querySelectorAll('.group-heading')) {
          const box = bounds(heading.querySelector('.group-heading-bg'));
          const text = bounds(heading.querySelector('.group-label'));
          if (text[0] < box[0] || text[0]+text[2] > box[0]+box[2]) failures.push('Boundary title exceeds its heading.');
        }
        for (const [index, route] of routes.entries()) {
          checked++;
          const tip = route.points.at(-1), previous = route.points.at(-2);
          const [x, y, w, h] = nodes.get(route.target);
          const clearTerminal = tip[0] === x-9 && previous[0] < tip[0] && tip[1] > y && tip[1] < y+h ||
            tip[0] === x+w+9 && previous[0] > tip[0] && tip[1] > y && tip[1] < y+h ||
            tip[1] === y-9 && previous[1] < tip[1] && tip[0] > x && tip[0] < x+w ||
            tip[1] === y+h+9 && previous[1] > tip[1] && tip[0] > x && tip[0] < x+w;
          if (!clearTerminal || Math.abs(tip[0]-previous[0])+Math.abs(tip[1]-previous[1]) < 23) failures.push('Arrow ' + route.index + ' has an unclear destination.');
          for (let segment = 1; segment < route.points.length; segment++) {
            const a = route.points[segment-1], b = route.points[segment];
            if (a[0] !== b[0] && a[1] !== b[1]) failures.push('Arrow ' + route.index + ' is not orthogonal.');
            if ([...nodes.values(), ...headers].some(box => hits(a, b, box))) failures.push('Arrow ' + route.index + ' crosses a node or heading.');
            for (const other of routes.slice(index+1)) for (let part = 1; part < other.points.length; part++) {
              if (shared(a, b, other.points[part-1], other.points[part])) failures.push('Arrows ' + route.index + '/' + other.index + ' share a segment.');
            }
          }
          // Verify the actual rounded SVG path too, rather than only its routing data.
          const length = route.path.getTotalLength();
          for (let distance = 0; distance <= length; distance += 4) {
            const point = route.path.getPointAtLength(distance);
            if ([...nodes.values(), ...headers].some(box => point.x > box[0] && point.x < box[0]+box[2] && point.y > box[1] && point.y < box[1]+box[3])) {
              failures.push('Rounded arrow ' + route.index + ' enters a node or heading.');
              break;
            }
          }
          const label = labels[index];
          if (!label || [...nodes.values(), ...headers, ...labels.slice(index+1)].some(box => overlaps(label, box))) failures.push('Connection number ' + route.index + ' overlaps content.');
          if (label && routes.some((other, otherIndex) => otherIndex !== index && other.points.slice(1).some((point, part) => hits(other.points[part], point, label)))) failures.push('Connection number ' + route.index + ' obscures another arrow.');
        }
        for (const marker of graph.querySelectorAll('marker')) {
          if (marker.getAttribute('markerUnits') !== 'userSpaceOnUse' || Number(marker.getAttribute('markerWidth')) > 12) failures.push('Arrowhead scales with stroke width.');
        }
      }
      return { checked, failures: [...new Set(failures)] };
    })()`);
    if (diagramRouting.failures.length) throw new Error('Unreadable diagram routing: ' + JSON.stringify(diagramRouting.failures));
    const permitted = new Set(['highlight-outline', 'connection-flow', 'packet-transfer']);
    if (layout.animations.some(animation => !permitted.has(animation.name) || !/pulse|node-emphasis|connector-emphasis|message-packet/.test(animation.className) || (animation.name === 'packet-transfer' ? animation.duration > 4000 || animation.iterations !== 'infinite' : animation.duration * animation.iterations > 5000))) {
      throw new Error('Unexpected animation or unbounded decorative emphasis.');
    }
    const packetMotion = await evaluate(`(async () => {
      const failures = [];
      let checked = 0;
      const frame = () => new Promise(resolveFrame => requestAnimationFrame(resolveFrame));
      // Read the introduction first: packages must still move without hover/focus.
      await new Promise(resolveDelay => setTimeout(resolveDelay, 5200));
      const visiblePackets = [...document.querySelectorAll('.message-packet')].filter(node => node.closest('.graph').getClientRects().length);
      for (const packet of visiblePackets) {
        const graph = packet.closest('.graph'), edge = packet.closest('.edge');
        const path = edge.querySelector('.connector');
        const figure = packet.closest('figure');
        const control = figure.querySelector('.packet-pause');
        if (!control || !figure.querySelector('label[for="' + control?.id + '"]') || !document.getElementById(figure.getAttribute('aria-describedby'))) failures.push('Packet pause lacks a native labeled control.');
        figure.scrollIntoView({ block: 'center' });
        const animation = packet.getAnimations()[0];
        if (!animation || animation.animationName !== 'packet-transfer' || animation.effect.getTiming().iterations !== Infinity) {
          failures.push('Package is not looping automatically after a reading delay.');
          continue;
        }
        const before = animation.currentTime;
        await new Promise(resolveTick => setTimeout(resolveTick, 180));
        if (animation.playState !== 'running' || animation.currentTime <= before + 50) failures.push('Package does not advance without hover/focus.');
        control.checked = true;
        await frame();
        await frame();
        if (getComputedStyle(packet).animationPlayState !== 'paused') failures.push('Pause checkbox does not stop packet motion.');
        const paused = animation.currentTime;
        await new Promise(resolveTick => setTimeout(resolveTick, 100));
        if (Math.abs(animation.currentTime-paused) > 1) failures.push('Package still advances while paused.');
        animation.pause();
        const duration = animation.effect.getTiming().duration;
        const length = path.getTotalLength();
        for (const fraction of [.1, .25, .5, .75, .9]) {
          animation.currentTime = duration * fraction;
          await frame();
          const matrix = graph.getScreenCTM().inverse().multiply(packet.getScreenCTM());
          const expected = path.getPointAtLength(18 + (length-43) * fraction);
          checked++;
          if (Math.hypot(matrix.e-expected.x, matrix.f-expected.y) > 1) failures.push('Package leaves its connector route.');
          if (Math.abs(matrix.b) > .001 || Math.abs(matrix.c) > .001 || Math.abs(matrix.a-1) > .001 || Math.abs(matrix.d-1) > .001) failures.push('Package rotates or scales during transfer.');
          for (const obstacle of graph.querySelectorAll('.node-box, .group-heading-bg, .edge-number-box')) {
            const box = obstacle.getBBox();
            if (matrix.e+12 > box.x && matrix.e-12 < box.x+box.width && matrix.f+12 > box.y && matrix.f-12 < box.y+box.height) failures.push('Package overlaps a node, heading, or number plate.');
          }
        }
        animation.currentTime = duration * 6.5;
        await frame();
        if (getComputedStyle(packet).opacity !== '1') failures.push('Package disappears in later cycles.');
        control.checked = false;
        animation.play();
        await frame();
        if (getComputedStyle(packet).animationPlayState !== 'running') failures.push('Package does not resume after unchecking pause.');
      }
      return { checked, failures: [...new Set(failures)] };
    })()`);
    if (packetMotion.failures.length) throw new Error('Invalid package animation: ' + JSON.stringify(packetMotion.failures));
    await evaluate('window.scrollTo(0, 0)');
    // Check representative report text against its actual opaque surface. This
    // covers editor tokens on both diff backgrounds as well as status labels.
    const contrast = await evaluate(`(() => {
      const selectors = ['h1', '.summary', '.context-block p', '.context-block .label',
        '.context-notes p', '.context-notes li', '.navigation a', '.navigation .index',
        '.mode', '.change-id', '.change-description', '.badge', '.code-file',
        '.code-symbol', '.code-kind', '.code-language', '.code-side-title',
        '.code-text', '.code-sign', '.code-lineno', '.code-line-note', '[class^="token-"]', '.code-summary',
        '.visual-heading', 'figcaption', '.connection-index', '.connection-direction',
        '.connection-label', '.connection-status', '.transport-label', '.basis',
        '.problem-key', '.issue-notes h4', '.issue-notes strong', '.issue-notes p',
        '.packet-guidance',
        '.risk p', '.risk-severity', '.footer'];
      const rgba = value => value.match(/[\\d.]+/g).map(Number);
      const luminance = color => {
        const rgb = color.slice(0, 3).map(channel => {
          const s = channel / 255;
          return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4;
        });
        return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
      };
      let minimum = Infinity, checked = 0;
      const failures = [];
      for (const selector of selectors) for (const node of document.querySelectorAll(selector)) {
        if (!node.textContent.trim() || !node.getClientRects().length) continue;
        let surface = node, background;
        while (surface) {
          const value = rgba(getComputedStyle(surface).backgroundColor);
          if (value.length === 3 || value[3] === 1) { background = value; break; }
          surface = surface.parentElement;
        }
        if (!background) continue;
        const foreground = rgba(getComputedStyle(node).color);
        const a = luminance(foreground), b = luminance(background);
        const ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        minimum = Math.min(minimum, ratio);
        checked++;
        if (ratio < 4.5) failures.push({ selector, text: node.textContent.trim().slice(0, 60), ratio: Number(ratio.toFixed(2)) });
      }
      return { checked, minimum: Number(minimum.toFixed(2)), failures };
    })()`);
    if (contrast.failures.length) throw new Error('Report text contrast is below 4.5:1: ' + JSON.stringify(contrast.failures));
    await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    const reducedMotion = await evaluate('document.getAnimations().length');
    if (reducedMotion !== 0) throw new Error('Reduced motion still animates content.');
    const staticPackets = await evaluate(`Array.from(document.querySelectorAll('.message-packet')).every(packet => getComputedStyle(packet).animationName === 'none' && getComputedStyle(packet).offsetDistance === '35%' && getComputedStyle(packet).opacity === '1')`);
    if (!staticPackets) throw new Error('Reduced-motion packages are not static and visible.');
    const screenshot = await cdp('Page.captureScreenshot', { format: 'png' });
    const output = join(resolve(destination), reportName + '-' + width + '.png');
    writeFileSync(output, Buffer.from(screenshot.data, 'base64'));
    if (width === 1440) {
      const categories = await evaluate(`Array.from(document.querySelectorAll('.icon-library section'), node => ({ title: node.querySelector('h2').textContent, y: node.getBoundingClientRect().top + scrollY, height: node.offsetHeight })).filter(node => node.title !== 'Generic components')`);
      for (const category of categories) {
        const catalogImage = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: category.y, width, height: category.height, scale: 1 } });
        const categoryName = category.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-$/, '');
        writeFileSync(join(resolve(destination), reportName + '-' + categoryName + '.png'), Buffer.from(catalogImage.data, 'base64'));
      }
      const bounds = await evaluate(`(() => {
        const change = document.querySelector('article.change');
        return change ? { y: document.getElementById('changes').offsetTop, height: change.offsetHeight + 80 } : null;
      })()`);
      if (bounds) {
        const detail = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: bounds.y, width, height: bounds.height, scale: 1 } });
        writeFileSync(join(resolve(destination), reportName + '-changes.png'), Buffer.from(detail.data, 'base64'));
      }
      const graph = await evaluate(`(() => {
        const node = document.querySelector('article.change .graph')?.closest('article.change');
        return node ? { y: node.offsetTop, height: node.offsetHeight } : null;
      })()`);
      if (graph) {
        const graphImage = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: graph.y, width, height: graph.height, scale: 1 } });
        writeFileSync(join(resolve(destination), reportName + '-flow.png'), Buffer.from(graphImage.data, 'base64'));
      }
      const ci = await evaluate(`(() => {
        const node = document.querySelector('article.change .entity-ci-worker')?.closest('article.change');
        return node ? { y: node.offsetTop, height: node.offsetHeight } : null;
      })()`);
      if (ci) {
        const ciImage = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: ci.y, width, height: ci.height, scale: 1 } });
        writeFileSync(join(resolve(destination), reportName + '-ci-worker.png'), Buffer.from(ciImage.data, 'base64'));
      }
    }
    const boundary = await evaluate(`(() => {
      const node = document.querySelector('article.change .process-boundary')?.closest('article.change');
      return node ? { y: node.offsetTop, height: node.offsetHeight } : null;
    })()`);
    if (boundary) {
      const boundaryImage = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: boundary.y, width, height: boundary.height, scale: 1 } });
      writeFileSync(join(resolve(destination), reportName + '-boundaries-' + width + '.png'), Buffer.from(boundaryImage.data, 'base64'));
    }
    const baseline = await evaluate(`(() => {
      const node = document.querySelector('#context .visual');
      return node ? { y: node.getBoundingClientRect().top + scrollY, height: node.offsetHeight } : null;
    })()`);
    if (baseline) {
      const baselineImage = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: baseline.y, width, height: baseline.height, scale: 1 } });
      writeFileSync(join(resolve(destination), reportName + '-baseline-' + width + '.png'), Buffer.from(baselineImage.data, 'base64'));
    }
    if (width === 1440) {
      const changes = await evaluate(`Array.from(document.querySelectorAll('article.change'), node => ({id: node.id, y: node.getBoundingClientRect().top + scrollY, height: node.offsetHeight}))`);
      for (const change of changes) {
        const changeImage = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: change.y, width, height: change.height, scale: 1 } });
        writeFileSync(join(resolve(destination), reportName + '-' + change.id + '.png'), Buffer.from(changeImage.data, 'base64'));
      }
    }
    results.push({ ...layout, diagramText, diagramRouting, brandArtwork, packetMotion, staticPackets, contrast, reducedMotion, screenshot: output });
  }
  if (pageErrors.length) throw new Error(pageErrors.join('; '));
  console.log(JSON.stringify({ checks: results, pageErrors }, null, 2));
} finally {
  if (socket) socket.close();
  const stopped = new Promise(resolveStopped => browser.once('exit', resolveStopped));
  if (browser.exitCode === null) {
    browser.kill();
    await Promise.race([stopped, sleep(3000)]);
  }
  // Delete only this helper's previously resolved, dedicated temporary profile.
  if (existsSync(checkedProfile) && realpathSync(checkedProfile) === checkedProfile && dirname(checkedProfile) === temporaryRoot) {
    try { rmSync(checkedProfile, { recursive: true, force: true, maxRetries: 3, retryDelay: 150 }); }
    catch { console.warn('Temporary browser profile could not be removed: ' + checkedProfile); }
  }
}
