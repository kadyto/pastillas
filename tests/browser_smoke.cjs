// QA opcional: PLAYWRIGHT_MODULE apunta a playwright o playwright-core instalado fuera del proyecto.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
let activePage, activeBrowser;

(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROMIUM_PATH || undefined, headless:true, args:['--no-sandbox']});
  activeBrowser=browser;
  const context = await browser.newContext({viewport:{width:1440,height:1050},locale:'es-ES',timezoneId:'Europe/Madrid'});
  const page = await context.newPage();
  activePage=page;
  const saved = async () => {
    await page.locator('dialog').waitFor({state:'hidden'});
    await page.waitForFunction(() => document.getElementById('toast').classList.contains('visible') && document.getElementById('toast').textContent === 'Guardado');
  };
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const base=process.env.TEST_BASE_URL||'http://127.0.0.1:8000';
  await page.goto(base);
  await page.getByRole('heading',{name:'Empezamos contigo'}).waitFor();
  await page.getByLabel('Usuario',{exact:true}).fill('qa-admin');
  await page.getByLabel('Contraseña').fill('solo-para-pruebas-123');
  await page.getByRole('button',{name:'Crear mi cuenta'}).click();
  await page.getByRole('heading',{name:'Tu botiquín, al día',exact:true}).waitFor();

  await page.locator('nav').getByRole('link',{name:'Recetas',exact:true}).click();
  await page.getByRole('button',{name:'Añadir receta',exact:true}).click();
  await page.getByLabel('Nombre o título').fill('Tratamiento habitual');
  await page.getByLabel('Profesional').fill('Mi profesional sanitario');
  await page.getByLabel('Referencia').fill('Receta de prueba');
  const tomorrow = new Date(Date.now()+86400000).toISOString().slice(0,10);
  await page.getByLabel('Fecha de renovación').fill(tomorrow);
  await page.getByLabel('Indicaciones y notas').fill('Revisar en la próxima consulta.');
  await page.getByRole('button',{name:'Guardar',exact:true}).click();
  await saved();

  await page.locator('nav').getByRole('link',{name:'Medicamentos',exact:true}).click();
  await page.getByRole('button',{name:'Añadir medicamento',exact:true}).first().click();
  await page.getByLabel('Nombre del medicamento').fill('Medicación habitual');
  await page.getByLabel('Marca').fill('Mi marca');
  await page.getByLabel('Concentración o dosis del envase').fill('Según mi receta');
  await page.getByLabel('Cantidad por toma').fill('0.5');
  await page.getByLabel('Existencias que tienes ahora').fill('20');
  await page.getByLabel('Intervalo en horas').fill('8');
  await page.getByLabel('Indicaciones',{exact:true}).fill('Seguir las indicaciones de mi receta.');
  await page.getByLabel('Receta vinculada').selectOption({label:'Tratamiento habitual'});
  await page.locator('dialog').getByRole('button',{name:'Añadir medicamento',exact:true}).click();
  await saved();
  assert.equal(await page.locator('.med-card').count(),1);

  // Programa una toma a segundos de distancia para verificar el descuento real
  // sin depender de la hora del runner ni obligar a confirmar en la interfaz.
  let data=await page.evaluate(()=>fetch('/api/dashboard').then(r=>r.json()));
  const beforeAuto=data.medications[0].stock;
  const scheduled=await page.evaluate(async()=>{
    const d=await fetch('/api/dashboard').then(r=>r.json()),m=d.medications[0];
    const at=Math.floor(Date.now()/1000)+3;
    const body={name:m.name,brand:m.brand,form:m.form,strength:m.strength,unit:m.unit,dose:m.dose,
      schedule:'interval',interval_hours:8,start_at:new Date(at*1000).toISOString(),timezone:m.timezone,
      active:true,reminders:true,warning_days:m.warning_days,prescription_id:m.prescription_id,instructions:m.instructions};
    const response=await fetch(`/api/medications/${m.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!response.ok)throw new Error(await response.text());return at;
  });
  await page.waitForFunction(async at=>{
    const d=await fetch('/api/dashboard').then(r=>r.json());return d.agenda.some(t=>t.scheduled_at===at&&t.automatic);
  },scheduled);
  await page.reload();
  await page.locator('nav').getByRole('link',{name:'Hoy',exact:true}).click();
  await page.locator('.dose-row.taken').first().waitFor();
  data = await page.evaluate(()=>fetch('/api/dashboard').then(r=>r.json()));
  assert.equal(data.medications[0].stock,beforeAuto-0.5);
  const currentRow=page.locator('.dose-row.taken').filter({has:page.locator(`[data-at="${scheduled}"]`)});
  await currentRow.getByRole('button',{name:'No la tomé',exact:true}).click();
  await page.locator('dialog').getByRole('button',{name:'Confirmar'}).click();
  await saved();
  await page.locator('.dose-row.skipped').waitFor();
  data = await page.evaluate(()=>fetch('/api/dashboard').then(r=>r.json()));
  assert.equal(data.medications[0].stock,beforeAuto);
  await page.reload();
  await page.getByRole('heading',{name:'Tu botiquín, al día',exact:true}).waitFor();
  data = await page.evaluate(()=>fetch('/api/dashboard').then(r=>r.json()));
  assert.equal(data.medications[0].stock,beforeAuto);

  await page.locator('nav').getByRole('link',{name:'Existencias',exact:true}).click();
  await page.getByRole('button',{name:'Registrar compra',exact:true}).click();
  await page.locator('input[name=amount]').fill('30');
  await page.getByLabel('Precio total').fill('4.99');
  await page.getByRole('button',{name:'Guardar existencias'}).click();
  await saved();
  data = await page.evaluate(()=>fetch('/api/dashboard').then(r=>r.json()));
  assert.equal(data.medications[0].stock,beforeAuto+30);
  await page.getByRole('button',{name:'Registrar compra',exact:true}).click();
  await page.getByLabel('Tipo de movimiento').selectOption('adjustment');
  await page.locator('input[name=amount]').fill('5');
  await page.getByRole('button',{name:'Guardar existencias'}).click();
  await saved();
  await page.locator('.inventory-row.warn').waitFor();
  await page.getByRole('button',{name:'Comprobar stock',exact:true}).click();
  await page.getByLabel('Cantidad que has contado').fill('6');
  await page.getByText('Diferencia: +1 pastillas.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Guardar existencias'}).click();
  await saved();
  data = await page.evaluate(()=>fetch('/api/dashboard').then(r=>r.json()));
  assert.equal(data.medications[0].stock,6);
  assert.ok(data.medications[0].stock_verified_at);
  const verified=await page.evaluate(()=>fetch('/api/export').then(r=>r.json()));
  assert.ok(verified.stock_movements.some(m=>m.kind==='verification'&&m.amount===1000));


  await page.locator('nav').getByRole('link',{name:'Medicamentos',exact:true}).click();
  await page.getByRole('button',{name:'Editar',exact:true}).click();
  await page.getByLabel('Tipo de pauta').selectOption('daily');
  await page.getByLabel('Horas fijas del día').fill('08:00, 20:00');
  await page.getByRole('button',{name:'Guardar cambios'}).click();
  await saved();
  assert.ok((await page.locator('.med-card').textContent()).includes('08:00 · 20:00'));

  await page.getByRole('button',{name:'Añadir medicamento',exact:true}).first().click();
  await page.getByLabel('Nombre del medicamento').fill('Jarabe de mi tratamiento');
  await page.getByLabel('Presentación').fill('Jarabe');
  await page.getByLabel('Unidad de existencias').fill('ml');
  await page.getByLabel('Cantidad por toma').fill('5');
  await page.getByLabel('Existencias que tienes ahora').fill('100');
  await page.getByLabel('Tipo de pauta').selectOption('as_needed');
  await page.locator('dialog').getByRole('button',{name:'Añadir medicamento',exact:true}).click();
  await saved();
  await page.locator('nav').getByRole('link',{name:'Hoy',exact:true}).click();
  await page.getByRole('button',{name:'Registrar toma',exact:true}).click();
  await page.locator('dialog').getByRole('button',{name:'Confirmar'}).click();
  await saved();
  data = await page.evaluate(()=>fetch('/api/dashboard').then(r=>r.json()));
  assert.equal(data.medications.find(m=>m.unit==='ml').stock,95);

  await page.locator('nav').getByRole('link',{name:'Medicamentos',exact:true}).click();
  await page.getByRole('button',{name:'Historial',exact:true}).first().click();
  await page.getByRole('heading',{name:'Movimientos de existencias'}).waitFor();
  await page.getByRole('button',{name:'Cerrar diálogo'}).click();
  await page.getByLabel('Buscar medicamentos').fill('Jarabe');
  assert.equal(await page.locator('.med-card').count(),1);
  await page.getByLabel('Buscar medicamentos').fill('');
  await page.locator('nav').getByRole('link',{name:'Ajustes',exact:true}).click();
  await page.getByRole('button',{name:'Guardar ajustes'}).click();
  await page.getByRole('heading',{name:'Avisos y horarios'}).waitFor();
  await page.getByRole('button',{name:'Crear usuario'}).click();
  await page.locator('dialog input[name=username]').fill('qa-otro');
  await page.locator('dialog input[name=password]').fill('otra-cuenta-prueba-123');
  await page.locator('dialog').getByRole('button',{name:'Crear usuario',exact:true}).click();
  await saved();
  const exportResult=await page.evaluate(()=>fetch('/api/export').then(r=>r.json()));
  assert.equal(exportResult.medications.length,2);
  assert.equal(exportResult.prescriptions.length,1);
  assert.ok(exportResult.doses.length>=2);
  assert.ok(exportResult.doses.some(d=>d.status==='skipped'));

  const folder=process.env.SCREENSHOT_DIR||'test-results';fs.mkdirSync(folder,{recursive:true});
  await page.locator('nav').getByRole('link',{name:'Hoy',exact:true}).click();
  await page.screenshot({path:`${folder}/escritorio.png`,fullPage:true});
  const colours=await page.evaluate(()=>({bg:getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(),primary:getComputedStyle(document.documentElement).getPropertyValue('--primary').trim()}));
  assert.equal(colours.bg,'#ffffff');assert.equal(colours.primary,'#00852e');
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:`${folder}/movil.png`,fullPage:true});
  for(const [hash,heading] of [['medications','Tus medicamentos'],['stock','Existencias sin sorpresas'],['prescriptions','Tus recetas, a mano'],['settings','A tu manera']]){
    await page.locator('nav').getByRole('link',{name:({medications:'Medicamentos',stock:'Existencias',prescriptions:'Recetas',settings:'Ajustes'})[hash],exact:true}).click();
    await page.getByRole('heading',{name:heading,exact:true}).waitFor();
    const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,offenders:[...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent.slice(0,80)}))}));
    assert.ok(layout.scroll<=layout.width+1,`${hash}: desbordamiento móvil ${JSON.stringify(layout)}`);
  }
  await page.getByRole('button',{name:'Cambiar a tema oscuro'}).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
  await page.locator('nav').getByRole('link',{name:'Hoy',exact:true}).click();
  await page.screenshot({path:`${folder}/movil-oscuro.png`,fullPage:true});

  await page.locator('nav').getByRole('link',{name:'Ajustes',exact:true}).click();
  await page.getByRole('button',{name:'Cerrar sesión',exact:true}).click();
  await page.locator('#login-form').waitFor({state:'visible'});
  await page.locator('#login-form input[name=username]').fill('qa-otro');
  await page.locator('#login-form input[name=password]').fill('otra-cuenta-prueba-123');
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await page.getByRole('heading',{name:'Tu botiquín, al día',exact:true}).waitFor();
  data=await page.evaluate(()=>fetch('/api/dashboard').then(r=>r.json()));
  assert.equal(data.medications.length,0);
  assert.equal(data.prescriptions.length,0);
  assert.deepEqual(errors,[]);
  await browser.close();
  console.log('Navegador OK: recetas, pautas, tomas, compras, correcciones, historial, exportación, móvil, tema e aislamiento de usuarios.');
})().catch(async error=>{
  console.error(error);
  if(activePage){
    console.error(await activePage.evaluate(async()=>({heading:document.querySelector('main h1')?.textContent,
      toast:document.getElementById('toast')?.textContent,login:!!document.getElementById('login-form'),
      dialog:document.querySelector('dialog')?.open,rows:[...document.querySelectorAll('.dose-row')].map(e=>({cls:e.className,text:e.textContent.slice(0,240)})),
      day:document.getElementById('agenda-day')?.value,body:document.querySelector('main')?.textContent.slice(0,2400),
      dashboard:await fetch('/api/dashboard').then(r=>r.json())})).catch(()=>({})));
    fs.mkdirSync('test-results',{recursive:true});
    await activePage.screenshot({path:'test-results/fallo.png',fullPage:true}).catch(()=>{});
  }
  await activeBrowser?.close().catch(()=>{});
  process.exit(1);
});
