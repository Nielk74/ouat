// Deterministic checks for the explorer's teaching model, independent of frame rate.
export async function checkTraffic(evaluate) {
  if (!await evaluate('!!window.ChangeExplanationTraffic')) return null;
  const result = await evaluate(`(() => {
    const model = window.ChangeExplanationTraffic, failures = [], samples = [];
    document.getElementById('motion-pause').click();
    const assertStates = snapshot => {
      for (const side of ['current','scaled']) {
        const state = snapshot[side];
        if (state.received !== state.completed+state.lost+state.waiting+state.active) failures.push('Conservation failed: '+side);
        if (state.active > state.slots || state.waiting > state.maxWaiting) failures.push('Capacity exceeded: '+side);
      }
      if (snapshot.current.received !== snapshot.scaled.received) failures.push('Arrivals differ between architectures.');
    };
    model.setDemand(18); model.reset(); model.advance(1.9);
    const burst = model.snapshot(); assertStates(burst); samples.push({name:'default burst',...burst});
    if (burst.current.lost === 0 || burst.scaled.lost !== 0 || burst.scaled.waiting === 0) failures.push('Burst does not show rejection versus bounded buffering.');
    model.advance(6.1);
    const drained = model.snapshot(); assertStates(drained); samples.push({name:'default drained',...drained});
    if (drained.scaled.waiting || drained.scaled.active || drained.scaled.lost || drained.scaled.completed !== drained.scaled.received) failures.push('Default burst does not finish during quiet time.');
    model.reset(); for (let i=0;i<80;i++) model.advance(.1);
    const sliced = model.snapshot(); assertStates(sliced);
    for (const side of ['current','scaled']) for (const key of ['received','completed','lost','waiting','active']) {
      if (sliced[side][key] !== drained[side][key]) failures.push('Frame-size changes outcome: '+side+'.'+key);
    }
    model.setDemand(40); model.reset(); model.advance(8);
    const overloaded = model.snapshot(); assertStates(overloaded); samples.push({name:'solution overload',...overloaded});
    if (!overloaded.scaled.lost || overloaded.scaled.completed <= overloaded.current.completed) failures.push('Scaled setup does not expose its finite capacity.');
    model.setDemand(2); model.reset(); model.advance(8);
    const light = model.snapshot(); assertStates(light); samples.push({name:'light load',...light});
    if (light.current.lost || light.scaled.lost) failures.push('Low load is rejected unnecessarily.');
    model.setDemand(18); model.reset(); model.advance(1.9);
    let labels = 0;
    for (const graphic of document.querySelectorAll('.traffic-diagram')) {
      for (const node of graphic.querySelectorAll('.traffic-node')) {
        const box = node.querySelector('rect').getBBox();
        for (const text of node.querySelectorAll('text')) {
          const bounds = text.getBBox(); labels++;
          if (bounds.x<box.x+1 || bounds.x+bounds.width>box.x+box.width-1 || bounds.y<box.y || bounds.y+bounds.height>box.y+box.height) failures.push('Traffic node label overflows: '+text.textContent);
        }
      }
    }
    return {samples, failures, burstSchedule:burst.schedule, labels};
  })()`);
  if (result.failures.length) throw new Error('Traffic model failed: '+result.failures.join('; '));
  const frozen = await evaluate('JSON.stringify(window.ChangeExplanationTraffic.snapshot())');
  await new Promise(done=>setTimeout(done,160));
  if (frozen !== await evaluate('JSON.stringify(window.ChangeExplanationTraffic.snapshot())')) throw new Error('Pause does not freeze traffic.');
  await evaluate(`document.getElementById('traffic-model').scrollIntoView({block:'center'})`);
  await new Promise(done=>setTimeout(done,80));
  await evaluate(`document.getElementById('motion-play').click()`);
  const beforePlay = await evaluate('window.ChangeExplanationTraffic.snapshot().elapsed');
  await new Promise(done=>setTimeout(done,200));
  const afterPlay = await evaluate('window.ChangeExplanationTraffic.snapshot().elapsed');
  if (afterPlay <= beforePlay) throw new Error('Play does not advance visible traffic.');
  if (afterPlay-beforePlay > .09) throw new Error('Teaching playback is too fast; 200 ms should advance about 50 ms of model time.');
  await evaluate(`document.getElementById('motion-pause').click()`);
  const paused = await evaluate('JSON.stringify(window.ChangeExplanationTraffic.snapshot())');
  await new Promise(done=>setTimeout(done,160));
  if (paused !== await evaluate('JSON.stringify(window.ChangeExplanationTraffic.snapshot())')) throw new Error('Pause does not freeze visible traffic.');
  await evaluate(`document.getElementById('motion-system').click()`);
  await evaluate('window.scrollTo(0,0)');
  return {...result, playback:{beforePlay,afterPlay,paused:true}};
}
