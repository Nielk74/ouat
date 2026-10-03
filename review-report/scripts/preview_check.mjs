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
    await cdp('Emulation.setEmulatedMedia', { features: [] });
    await cdp('Page.navigate', { url });
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      ready = await evaluate('location.href === ' + JSON.stringify(url) + ' && document.readyState === "complete"');
      if (ready) break;
      await sleep(50);
    }
    if (!ready) throw new Error('Report did not finish loading.');
    const nativeMotion = await evaluate(`({
      reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
      animations: document.getAnimations().length,
      systemSelected: document.getElementById('motion-system')?.checked ?? null,
      reducedExplanationVisible: Boolean(document.querySelector('.motion-system-reduced')?.getClientRects().length)
    })`);
    if (nativeMotion.reduced && (nativeMotion.animations || nativeMotion.systemSelected === true && !nativeMotion.reducedExplanationVisible)) throw new Error('Native reduced-motion view animates or lacks an explanation.');
    await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
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
    const connectionBadges = await evaluate(`(() => {
      const failures = [];
      let checked = 0;
      for (const badge of document.querySelectorAll('.connection-status')) {
        checked++;
        const heading = badge.parentElement;
        if (!heading.classList.contains('connection-heading') || !heading.querySelector('.connection-direction')) {
          failures.push('Connection status is detached from its title.');
          continue;
        }
        const previous = badge.previousElementSibling.getBoundingClientRect();
        const box = badge.getBoundingClientRect();
        if (box.top < previous.bottom && box.bottom > previous.top) {
          if (box.left-previous.right > 12 || box.left < previous.right-1) failures.push('Connection status is too far from its title.');
        } else if (Math.abs(box.left-heading.getBoundingClientRect().left) > 1) {
          failures.push('Wrapped connection status is not aligned with its title.');
        }
      }
      return { checked, failures };
    })()`);
    if (connectionBadges.failures.length) throw new Error('Invalid connection badges: ' + JSON.stringify(connectionBadges.failures));
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
    const permitted = new Set(['highlight-outline', 'connection-flow', 'packet-transfer', 'behavior-travel', 'behavior-waiting', 'scenario-before', 'scenario-after', 'scenario-progress', 'scenario-message', 'scenario-slow-progress', 'scenario-accumulate', 'scenario-accumulate-2', 'scenario-accumulate-3', 'scenario-accumulate-4']);
    for (let count = 2; count <= 5; count++) for (let step = 1; step <= count; step++) permitted.add('behavior-window-' + count + '-' + step);
    if (layout.animations.some(animation => !permitted.has(animation.name) || !/pulse|node-emphasis|connector-emphasis|message-packet|behavior-|scenario-/.test(animation.className) || (animation.name.startsWith('scenario-') ? animation.duration !== 12000 || animation.iterations !== 'infinite' : animation.name.startsWith('behavior-') ? animation.duration > 20000 || animation.iterations !== 'infinite' : animation.name === 'packet-transfer' ? animation.duration > 4000 || animation.iterations !== 'infinite' : animation.duration * animation.iterations > 5000))) {
      throw new Error('Unexpected animation or unbounded decorative emphasis.');
    }
    const packetMotion = await evaluate(`(async () => {
      const failures = [];
      let checked = 0;
      const transports = [];
      const frame = () => new Promise(resolveFrame => requestAnimationFrame(resolveFrame));
      // Read the introduction first: packages must still move without hover/focus.
      await new Promise(resolveDelay => setTimeout(resolveDelay, 5200));
      const visiblePackets = [...document.querySelectorAll('.message-packet')].filter(node => node.closest('.graph').getClientRects().length);
      for (const packet of visiblePackets) {
        const graph = packet.closest('.graph'), edge = packet.closest('.edge');
        transports.push(edge.classList.contains('transport-deploy') ? 'deploy' : 'message');
        const path = edge.querySelector('.connector');
        const figure = packet.closest('figure');
        const control = document.getElementById('motion-pause');
        if (!control || !document.querySelector('label[for="motion-pause"]') || !document.getElementById(figure.getAttribute('aria-describedby'))) failures.push('Packet pause lacks a shared native labeled control.');
        figure.scrollIntoView({ block: 'center' });
        const animation = packet.getAnimations()[0];
        if (!animation || animation.animationName !== 'packet-transfer' || animation.effect.getTiming().iterations !== Infinity) {
          failures.push('Package is not looping automatically after a reading delay.');
          continue;
        }
        const before = animation.currentTime;
        const beforePosition = graph.getScreenCTM().inverse().multiply(packet.getScreenCTM());
        await new Promise(resolveTick => setTimeout(resolveTick, 180));
        if (animation.playState !== 'running' || animation.currentTime <= before + 50) failures.push('Package does not advance without hover/focus.');
        const afterPosition = graph.getScreenCTM().inverse().multiply(packet.getScreenCTM());
        // Neighboring nodes can leave only a short transfer lane. Detect frozen
        // geometry without demanding a fixed distance greater than its motion.
        const minimumMovement = Math.min(2, Math.max(.1, (path.getTotalLength()-43)/100));
        if (Math.hypot(afterPosition.e-beforePosition.e, afterPosition.f-beforePosition.f) < minimumMovement) failures.push('Animation clock advances but the visible packet does not move.');
        control.checked = true;
        await frame();
        await frame();
        if (getComputedStyle(packet).animationPlayState !== 'paused') failures.push('Shared Pause does not stop packet motion.');
        const paused = animation.currentTime;
        await new Promise(resolveTick => setTimeout(resolveTick, 100));
        if (Math.abs(animation.currentTime-paused) > 1) failures.push('Package still advances while paused.');
        animation.pause();
        const duration = animation.effect.getTiming().duration;
        const delay = animation.effect.getTiming().delay;
        const length = path.getTotalLength();
        for (const fraction of [.1, .25, .5, .75, .9]) {
          // Sample the intended active phase, including a mid-route startup offset.
          animation.currentTime = delay + duration * (1 + fraction);
          await frame();
          const matrix = graph.getScreenCTM().inverse().multiply(packet.getScreenCTM());
          const expected = path.getPointAtLength(18 + (length-43) * fraction);
          checked++;
          if (Math.hypot(matrix.e-expected.x, matrix.f-expected.y) > 1) failures.push('Package leaves its connector route: sample=' + fraction + ', progress=' + animation.effect.getComputedTiming().progress + ', delay=' + animation.effect.getTiming().delay);
          if (Math.abs(matrix.b) > .001 || Math.abs(matrix.c) > .001 || Math.abs(matrix.a-1) > .001 || Math.abs(matrix.d-1) > .001) failures.push('Package rotates or scales during transfer.');
          for (const obstacle of graph.querySelectorAll('.node-box, .group-heading-bg, .edge-number-box')) {
            const box = obstacle.getBBox();
            if (matrix.e+12 > box.x && matrix.e-12 < box.x+box.width && matrix.f+12 > box.y && matrix.f-12 < box.y+box.height) failures.push('Package overlaps a node, heading, or number plate.');
          }
        }
        animation.currentTime = delay + duration * 6.5;
        await frame();
        if (getComputedStyle(packet).opacity !== '1') failures.push('Package disappears in later cycles.');
        document.getElementById('motion-play').checked = true;
        animation.play();
        await frame();
        if (getComputedStyle(packet).animationPlayState !== 'running') failures.push('Package does not resume after selecting Play.');
      }
      return { checked, transports, failures: [...new Set(failures)] };
    })()`);
    if (packetMotion.failures.length) throw new Error('Invalid package animation: ' + JSON.stringify(packetMotion.failures));
    const sequenceMotion = await evaluate(`(async () => {
      const failures = [], samples = [];
      const frame = () => new Promise(done => requestAnimationFrame(done));
      for (const graph of document.querySelectorAll('.graph')) {
        if (!graph.getClientRects().length || !graph.querySelector('.behavior-phase')) continue;
        const figure = graph.closest('figure');
        figure.scrollIntoView({ block: 'center' });
        const pane = graph.closest('.behavior-pane') || figure;
        const phases = [...graph.querySelectorAll('.behavior-phase'), ...pane.querySelectorAll('.behavior-step-highlight')];
        const active = graph.querySelector('.behavior-travel');
        const count = pane.querySelectorAll('.behavior-step').length;
        const seek = async time => {
          for (const element of [...phases, ...graph.querySelectorAll('.behavior-travel, .behavior-wait-outline')]) {
            const animation = element.getAnimations()[0];
            if (!animation) { failures.push('Missing behavior animation.'); continue; }
            animation.pause();
            animation.currentTime = time;
          }
          await frame();
        };
        for (let step = 1; step <= count; step++) {
          await seek((step-1)*4000+2000);
          const visible = phases.filter(node => Number(getComputedStyle(node).opacity) > .9).map(node => Number(node.dataset.step));
          if (!visible.length || visible.some(number => number !== step)) failures.push('Behavior order/step highlighting is out of sync.');
          samples.push({ step, visible });
        }
        await seek(count*4000+1000);
        if (Number(getComputedStyle(graph.querySelector('[data-step="1"]')).opacity) !== 1) failures.push('Behavior does not repeat after its first cycle.');
        for (const signal of graph.querySelectorAll('.behavior-travel')) {
          const path = signal.closest('.edge').querySelector('.connector');
          const animation = signal.getAnimations()[0];
          const length = path.getTotalLength();
          for (const fraction of [.1, .25, .5, .75, .9]) {
            animation.currentTime = fraction*4000;
            await frame();
            const matrix = graph.getScreenCTM().inverse().multiply(signal.getScreenCTM());
            const expected = path.getPointAtLength(18+(length-43)*fraction);
            if (Math.hypot(matrix.e-expected.x, matrix.f-expected.y) > 1) failures.push('Behavior signal leaves its connector.');
            for (const obstacle of graph.querySelectorAll('.node-box, .group-heading-bg, .edge-number-box')) {
              const box = obstacle.getBBox();
              if (matrix.e+12 > box.x && matrix.e-12 < box.x+box.width && matrix.f+12 > box.y && matrix.f-12 < box.y+box.height) failures.push('Behavior signal overlaps diagram content.');
            }
          }
        }
        await seek(1000);
        for (const element of [...phases, ...graph.querySelectorAll('.behavior-travel, .behavior-wait-outline')]) element.getAnimations()[0]?.play();
        if (active) {
          const before = active.getScreenCTM();
          await new Promise(done => setTimeout(done, 180));
          const after = active.getScreenCTM();
          if (Math.hypot(after.e-before.e, after.f-before.f) < .1) failures.push('Behavior clock advances but its signal does not move.');
        }
        const outline = graph.querySelector('.behavior-wait-outline');
        if (outline) {
          const beforeDash = getComputedStyle(outline).strokeDashoffset;
          await new Promise(done => setTimeout(done, 120));
          if (getComputedStyle(outline).strokeDashoffset === beforeDash) failures.push('Waiting outline is not moving.');
        }
      }
      return { samples, failures: [...new Set(failures)] };
    })()`);
    if (sequenceMotion.failures.length) throw new Error('Invalid baseline behavior animation: ' + JSON.stringify(sequenceMotion.failures));
    const scenarioMotion = await evaluate(`(async () => {
      const failures = [], samples = [];
      const frame = () => new Promise(done => requestAnimationFrame(done));
      for (const scene of document.querySelectorAll('.problem-scenario')) {
        const animations = scene.getAnimations({ subtree: true });
        if (!animations.length) { failures.push('Scenario has no playback.'); continue; }
        const visible = selector => [...scene.querySelectorAll(selector)].filter(node => Number(getComputedStyle(node).opacity) > .9).length;
        const state = () => ({
          normal: visible('.scenario-normal'), failure: visible('.scenario-failure'),
          progress: scene.querySelector('.scenario-progress-fill') ? new DOMMatrix(getComputedStyle(scene.querySelector('.scenario-progress-fill')).transform).a : null,
          items: visible('.scenario-backlog-item, .scenario-capacity-slot'),
          messageX: scene.querySelector('.scenario-message-token') ? new DOMMatrix(getComputedStyle(scene.querySelector('.scenario-message-token')).transform).e : null,
          jobVisible: visible('.scenario-job-symbol'),
        });
        const seek = async time => {
          for (const animation of animations) { animation.pause(); animation.currentTime = time; }
          await frame();
          return state();
        };
        const start = await seek(500), active = await seek(3000), beforeFailure = await seek(5000);
        const failed = await seek(8000), held = await seek(11000), replay = await seek(12500);
        const template = scene.dataset.scenario;
        if (!start.normal || start.failure || failed.normal || !failed.failure || held.normal || !held.failure || !replay.normal || replay.failure) failures.push(template + ': normal/failure/replay states are not synchronized.');
        if (!scene.querySelector('.scenario-condition')?.textContent.trim() || !scene.querySelector('.scenario-explanation')?.textContent.trim() || scene.querySelectorAll('.scenario-story li').length !== 3) failures.push(template + ': condition or causal explanation is missing.');
        if (template === 'interrupted-work') {
          if (!(active.progress > start.progress && beforeFailure.progress > active.progress && failed.progress > .1 && failed.progress < .9 && Math.abs(held.progress-failed.progress) < .001)) failures.push('Interrupted work does not stop unfinished and hold its progress.');
          if (!start.jobVisible || failed.jobVisible || !scene.querySelector('.scenario-runtime .scenario-failure') || !scene.querySelector('.scenario-card-to .scenario-empty-result')) failures.push('Process stop does not interrupt the job and leave a missing result.');
        } else if (template === 'message-loss') {
          if (!(active.messageX > start.messageX && start.jobVisible && !failed.jobVisible) || !scene.querySelector('.scenario-card-to .scenario-empty-result') || scene.querySelector('.scenario-card-to .scenario-message-token')) failures.push('Lost message does not travel then disappear before delivery.');
        } else if (template === 'bottleneck' || template === 'saturation') {
          const expected = template === 'bottleneck' ? 4 : 3;
          if (start.items !== 0 || active.items <= start.items || beforeFailure.items < active.items || failed.items !== expected || held.items !== expected) failures.push(template + ': pending items/capacity do not accumulate from an empty start.');
          if (template === 'bottleneck' && !(held.progress > failed.progress && failed.progress > active.progress)) failures.push('Bottleneck stops all processing instead of showing continued throughput.');
          if (!scene.querySelector('.scenario-card-to .scenario-delay') || scene.querySelector('.scenario-failure-mark')) failures.push(template + ': delayed work is incorrectly represented as lost.');
        } else failures.push('Unknown consequence pattern: ' + template);
        samples.push({ template, start, active, failed, held });
        await seek(2000);
        animations.forEach(animation => animation.play());
        const before = state();
        await new Promise(done => setTimeout(done, 180));
        const after = state();
        if (template === 'interrupted-work' || template === 'bottleneck') {
          if (after.progress <= before.progress) failures.push(template + ': progress is not visibly advancing during playback.');
        } else if (template === 'message-loss' && after.messageX <= before.messageX) failures.push('Message is not visibly moving during playback.');
      }
      return { samples, failures: [...new Set(failures)] };
    })()`);
    if (scenarioMotion.failures.length) throw new Error('Invalid consequence animation: ' + JSON.stringify(scenarioMotion.failures));
    if (scenarioMotion.samples.length) {
      for (const [phase, time] of [['active', 2000], ['outcome', 8000]]) {
        const scenes = await evaluate(`(async () => {
          for (const scene of document.querySelectorAll('.problem-scenario')) for (const animation of scene.getAnimations({ subtree: true })) { animation.pause(); animation.currentTime = ${time}; }
          await new Promise(done => requestAnimationFrame(done));
          return [...document.querySelectorAll('.problem-scenario')].map((scene, index) => ({ index, template: scene.dataset.scenario, y: scene.getBoundingClientRect().top + scrollY, height: scene.offsetHeight }));
        })()`);
        for (const scene of scenes) {
          const shot = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: scene.y, width, height: scene.height, scale: 1 } });
          writeFileSync(join(resolve(destination), reportName + '-scenario-' + scene.index + '-' + phase + '-' + width + '.png'), Buffer.from(shot.data, 'base64'));
        }
      }
      await evaluate(`document.querySelectorAll('.problem-scenario').forEach(scene => scene.getAnimations({ subtree: true }).forEach(animation => animation.play()))`);
    }
    let responsiveSequence = null;
    if (width === 1440 && sequenceMotion.samples.length) {
      await evaluate(`(() => {
        for (const phase of document.querySelectorAll('#context .behavior-phase')) {
          if (!phase.getClientRects().length) continue;
          const animation = phase.getAnimations()[0];
          animation.currentTime = 6000;
          animation.play();
        }
      })()`);
      await cdp('Emulation.setDeviceMetricsOverride', { width: 375, height: 1100, deviceScaleFactor: 1, mobile: true });
      await sleep(120);
      responsiveSequence = await evaluate(`(() => {
        const active = selector => [...document.querySelectorAll(selector)].filter(node => node.getClientRects().length && Number(getComputedStyle(node).opacity) > .9).map(node => Number(node.dataset.step));
        return { graph: active('#context .graph .behavior-phase'), strip: active('#context .behavior-step-highlight') };
      })()`);
      if (!responsiveSequence.graph.length || !responsiveSequence.strip.length || responsiveSequence.graph.some(step => !responsiveSequence.strip.includes(step))) throw new Error('Responsive sequence loses synchronization: ' + JSON.stringify(responsiveSequence));
      await cdp('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: false });
    }
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
        '.packet-guidance', '.motion-controls legend', '.motion-controls label', '.motion-controls p', '.behavior-step strong', '.behavior-step div > span', '.behavior-note',
        '.scenario-heading h4', '.scenario-heading > span', '.scenario-condition', '.scenario-runtime', '.scenario-component h5', '.scenario-component span', '.scenario-component-state > span', '.scenario-graphic-note', '.scenario-story li', '.scenario-explanation p', '.scenario-consequence strong', '.scenario-note', '.scenario-failure',
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
    await evaluate(`document.getElementById('motion-system') && (document.getElementById('motion-system').checked = true)`);
    await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    const reducedMotion = await evaluate('document.getAnimations().length');
    if (reducedMotion !== 0) throw new Error('Reduced motion still animates content.');
    const staticPackets = await evaluate(`Array.from(document.querySelectorAll('.message-packet')).every(packet => getComputedStyle(packet).animationName === 'none' && getComputedStyle(packet).offsetDistance === '35%' && getComputedStyle(packet).opacity === '1')`);
    if (!staticPackets) throw new Error('Reduced-motion packages are not static and visible.');
    const staticScenarioExpression = `(() => {
      const failures = [];
      for (const scene of document.querySelectorAll('.problem-scenario')) {
        if ([...scene.querySelectorAll('.scenario-normal')].some(node => Number(getComputedStyle(node).opacity) !== 0) || [...scene.querySelectorAll('.scenario-failure')].some(node => Number(getComputedStyle(node).opacity) !== 1)) failures.push(scene.dataset.scenario + ': static view does not show the failure outcome.');
        if (scene.dataset.scenario === 'interrupted-work') {
          const progress = new DOMMatrix(getComputedStyle(scene.querySelector('.scenario-progress-fill')).transform).a;
          if (progress <= 0 || progress >= 1) failures.push('Static interrupted work appears completed or unstarted.');
        }
        if ([...scene.querySelectorAll('.scenario-backlog-item, .scenario-capacity-slot')].some(node => Number(getComputedStyle(node).opacity) !== 1)) failures.push('Static backlog/capacity hides occupied items.');
      }
      return { checked: document.querySelectorAll('.problem-scenario').length, failures };
    })()`;
    const staticScenarios = await evaluate(staticScenarioExpression);
    if (staticScenarios.failures.length) throw new Error('Invalid reduced-motion consequence: ' + JSON.stringify(staticScenarios.failures));
    const reducedPlayback = await evaluate(`(async () => {
      const control = document.getElementById('motion-play');
      if (!control) return { checked: 0, failures: [] };
      const failures = [], frame = () => new Promise(done => requestAnimationFrame(done));
      const staticState = () => [...document.querySelectorAll('.message-packet, .behavior-phase, .behavior-travel, .scenario-normal, .scenario-failure, .scenario-progress-fill, .scenario-backlog-item, .scenario-capacity-slot')].map(node => {
        const style = getComputedStyle(node);
        return [style.opacity, style.transform, style.offsetDistance];
      });
      const beforePause = JSON.stringify(staticState());
      document.getElementById('motion-pause').checked = true;
      await frame(); await frame();
      await new Promise(done => setTimeout(done, 120));
      if (JSON.stringify(staticState()) !== beforePause) failures.push('Pause changes the static reduced-motion view before Play.');
      if (document.getAnimations().some(animation => animation.playState !== 'paused' || animation.currentTime !== 0)) failures.push('Pause starts playback before Play.');
      document.getElementById('motion-system').checked = true;
      await frame(); await frame();
      control.checked = true;
      await frame(); await frame();
      for (const pane of document.querySelectorAll('.behavior-pane')) {
        if (!pane.getClientRects().length) continue;
        const phases = [...pane.querySelectorAll('.behavior-phase')];
        const count = pane.querySelectorAll('.behavior-step').length;
        const animations = pane.getAnimations({ subtree: true });
        for (let step = 1; step <= count; step++) {
          for (const animation of animations) { animation.pause(); animation.currentTime = (step-1)*4000+500; }
          await frame();
          const visible = phases.filter(node => Number(getComputedStyle(node).opacity) > .9).map(node => Number(node.dataset.step));
          if (!visible.length || visible.some(number => number !== step)) failures.push('Reduced-motion Play shows future sequence steps before their turn.');
        }
        for (const animation of animations) animation.play();
      }
      // Discard test-controlled WAAPI clocks before checking native controls.
      document.getElementById('motion-system').checked = true;
      await frame(); await frame();
      control.checked = true;
      await frame(); await frame();
      const markers = [...document.querySelectorAll('.message-packet, .behavior-travel')].filter(node => node.closest('.graph').getClientRects().length);
      const moving = markers[0];
      if (moving) {
        const before = moving.getScreenCTM();
        await new Promise(done => setTimeout(done, 200));
        const after = moving.getScreenCTM();
        if (Math.hypot(after.e-before.e, after.f-before.f) < .1) failures.push('Play does not visibly override reduced motion.');
      }
      if (!document.getAnimations().length) failures.push('Play has no active animations.');
      const progress = document.querySelector('.scenario-progress-fill');
      if (progress) {
        progress.getAnimations()[0].currentTime = 2000;
        await frame();
        const before = new DOMMatrix(getComputedStyle(progress).transform).a;
        await new Promise(done => setTimeout(done, 180));
        if (new DOMMatrix(getComputedStyle(progress).transform).a <= before) failures.push('Play does not advance scenario progress under reduced motion.');
      }
      document.getElementById('motion-pause').checked = true;
      await frame(); await frame();
      const animations = document.getAnimations();
      const times = animations.map(animation => animation.currentTime);
      await new Promise(done => setTimeout(done, 120));
      if (animations.some((animation, index) => animation.playState !== 'paused' || Math.abs(animation.currentTime-times[index]) > 1)) failures.push('Pause does not freeze playback under reduced motion.');
      if (!animations.length) failures.push('Pause resets rather than freezes the animation.');
      control.checked = true;
      await frame();
      if (document.getAnimations().some(animation => animation.playState !== 'running')) failures.push('Play does not resume paused reduced-motion playback.');
      return { checked: markers.length, failures };
    })()`);
    if (reducedPlayback.failures.length) throw new Error('Invalid reduced-motion controls: ' + JSON.stringify(reducedPlayback.failures));
    await cdp('Emulation.setEmulatedMedia', { media: 'print', features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    const printMotion = await evaluate(`({ animations: document.getAnimations().length, phasesVisible: [...document.querySelectorAll('.behavior-phase:not(.behavior-step-highlight)')].every(node => Number(getComputedStyle(node).opacity) === 1) })`);
    if (printMotion.animations || !printMotion.phasesVisible) throw new Error('Print animates or hides behavior indications after Play.');
    const printScenarios = await evaluate(staticScenarioExpression);
    if (printScenarios.failures.length) throw new Error('Invalid print consequence: ' + JSON.stringify(printScenarios.failures));
    await evaluate(`document.getElementById('motion-system') && (document.getElementById('motion-system').checked = true)`);
    await cdp('Emulation.setEmulatedMedia', { media: 'screen', features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
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
    results.push({ ...layout, nativeMotion, diagramText, connectionBadges, diagramRouting, brandArtwork, packetMotion, sequenceMotion, scenarioMotion, responsiveSequence, staticPackets, staticScenarios, contrast, reducedMotion, reducedPlayback, printMotion, printScenarios, screenshot: output });
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
