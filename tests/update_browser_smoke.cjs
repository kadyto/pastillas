const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
let browser,page;

(async()=>{
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||undefined,headless:true,args:['--no-sandbox']});
  page=await browser.newPage({viewport:{width:390,height:844},locale:'es-ES',timezoneId:'Europe/Madrid'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.TEST_BASE_URL||'http://127.0.0.1:8098');
  await page.getByLabel('Usuario',{exact:true}).fill('qa-version');
  await page.getByLabel('Contraseña').fill('pruebas-version-123');
  await page.getByRole('button',{name:'Crear mi cuenta'}).click();
  await page.getByRole('heading',{name:'Tu botiquín, al día',exact:true}).waitFor();
  const footer=page.locator('.app-footer');
  await footer.getByRole('link',{name:'GitHub',exact:true}).waitFor();
  assert.equal(await footer.getByRole('link',{name:'GitHub',exact:true}).getAttribute('href'),'https://github.com/kadyto/pastillas');
  const fixture=async(body)=>page.evaluate(async body=>{
    const response=await fetch('/api/test-updates',body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
    return response.json();
  },body);
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).click();
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).waitFor();
  assert.match(await footer.textContent(),/Disponible: 0\.4\.1/);
  const initial=(await fixture()).github_requests;
  await page.reload();
  await page.getByRole('heading',{name:'Tu botiquín, al día',exact:true}).waitFor();
  assert.equal((await fixture()).github_requests,initial);
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).click();
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).waitFor();
  assert.equal((await fixture()).github_requests,initial+2);

  await fixture({fail:true});
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).click();
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).waitFor();
  assert.match(await footer.textContent(),/No se pudo comprobar la versión/);
  assert.doesNotMatch(await footer.textContent(),/Tienes la última versión/);
  await fixture({fail:false,latest:'0.4.0'});
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).click();
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).waitFor();
  assert.match(await footer.textContent(),/Tienes la última versión/);
  await fixture({latest:'0.10.0'});
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).click();
  await footer.getByRole('button',{name:'Comprobar ahora',exact:true}).waitFor();
  assert.match(await footer.textContent(),/Disponible: 0\.10\.0/);
  await footer.getByRole('button',{name:'Actualizar con Dockhand',exact:true}).click();
  await page.locator('dialog').getByRole('button',{name:'Actualizar con Dockhand',exact:true}).click();
  await page.locator('dialog').waitFor({state:'hidden'});
  await footer.getByText('Actualización solicitada a Dockhand. Comprueba el despliegue antes de repetirla.',{exact:true}).waitFor();
  let delivered;
  for(let attempt=0;attempt<30;attempt++){
    delivered=(await fixture()).deploy_requests;
    if(delivered===1)break;
    await page.waitForTimeout(100);
  }
  assert.equal(delivered,1);
  const status=await page.evaluate(()=>fetch('/api/version').then(r=>r.json()));
  assert.equal(status.installed_version,'0.4.0');
  assert.ok(['running','requested'].includes(status.deploy_status));
  assert.ok(!JSON.stringify(status).includes('secreto-sintetico'));
  await page.reload();
  await footer.getByRole('button',{name:'Actualizar con Dockhand',exact:true}).waitFor();
  await footer.getByRole('button',{name:'Actualizar con Dockhand',exact:true}).click();
  assert.ok(await page.locator('dialog').getByRole('button',{name:'Actualizar con Dockhand',exact:true}).isDisabled());
  await page.getByRole('button',{name:'Cerrar diálogo'}).click();

  await fixture({unconfigured:true});
  await page.reload();
  await footer.getByRole('button',{name:'Cómo actualizar',exact:true}).waitFor();
  await footer.getByRole('button',{name:'Cómo actualizar',exact:true}).click();
  assert.equal(await page.locator('dialog').getByRole('link',{name:'Descargar código de GitHub',exact:true}).getAttribute('href'),'https://github.com/kadyto/pastillas/archive/refs/heads/main.tar.gz');
  await page.getByRole('button',{name:'Cerrar diálogo'}).click();
  const icon=await page.evaluate(async()=>{
    const response=await fetch('/icon-192.png?v=0.4.0');
    return {type:response.headers.get('Content-Type'),cache:response.headers.get('Cache-Control'),size:(await response.arrayBuffer()).byteLength};
  });
  assert.equal(icon.type,'image/png');assert.match(icon.cache,/immutable/);assert.ok(icon.size>1000&&icon.size<200000);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  fs.mkdirSync('test-results',{recursive:true});
  await footer.scrollIntoViewIfNeeded();
  await page.screenshot({path:'test-results/version-movil.png',fullPage:true});
  assert.deepEqual(errors,[]);
  await browser.close();
  console.log('Versiones OK: pie móvil, comprobación forzada, caché, error, última versión, webhook y descarga alternativa.');
})().catch(async error=>{
  console.error(error);
  if(page){fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/version-fallo.png',fullPage:true}).catch(()=>{});}
  await browser?.close().catch(()=>{});process.exit(1);
});
