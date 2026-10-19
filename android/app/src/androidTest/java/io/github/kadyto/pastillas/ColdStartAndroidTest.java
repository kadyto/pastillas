package io.github.kadyto.pastillas;

import static org.junit.Assert.*;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;
import org.junit.runner.RunWith;

/** No inicializa Python desde la prueba: verifica el arranque normal de la app. */
@RunWith(AndroidJUnit4.class)
public final class ColdStartAndroidTest {
    private WebView findWeb(View view) {
        if(view instanceof WebView)return (WebView)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){
            WebView child=findWeb(((ViewGroup)view).getChildAt(i));if(child!=null)return child;
        }
        return null;
    }
    @Test public void arranqueNormalTrasCerrarElProcesoSinInternet() throws Exception {
        UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
        device.executeShellCommand("svc wifi disable");device.executeShellCommand("svc data disable");
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            long deadline=SystemClock.elapsedRealtime()+60000;
            while(SystemClock.elapsedRealtime()<deadline){
                CountDownLatch done=new CountDownLatch(1);AtomicReference<String> ready=new AtomicReference<>("false");
                scenario.onActivity(activity->{
                    WebView web=findWeb(activity.getWindow().getDecorView());
                    if(web==null){done.countDown();return;}
                    web.evaluateJavascript("Boolean(window.PastillasNative&&document.querySelector('h1')?.textContent.includes('Tu botiquín'))",value->{ready.set(value);done.countDown();});
                });
                assertTrue(done.await(5,TimeUnit.SECONDS));
                if("true".equals(ready.get())){
                    SystemClock.sleep(500);
                    java.io.File capture=new java.io.File(InstrumentationRegistry.getInstrumentation().getTargetContext().getCacheDir(),"pastillas-cold-start.png");
                    assertTrue(device.takeScreenshot(capture));return;
                }
                SystemClock.sleep(200);
            }
            fail("El arranque normal debe llegar al botiquín sin inicialización desde las pruebas ni conexión a internet");
        }
    }
}
