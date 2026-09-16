import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

// Use an existing Playwright installation; do not modify the runtime or user browser.
const modulePath=process.env.ST7789_PLAYWRIGHT_PATH;
const {chromium}=await import(modulePath ? pathToFileURL(modulePath).href : 'playwright');
const url=process.argv[2] || 'http://127.0.0.1:8092/';
const screenshots=process.env.ST7789_SCREENSHOTS;
if(screenshots)fs.mkdirSync(screenshots,{recursive:true});
const browser=await chromium.launch({
  headless:true,
  ...(process.env.ST7789_BROWSER_CHANNEL ? {channel:process.env.ST7789_BROWSER_CHANNEL} : {})
});

try{
  for(const width of [1440,980,390,320]){
    for(const language of ['en','pt-BR']){
      const context=await browser.newContext({viewport:{width,height:1000},locale:language});
      const page=await context.newPage();
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
      page.on('response',response=>{if(response.status()>=400)errors.push(`${response.status()} ${response.url()}`);});
      await page.goto(url,{waitUntil:'networkidle'});
      assert.equal(await page.locator('h1').count(),1);
      assert.equal(await page.locator('html').getAttribute('lang'),language);
      // Load below-the-fold lazy images too, without needing manual scrolling.
      const images=await page.locator('img').evaluateAll(async elements=>{
        await Promise.all(elements.map(async img=>{img.loading='eager';await img.decode();}));
        return elements.map(img=>({
          src:img.getAttribute('src'),
          width:parseFloat(getComputedStyle(img).width),
          height:parseFloat(getComputedStyle(img).height),
          naturalWidth:img.naturalWidth,naturalHeight:img.naturalHeight
        }));
      });
      assert.equal(images.length,5);
      for(const img of images){
        assert.ok(img.width>0 && img.height>0 && img.naturalWidth>0,`Unloaded image: ${img.src}`);
        assert.ok(Math.abs(img.width/img.height-img.naturalWidth/img.naturalHeight)<0.01,
          `Distorted image at ${width}px: ${JSON.stringify(img)}`);
        assert.ok(img.width<=width,`Image overflows viewport: ${img.src}`);
      }
      const overflow=await page.evaluate(()=>({
        pageWidth:document.documentElement.scrollWidth,
        elements:[...document.querySelectorAll('body *')].map(element=>({
          tag:element.tagName,class:element.className,right:element.getBoundingClientRect().right
        })).filter(element=>element.right>innerWidth+1).slice(0,12)
      }));
      assert.ok(overflow.pageWidth<=width,`Horizontal overflow at ${width}px: ${JSON.stringify(overflow)}`);
      assert.equal(await page.locator('#pixKey').innerText(),'oabraaobatista@gmail.com');
      // Both language paths and anchor navigation must remain usable.
      await page.locator('#languageSelect').selectOption(language==='en' ? 'pt-BR' : 'en');
      await page.reload({waitUntil:'networkidle'});
      assert.equal(await page.locator('html').getAttribute('lang'),language==='en' ? 'pt-BR' : 'en');
      await page.locator('#languageSelect').selectOption(language);
      await page.locator('.cta-row a[href="#support"]').click();
      assert.equal(new URL(page.url()).hash,'#support');
      assert.deepEqual(errors,[],`Browser errors at ${width}px/${language}`);
      if(screenshots && language==='pt-BR' && [1440,390].includes(width)){
        await page.emulateMedia({reducedMotion:'reduce'});
        await page.evaluate(()=>document.activeElement?.blur());
        for(const [name,selector] of [['hero','.hero'],['panel','.control-section'],['hardware','.hardware-gallery'],['pix','.support-section']]){
          await page.locator(selector).screenshot({path:path.join(screenshots,`${width}-${name}.png`)});
        }
      }
      console.log(`PASS ${width}px/${language}: all 5 images proportional, QR square, language and navigation OK`);
      await context.close();
    }
  }
}finally{
  await browser.close();
}
