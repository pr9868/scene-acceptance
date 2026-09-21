import {chromium} from 'playwright';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const baseURL=process.env.VIEWER_URL || 'http://127.0.0.1:8765/';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const browser=await chromium.launch({...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{}),headless:true,args:['--no-first-run','--no-default-browser-check'],});
const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const page=await context.newPage();const errors=[],requests=[],failed=[];
page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
page.on('request',r=>requests.push(r.url()));page.on('requestfailed',r=>failed.push({url:r.url(),failure:r.failure()}));
const assert=(v,msg)=>{if(!v)throw Error(msg);};
try {
 await page.goto(new URL('viewer/',baseURL).href,{waitUntil:'networkidle'});
 await page.waitForFunction(()=>window.viewer?.ready,{timeout:30000});
 const loaded=await page.evaluate(()=>window.viewer.getState());assert(loaded.duration===4,'Four-second clip');
 await page.locator('#play').click();const paused=await page.evaluate(()=>window.viewer.getState());assert(!paused.playing,'Pause button');
 await page.waitForTimeout(180);assert((await page.evaluate(()=>window.viewer.getState())).time===paused.time,'Pause holds pose');
 const samples=[];
 for(let i=0;i<=480;i++){
  const t=i/120;const state=await page.evaluate(t=>{window.viewer.setTime(t);const state=window.viewer.getState();const rod=window.viewer.model.getObjectByName('Connecting_Rod_Pose');const pin=window.viewer.model.getObjectByName('Crank_Pin');const point=pin.position.clone();point.set(0,0,0);state.rodStart=rod.localToWorld(point.clone()).toArray();point.set(.11,0,0);state.rodEnd=rod.localToWorld(point).toArray();return state;},t);samples.push(state);
 }
 const dist=(a,b)=>Math.hypot(...a.map((x,i)=>x-b[i]));
 const max={radius:0,rod:0,guide:0,analyticSlider:0,rodStartPin:0,rodEndPin:0};
 for(const state of samples){const p=state.pins,c=p.Crank_Center,q=p.Crank_Pin,r=p.Slider_Pin;assert(c&&q&&r,'Named GLB reference nodes');
  max.radius=Math.max(max.radius,Math.abs(dist(c,q)-.035));max.rod=Math.max(max.rod,Math.abs(dist(q,r)-.110));max.guide=Math.max(max.guide,Math.abs(r[2]),Math.abs(r[1]-.102));max.rodStartPin=Math.max(max.rodStartPin,dist(state.rodStart,q));max.rodEndPin=Math.max(max.rodEndPin,dist(state.rodEnd,r));
  const theta=state.time*Math.PI/2,expected=-.09+.035*Math.cos(theta)+Math.sqrt(.11**2-(.035*Math.sin(theta))**2);max.analyticSlider=Math.max(max.analyticSlider,Math.abs(r[0]-expected));
 }assert(Math.max(...Object.values(max))<.000015,'Exported GLB kinematics within 15 µm');
 await page.locator('#timeline').fill('2.75');await page.locator('#timeline').dispatchEvent('input');assert(Math.abs((await page.evaluate(()=>window.viewer.getState())).time-2.75)<1e-7,'Timeline input');
 await page.locator('#timeline').focus();await page.keyboard.press('ArrowRight');assert((await page.evaluate(()=>window.viewer.getState())).time>2.75,'Keyboard scrubbing');
 await page.evaluate(()=>window.viewer.setTime(3.94));await page.locator('#play').click();await page.waitForTimeout(300);const looped=await page.evaluate(()=>window.viewer.getState());assert(looped.time<.6&&looped.playing,'Playback loops');
 await page.locator('#play').click();await page.locator('#reset').click();assert((await page.evaluate(()=>window.viewer.getState())).time===0,'Restart resets time');
 await page.evaluate(()=>{window.viewer.setTime(35/60);window.viewer.setView('overview');});await page.waitForTimeout(200);
 const before=await page.evaluate(()=>window.viewer.camera.position.toArray());const bounds=await page.locator('#viewport').boundingBox();
 await page.mouse.move(bounds.x+bounds.width*.5,bounds.y+bounds.height*.55);await page.mouse.down();await page.mouse.move(bounds.x+bounds.width*.5+90,bounds.y+bounds.height*.55+20,{steps:12});await page.mouse.up();await page.waitForTimeout(250);
 const after=await page.evaluate(()=>window.viewer.camera.position.toArray());assert(dist(before,after)>.01,'Orbit drag changes camera');
 const zoomBefore=await page.evaluate(()=>window.viewer.camera.position.distanceTo(window.viewer.controls.target));await page.mouse.wheel(0,180);await page.waitForTimeout(250);const zoomAfter=await page.evaluate(()=>window.viewer.camera.position.distanceTo(window.viewer.controls.target));assert(Math.abs(zoomAfter-zoomBefore)>.01,'Wheel zoom');
 await page.locator('[data-view="overview"]').click();await page.waitForTimeout(300);await page.screenshot({path:path.join(root,'output/viewer-overview.png')});
 await page.locator('[data-view="top"]').click();await page.waitForTimeout(300);await page.screenshot({path:path.join(root,'logs/viewer-top.png')});
 await page.locator('[data-view="end"]').click();await page.waitForTimeout(300);await page.screenshot({path:path.join(root,'logs/viewer-end.png')});
 await page.setViewportSize({width:390,height:844});await page.locator('[data-view="overview"]').click();await page.waitForTimeout(300);await page.screenshot({path:path.join(root,'logs/viewer-mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile no horizontal overflow');
 assert(!failed.length,'No failed requests');assert(!requests.some(u=>!u.startsWith(baseURL)&&!u.startsWith('data:')),'Local-only requests');
 // A missing favicon is recorded separately; all application assets must load.
 const substantiveErrors=errors.filter(e=>!e.includes('404'));assert(!substantiveErrors.length,'No JS/WebGL errors: '+substantiveErrors.join('; '));
 const report={status:'PASS',browser:browser.version(),playwright:require('playwright/package.json').version,three:'0.180.0',animationDuration:loaded.duration,sampledPoses:samples.length,maximumErrorsMetres:max,checks:['GLB loaded','named reference nodes','radius and rod distance','linear guide','analytic slider position','play/pause','pause holds pose','timeline input','keyboard scrubbing','loop playback','restart','orbit drag','wheel zoom','three camera presets','desktop screenshot','mobile no horizontal overflow','local-only network'],consoleErrors:errors,failedRequests:failed,requestURLs:[...new Set(requests)]};
 fs.writeFileSync(path.join(root,'logs/browser-validation.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
} catch(e){await page.screenshot({path:path.join(root,'logs/browser-failure.png'),fullPage:true});console.error(e);console.error({errors,failed});process.exitCode=1;}finally{await browser.close();}
