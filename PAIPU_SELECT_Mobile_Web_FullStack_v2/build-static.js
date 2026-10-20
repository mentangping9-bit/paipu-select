const fs=require('node:fs'),path=require('node:path');
const root=__dirname,out=path.join(root,'static-dist');
fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(out,{recursive:true});
const backend='https://paipu-select.onrender.com';
const build=(process.env.RENDER_GIT_COMMIT||'local').slice(0,12);
for(const name of ['index.html','styles.css','i18n.js','converter.js','link-utils.js','backend.js','app.js']){
 let text=fs.readFileSync(path.join(root,'public',name),'utf8');
 if(name==='index.html'){
  text=text.replace('<head>','<head>\n<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\'; style-src \'self\'; connect-src \'self\' '+backend+'; img-src \'self\'; base-uri \'none\'; object-src \'none\'; form-action \'self\'">');
  text=text.replace('<script src="./i18n.js">','<script src="./backend-config.js"></script><script src="./i18n.js">');
  text=text.replaceAll('href="?setup=1"','href="'+backend+'/?setup=1"');
  text=text.replace(/(src|href)="\.\/([^"?]+\.(?:js|css))"/g,(_,attr,file)=>attr+'="./'+file+'?v='+build+'"');
 }
 fs.writeFileSync(path.join(out,name),text);
}
fs.writeFileSync(path.join(out,'backend-config.js'),'globalThis.PaipuBackendOrigin='+JSON.stringify(backend)+';\nif(new URL(location.href).searchParams.get("setup")==="1")location.replace('+JSON.stringify(backend+'/?setup=1')+');\n');
console.log('Static frontend built:',build);
