import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root=path.resolve(import.meta.dirname,'..');
const site=path.join(root,'site');
const html=fs.readFileSync(path.join(site,'index.html'),'utf8');
const script=fs.readFileSync(path.join(site,'app.js'),'utf8');
const canonical='https://abraaobat.github.io/raspberrypi-st7789-dashboard/';

new vm.Script(script);
assert.equal((html.match(/<h1\b/g)||[]).length,1,'The page must have one primary heading');
assert.ok(html.includes(`rel="canonical" href="${canonical}"`),'Canonical URL is missing');
assert.ok(/<meta name="description" content="[^"]+"/.test(html),'Description is missing');
assert.ok(html.includes('data-copy-pix'),'PIX copy controls are missing');
assert.ok(html.includes('id="pixKey"'),'The visible PIX key is missing');

for(const [,reference] of html.matchAll(/(?:src|href)="(\.\/[^"?#]+)"/g)){
  assert.ok(fs.statSync(path.resolve(site,reference)).isFile(),`Missing local asset: ${reference}`);
}
const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]));
for(const [,fragment] of html.matchAll(/href="#([^"]+)"/g)){
  assert.ok(ids.has(fragment),`Missing section: ${fragment}`);
}
const structured=html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
assert.ok(structured,'Structured data is missing');
assert.equal(JSON.parse(structured[1]).url,canonical);
assert.ok(fs.readFileSync(path.join(site,'sitemap.xml'),'utf8').includes(`<loc>${canonical}</loc>`));
assert.ok(fs.readFileSync(path.join(site,'robots.txt'),'utf8').includes(`${canonical}sitemap.xml`));

function runLanguage(saved,browserLanguage){
  const select={value:'',addEventListener(){}};
  const key={textContent:'public-pix-key'};
  const year={textContent:''};
  const description={setAttribute(){}};
  const context={
    document:{
      documentElement:{lang:'en'},
      getElementById(id){return {languageSelect:select,pixKey:key,year}[id];},
      querySelector(){return description;},
      querySelectorAll(){return [];}
    },
    navigator:{language:browserLanguage},
    localStorage:{getItem(){return saved;},setItem(){}},
    setTimeout,
    Date
  };
  vm.runInNewContext(`${script}\nglobalThis.catalog=translations;`,context);
  return context;
}

assert.equal(runLanguage(null,'pt-BR').document.documentElement.lang,'pt-BR');
assert.equal(runLanguage(null,'en-US').document.documentElement.lang,'en');
assert.equal(runLanguage('en','pt-BR').document.documentElement.lang,'en','Saved English must override browser language');
assert.equal(runLanguage('pt-BR','en-US').document.documentElement.lang,'pt-BR');
const catalog=runLanguage(null,'en-US').catalog;
for(const [,key] of html.matchAll(/data-i18n="([^"]+)"/g)){
  for(const language of ['en','pt-BR'])assert.ok(catalog[language][key],`Missing ${language} translation: ${key}`);
}

console.log('Site validation: assets, metadata, sections, translations and language persistence OK.');
