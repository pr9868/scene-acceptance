const fs=require('node:fs');const path=require('node:path');const validator=require('../tools/gltf-validator');
const root=path.resolve(__dirname,'..');
validator.validateBytes(new Uint8Array(fs.readFileSync(path.join(root,'output/crank_slider.glb'))),{uri:'crank_slider.glb'}).then(report=>{
 fs.writeFileSync(path.join(root,'logs/gltf-validator.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({validator:validator.version(),issues:report.issues},null,2));
 if(report.issues.numErrors)process.exitCode=1;
});
