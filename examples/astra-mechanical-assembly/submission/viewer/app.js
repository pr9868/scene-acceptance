import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const viewport=document.querySelector('#viewport');
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.15;viewport.appendChild(renderer.domElement);
const scene=new THREE.Scene();
const camera=new THREE.PerspectiveCamera(34,1,.002,20);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.minDistance=.22;controls.maxDistance=1.4;controls.maxPolarAngle=Math.PI*.92;
const views={overview:[.31,.38,.44],top:[0,.57,.0001],end:[.48,.15,.04]};
function setView(name){camera.position.set(...views[name]);controls.target.set(-.005,.045,0);controls.update();document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));}
setView('overview');
const pmrem=new THREE.PMREMGenerator(renderer);const room=new RoomEnvironment();const env=pmrem.fromScene(room,.04);scene.environment=env.texture;room.dispose();pmrem.dispose();
scene.add(new THREE.HemisphereLight(0xd3e4ff,0x182230,2));
function light(color,power,pos){const l=new THREE.DirectionalLight(color,power);l.position.set(...pos);scene.add(l);return l;}
const key=light(0xdeebff,3,[-.2,.5,.25]);key.castShadow=true;key.shadow.mapSize.set(2048,2048);Object.assign(key.shadow.camera,{left:-.3,right:.3,top:.3,bottom:-.3,near:.01,far:2});key.shadow.bias=-.0001;key.shadow.normalBias=.0003;
light(0xffc18c,2,[.2,.25,-.3]);
const ground=new THREE.Mesh(new THREE.PlaneGeometry(10,10),new THREE.ShadowMaterial({opacity:.3}));ground.rotation.x=-Math.PI/2;ground.position.y=-.0008;ground.receiveShadow=true;scene.add(ground);
const timeline=document.querySelector('#timeline'),play=document.querySelector('#play');
let mixer,clip,model,playing=true,time=35/60,last=performance.now(),frameCount=0;
function setPlaying(value){playing=value;play.textContent=value?'Ⅱ':'▶';play.setAttribute('aria-label',value?'Pause animation':'Play animation');document.querySelector('#status').textContent=value?'PLAYING':'PAUSED';}
function pose(t){time=THREE.MathUtils.clamp(t,0,4);if(mixer){mixer.setTime(time===4?4-1e-8:time);model.updateMatrixWorld(true);}timeline.value=time;document.querySelector('#time').textContent=time.toFixed(2);document.querySelector('#angle').textContent=(time*90).toFixed(1)+'°';const slider=model?.getObjectByName('Slider_Pin');if(slider){const p=slider.getWorldPosition(new THREE.Vector3());document.querySelector('#displacement').textContent=((p.x+.09)*1000).toFixed(1)+' mm';}}
play.addEventListener('click',()=>setPlaying(!playing));timeline.addEventListener('input',()=>{setPlaying(false);pose(Number(timeline.value));});
document.querySelector('#reset').addEventListener('click',()=>pose(0));
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
document.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','BUTTON','A'].includes(document.activeElement.tagName)){e.preventDefault();setPlaying(!playing);}});
new ResizeObserver(()=>{const w=viewport.clientWidth,h=viewport.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.fov=THREE.MathUtils.radToDeg(2*Math.atan(Math.tan(THREE.MathUtils.degToRad(34/2))*Math.max(1,1.25/camera.aspect)));camera.updateProjectionMatrix();}).observe(viewport);
try{
 const gltf=await new GLTFLoader().loadAsync('../output/crank_slider.glb');model=gltf.scene;scene.add(model);
 model.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}});
 if(gltf.animations.length!==1)throw Error(`Expected one animation, found ${gltf.animations.length}`);
 clip=gltf.animations[0];if(Math.abs(clip.duration-4)>.001)throw Error(`Expected 4-second clip, found ${clip.duration}`);
 mixer=new THREE.AnimationMixer(model);mixer.clipAction(clip).play();pose(time);document.querySelector('#loading').hidden=true;
 window.viewer={ready:true,model,scene,camera,controls,clip,setTime:t=>{setPlaying(false);pose(t);},setPlaying,setView,getState:()=>({time,playing,frameCount,duration:clip.duration,parts:model.children.length,pins:Object.fromEntries(['Crank_Center','Crank_Pin','Slider_Pin'].map(n=>{const o=model.getObjectByName(n);return [n,o?o.getWorldPosition(new THREE.Vector3()).toArray():null];}))})};
}catch(error){document.querySelector('#loading').textContent='Could not load assembly: '+error.message;console.error(error);window.viewer={ready:false,error:String(error)};}
renderer.setAnimationLoop(now=>{const dt=Math.min((now-last)/1000,.1);last=now;if(playing&&mixer)pose((time+dt)%4);controls.update();renderer.render(scene,camera);frameCount++;});
