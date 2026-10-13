const $ = (selector, root = document) => root.querySelector(selector);
const app = $('#app'), dialog = $('#dialog');
const paths = {
  github: '<path d="M9 19c-4 1-4-2-6-2m12 5v-3.9c0-1 .1-1.8-.5-2.3 3.3-.4 6.8-1.6 6.8-7.2a5.6 5.6 0 0 0-1.5-3.8c.2-.4.7-1.8-.2-3.7 0 0-1.2-.4-4 1.4a13.6 13.6 0 0 0-7.2 0C5.6.7 4.4 1.1 4.4 1.1c-.9 1.9-.4 3.3-.2 3.7a5.6 5.6 0 0 0-1.5 3.8c0 5.6 3.5 6.8 6.8 7.2-.5.4-.7 1.1-.7 2.2V22"/>',
  pill: '<path d="m10.5 20.5 10-10a6.4 6.4 0 0 0-9-9l-10 10a6.4 6.4 0 0 0 9 9Z"/><path d="m8.5 8.5 7 7"/>',
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M9 21v-8h6v8"/>',
  box: '<path d="m3 7 9-4 9 4v10l-9 4-9-4Z"/><path d="m3 7 9 5 9-5M12 12v9M7.5 5l9 5"/>',
  rx: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6M9 15h3"/>',
  settings: '<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/><path d="m9 3-1 3-3 1-2 3 2 2-1 3 2 3 3-1 2 3h3l1-3 3-1 2-3-2-2 1-3-2-3-3 1-2-3Z"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="m6 6 12 12M6 18 18 6"/>',
  arrow: '<path d="m9 5 7 7-7 7"/>',
  left: '<path d="m15 5-7 7 7 7"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
  moon: '<path d="M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z"/>',
  edit: '<path d="m15 4 5 5M4 20l4-1L21 6a2 2 0 0 0-3-3L5 16Z"/>',
  undo: '<path d="M3 10h11a6 6 0 0 1 0 12M3 10l5-5M3 10l5 5"/>',
  drop: '<path d="M12 3s7 8 7 12a7 7 0 0 1-14 0c0-4 7-12 7-12Z"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 11h18M8 15h2M14 15h2"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  logout: '<path d="M9 3H3v18h6M9 12h12m-5-5 5 5-5 5"/>',
};
const icon = (name, size = 20) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.pill}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number = value => new Intl.NumberFormat('es-ES', {maximumFractionDigits: 3}).format(value ?? 0);
const state = {user: null, data: null, alerts: [], agenda: [], day: '', filter: 'all', medFilter: 'active', stockFilter: 'all', search: '', setup: false, version: '', ntfy: '', busy: false, updates: null, checkingVersion: false};
let requestVersion = 0, toastTimer, notificationIds = new Set();
let theme;
try { theme = localStorage.getItem('pastillas-theme') || 'light'; } catch { theme = 'light'; }
document.documentElement.dataset.theme = theme;
const nav = [ ['today','Hoy','home'], ['medications','Medicamentos','pill'], ['stock','Existencias','box'], ['prescriptions','Recetas','rx'], ['settings','Ajustes','settings'] ];
const route = () => location.hash.slice(1) || 'today';
const medById = id => state.data?.medications.find(m => m.id === Number(id));
const tz = () => state.user?.timezone || 'Europe/Madrid';
const dateFmt = (at, options = {}) => new Intl.DateTimeFormat('es-ES', {timeZone: tz(), ...options}).format(new Date(at * 1000));
const clock = at => dateFmt(at, {hour:'2-digit', minute:'2-digit'});
const fullDate = at => dateFmt(at, {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'});
function inputDate(at, timeZone = tz()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {timeZone, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hourCycle:'h23'}).formatToParts(new Date(at * 1000)).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}
const dateText = day => new Intl.DateTimeFormat('es-ES', {day:'numeric', month:'long', year:'numeric', timeZone:'UTC'}).format(new Date(`${day}T12:00:00Z`));
const formIcon = med => /jarabe|gota|líquid|liquid|soluci|inyec/i.test(med.form) ? 'drop' : 'pill';
const button = (action, label, name = '', extra = '', cls = '') => `<button class="button ${cls}" data-action="${action}" ${extra}>${name ? icon(name,17) : ''}${label}</button>`;
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $('#toast').textContent = message;
  $('#toast').className = `visible${error ? ' error' : ''}`;
  toastTimer = setTimeout(() => $('#toast').className = '', 6000);
}
async function api(path, method = 'GET', body) {
  const response = await fetch(`/api${path}`, {method, credentials:'same-origin', cache:'no-store', headers: method === 'GET' ? {} : {'Content-Type':'application/json'}, body: method === 'GET' ? undefined : JSON.stringify(body || {})});
  let data;
  try { data = await response.json(); } catch { throw new Error('El servidor no responde correctamente. Revisa la conexión.'); }
  if (!response.ok) {
    if (response.status === 401 && !['/login','/setup'].includes(path)) { const wasLoggedIn=!!state.user; state.user = null; state.data = null; state.alerts = []; if (dialog.open) dialog.close(); if(wasLoggedIn)renderLogin('La sesión no se ha podido mantener. Si acabas de entrar, revisa las cookies del navegador y la configuración del proxy.'); }
    throw new Error(data.error || 'No se pudo completar la operación.');
  }
  return data;
}
const empty = (title, message, action = '', label = '') => `<div class="empty"><div class="empty-icon">${icon('pill',30)}</div><h2>${title}</h2><p>${message}</p>${action ? button(action,label,'plus','','primary') : ''}</div>`;
function renderLogin(message = '') {
  app.innerHTML = `<main class="login-shell" id="content"><div class="login-card"><a class="brand" href="/"> <img src="/icon-192.png?v=0.4.0" alt=""><div>Pastillas<small>Tu botiquín, al día</small></div></a><h1>${state.setup ? 'Empezamos contigo' : 'Bienvenido a tu botiquín'}</h1><p>${state.setup ? 'Crea tu cuenta administradora para organizar medicamentos, tomas y existencias.' : 'Todo lo que necesitas para seguir tu tratamiento, en un solo lugar.'}</p><div class="error-box" id="login-error" role="alert"></div><form id="login-form"><label>Usuario<input name="username" autocomplete="username" required minlength="3" maxlength="60"></label><label>Contraseña<input type="password" name="password" autocomplete="${state.setup ? 'new-password' : 'current-password'}" required minlength="12" maxlength="256"><small>Al menos 12 caracteres.</small></label><button class="button primary" type="submit">${state.setup ? 'Crear mi cuenta' : 'Entrar'}${icon('arrow',17)}</button></form><p class="help">Tus datos se guardan en tu servidor.<br><a href="https://github.com/kadyto/pastillas" target="_blank" rel="noopener noreferrer">GitHub · Pastillas ${esc(state.version)}</a></p></div></main>`;
  $('#login-error').textContent = message;
  $('#login-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget, submit = $('button', form);
    submit.disabled = true; $('#login-error').textContent = '';
    try {
      state.user = await api(state.setup ? '/setup' : '/login', 'POST', Object.fromEntries(new FormData(form)));
      state.setup = false;
      const session = await api('/session');
      if(!session.user){state.user=null;const message='La contraseña es correcta, pero el navegador no conserva la sesión. Revisa las cookies y que el proxy transmita Cookie y Set-Cookie.';renderLogin(message);throw new Error(message);}
      state.setup = false; state.day = ''; state.search = ''; state.data = null; notificationIds = new Set(); location.hash = 'today';
      await refresh();
    } catch (error) { $('#login-error')?.replaceChildren(document.createTextNode(error.message)); submit.disabled = false; }
  });
}
function shell(content) {
  const page = nav.find(n => n[0] === route());
  app.innerHTML = `<aside class="sidebar"><a class="brand" href="#today"><img src="/icon-192.png?v=0.4.0" alt=""><div>Pastillas<small>Tu botiquín, al día</small></div></a><nav aria-label="Navegación principal">${nav.map(([key,title,ic]) => `<a class="nav-link" href="#${key}" ${route() === key ? 'aria-current="page"' : ''}>${icon(ic)}<span>${title}</span></a>`).join('')}</nav><div class="sidebar-bottom"><div class="sidebar-note">${icon('shield',22)}<strong>Tu salud, en tus manos</strong>Un poco de organización.<br>Una cosa menos de la que preocuparte.</div><div class="sidebar-footer"><a href="https://github.com/kadyto/pastillas" target="_blank" rel="noopener noreferrer">Pastillas ${esc(state.version)}</a><button class="icon-button" data-action="logout" aria-label="Cerrar sesión">${icon('logout',17)}</button></div></div></aside><main class="main" id="content"><div class="topbar"><div class="breadcrumb">Mi botiquín &nbsp;/&nbsp; <span>${esc(page?.[1] || 'Avisos')}</span></div><a class="mobile-brand" href="#today"><img src="/icon-192.png?v=0.4.0" alt="">Pastillas</a><div class="top-actions"><button class="icon-button" data-action="theme" aria-label="Cambiar a tema ${theme === 'light' ? 'oscuro' : 'claro'}">${icon(theme === 'light' ? 'moon' : 'sun',18)}</button><a class="icon-button" href="#alerts" aria-label="Avisos${state.data.unread_alerts ? `, ${state.data.unread_alerts} sin leer` : ''}">${icon('bell',18)}${state.data.unread_alerts ? '<span class="dot"></span>' : ''}</a><div class="avatar" aria-hidden="true">${esc(state.user.username.slice(0,2).toUpperCase())}</div><span class="username">${esc(state.user.username)}</span></div></div>${!navigator.onLine ? '<div class="offline" role="alert">Sin conexión. Conecta con el servidor para registrar tomas y compras.</div>' : ''}${medicineBanner()}${content}<p class="footer-note">Sigue la pauta indicada por tu profesional sanitario. Las previsiones dependen de la pauta y las existencias registradas.<br>Zona horaria: ${esc(tz())}</p>${versionFooter()}</main>`;
}
function versionFooter() {
  const info=state.updates;
  const checking=state.checkingVersion||info?.checking;
  let label='Versión pendiente de comprobar', statusClass='neutral';
  if(checking) label='Comprobando GitHub…';
  else if(info?.error){label='No se pudo comprobar la versión';statusClass='amber';}
  else if(info?.state==='available'){label=`Disponible: ${info.latest_version}`;statusClass='amber';}
  else if(info?.state==='current'){label='Tienes la última versión';statusClass='';}
  else if(info?.state==='ahead')label=`En GitHub: ${info.latest_version}`;
  const updating=['queued','running','requested'].includes(info?.deploy_status);
  const message=updating?'Actualización solicitada a Dockhand. Comprueba el despliegue antes de repetirla.':info?.deploy_error;
  return `<footer class="app-footer" aria-label="Versión y código fuente"><div class="version-row"><a class="footer-repository" href="https://github.com/kadyto/pastillas" target="_blank" rel="noopener noreferrer">${icon('github',17)} GitHub</a><span>Instalada: <strong>${esc(state.version)}</strong></span><span class="status ${statusClass}" role="status">${esc(label)}</span></div><div class="footer-actions"><button type="button" class="footer-link" data-action="version-check" ${checking?'disabled':''}>${checking?'Comprobando…':'Comprobar ahora'}</button>${state.user.admin?`<button type="button" class="footer-link" data-action="version-update">${info?.update_available&&info?.deployment_configured?'Actualizar con Dockhand':'Cómo actualizar'}</button>`:''}</div><p class="version-help">${info?.checked_at?`Última comprobación correcta: ${fullDate(info.checked_at)}. `:''}Comprobación automática cada 24 horas.${info?.error?` ${esc(info.error)}`:''}</p>${message?`<p class="version-help" role="status">${esc(message)}</p>`:''}</footer>`;
}
function updateDialog() {
  const info=state.updates;
  const configured=info?.deployment_configured;
  const updating=['queued','running','requested'].includes(info?.deploy_status);
  openDialog('Actualizar Pastillas',`<p class="help">Versión instalada: <strong>${esc(state.version)}</strong>${info?.latest_version?` · Última comprobada en GitHub: <strong>${esc(info.latest_version)}</strong>`:''}.</p>${configured?`<p class="inline-note form-section">Dockhand descargará el contenido de GitHub, reconstruirá la imagen y recreará el stack conservando su carpeta o volumen de datos. La app puede desconectarse durante el despliegue.</p>${updating?'<p class="help form-section">Ya hay una solicitud de actualización. Revisa el despliegue en Dockhand antes de volver a intentarlo.</p>':''}<div class="form-actions">${button('close','Cerrar')}<button type="button" class="button primary" id="start-update" ${!info.update_available||info.error||updating?'disabled':''}>Actualizar con Dockhand</button></div>`:`<p class="inline-note form-section">Para actualizar desde aquí, configura el webhook del stack Git de Pastillas en Dockhand. Activa la construcción de imágenes y conserva el nombre del stack y sus datos.</p>${info?.deployment_configuration_error?`<p class="help">${esc(info.deployment_configuration_error)}</p>`:''}<div class="picker-actions"><a class="button small-button" href="https://github.com/kadyto/pastillas/blob/main/docs/actualizaciones.md" target="_blank" rel="noopener noreferrer">Configurar actualización con Dockhand</a><a class="button small-button" href="https://github.com/kadyto/pastillas/archive/refs/heads/main.tar.gz" target="_blank" rel="noopener noreferrer">Descargar código de GitHub</a></div><p class="help">Descargar el código no actualiza el contenedor. En Dockhand debes reconstruir la imagen y recrear el stack.</p><div class="form-actions">${button('close','Cerrar')}</div>`}`);
  $('#start-update',dialog)?.addEventListener('click',async event=>{
    const submit=event.currentTarget;submit.disabled=true;submit.textContent='Solicitando actualización…';
    try{state.updates=await api('/version/update','POST');dialog.close();render();toast('Actualización solicitada a Dockhand.');pollDeployment(state.version);}
    catch(error){$('#form-error').textContent=error.message;submit.disabled=false;submit.textContent='Actualizar con Dockhand';}
  });
}
async function pollDeployment(previousVersion) {
  for(let attempt=0;attempt<40;attempt++){
    await new Promise(resolve=>setTimeout(resolve,3000));
    if(!state.user)return;
    try{
      const info=await api('/version');state.updates=info;state.version=info.installed_version;
      if(info.installed_version!==previousVersion){location.reload();return;}
      if(!dialog.open&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))render();
      if(['failed','skipped','unknown','completed'].includes(info.deploy_status))return;
    }catch{}
  }
  toast('Comprueba el resultado del despliegue en Dockhand.');
}
function heading(title, subtitle, action = '', label = '') {
  return `<div class="heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${action ? button(action,label,'plus','','primary') : ''}</div>`;
}
function supply(med) {
  if (!med.active) return 'Tratamiento en pausa';
  if (med.schedule === 'as_needed') return `${number(med.doses_left)} tomas disponibles`;
  if (med.enough_until_end) return 'Cubre el tratamiento';
  if (med.days_left === null) return 'Sin tomas futuras previstas';
  if (med.doses_left === 0) return 'Sin cantidad para otra toma';
  return `${number(Math.ceil(med.days_left))} ${Math.ceil(med.days_left) === 1 ? 'día' : 'días'} de cobertura aprox.`;
}
function low(med) { return med.active && (!med.end_at || med.end_at >= state.data.now) && (med.stock_warning || med.stock < med.dose); }
function scheduleText(med) {
  if (med.schedule === 'as_needed') return 'Según necesidad';
  if (med.schedule === 'daily') return med.times.join(' · ');
  return `Cada ${number(med.interval_hours)} horas`;
}
function doseRow(item) {
  const pending=item.status==='pending', future=item.scheduled_at>state.data.now;
  const taken=item.status==='taken', skipped=item.status==='skipped', untracked=item.status==='untracked';
  const label=pending?'PREVISTA':untracked?'SIN DESCUENTO PREVIO':item.automatic?'DESCUENTO AUTOMÁTICO':skipped?'OMITIDA':'CONFIRMADA';
  const quantity=item.expected_amount??item.dose;
  return `<article class="dose-row ${esc(item.status)}"><div class="dose-time">${clock(item.scheduled_at)}<small>${label}</small></div><div class="dose-icon">${icon(formIcon(item),22)}</div><div class="dose-body"><h3>${esc(item.name)}</h3><p>${number(quantity)} ${esc(item.unit)}${item.strength?` · ${esc(item.strength)}`:''}${item.brand?` · ${esc(item.brand)}`:''}</p>${item.instructions?`<p class="instruction">${esc(item.instructions)}</p>`:''}${item.stock_shortfall?'<p class="stock-shortfall">Stock registrado insuficiente. Comprueba las existencias.</p>':''}${pending?'<p class="help">Se descontará automáticamente a su hora.</p>':''}${untracked?'<p class="help">Anterior al cálculo automático; el stock actual se conserva.</p>':''}</div><div class="dose-actions">${taken?`<span class="status">${icon(item.automatic?'clock':'check',13)}${item.automatic?'Asumida':'Confirmada'}</span>${button('skip','No la tomé','',`data-id="${item.medication_id}" data-at="${item.scheduled_at}"`,'small-button')}`:skipped?`<span class="status neutral">${icon('x',13)}Omitida</span>${button('take','Sí la tomé','',`data-id="${item.medication_id}" data-at="${item.scheduled_at}" ${future?'disabled':''}`,'small-button')}`:untracked?'<span class="status neutral">Sin ajuste previo</span>':button('skip','Omitir','',`data-id="${item.medication_id}" data-at="${item.scheduled_at}" ${future?'disabled title="Podrás omitirla cuando llegue su hora"':''}`,'small-button')}</div></article>`;
}
function renderToday() {
  const all = state.agenda, today = state.day === state.data.today;
  const taken = all.filter(i => i.status === 'taken').length;
  const visible = all.filter(i => state.filter === 'all' || i.status === state.filter);
  const stock = state.data.medications.filter(low);
  const renewal = state.data.prescriptions.filter(r => r.renewal_warning);
  const next = state.data.agenda.find(i => i.status === 'pending' && i.scheduled_at >= state.data.now - 900);
  const active = state.data.medications.filter(m => m.active);
  const manual = active.filter(m => m.schedule === 'as_needed');
  shell(`${heading('Tu botiquín, al día', 'Cada toma cuenta. Aquí tienes todo bajo control.', 'med-new', 'Añadir medicamento')}${today ? `<section class="hero"><div><span class="eyebrow">${esc(new Intl.DateTimeFormat('es-ES',{timeZone:tz(),weekday:'long',day:'numeric',month:'long'}).format(new Date(state.data.now*1000)))}</span><h2>${next ? `Tu próxima toma, a las ${clock(next.scheduled_at)}` : active.length ? 'Un día más, cuidándote.' : 'Un poco de orden. Mucha tranquilidad.'}</h2><p>${next ? `${esc(next.name)} · ${number(next.dose)} ${esc(next.unit)}${next.strength ? ` · ${esc(next.strength)}` : ''}` : active.length ? 'Consulta tus tomas y revisa qué necesitas reponer.' : 'Añade tu primer medicamento y deja que el botiquín haga las cuentas.'}</p></div><div class="hero-art" aria-hidden="true"><div class="pill-illustration"></div><div class="pill-illustration"></div></div></section>` : ''}<section class="stats" aria-label="Resumen"><div class="stat"><div class="stat-top">Tomas del día ${icon('clock')}</div><strong>${all.length}</strong><small>${today ? 'Programadas para hoy' : esc(dateText(state.day))}</small></div><button type="button" class="stat stat-action" data-action="dose-summary" aria-controls="daily-doses" aria-label="Ver tomas descontadas: ${taken} de ${all.length} en total"><span class="stat-top">Tomas descontadas ${icon('check')}</span><strong>${taken}</strong><small>${taken === 1 ? 'toma descontada' : 'tomas descontadas'} de ${all.length} en total</small><span class="stat-link">Ver detalle ${icon('arrow',13)}</span></button><a href="#medications" class="stat"><div class="stat-top">Medicamentos ${icon('pill')}</div><strong>${active.length}</strong><small>Tratamientos activos</small></a><a href="#stock" class="stat ${stock.length ? 'warn' : ''}"><div class="stat-top">Para reponer ${icon('box')}</div><strong>${stock.length}</strong><small>${stock.length ? 'Prepara tu próxima compra' : 'Existencias bajo control'}</small></a></section><div class="home-columns"><section id="daily-doses" tabindex="-1" aria-labelledby="daily-doses-title"><div class="section-title"><h2 id="daily-doses-title">${today ? 'Tus tomas de hoy' : 'Agenda de tomas'} <span class="count">${all.length}</span></h2><div class="day-control"><button class="icon-button" data-action="day-prev" aria-label="Día anterior">${icon('left',16)}</button><input type="date" id="agenda-day" value="${state.day}" min="2000-01-01" max="2100-12-31" aria-label="Fecha de la agenda"><button class="icon-button" data-action="day-next" aria-label="Día siguiente">${icon('arrow',16)}</button></div></div><div class="tabs agenda-tabs" aria-label="Filtrar tomas">${[['all','Todas'],['pending','Próximas'],['taken','Descontadas'],['skipped','Omitidas']].map(([key,label])=>`<button data-action="dose-filter" data-value="${key}" aria-pressed="${state.filter === key}">${label}</button>`).join('')}</div><div class="dose-list">${visible.length ? visible.map(doseRow).join('') : empty(all.length ? 'Sin tomas en este filtro' : active.length ? 'Sin tomas programadas' : 'Tu botiquín empieza aquí', all.length ? 'No hay tomas con este filtro.' : active.length ? 'Puedes elegir otro día o registrar una toma según necesidad.' : 'Guarda tus medicamentos, indica la pauta y registra las existencias que tienes.', all.length || active.length ? '' : 'med-new', 'Añadir mi primer medicamento')}</div>${manual.length && today ? `<div class="section-title form-section"><h2>Según necesidad</h2></div><div class="dose-list">${manual.map(m=>`<article class="dose-row"><div class="dose-icon">${icon(formIcon(m))}</div><div class="dose-body"><h3>${esc(m.name)}</h3><p>${number(m.dose)} ${esc(m.unit)} por toma · ${esc(m.instructions)}</p></div>${button('manual','Registrar toma','check',`data-id="${m.id}"`,'small-button')}</article>`).join('')}</div>` : ''}</section><aside><div class="section-title"><h2>Tu próxima compra</h2><a class="link-button" href="#stock">Ver todo ${icon('arrow',14)}</a></div><div class="panel">${stock.length ? stock.slice(0,4).map(m=>`<div class="shopping-item"><h3>${esc(m.name)}</h3><p>${number(m.stock)} ${esc(m.unit)} disponibles</p><div><span class="status amber">${esc(supply(m))}</span><button class="icon-button" data-action="stock-add" data-id="${m.id}" aria-label="Registrar compra de ${esc(m.name)}">${icon('plus',17)}</button></div></div>`).join('') : `<div class="shopping-item"><div><span class="dose-icon">${icon('check')}</span><h3>Todo en orden</h3></div><p>${active.length ? 'No necesitas reponer ningún medicamento según las pautas registradas.' : 'Aquí verás qué medicamentos conviene reponer.'}</p></div>`}</div>${renewal.length ? `<div class="mini-note"><strong>${icon('rx',16)} Tienes ${renewal.length} ${renewal.length === 1 ? 'receta' : 'recetas'} para renovar</strong>${renewal.slice(0,3).map(r=>esc(r.title)).join(' · ')}<br><a href="#prescriptions" class="link-button">Revisar recetas ${icon('arrow',14)}</a></div>` : `<div class="mini-note"><strong>${icon('bell',16)} Que no se te pase</strong>Configura los avisos de tomas y existencias para recibirlos también en tu móvil.<br><a href="#settings" class="link-button">Configurar avisos ${icon('arrow',14)}</a></div>`}</aside></div>`);
  $('#agenda-day').addEventListener('change', event => { if (event.target.value) changeDay(event.target.value); });
}
function expiryBadge(med) {
  if (!med.expiry_date) return '';
  const expired=med.expiry_date<state.data.today, today=med.expiry_date===state.data.today;
  const label=expired?'Caducado':today?'Caduca hoy':'Caducidad';
  return `<span class="status ${expired?'red':today?'amber':'neutral'}">${icon('clock',13)}${esc(label)}: ${esc(dateText(med.expiry_date))}</span>`;
}
function medCard(med) {
  const recipe = state.data.prescriptions.find(r=>r.id === med.prescription_id);
  return `<article class="med-card ${!med.active ? 'paused' : ''}"><div class="med-top"><div class="dose-icon">${icon(formIcon(med),23)}</div><div><h3>${esc(med.name)}</h3><p>${esc([med.brand,med.form,med.strength].filter(Boolean).join(' · '))}</p></div><span class="status ${!med.active ? 'neutral' : low(med) ? 'amber' : ''}">${!med.active ? 'En pausa' : low(med) ? 'Reponer' : 'Activo'}</span></div><dl class="med-facts"><div><dt>PAUTA</dt><dd>${number(med.dose)} ${esc(med.unit)}<br>${esc(scheduleText(med))}</dd></div><div><dt>EXISTENCIAS</dt><dd>${number(med.stock)} ${esc(med.unit)}<br><span class="muted">${esc(supply(med))}</span></dd></div></dl>${med.expiry_date ? `<p class="expiry-note">${expiryBadge(med)}</p>` : ''}${med.instructions ? `<p class="muted">${esc(med.instructions)}</p>` : ''}${recipe ? `<p class="muted">${icon('rx',14)} ${esc(recipe.title)}</p>` : ''}${med.end_at ? `<p class="muted">Hasta ${fullDate(med.end_at)}</p>` : ''}${medicineBadge(med)}<div class="card-actions">${button('stock-add','Compra','plus',`data-id="${med.id}"`,'small-button')}${button('stock-verify','Comprobar stock','check',`data-id="${med.id}"`,'small-button')}${button('med-edit','Editar','edit',`data-id="${med.id}"`,'small-button')}${button('medicine-info','Información','rx',`data-id="${med.id}"`,'small-button')}${button('history','Historial','clock',`data-id="${med.id}"`,'small-button push')}</div></article>`;
}
function matchingMeds() {
  const query = state.search.toLocaleLowerCase('es');
  return state.data.medications.filter(m=>`${m.name} ${m.brand} ${m.form} ${m.strength}`.toLocaleLowerCase('es').includes(query));
}
function renderMedications() {
  const meds = matchingMeds().filter(m=>state.medFilter==='all' || (state.medFilter==='active' ? m.active : !m.active));
  shell(`${heading('Tus medicamentos', 'Tu tratamiento, con el nombre y la presentación que tú usas.', 'med-new', 'Añadir medicamento')}<div class="toolbar"><label class="search">${icon('search',19)}<input id="med-search" type="search" placeholder="Buscar nombre, marca o presentación…" value="${esc(state.search)}" aria-label="Buscar medicamentos"></label><div class="tabs" aria-label="Filtrar medicamentos">${[['active','Activos'],['paused','En pausa'],['all','Todos']].map(([key,label])=>`<button data-action="med-filter" data-value="${key}" aria-pressed="${state.medFilter === key}">${label}</button>`).join('')}</div></div><div id="med-results" class="med-grid">${meds.map(medCard).join('')}</div>${!meds.length ? empty('Aún no hay medicamentos aquí', 'Añade tu primer medicamento o cambia el filtro de búsqueda.', 'med-new', 'Añadir medicamento') : ''}`);
  $('#med-search').addEventListener('input', event => { state.search = event.target.value; const meds = matchingMeds().filter(m=>state.medFilter==='all'||(state.medFilter==='active'?m.active:!m.active)); $('#med-results').innerHTML=meds.length?meds.map(medCard).join(''):empty('Sin resultados','Prueba con otro nombre o marca.'); });
}
function renderStock() {
  const meds = matchingMeds().filter(m=>m.active && (state.stockFilter==='all' || low(m)));
  shell(`${heading('Existencias sin sorpresas', 'Registra lo que compras y anticipa cuándo necesitarás reponer.') }<div class="toolbar"><div class="tabs" aria-label="Filtrar existencias">${[['all','Todo el botiquín'],['low','Para reponer']].map(([key,label])=>`<button data-action="stock-filter" data-value="${key}" aria-pressed="${state.stockFilter === key}">${label}</button>`).join('')}</div><span class="help">El stock baja automáticamente con cada toma prevista. Puedes comprobarlo contando lo que queda.</span></div><div class="inventory-list">${meds.length ? meds.map(m=>`<article class="inventory-row ${low(m)?'warn':''}"><div class="dose-icon">${icon(formIcon(m))}</div><div class="inventory-name"><h3>${esc(m.name)}</h3><p>${esc([m.brand,m.strength].filter(Boolean).join(' · '))}</p></div><div class="inventory-stock"><strong>${number(m.stock)}</strong><small>${esc(m.unit)} · stock calculado</small>${m.stock_verified_at?`<small>Comprobado: ${fullDate(m.stock_verified_at)}</small>`:''}${m.expiry_date?`<small class="expiry-note">${expiryBadge(m)}</small>`:''}</div><div class="inventory-forecast"><span class="status ${low(m)?'amber':''}">${esc(supply(m))}</span><div class="progress" aria-hidden="true"><span></span></div><p>${m.runs_out_at ? `Primera toma sin cubrir: ${fullDate(m.runs_out_at)}` : 'Según la pauta registrada'}</p></div><div class="inventory-actions">${button('stock-add','Registrar compra','plus',`data-id="${m.id}"`,'small-button')}${button('stock-verify','Comprobar stock','check',`data-id="${m.id}"`,'small-button')}</div></article>`).join('') : empty('Todo bajo control', state.stockFilter === 'low' ? 'No hay medicamentos que necesiten reposición.' : 'Añade un medicamento con las existencias que tienes.', state.stockFilter === 'low' ? '' : 'med-new', 'Añadir medicamento')}</div><div class="mini-note"><strong>Una previsión que se adapta a ti</strong>La fecha indica la primera toma futura que tus existencias no cubrirían. Las tomas omitidas devuelven su descuento. Comprobar stock guarda la cantidad que hayas contado. Puedes definir cuántos días antes quieres recibir el aviso en cada medicamento.</div>`);
}
function renderPrescriptions() {
  shell(`${heading('Tus recetas, a mano', 'Guarda las indicaciones y recuerda cuándo toca renovarlas.', 'rx-new', 'Añadir receta')}<div class="med-grid">${state.data.prescriptions.map(r=>`<article class="prescription-card"><div class="section-title"><div class="dose-icon">${icon('rx',23)}</div><span class="status ${r.renewal_warning?'amber':'neutral'}">${r.renewal_date ? `Renovar: ${esc(dateText(r.renewal_date))}` : 'Sin fecha de renovación'}</span></div><h3>${esc(r.title)}</h3>${r.doctor?`<p>Profesional: ${esc(r.doctor)}</p>`:''}${r.reference?`<p>Referencia: ${esc(r.reference)}</p>`:''}${r.notes?`<p>${esc(r.notes)}</p>`:''}<p class="rx-meds">${icon('pill',15)} ${esc(state.data.medications.filter(m=>m.prescription_id===r.id).map(m=>m.name).join(' · ') || 'Sin medicamentos vinculados')}</p><div class="card-actions">${button('rx-edit','Editar','edit',`data-id="${r.id}"`,'small-button')}${button('rx-delete','Eliminar','',`data-id="${r.id}"`,'small-button danger push')}</div></article>`).join('')}</div>${state.data.prescriptions.length?'':empty('Una receta, todo su tratamiento','Guarda su referencia, las indicaciones y la fecha de renovación. Después puedes vincularla a tus medicamentos.','rx-new','Añadir mi primera receta')}`);
}
function renderSettings() {
  const user=state.user;
  let enabled=false; try { enabled=localStorage.getItem(`pastillas-notify-${user.id}`)==='true'; } catch {}
  const supported='Notification' in window && window.isSecureContext;
  const topicUrl=`${state.ntfy}/${encodeURIComponent(user.ntfy_topic)}`;
  shell(`${heading('A tu manera', 'Configura tus avisos, tu cuenta y la hora de tu botiquín.')}<div class="settings-grid"><section class="panel"><h2>${icon('bell',20)} Avisos y horarios</h2><p>Los avisos en la app siempre están disponibles. Elige cómo recibirlos fuera de ella.</p><div class="error-box" id="settings-error" role="alert"></div><form id="settings-form" class="form-stack"><label>Zona horaria de la agenda<input name="timezone" value="${esc(user.timezone)}" required list="timezones"><datalist id="timezones"><option>Europe/Madrid</option><option>Atlantic/Canary</option><option>America/Mexico_City</option><option>America/Bogota</option><option>America/Argentina/Buenos_Aires</option><option>Etc/UTC</option></datalist><small>Los medicamentos conservan su propia zona horaria. Edita cada pauta para cambiarla.</small></label><label class="check"><input type="checkbox" name="stock_alerts" ${user.stock_alerts?'checked':''}>Avisos de existencias bajas</label><label class="check"><input type="checkbox" name="prescription_alerts" ${user.prescription_alerts?'checked':''}>Recordar renovación de recetas (7 días antes)</label><fieldset class="form-stack form-section"><legend>Avisos en el móvil con ntfy</legend><label class="check"><input type="checkbox" name="ntfy_enabled" ${user.ntfy_enabled?'checked':''}>Enviar avisos a ntfy aunque cierre la web</label><label>Tema privado de ntfy<input name="ntfy_topic" value="${esc(user.ntfy_topic)}" minlength="16" maxlength="100" pattern="[A-Za-z0-9_-]{16,100}"><small>Conserva este nombre largo y aleatorio; quien lo conozca puede leer los avisos si el servidor no exige autenticación.</small></label><p class="help">1. Instala <a href="https://ntfy.sh" target="_blank" rel="noopener noreferrer">ntfy</a> en el móvil.<br>2. Suscríbete al tema de arriba en el servidor <strong>${esc(state.ntfy)}</strong>.<br>3. Activa el envío y guarda.<br>Se enviarán nombres de medicamentos e indicaciones a ese servidor. Para más privacidad puedes usar tu propio servidor ntfy.<br><a href="${esc(topicUrl)}" target="_blank" rel="noopener noreferrer">Abrir mi tema en ntfy ${icon('arrow',12)}</a></p></fieldset><button class="button primary" type="submit">Guardar ajustes</button></form><div class="form-section"><h3>Avisos en este navegador</h3><p class="help">Necesitan HTTPS o localhost y que la app siga abierta. Con la web cerrada utiliza ntfy.</p>${button('browser-notify', enabled ? 'Desactivar avisos del navegador' : 'Activar avisos del navegador','bell', !supported?'disabled':'','small-button')}<p class="help">${!supported ? 'No disponibles en este navegador o conexión HTTP.' : Notification.permission === 'denied' ? 'El permiso está bloqueado. Cámbialo en los ajustes del navegador.' : enabled ? 'Activados en este dispositivo.' : 'Desactivados en este dispositivo.'}</p></div></section><div class="form-stack"><section class="panel"><h2>${icon('shield',20)} Tu cuenta</h2><p>Has iniciado sesión como <strong>${esc(user.username)}</strong>.</p>${button('password','Cambiar contraseña','edit','','small-button')}${user.admin?`<div class="form-section"><h3>Más personas, su propio botiquín</h3><p class="help">Cada usuario tiene sus medicamentos, recetas y avisos separados.</p>${button('user-new','Crear usuario','plus','','small-button')}</div>`:''}<div class="form-section"><button class="logout" data-action="logout">${icon('logout',17)} Cerrar sesión</button></div></section><section class="panel"><h2>${icon('download',20)} Tus datos</h2><p>Descarga tus medicamentos, recetas, tomas y movimientos de existencias en un archivo JSON.</p><a class="button small-button" href="/api/export" download> ${icon('download',17)} Exportar mis datos</a><p class="help form-section">La copia completa del servidor se realiza con la herramienta SQLite incluida. Encontrarás los pasos en la documentación del repositorio.</p></section><section class="panel"><h2>Pastillas ${esc(state.version)}</h2><p>Tu botiquín personal, alojado en tu servidor.</p><a class="link-button" href="https://github.com/kadyto/pastillas" target="_blank" rel="noopener noreferrer">Código y documentación ${icon('arrow',14)}</a></section></div></div>`);
  $('#settings-form').addEventListener('submit', async event=>{
    event.preventDefault();const form=event.currentTarget;const submit=$('button[type=submit]',form);submit.disabled=true;$('#settings-error').textContent='';
    try{state.user=await api('/settings','PUT',{...Object.fromEntries(new FormData(form)),ntfy_enabled:form.ntfy_enabled.checked,stock_alerts:form.stock_alerts.checked,prescription_alerts:form.prescription_alerts.checked});toast('Ajustes guardados');await refresh();}catch(error){$('#settings-error').textContent=error.message;submit.disabled=false;}
  });
}
function renderAlerts() {
  shell(`${heading('Tus avisos', 'Tomas, reposiciones, recetas y avisos de AEMPS, en un solo lugar.')}<div class="section-title"><span class="help">Se conservan los avisos de los últimos 90 días.</span>${button('alerts-read','Marcar todo como leído','check','','small-button')}</div><div class="alert-list">${state.alerts.length?state.alerts.map(a=>`<article class="alert-row ${a.read?'':'unread'}"><div class="dose-icon">${icon(a.kind==='dose'?'clock':a.kind==='stock'?'box':a.kind==='safety'?'shield':a.kind==='supply'?'box':'rx')}</div><div><h3>${esc(a.title)}</h3><p>${esc(a.message)}</p><small>${fullDate(a.created_at)} ${state.user.ntfy_enabled ? `· ${a.delivered?'Enviado a ntfy':a.attempts>=5?'No se pudo enviar a ntfy':a.created_at<state.data.now-600?'No enviado a ntfy':'Pendiente de envío a ntfy'}`:''}</small></div></article>`).join(''):empty('Sin avisos por ahora','Los recordatorios de tus pautas, existencias y recetas aparecerán aquí.')}</div>`);
}
function render() {
  if (!state.user) return renderLogin();
  if (!state.data) return;
  ({today:renderToday,medications:renderMedications,stock:renderStock,prescriptions:renderPrescriptions,settings:renderSettings,alerts:renderAlerts}[route()]||renderToday)();
}
async function refresh() {
  if(!state.user)return;
  const version=++requestVersion;
  const [data,alertList,updateStatus]=await Promise.all([api('/dashboard'),api('/alerts'),api('/version')]);
  if(version!==requestVersion||!state.user)return;
  state.data=data;state.alerts=alertList;state.updates=updateStatus;state.version=updateStatus.installed_version;state.day=state.day||data.today;
  state.agenda=state.day===data.today?data.agenda:await api(`/agenda?day=${encodeURIComponent(state.day)}`);
  if(version!==requestVersion)return;
  render();notify();
}
async function changeDay(day) {
  if(day<'2000-01-01'||day>'2100-12-31')return;
  state.day=day;
  try{await refresh();}catch(error){toast(error.message,true);}
}
function openDialog(title, content) {
  if(dialog.open)dialog.close();
  clearTimeout(toastTimer); $('#toast').className = '';
  dialog.innerHTML=`<div class="dialog-header"><h2 id="dialog-title">${esc(title)}</h2><button class="icon-button" data-action="close" aria-label="Cerrar diálogo">${icon('x',18)}</button></div><div class="dialog-body"><div class="error-box" id="form-error" role="alert"></div>${content}</div>`;
  dialog.showModal();
}
function bindDialog(save) {
  const form=$('form',dialog);
  form.addEventListener('submit',async event=>{
    event.preventDefault();const submit=$('button[type=submit]',form);submit.disabled=true;$('#form-error').textContent='';
    try{await save(form,Object.fromEntries(new FormData(form)));dialog.close();await refresh();toast('Guardado');}catch(error){if(dialog.open){$('#form-error').textContent=error.message;submit.disabled=false;}else toast(error.message,true);}
  });
}
const formActions=(label='Guardar')=>`<div class="form-actions">${button('close','Cancelar')}<button class="button primary" type="submit">${label}</button></div>`;
function medForm(med) {
  const m=med||{name:'',brand:'',form:'Pastillas',strength:'',unit:'pastillas',dose:1,stock:0,schedule:'interval',interval_hours:8,times:['08:00','20:00'],timezone:tz(),start_at:Math.floor(Date.now()/60000)*60,end_at:null,active:true,reminders:true,warning_days:7,instructions:'',prescription_id:null};
  openDialog(med?'Editar medicamento':'Añadir medicamento',`<form>${medicinePicker(med)}<fieldset><legend>El medicamento que tú usas</legend><div class="form-grid"><label class="full">Nombre del medicamento<input name="name" value="${esc(m.name)}" placeholder="Ej. nombre del medicamento" required maxlength="200"></label><label>Marca <span class="muted">(opcional)</span><input name="brand" value="${esc(m.brand)}" maxlength="200" placeholder="Marca o fabricante"></label><label>Presentación<input name="form" value="${esc(m.form)}" list="forms" required maxlength="100"><datalist id="forms"><option>Pastillas</option><option>Cápsulas</option><option>Jarabe</option><option>Gotas</option><option>Crema</option><option>Inyección</option><option>Inhalador</option><option>Sobres</option></datalist></label><label class="full">Concentración o dosis del envase<input name="strength" value="${esc(m.strength)}" placeholder="Ej. 500 mg, 20 mg/ml…" maxlength="100"><small>Texto libre, tal como figura en tu envase.</small></label><label>Unidad de existencias<input name="unit" value="${esc(m.unit)}" required maxlength="50" list="units"><datalist id="units"><option>pastillas</option><option>cápsulas</option><option>ml</option><option>gotas</option><option>gramos</option><option>dosis</option><option>sobres</option></datalist><small>Usa la misma unidad para cada toma y compra.</small></label><label>Cantidad por toma<input name="dose" type="number" min="0.001" max="1000000000" step="0.001" value="${m.dose}" required><small>Ej. 0,5 pastillas o 5 ml. No convierte unidades.</small></label>${!med?`<label class="full">Existencias que tienes ahora<input name="stock" type="number" min="0" max="1000000000" step="0.001" value="0" required><small>Si tienes 2 cajas de 30 pastillas, introduce 60.</small></label>`:''}<label class="full">Fecha de caducidad <span class="muted">(opcional)</span><input name="expiry_date" type="date" value="${esc(m.expiry_date||'')}" min="2000-01-01" max="2100-12-31"><small>La fecha del envase. Si tienes varios, indica la caducidad más próxima.</small></label></div></fieldset><fieldset class="form-section"><legend>Cuándo lo tomas</legend><div class="form-grid"><label class="full">Tipo de pauta<select name="schedule"><option value="interval" ${m.schedule==='interval'?'selected':''}>Cada cierto número de horas</option><option value="daily" ${m.schedule==='daily'?'selected':''}>A horas fijas cada día</option><option value="as_needed" ${m.schedule==='as_needed'?'selected':''}>Según necesidad (sin horario)</option></select></label><label id="interval-field" class="full">Intervalo en horas<input name="interval_hours" type="number" min="1" max="720" step="0.5" value="${m.interval_hours}" list="intervals"><datalist id="intervals"><option>6</option><option>8</option><option>12</option><option>24</option></datalist><small>Los intervalos se cuentan desde la primera toma, incluso por la noche.</small></label><label id="times-field" class="full">Horas fijas del día<input name="times_text" value="${esc(m.times.join(', '))}" placeholder="08:00, 14:00, 20:00"><small>Formato de 24 horas, separado por comas.</small></label><label class="full">Zona horaria de esta pauta<input name="timezone" value="${esc(m.timezone)}" required maxlength="100"><small>Las fechas y horas de este formulario se interpretan en esta zona.</small></label><label class="mobile-full">Primera toma / inicio<input name="start_local" type="datetime-local" value="${inputDate(m.start_at,m.timezone)}" min="2000-01-01T00:00" max="2100-12-31T23:59" required></label><label class="mobile-full">Fin del tratamiento <span class="muted">(opcional)</span><input name="end_local" type="datetime-local" value="${m.end_at?inputDate(m.end_at,m.timezone):''}" min="2000-01-01T00:00" max="2100-12-31T23:59"><small>La fecha incluye esa última hora.</small></label><label class="full">Indicaciones<input name="instructions" value="${esc(m.instructions)}" maxlength="4000" placeholder="Ej. después de comer, con agua…"></label></div></fieldset><fieldset class="form-section"><legend>Receta y avisos</legend><div class="form-grid"><label class="full">Receta vinculada<select name="prescription_id"><option value="">Sin receta vinculada</option>${state.data.prescriptions.map(r=>`<option value="${r.id}" ${r.id===m.prescription_id?'selected':''}>${esc(r.title)}</option>`).join('')}</select></label><label class="full">Avisar de reposición con estos días de antelación<input name="warning_days" type="number" min="0" max="365" step="1" value="${m.warning_days}" required></label><label class="check full"><input type="checkbox" name="reminders" ${m.reminders?'checked':''}>Recordar cada toma programada</label><label class="check full"><input type="checkbox" name="active" ${m.active?'checked':''}>Tratamiento activo</label></div></fieldset>${med?'<p class="inline-note form-section">Al cambiar la pauta se recalculan las tomas pendientes; el historial y las existencias se conservan. Para terminar temporalmente el tratamiento, desactívalo.</p>':''}${formActions(med?'Guardar cambios':'Añadir medicamento')}${med?`<button class="logout danger" type="button" data-action="med-delete" data-id="${m.id}">Eliminar medicamento e historial</button>`:''}</form>`);
  const form=$('form',dialog);
  bindMedicinePicker(form,med);
  let savedId=med?.id;
  function visibility(){ $('#interval-field').hidden=form.schedule.value!=='interval';$('#times-field').hidden=form.schedule.value!=='daily';form.times_text.required=form.schedule.value==='daily';form.interval_hours.required=form.schedule.value==='interval'; }
  form.schedule.addEventListener('change',visibility);visibility();
  bindDialog(async(form,data)=>{
    const body={...data,dose:data.dose,stock:data.stock||0,interval_hours:Number(data.interval_hours)||24,times:data.times_text.split(',').map(t=>t.trim()).filter(Boolean),prescription_id:data.prescription_id?Number(data.prescription_id):null,warning_days:Number(data.warning_days),reminders:form.reminders.checked,active:form.active.checked};
    const result=await api(savedId?`/medications/${savedId}`:'/medications',savedId?'PUT':'POST',body);
    savedId=result.id;
    const number=form.cima_nregistro.value, cn=form.cima_cn.value, url=form.vademecum_url.value.trim();
    const old=med?.information?.link;
    if(number && (number!==old?.nregistro || cn!==old?.cn || url!==(old?.vademecum_url||''))) {
      try {await api(`/medications/${savedId}/information`,'POST',{nregistro:number,cn,vademecum_url:url});}
      catch(error){throw new Error(`El medicamento está guardado, pero no se ha vinculado la información: ${error.message}`);}
    } else if(!number && old) await api(`/medications/${savedId}/information`,'DELETE');
    else if(url && !number) throw new Error('El medicamento está guardado. Busca la URL y elige el envase para vincular la información.');
  });
}
function stockForm(med,initialKind='purchase') {
  openDialog(`Existencias · ${med.name}`,`<p>Stock calculado: <strong>${number(med.stock)} ${esc(med.unit)}</strong>. Cada toma consume ${number(med.dose)} ${esc(med.unit)}.</p><form class="form-stack"><label>Tipo de movimiento<select name="kind"><option value="purchase">Registrar una compra</option><option value="adjustment">Corregir el total disponible</option></select></label><label><span id="stock-label">Cantidad comprada (${esc(med.unit)})</span><input name="amount" type="number" min="0.001" max="1000000000" step="0.001" required placeholder="Ej. 30"><small id="stock-help">Indica la cantidad total en ${esc(med.unit)}, no el número de cajas.</small></label><label>Precio total <span class="muted">(opcional, €)</span><input type="number" name="price" min="0" max="1000000000" step="0.01" placeholder="0,00"></label><label>Nota <span class="muted">(opcional)</span><input name="note" maxlength="1000" placeholder="Farmacia, número de cajas…"></label>${formActions('Guardar existencias')}</form>`);
  const form=$('form',dialog);
  const option=document.createElement('option');option.value='verification';option.textContent='Comprobar el stock contado';form.kind.append(option);
  const comparison=document.createElement('div');comparison.className='stock-comparison';comparison.setAttribute('aria-live','polite');$('label',form).after(comparison);
  function checkCount(){
    if(form.kind.value!=='verification'){comparison.innerHTML='';return;}
    const raw=form.amount.value, counted=Number(raw), diff=Math.round((counted-med.stock)*1000)/1000;
    comparison.innerHTML=`<div class="stock-check-grid"><div><small>Stock calculado</small><strong>${number(med.stock)} ${esc(med.unit)}</strong></div><div><small>Cantidad contada</small><strong>${raw!==''?`${number(counted)} ${esc(med.unit)}`:'Por comprobar'}</strong></div></div>${raw!==''?`<p>${diff===0?'Coincide con el stock calculado.':`Diferencia: ${diff>0?'+':''}${number(diff)} ${esc(med.unit)}.`}</p><p class="help">${diff>0?'Tener más unidades puede corresponder a una toma omitida o una compra sin registrar. ':''}Al guardar se actualizará el total y quedará registrada la comprobación.</p>`:''}`;
  }
  function mode(){
    const purchase=form.kind.value==='purchase',verify=form.kind.value==='verification';
    form.price.closest('label').hidden=!purchase;if(!purchase)form.price.value='';
    if(verify){$('#stock-label').textContent=`Cantidad que has contado (${med.unit})`;$('#stock-help').textContent='Cuenta lo que queda realmente, incluidas unidades sueltas. Puedes introducir cero.';form.amount.min='0';form.amount.value='';}
    checkCount();
  }
  form.kind.addEventListener('change',mode);form.amount.addEventListener('input',checkCount);
  form.kind.value=initialKind;mode();
  form.kind.addEventListener('change',()=>{const adjustment=form.kind.value==='adjustment';$('#stock-label').textContent=adjustment?`Total contado (${med.unit})`:`Cantidad comprada (${med.unit})`;$('#stock-help').textContent=adjustment?'Este número sustituye al total de existencias. El historial registra la diferencia.':`Indica la cantidad total en ${med.unit}, no el número de cajas.`;form.amount.min=adjustment?'0':'0.001';form.amount.value=adjustment?med.stock:'';});
  bindDialog((form,data)=>api(`/medications/${med.id}/stock`,'POST',data));
}
function rxForm(recipe) {
  const r=recipe||{};
  openDialog(recipe?'Editar receta':'Añadir receta',`<form class="form-stack"><label>Nombre o título<input name="title" required maxlength="200" value="${esc(r.title)}" placeholder="Ej. tratamiento habitual"></label><div class="form-grid"><label>Profesional <span class="muted">(opcional)</span><input name="doctor" maxlength="200" value="${esc(r.doctor)}"></label><label>Referencia <span class="muted">(opcional)</span><input name="reference" maxlength="200" value="${esc(r.reference)}"></label></div><label>Fecha de renovación <span class="muted">(opcional)</span><input name="renewal_date" type="date" min="2000-01-01" max="2100-12-31" value="${esc(r.renewal_date)}"><small>Recibirás un aviso desde 7 días antes si está activado.</small></label><label>Indicaciones y notas<textarea name="notes" rows="4" maxlength="4000">${esc(r.notes)}</textarea></label><p class="inline-note">Después de guardar puedes vincular esta receta desde el formulario de cada medicamento.</p>${formActions()}</form>`);
  bindDialog((form,data)=>api(recipe?`/prescriptions/${recipe.id}`:'/prescriptions',recipe?'PUT':'POST',data));
}
async function showHistory(med) {
  const data=await api(`/medications/${med.id}/history`);
  const kinds={initial:'Existencias iniciales',purchase:'Compra',adjustment:'Corrección de inventario',verification:'Comprobación física del stock',dose:'Toma confirmada',automatic_dose:'Descuento automático',undo:'Descuento devuelto'};
  openDialog(`Historial · ${med.name}`,`<p>Últimas 100 tomas y 100 movimientos. La exportación incluye el historial completo.</p><div class="history-tabs"><h3>Tomas registradas</h3>${data.doses.length?data.doses.map(d=>`<div class="history-row"><div>${fullDate(d.scheduled_at)}<p>${d.status==='taken'?`${number(d.expected_amount||d.amount)} ${esc(med.unit)} · ${d.automatic?'asumida automáticamente':'confirmada'}`:'Omitida'}${d.note?` · ${esc(d.note)}`:''}</p></div><button class="icon-button" data-action="undo" data-id="${d.id}" aria-label="Deshacer toma">${icon('undo',16)}</button></div>`).join(''):'<p class="help">Todavía no hay tomas registradas.</p>'}<h3>Movimientos de existencias</h3>${data.movements.map(m=>`<div class="history-row"><div>${esc(kinds[m.kind]||m.kind)}<p>${fullDate(m.recorded_at)}${m.note?` · ${esc(m.note)}`:''}${m.price_cents!==null?` · ${number(m.price_cents/100)} €`:''}</p></div><strong>${m.amount>0?'+':''}${number(m.amount)} ${esc(med.unit)}</strong></div>`).join('')}</div><div class="form-actions">${button('close','Cerrar')}</div>`);
}
function confirm(title,message,onConfirm) {
  openDialog(title,`<p>${message}</p><form>${formActions('Confirmar')}</form>`);
  bindDialog(onConfirm);
}
function accountForm(kind) {
  const isUser=kind==='user';
  openDialog(isUser?'Crear un usuario':'Cambiar contraseña',`<form class="form-stack">${isUser?'<label>Usuario<input name="username" minlength="3" maxlength="60" autocomplete="off" required></label>':'<label>Contraseña actual<input name="current_password" type="password" autocomplete="current-password" maxlength="256" required></label>'}<label>${isUser?'Contraseña inicial':'Nueva contraseña'}<input name="password" type="password" minlength="12" maxlength="256" autocomplete="new-password" required><small>Al menos 12 caracteres.</small></label>${formActions(isUser?'Crear usuario':'Guardar contraseña')}</form>`);
  bindDialog((form,data)=>api(isUser?'/users':'/password',isUser?'POST':'PUT',data));
}
async function notify() {
  let enabled=false;try{enabled=localStorage.getItem(`pastillas-notify-${state.user.id}`)==='true';}catch{}
  if(!enabled||!('Notification' in window)||Notification.permission!=='granted')return;
  for(const alert of state.alerts){
    if(notificationIds.has(alert.id)||alert.read||alert.created_at<state.data.now-90)continue;
    notificationIds.add(alert.id);
    const options={body:alert.message,icon:'/icon-192.png?v=0.4.0',tag:`pastillas-${state.user.id}-${alert.id}`};
    try{const registration=await navigator.serviceWorker?.ready;if(registration)await registration.showNotification(alert.title,options);else new Notification(alert.title,options);}catch{}
  }
}
document.addEventListener('click',async event=>{
  const target=event.target.closest('[data-action]');if(!target)return;
  const action=target.dataset.action,id=Number(target.dataset.id),at=Number(target.dataset.at);
  if(state.busy && !['close','theme'].includes(action))return;
  try{
    if(action==='version-check'){
      if(state.checkingVersion)return;
      state.checkingVersion=true;render();
      try{state.updates=await api('/version/check','POST');state.version=state.updates.installed_version;}
      finally{state.checkingVersion=false;render();}
      return;
    }
    if(action==='version-update')return updateDialog();
    if(action==='close'){dialog.close();return;}
    if(action==='theme'){theme=theme==='light'?'dark':'light';document.documentElement.dataset.theme=theme;try{localStorage.setItem('pastillas-theme',theme);}catch{}render();return;}
    if(action==='med-new')return medForm();
    if(action==='med-edit')return medForm(medById(id));
    if(action==='stock-add')return stockForm(medById(id));
    if(action==='stock-verify')return stockForm(medById(id),'verification');
    if(action==='rx-new')return rxForm();
    if(action==='rx-edit')return rxForm(state.data.prescriptions.find(r=>r.id===id));
    if(action==='history')return await showHistory(medById(id));
    if(action==='medicine-info')return await showMedicineInfo(medById(id));
    if(action==='password')return accountForm('password');
    if(action==='user-new')return accountForm('user');
    if(action==='med-delete')return confirm('Eliminar medicamento',`Se eliminarán <strong>${esc(medById(id).name)}</strong>, sus tomas y todos sus movimientos. Para conservar el historial puedes poner el tratamiento en pausa.`,()=>api(`/medications/${id}`,'DELETE'));
    if(action==='rx-delete')return confirm('Eliminar receta','Se borrará la receta; los medicamentos vinculados se conservarán.',()=>api(`/prescriptions/${id}`,'DELETE'));
    if(action==='manual')return confirm('Registrar toma según necesidad',`Vas a registrar <strong>${number(medById(id).dose)} ${esc(medById(id).unit)}</strong> de ${esc(medById(id).name)} ahora.`,()=>api(`/medications/${id}/doses`,'POST',{status:'taken'}));
    if(action==='skip')return confirm('Omitir esta toma',`Se devolverá al stock el descuento aplicado y se marcará como omitida la toma de <strong>${esc(medById(id).name)}</strong> a las ${clock(at)} . Las próximas tomas seguirán su horario.`,()=>api(`/medications/${id}/doses`,'POST',{scheduled_at:at,status:'skipped'}));
    if(action==='undo')return confirm('Deshacer toma','Se devolverá el descuento al stock. Las tomas programadas quedarán omitidas para que no vuelvan a descontarse.',()=>api(`/doses/${id}`,'DELETE'));
    if(action==='dose-summary'){
      state.filter='taken';render();
      const agenda=$('#daily-doses');
      agenda.focus({preventScroll:true});
      agenda.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
      return;
    }
    if(action==='dose-filter'){state.filter=target.dataset.value;render();return;}
    if(action==='med-filter'){state.medFilter=target.dataset.value;render();return;}
    if(action==='stock-filter'){state.stockFilter=target.dataset.value;state.search='';render();return;}
    if(action==='day-prev'||action==='day-next'){const d=new Date(`${state.day}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+(action==='day-prev'?-1:1));return changeDay(d.toISOString().slice(0,10));}
    if(action==='browser-notify'){
      let enabled=false;try{enabled=localStorage.getItem(`pastillas-notify-${state.user.id}`)==='true';}catch{}
      if(!enabled){const permission=await Notification.requestPermission();if(permission!=='granted'){toast('No se ha concedido permiso para notificaciones.',true);return;}}
      try{localStorage.setItem(`pastillas-notify-${state.user.id}`,String(!enabled));}catch{throw new Error('Este navegador no permite guardar la preferencia.');}renderSettings();return;
    }
    state.busy=true;target.disabled=true;
    if(action==='take'){await api(`/medications/${id}/doses`,'POST',{scheduled_at:at,status:'taken'});await refresh();toast('Toma registrada. Existencias actualizadas.');}
    if(action==='alerts-read'){await api('/alerts/read','POST');await refresh();toast('Avisos marcados como leídos');}
    if(action==='logout'){await api('/logout','POST');state.user=null;state.data=null;state.search='';state.alerts=[];notificationIds.clear();if(dialog.open)dialog.close();renderLogin();}
    if(action==='retry')await boot();
  }catch(error){toast(error.message,true);}finally{state.busy=false;target.disabled=false;}
});
window.addEventListener('hashchange',()=>{if(dialog.open)dialog.close();state.search='';render();window.scrollTo({top:0});});
window.addEventListener('online',()=>{refresh().catch(error=>toast(error.message,true));});
window.addEventListener('offline',()=>{if(!dialog.open)render();});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state.user&&!dialog.open)refresh().catch(()=>{});});
setInterval(()=>{if(state.user&&!dialog.open&&!state.busy&&route()!=='settings'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))refresh().catch(error=>toast(error.message,true));},30000);
async function boot(){
  try{const session=await api('/session');state.user=session.user;state.setup=session.setup_required;state.version=session.version;state.ntfy=session.ntfy_base_url;
    if(state.user)await refresh();else renderLogin();
    if('serviceWorker' in navigator && window.isSecureContext)navigator.serviceWorker.register('/sw.js').catch(()=>{});
  }catch(error){app.innerHTML=`<main class="login-shell" id="content"><div class="login-card"><h1>No se pudo abrir el botiquín</h1><p>${esc(error.message)}</p>${button('retry','Volver a intentar','undo','','primary')}</div></main>`;}
}
function externalLink(url,label,cls='button small-button') {
  return /^https:\/\//.test(url||'') ? `<a class="${cls}" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : '';
}
function medicineBadge(med) {
  const info=med.information;
  if(!info)return '<p class="help">Vincula CIMA/AEMPS desde Información para consultar documentos y avisos.</p>';
  const notices=info.data.notices||[], linked=info.link;
  const label=info.status==='pending'?'Comprobando AEMPS…':info.status==='unavailable'?'No se pudo comprobar AEMPS':info.status==='stale'?'Información pendiente de actualizar':notices.length?`${notices.length} aviso${notices.length===1?'':'s'} de AEMPS`:'Sin avisos en la última comprobación';
  return `<p class="medicine-badge ${notices.length||['unavailable','stale'].includes(info.status)?'medicine-warning':''}">${icon('shield',15)} ${esc(label)}${linked.cn?` · CN ${esc(linked.cn)}`:''}</p>`;
}
function medicineBanner() {
  if(!['today','medications','alerts'].includes(route()))return '';
  const meds=state.data.medications.filter(m=>m.active&&(!m.end_at||m.end_at>=state.data.now)&&m.information);
  const notices=meds.filter(m=>m.information.data.notices?.length);
  const failed=meds.filter(m=>['unavailable','stale'].includes(m.information.status));
  const pending=meds.some(m=>m.information.status==='pending');
  if(!notices.length&&!failed.length&&!pending)return '';
  return `<section class="medicine-banner" aria-label="Información de AEMPS"><strong>${icon('shield',17)} Información de tus medicamentos</strong>${notices.map(m=>`<div>${esc(m.name)}: ${m.information.data.notices.length} aviso(s) de seguridad o suministro. ${button('medicine-info','Consultar','',`data-id="${m.id}"`,'small-button')}</div>`).join('')}${failed.length?`<p>La información de ${esc(failed.map(m=>m.name).join(', '))} no está actualizada. Abre Información para ver el último intento.</p>`:''}${pending?'<p>Comprobando los medicamentos vinculados. Cada comprobación se conserva durante 12 horas.</p>':''}</section>`;
}
function medicinePicker(med) {
  const link=med?.information?.link;
  return `<fieldset class="medicine-picker"><legend>Información del medicamento <span class="muted">(opcional)</span></legend><p class="help">Busca en CIMA/AEMPS por nombre o pega una URL de Vademécum. Elige la concentración y el envase que usas.</p><input type="hidden" name="cima_nregistro" value="${esc(link?.nregistro||'')}"><input type="hidden" name="cima_cn" value="${esc(link?.cn||'')}"><label>Nombre o URL de Vademécum<input name="medicine_query" maxlength="600" placeholder="Omacor o https://www.vademecum.es/espana/medicamento/…" value="${esc(link?.vademecum_url||med?.name||'')}"></label><div class="picker-actions"><button type="button" class="button small-button" id="medicine-search-button">${icon('search',16)} Buscar medicamento</button><button type="button" class="button small-button" id="medicine-clear-button">Quitar vinculación</button></div><div id="medicine-search-results" aria-live="polite"></div><p id="medicine-selection" class="inline-note">${link?esc(`${link.cima_name} · ${link.presentation_name||'Sin envase'}${link.cn?' · CN '+link.cn:''}`):'Sin medicamento vinculado. La pauta y las existencias las defines tú.'}</p><label>URL de Vademécum <span class="muted">(para equivalencias internacionales)</span><input name="vademecum_url" type="url" maxlength="600" value="${esc(link?.vademecum_url||'')}" placeholder="https://www.vademecum.es/espana/medicamento/…"><small>Se conserva como referencia. El identificador de Vademécum no es el número de registro de CIMA.</small></label></fieldset>`;
}
function bindMedicinePicker(form,med) {
  const searchButton=$('#medicine-search-button',form), results=$('#medicine-search-results',form);
  const selectLabel=$('#medicine-selection',form);
  let page=1, currentQuery='';
  async function lookup(nextPage=1) {
    searchButton.disabled=true;results.textContent='Buscando en CIMA/AEMPS…';
    try {
      const query=nextPage===1?(form.medicine_query.value.trim()||form.name.value.trim()):currentQuery;
      const data=await api(`/medicine-search?q=${encodeURIComponent(query)}&page=${nextPage}`);
      if(!form.isConnected)return;
      currentQuery=query;page=data.page;
      if(data.vademecum_url)form.vademecum_url.value=data.vademecum_url;
      results.innerHTML=`<p class="help">Fuente: ${esc(data.source)} · ${data.total} resultado(s) · página ${page}</p><div class="medicine-results">${data.results.map(r=>`<button type="button" class="medicine-result" data-registry="${esc(r.nregistro)}"><strong>${esc(r.name)}</strong><small>${esc(r.laboratory)} · Registro ${esc(r.nregistro)}</small></button>`).join('')||'<p>Sin resultados. Prueba con el nombre comercial de tu envase.</p>'}</div><div class="picker-actions">${page>1?'<button type="button" class="button small-button" id="medicine-prev">Anterior</button>':''}${page*25<data.total?'<button type="button" class="button small-button" id="medicine-next">Siguiente</button>':''}</div>`;
      $('#medicine-prev',results)?.addEventListener('click',()=>lookup(page-1));
      $('#medicine-next',results)?.addEventListener('click',()=>lookup(page+1));
      for(const result of results.querySelectorAll('[data-registry]'))result.addEventListener('click',async()=>{
        result.disabled=true;
        try {
          const item=await api(`/medicine-catalog?nregistro=${encodeURIComponent(result.dataset.registry)}`);
          if(!form.isConnected)return;
          results.innerHTML=`<p><strong>${esc(item.name)}</strong></p><label>Envase / código nacional<select id="medicine-presentation"><option value="">${item.presentations.length?'Selecciona tu envase':'Sin presentaciones disponibles'}</option>${item.presentations.map(p=>`<option value="${esc(p.cn)}">${esc(p.name)} · CN ${esc(p.cn)}${p.marketed?'':' · No comercializado'}</option>`).join('')}</select></label><button type="button" class="button primary small-button" id="medicine-select">Vincular este medicamento</button>`;
          $('#medicine-select',results).addEventListener('click',()=>{
            const cn=$('#medicine-presentation',results).value;
            if(item.presentations.length&&!cn){$('#form-error').textContent='Elige el envase exacto que usas.';return;}
            form.cima_nregistro.value=item.nregistro;form.cima_cn.value=cn;
            if(!form.name.value.trim()){form.name.value=item.name;if(item.form)form.form.value=item.form;if(item.strength)form.strength.value=item.strength;}
            const presentation=item.presentations.find(p=>p.cn===cn);
            selectLabel.textContent=`${item.name} · ${presentation?.name||'Sin envase'}${cn?' · CN '+cn:''}`;
            results.replaceChildren();$('#form-error').textContent='';
          });
        } catch(error){$('#form-error').textContent=error.message;result.disabled=false;}
      });
    } catch(error){if(form.isConnected){results.textContent='';$('#form-error').textContent=error.message;}}
    finally{searchButton.disabled=false;}
  }
  searchButton.addEventListener('click',()=>lookup());
  form.medicine_query.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();lookup();}});
  $('#medicine-clear-button',form).addEventListener('click',()=>{form.cima_nregistro.value='';form.cima_cn.value='';form.vademecum_url.value='';results.replaceChildren();selectLabel.textContent='Sin medicamento vinculado.';});
}
async function showMedicineInfo(med) {
  const info=await api(`/medications/${med.id}/information`);
  if(!info){medForm(med);$('#medicine-query',dialog)?.focus();return;}
  openDialog(`Información · ${med.name}`,'<div id="medicine-panel"></div>');
  const panel=$('#medicine-panel',dialog);
  function draw(item) {
    const notes=item.data.notices||[], docs=item.data.documents||[], link=item.link;
    const status=item.status==='pending'?'Comprobando CIMA/AEMPS…':item.status==='fresh'?'Información comprobada':'La información no está actualizada';
    panel.innerHTML=`<p><strong>${esc(link.cima_name)}</strong><br>${esc(link.presentation_name||'Sin envase seleccionado')}${link.cn?` · CN ${esc(link.cn)}`:''}</p><p class="inline-note">${esc(status)}${item.checked_at?`<br>Última comprobación correcta: ${fullDate(item.checked_at)}`:''}${item.attempted_at?`<br>Último intento: ${fullDate(item.attempted_at)}`:''}${item.next_check_at?`<br>Próxima comprobación posible al entrar: ${fullDate(item.next_check_at)}`:''}</p>${item.error?`<p class="error-box" role="alert">${esc(item.error)}</p>`:''}<div class="info-tabs" aria-label="Información del medicamento"><button class="button small-button" type="button" data-info-tab="notices">Avisos</button><button class="button small-button" type="button" data-info-tab="2">Prospecto</button><button class="button small-button" type="button" data-info-tab="1">Ficha técnica</button><button class="button small-button" type="button" data-info-tab="equivalents">Equivalencias</button></div><div id="medicine-content"></div><div class="form-actions">${button('med-edit','Editar vinculación','edit',`data-id="${med.id}"`,'small-button')}${button('close','Cerrar')}</div>`;
    const content=$('#medicine-content',panel);
    async function tab(name) {
      for(const b of panel.querySelectorAll('[data-info-tab]'))b.setAttribute('aria-pressed',String(b.dataset.infoTab===name));
      if(name==='notices'){
        content.innerHTML=`<h3>Notas de seguridad y suministro</h3><p class="help">Fuente: CIMA / AEMPS. Las notas pueden ser anteriores a tu tratamiento; consulta su fecha y a qué medicamentos afectan.</p>${notes.length?notes.map(n=>`<article class="medicine-notice"><span class="status amber">${n.kind==='supply'?'Suministro':'Seguridad'}</span><h4>${esc(n.title)}</h4>${n.date?`<p class="help">Publicado: ${esc(dateFmt(n.date,{day:'numeric',month:'long',year:'numeric'}))}</p>`:''}${n.message?`<p>${esc(n.message)}</p>`:''}${n.expected_end?`<p>Fin previsto: ${esc(dateFmt(n.expected_end,{day:'numeric',month:'long',year:'numeric'}))}</p>`:''}${externalLink(n.url,'Ver aviso original')}</article>`).join(''):`<p>${item.status==='fresh'?'AEMPS no devuelve notas de seguridad ni problemas de suministro para la vinculación consultada.':'Todavía no hay una comprobación vigente. No se puede confirmar si hay avisos.'}</p>`}${link.vademecum_url?`<div class="picker-actions">${externalLink(link.vademecum_url,'Ver medicamento en Vademécum')}</div>`:''}`;
      }else if(name==='equivalents'){
        content.innerHTML=`<h3>Equivalencias internacionales</h3>${item.equivalents_url?externalLink(item.equivalents_url,'Consultar equivalencias en Vademécum'):'<p>Añade la URL de Vademécum desde Editar vinculación para consultar las equivalencias de este medicamento.</p>'}<p class="help">Fuente: Vademécum.es. La lista puede incluir concentraciones y formas diferentes; no confirma una sustitución. Comprueba país, concentración y presentación con tu farmacéutico.</p><div class="equivalents-reader" aria-live="polite"></div>`;
        const reader=$('.equivalents-reader',content);
        async function load(country=''){
          reader.textContent='Consultando equivalencias públicas de Vademécum…';
          try{
            const data=await api(`/medications/${med.id}/equivalents${country?'?country='+encodeURIComponent(country):''}`);
            if(!reader.isConnected)return;
            const original=$('a',content);if(original)original.href=data.url;
            reader.innerHTML=`<label>País de las equivalencias<select id="equivalents-country">${data.countries.map(c=>`<option value="${esc(c.code)}" ${c.code===data.country?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><p class="help">${data.results.length} resultado(s) en ${esc(data.country_name)}${data.checked_at?` · Consultado: ${fullDate(data.checked_at)}`:''}</p><div class="medicine-results">${data.results.map(r=>`<article class="medicine-result"><strong>${esc(r.name)}</strong><small>${esc(r.details)}</small>${externalLink(r.url,'Ver en Vademécum','help')}</article>`).join('')||'<p>Vademécum no devuelve equivalencias para este país.</p>'}</div>`;
            $('#equivalents-country',reader).addEventListener('change',event=>load(event.target.value));
          }catch(error){if(reader.isConnected)reader.textContent=error.message;}
        }
        if(item.equivalents_url)await load();
      }else{
        const doc=docs.find(d=>String(d.type)===name);
        const links=externalLink(doc?.url,name==='2'?'Prospecto original de AEMPS':'Ficha técnica original de AEMPS')+externalLink(doc?.pdf_url,'PDF de AEMPS');
        content.innerHTML=`<h3>${name==='2'?'Prospecto':'Ficha técnica'}</h3><div class="picker-actions">${links}</div><div class="medicine-document" aria-live="polite">Cargando documento de CIMA/AEMPS…</div>`;
        const reader=$('.medicine-document',content);
        try {
          const data=await api(`/medications/${med.id}/document?type=${name}`);
          if(!reader.isConnected)return;
          reader.innerHTML=data.sections.map((s,index)=>`<details ${index===0?'open':''}><summary>${esc(s.section)} ${esc(s.title)}</summary><div class="document-section">${s.html}</div></details>`).join('');
        }catch(error){if(reader.isConnected)reader.textContent=error.message;}
      }
    }
    for(const b of panel.querySelectorAll('[data-info-tab]'))b.addEventListener('click',()=>tab(b.dataset.infoTab));
    tab('notices');
  }
  draw(info);
  if(info.status==='pending'){
    for(let attempt=0;attempt<15;attempt++){
      await new Promise(resolve=>setTimeout(resolve,2000));
      if(!dialog.open||!panel.isConnected)return;
      const current=await api(`/medications/${med.id}/information`);
      if(current&&current.status!=='pending'){draw(current);return;}
    }
  }
}
boot();
