package io.github.kadyto.pastillas;

import static org.junit.Assert.*;
import android.app.Notification;
import android.app.NotificationManager;
import android.content.Context;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public final class OfflineAndroidTest {
    private Context context;
    private ActivityScenario<MainActivity> scenario;

    @Before public void offline() throws Exception {
        context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        UiDevice device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
        device.executeShellCommand("svc wifi disable");device.executeShellCommand("svc data disable");
        long offlineDeadline = SystemClock.elapsedRealtime() + 10000;
        while (BotiquinWorker.online(context) && SystemClock.elapsedRealtime() < offlineDeadline) SystemClock.sleep(100);
        assertFalse("La prueba debe ejecutarse con la red desconectada", BotiquinWorker.online(context));
        RuntimeApi.module(context);
        JSONObject erased = new JSONObject(RuntimeApi.call(context, "request", "POST", "/api/android/erase", "{\"confirm\":\"BORRAR\"}"));
        assertEquals(200, erased.getInt("status"));
        context.getSystemService(NotificationManager.class).cancelAll();
    }
    private WebView findWeb(View view) {
        if (view instanceof WebView) return (WebView) view;
        if (view instanceof ViewGroup) for (int i=0;i<((ViewGroup)view).getChildCount();i++) {
            WebView child=findWeb(((ViewGroup)view).getChildAt(i));if(child!=null)return child;
        }
        return null;
    }
    private String js(String script) throws Exception {
        AtomicReference<String> value=new AtomicReference<>("null");CountDownLatch done=new CountDownLatch(1);
        scenario.onActivity(activity->{
            WebView web=findWeb(activity.getWindow().getDecorView());
            if(web==null){done.countDown();return;}
            web.evaluateJavascript(script,result->{value.set(result);done.countDown();});
        });
        assertTrue("La interfaz debe responder",done.await(5,TimeUnit.SECONDS));return value.get();
    }
    private void waitJs(String condition) throws Exception {
        long until=SystemClock.elapsedRealtime()+30000;
        while(SystemClock.elapsedRealtime()<until){if("true".equals(js("Boolean("+condition+")")))return;SystemClock.sleep(150);}
        fail("No se cumplió: "+condition+". Interfaz: "+js("document.body.innerText"));
    }
    private JSONObject body(String method,String path,JSONObject payload,int expected) throws Exception {
        JSONObject result=new JSONObject(RuntimeApi.call(context,"request",method,"/api"+path,payload==null?"{}":payload.toString()));
        assertEquals(result.toString(),expected,result.getInt("status"));return result.getJSONObject("body");
    }

    @Test public void botiquinFuncionaSinInternetYConservaDatosTrasRecrearLaActividad() throws Exception {
        try(ActivityScenario<MainActivity> opened=ActivityScenario.launch(MainActivity.class)) {
            scenario=opened;
            waitJs("document.querySelector('[data-action=\"med-new\"]')");
            assertFalse(body("GET","/android/settings",null,200).getBoolean("external_sources"));
            js("document.querySelector('[data-action=\"med-new\"]').click()");
            waitJs("document.querySelector('dialog').open");
            js("(()=>{const f=document.querySelector('dialog form');f.querySelector('[name=name]').value='Botiquín sin red';f.querySelector('[name=stock]').value='12';f.querySelector('[name=dose]').value='0.5';f.querySelector('[name=expiry_date]').value='2028-05-31';f.querySelector('[name=schedule]').value='as_needed';f.querySelector('[name=schedule]').dispatchEvent(new Event('change'));f.querySelector('[type=submit]').click();})()");
            waitJs("!document.querySelector('dialog').open&&document.body.innerText.includes('Botiquín sin red')");
            JSONObject dashboard=body("GET","/dashboard",null,200);
            JSONObject med=dashboard.getJSONArray("medications").getJSONObject(0);
            assertEquals(12,med.getDouble("stock"),0.0001);assertEquals("2028-05-31",med.getString("expiry_date"));
            js("fetch('/api/medications/"+med.getInt("id")+"/doses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'taken'})}).then(r=>{window.nativeTestRecorded=r.ok;})");
            waitJs("window.nativeTestRecorded===true");
            assertEquals(11.5,body("GET","/dashboard",null,200).getJSONArray("medications").getJSONObject(0).getDouble("stock"),0.0001);
            opened.recreate();
            waitJs("document.body.innerText.includes('Botiquín sin red')");
            js("location.hash='settings'");
            waitJs("document.body.innerText.includes('Recordatorios Android')");
            assertFalse("Android no debe mostrar configuración de servidor",js("document.querySelector('main').innerText").contains("Enviar avisos a ntfy"));
            JSONObject exported=new JSONObject(RuntimeApi.call(context,"export_json"));
            assertEquals(1,exported.getJSONArray("medications").length());
            assertEquals(1,exported.getJSONArray("doses").length());
        }
    }

    @Test public void laAlarmaNotificaConLaActividadCerradaSinInternet() throws Exception {
        UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
        device.executeShellCommand("pm grant "+context.getPackageName()+" android.permission.POST_NOTIFICATIONS");
        device.executeShellCommand("appops set "+context.getPackageName()+" SCHEDULE_EXACT_ALARM allow");
        assertTrue(ReminderScheduler.permitted(context));assertTrue(ReminderScheduler.exact(context));
        long scheduled=Instant.now().getEpochSecond()+15;
        JSONObject medication=new JSONObject().put("name","Recordatorio local de prueba").put("form","Pastillas").put("unit","pastillas")
            .put("dose",1).put("stock",3).put("schedule","interval").put("interval_hours",8)
            .put("timezone","Europe/Madrid").put("start_at",Instant.ofEpochSecond(scheduled).toString());
        body("POST","/medications",medication,201);
        try(ActivityScenario<MainActivity> opened=ActivityScenario.launch(MainActivity.class)) {
            scenario=opened;waitJs("document.querySelector('h1')");
            ReminderScheduler.tick(context,0);
        }
        NotificationManager manager=context.getSystemService(NotificationManager.class);
        long until=SystemClock.elapsedRealtime()+60000;boolean found=false;
        while(SystemClock.elapsedRealtime()<until&&!found){
            for(android.service.notification.StatusBarNotification item:manager.getActiveNotifications())
                if("Hora de tu toma".equals(item.getNotification().extras.getString(Notification.EXTRA_TITLE)))found=true;
            if(!found)SystemClock.sleep(250);
        }
        assertTrue("El recordatorio local debe llegar con la actividad cerrada y sin red",found);
        JSONObject med=body("GET","/dashboard",null,200).getJSONArray("medications").getJSONObject(0);
        assertEquals(2,med.getDouble("stock"),0.0001);
    }
}
