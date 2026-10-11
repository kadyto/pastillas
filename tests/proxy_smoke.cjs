const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
let browser;

async function login(page, base, password='contrasena-proxy-123') {
  await page.goto(base);
  await page.locator('#login-form input[name=username]').fill('proxy-test');
  await page.locator('#login-form input[name=password]').fill(password);
  await page.locator('#login-form button[type=submit]').click();
}

(async () => {
  browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || undefined, headless: true, args:['--no-sandbox']});
  const http = process.env.PROXY_HTTP_URL || 'http://127.0.0.1:8096';
  const https = process.env.PROXY_HTTPS_URL || 'https://127.0.0.1:8444';
  const blockedUrl = process.env.PROXY_BLOCKED_URL || 'https://127.0.0.1:8445';
  for (const base of [http, https]) {
    const context = await browser.newContext({ignoreHTTPSErrors:true});
    // Una cookie de otra app del dominio, creada antes que la sesión propia.
    await context.addCookies([{name:'preferencias',value:'{"theme":"dark"}',url:base}]);
    const page = await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await login(page, base);
    await page.getByRole('heading',{name:'Tu botiquín, al día',exact:true}).waitFor();
    let session=await page.evaluate(()=>fetch('/api/session',{cache:'no-store'}).then(r=>r.json()));
    assert.equal(session.user.username,'proxy-test');
    let cookies=await context.cookies(base);
    const own=cookies.find(c=>c.name==='pastillas_session');
    assert.ok(own);
    assert.equal(own.secure,base.startsWith('https:'));
    assert.equal(own.httpOnly,true);
    assert.equal(own.sameSite,'Lax');
    await page.reload();
    await page.getByRole('heading',{name:'Tu botiquín, al día',exact:true}).waitFor();
    // Una cookie antigua con una ruta más específica puede coexistir con la nueva.
    await context.addCookies([{name:'pastillas_session',value:'a'.repeat(43),domain:'127.0.0.1',path:'/api',secure:base.startsWith('https:')}]);
    session=await page.evaluate(()=>fetch('/api/session',{cache:'no-store'}).then(r=>r.json()));
    assert.equal(session.user.username,'proxy-test');
    await page.reload();
    await page.getByRole('heading',{name:'Tu botiquín, al día',exact:true}).waitFor();
    await page.locator('nav').getByRole('link',{name:'Ajustes',exact:true}).click();
    await page.locator('main').getByRole('button',{name:'Cerrar sesión',exact:true}).click();
    await page.locator('#login-form').waitFor({state:'visible'});
    session=await page.evaluate(()=>fetch('/api/session',{cache:'no-store'}).then(r=>r.json()));
    assert.equal(session.user,null);
    await page.reload();
    await page.locator('#login-form').waitFor({state:'visible'});
    assert.deepEqual(errors,[]);
    await context.close();
  }
  const blocked=await browser.newContext({ignoreHTTPSErrors:true});
  const page=await blocked.newPage();
  await login(page,blockedUrl);
  await page.waitForFunction(()=>document.getElementById('login-error')?.textContent.includes('no conserva la sesión'));
  assert.equal(await page.locator('#login-form').isVisible(),true);
  await page.waitForTimeout(300);
  assert.ok((await page.locator('#login-error').textContent()).includes('La contraseña es correcta'));
  await blocked.close();
  const wrong=await browser.newContext({ignoreHTTPSErrors:true});
  const wrongPage=await wrong.newPage();
  await login(wrongPage,https,'contrasena-incorrecta-123');
  await wrongPage.waitForFunction(()=>document.getElementById('login-error')?.textContent.includes('Usuario o contraseña incorrectos'));
  await wrong.close();
  await browser.close();
  console.log('Proxy OK: HTTP, HTTPS, cookies de otras apps, recarga, logout y diagnóstico de sesión bloqueada.');
})().catch(async error=>{console.error(error);await browser?.close().catch(()=>{});process.exit(1);});
