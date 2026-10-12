// waitForFunction no espera predicados Promise; son objetos truthy.
// Se espera y comprueba cada respuesta antes de continuar con la interfaz.
async function waitForDashboard(page,predicate,timeout=15000){
  const until=Date.now()+timeout;
  while(Date.now()<until){
    const data=await page.evaluate(()=>fetch('/api/dashboard').then(response=>response.json()));
    if(predicate(data))return data;
    await page.waitForTimeout(150);
  }
  throw new Error('El dashboard no alcanzó el estado esperado dentro del plazo.');
}
module.exports={waitForDashboard};
