/* Explorer-only, deterministic capacity illustration. Dots represent requests. */
(() => {
  'use strict';
  const root = document.getElementById('traffic-model');
  if (!root) return;
  const demandControl = document.getElementById('traffic-demand');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const EPSILON = 1e-9;
  const SERVICE_SECONDS = .5;
  const CYCLE_SECONDS = 4;
  const BURST_SECONDS = 2;
  const PLAYBACK_RATE = .25;
  let demand = Math.max(2, Math.min(40, Number(demandControl?.value) || 18));
  let visible = !('IntersectionObserver' in window);
  let printing = false;
  let representative = false;
  let previousFrame = null;
  let savedPrintEngine = null;
  const makeSide = (slots, maxWaiting) => ({
    slots, maxWaiting, capacity: slots / SERVICE_SECONDS,
    received: 0, completed: 0, lost: 0, active: [], waiting: [], rejected: []
  });
  const makeEngine = () => ({elapsed: 0, nextRequest: 1,
    current: makeSide(1, 6), scaled: makeSide(12, 36)});
  let engine = makeEngine();
  const moving = () => !printing && !document.hidden && visible &&
    !document.getElementById('motion-pause')?.checked &&
    (document.getElementById('motion-play')?.checked || !reduced.matches);
  const staticPreference = () => reduced.matches && !document.getElementById('motion-play')?.checked;
  const marker = side => `<defs><marker id="traffic-${side}-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0L6 3L0 6"/></marker></defs>`;
  const node = (x, y, width, label, symbol, extra = '') =>
    `<g class="traffic-node ${extra}"><rect x="${x-width/2}" y="${y-29}" width="${width}" height="58" rx="6"/><use href="#entity-${symbol}" x="${x-15}" y="${y-22}" width="30" height="30"/><text x="${x}" y="${y+22}">${label}</text></g>`;
  const route = (side, points) => `<polyline class="traffic-route" points="${points}" marker-end="url(#traffic-${side}-arrow)"/>`;
  const users = (side, x) => `<g class="traffic-users"><text class="traffic-note" x="${x}" y="76">Many users</text>${[-15,0,15].map(offset => `<circle cx="${x+offset}" cy="92" r="3.5"/><path d="M${x+offset-6} 106v-2a6 6 0 0 1 12 0v2"/>`).join('')}</g>${route(side,`${x},113 ${x},132`)}`;
  const current = `${marker('current')}
    ${users('current',70)}
    ${route('current','110,166 270,166')}${route('current','350,166 515,166')}
    ${node(70,166,80,'Frontend','client')}${node(310,166,80,'API','server')}${node(555,166,80,'DB','database')}
    <text class="traffic-note" x="310" y="218">Synchronous work</text>
    <rect class="traffic-service-track" x="282" y="231" width="56" height="5" rx="2"/>
    <rect class="traffic-service-fill" x="282" y="231" width="0" height="5" rx="2"/>
    <g class="traffic-waiting"></g><g class="traffic-active"></g><g class="traffic-rejected"></g>
    <text class="traffic-queue-label" x="214" y="278"></text>
    <text class="traffic-note" x="310" y="318">Too much work arrives at once.</text>`;
  const scaled = `${marker('scaled')}
    ${users('scaled',40)}
    ${route('scaled','73,166 96,166')}
    ${route('scaled','144,166 162,166 162,96 180,96')}
    ${route('scaled','144,166 180,166')}
    ${route('scaled','144,166 162,166 162,236 180,236')}
    ${route('scaled','240,96 256,96 256,166 272,166')}
    ${route('scaled','240,166 272,166')}
    ${route('scaled','240,236 256,236 256,166 272,166')}
    ${route('scaled','338,166 364,166')}${route('scaled','436,166 460,166')}${route('scaled','530,166 560,166')}
    ${node(40,166,66,'Frontend','client')}${node(120,166,48,'LB','generic','traffic-added')}
    ${node(210,96,60,'API','server','traffic-changed')}${node(210,166,60,'API','server','traffic-added')}${node(210,236,60,'API','server','traffic-added')}
    ${node(305,166,66,'Queue','queue','traffic-added')}${node(400,166,72,'Workers','worker','traffic-added')}${node(495,166,70,'DB pool','database','traffic-added')}${node(590,166,60,'DB','database')}
    <text class="traffic-note" x="210" y="291">API replicas</text>
    <text class="traffic-note" x="400" y="218">Parallel work</text>
    <g class="traffic-waiting"></g><g class="traffic-active"></g><g class="traffic-rejected"></g>
    <text class="traffic-queue-label" x="305" y="278"></text>
    <text class="traffic-note" x="310" y="318">Waiting work stays in the queue.</text>`;
  const diagrams = {};
  for (const [side, markup] of [['current', current], ['scaled', scaled]]) {
    const placeholder = document.getElementById(`traffic-${side}-diagram`);
    if (!placeholder) continue;
    placeholder.innerHTML = `<svg class="traffic-diagram" viewBox="0 0 640 340" role="img" aria-labelledby="traffic-${side}-graphic-title traffic-${side}-description"><title id="traffic-${side}-graphic-title">${side === 'current' ? 'Single synchronous API' : 'Balanced APIs, queue and worker pool'}</title><desc id="traffic-${side}-description">${side === 'current' ? 'Many users reach a frontend that calls one API and database. One request runs while at most six connections wait.' : 'The same users and frontend demand reach a load balancer, three API replicas, a bounded durable queue, twelve concurrent workers, a database connection pool and the database.'} Moving dots represent requests; crosses represent rejected requests.</desc>${markup}</svg>`;
    const svg = placeholder.querySelector('svg');
    diagrams[side] = {svg, active: svg.querySelector('.traffic-active'),
      waiting: svg.querySelector('.traffic-waiting'), rejected: svg.querySelector('.traffic-rejected'),
      label: svg.querySelector('.traffic-queue-label'), fill: svg.querySelector('.traffic-service-fill')};
  }
  function start(side, request, now) {
    const occupied = new Set(side.active.map(item => item.slot));
    let slot = 0;
    while (occupied.has(slot)) slot++;
    side.active.push({...request, slot, start: now, finish: now + SERVICE_SECONDS});
  }
  function receive(side, id, now) {
    side.received++;
    const request = {id, arrived: now};
    if (side.active.length < side.slots) start(side, request, now);
    else if (side.waiting.length < side.maxWaiting) side.waiting.push(request);
    else {
      side.lost++;
      side.rejected.push({...request, rejected: now});
    }
  }
  function finish(side, now) {
    const done = side.active.filter(request => request.finish <= now + EPSILON);
    side.completed += done.length;
    side.active = side.active.filter(request => request.finish > now + EPSILON);
    while (side.waiting.length && side.active.length < side.slots) start(side, side.waiting.shift(), now);
  }
  function advance(seconds) {
    const duration = Number(seconds);
    if (!Number.isFinite(duration) || duration < 0 || duration > 3600) throw new RangeError('Advance needs 0–3600 seconds.');
    const target = engine.elapsed + duration;
    for (;;) {
      const perBurst = CYCLE_SECONDS * demand;
      const arrival = Math.floor((engine.nextRequest-1)/perBurst)*CYCLE_SECONDS +
        ((engine.nextRequest-1)%perBurst+1)/(demand*CYCLE_SECONDS/BURST_SECONDS);
      const completions = [...engine.current.active, ...engine.scaled.active].map(request => request.finish);
      const next = Math.min(arrival, ...completions);
      if (next > target + EPSILON) break;
      engine.elapsed = next;
      finish(engine.current, next);
      finish(engine.scaled, next);
      if (arrival <= next + EPSILON) {
        const id = engine.nextRequest++;
        receive(engine.current, id, next);
        receive(engine.scaled, id, next);
      }
    }
    engine.elapsed = target;
    for (const side of [engine.current, engine.scaled]) side.rejected = side.rejected.filter(request => target - request.rejected < .8);
    representative = false;
    paint();
    return snapshot();
  }
  function snapshot() {
    const summary = side => ({received: side.received, completed: side.completed, lost: side.lost,
      waiting: side.waiting.length, active: side.active.length, capacity: side.capacity,
      slots: side.slots, maxWaiting: side.maxWaiting});
    return {elapsed: engine.elapsed, demand, playbackRate: PLAYBACK_RATE,
      schedule: {cycleSeconds: CYCLE_SECONDS, burstSeconds: BURST_SECONDS, burstRate: demand*CYCLE_SECONDS/BURST_SECONDS},
      current: summary(engine.current), scaled: summary(engine.scaled)};
  }
  function position(points, fraction) {
    const lengths = points.slice(1).map((point, index) => Math.hypot(point[0]-points[index][0], point[1]-points[index][1]));
    let distance = Math.max(0, Math.min(1, fraction)) * lengths.reduce((sum, length) => sum + length, 0);
    for (let index = 0; index < lengths.length; index++) {
      if (distance <= lengths[index]) {
        const share = distance / lengths[index];
        return [points[index][0] + (points[index+1][0]-points[index][0])*share,
          points[index][1] + (points[index+1][1]-points[index][1])*share];
      }
      distance -= lengths[index];
    }
    return points.at(-1);
  }
  const dot = (x, y, extra = '') => `<circle class="traffic-request ${extra}" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="4"/>`;
  function paint() {
    for (const name of ['current', 'scaled']) {
      const side = engine[name], display = diagrams[name];
      const status = document.getElementById(`traffic-${name}-state`);
      if (status) status.textContent = !side.received ? 'Ready' : side.waiting.length === side.maxWaiting && side.lost
        ? 'Full: overflow rejected' : side.waiting.length ? name === 'scaled' ? 'Queue buffering burst' : 'Waiting callers'
          : side.active.length ? 'Processing requests' : 'Quiet between bursts';
      if (!display) continue;
      display.svg.classList.toggle('traffic-overloaded', demand > side.capacity && side.waiting.length === side.maxWaiting);
      display.active.innerHTML = side.active.map(request => {
        const phase = (engine.elapsed-request.start)/SERVICE_SECONDS;
        const lane = (request.id % 3 - 1) * 70;
        const offset = name === 'scaled' ? (request.slot % 4 - 1.5)*5 : 0;
        const resumed = request.start > request.arrived + EPSILON;
        const points = name === 'current'
          ? resumed ? [[350,166],[515,166]] : [[110,166],[310,166],[515,166]]
          : resumed ? [[305,166],[400,166],[495,166],[560,166]]
            : [[73,166],[162,166],[162,166+lane],[210,166+lane],[256,166+lane],[256,166],[305,166],[400,166],[495,166],[560,166]];
        const [x,y] = position(points, phase);
        return dot(x,y+offset);
      }).join('');
      display.waiting.innerHTML = side.waiting.map((_, index) => name === 'current'
        ? dot(194+(index%3)*13,242+Math.floor(index/3)*13,'traffic-pending')
        : dot(277+(index%9)*7,231+Math.floor(index/9)*9,'traffic-pending')).join('');
      display.label.textContent = name === 'current' ? 'Waiting callers' : 'Queued work';
      display.rejected.innerHTML = side.rejected.map(request => {
        const progress = (engine.elapsed-request.rejected)/.8;
        const lane = (request.id%3-1)*70;
        const points = name === 'current' ? [[110,166],[270,166]] : [[73,166],[162,166],[162,166+lane],[180,166+lane]];
        const [x,baseY] = position(points, progress/.65);
        const y = baseY+(name === 'current' ? (request.id%3-1)*9 : 0);
        return progress < .65 ? dot(x,y,'traffic-rejecting') : `<path class="traffic-rejection" d="M${x-4} ${y-4}l8 8m0-8-8 8"/>`;
      }).join('');
      if (display.fill) display.fill.setAttribute('width', String(side.active.length ? 56*(engine.elapsed-side.active[0].start)/SERVICE_SECONDS : 0));
    }
    root.dataset.trafficMode = representative ? 'static' : moving() ? 'playing' : 'paused';
    if (demandControl) demandControl.value = String(demand);
    const output = document.getElementById('traffic-demand-value');
    const intensity = demand <= 8 ? 'Light' : demand <= 24 ? 'Busy' : 'Heavy';
    if (output) output.textContent = intensity;
    demandControl?.setAttribute('aria-valuetext', `${intensity} traffic`);
  }
  function reset() {
    engine = makeEngine();
    representative = false;
    previousFrame = null;
    paint();
    return snapshot();
  }
  function setDemand(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new TypeError('Demand must be a number.');
    demand = Math.max(2, Math.min(40, Math.round(number)));
    return reset();
  }
  function staticPreview() {
    reset();
    advance(10);
    representative = true;
    paint();
  }
  window.ChangeExplanationTraffic = {reset, setDemand, advance, snapshot};
  demandControl?.addEventListener('input', () => {
    setDemand(demandControl.value);
    if (staticPreference()) staticPreview();
  });
  document.getElementById('traffic-restart')?.addEventListener('click', () => {
    reset();
    if (staticPreference()) staticPreview();
  });
  for (const control of document.querySelectorAll('[name="diagram-motion"]')) control.addEventListener('change', () => {
    previousFrame = null;
    if (document.getElementById('motion-play')?.checked && representative) reset();
    else if (staticPreference() && engine.elapsed === 0) staticPreview();
    paint();
  });
  reduced.addEventListener('change', () => {
    previousFrame = null;
    if (staticPreference() && engine.elapsed === 0) staticPreview();
    paint();
  });
  document.addEventListener('visibilitychange', () => {previousFrame = null;});
  if ('IntersectionObserver' in window) new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    previousFrame = null;
    paint();
  }, {threshold: .02}).observe(root);
  window.addEventListener('beforeprint', () => {
    printing = true;
    savedPrintEngine = {engine, representative};
    engine = makeEngine();
    advance(10);
    representative = true;
    paint();
  });
  window.addEventListener('afterprint', () => {
    if (savedPrintEngine) ({engine, representative} = savedPrintEngine);
    savedPrintEngine = null;
    printing = false;
    previousFrame = null;
    paint();
  });
  if (staticPreference()) staticPreview();
  else paint();
  function frame(timestamp) {
    if (moving()) {
      if (previousFrame !== null) advance((timestamp-previousFrame)/1000*PLAYBACK_RATE);
      previousFrame = timestamp;
    } else previousFrame = null;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
