package io.github.kadyto.pastillas;

import android.content.Context;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.util.TimeZone;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Python embebido: llamadas en memoria a SQLite, sin proceso ni servidor HTTP. */
final class RuntimeApi {
    private static PyObject module;
    private static final java.util.concurrent.ExecutorService SOURCES = Executors.newSingleThreadExecutor();
    private static final AtomicBoolean sourcesRunning = new AtomicBoolean();
    static synchronized PyObject module(Context context) {
        if (module == null) {
            Context app = context.getApplicationContext();
            if (!Python.isStarted()) Python.start(new AndroidPlatform(app));
            PyObject candidate = Python.getInstance().getModule("app.android_runtime");
            candidate.callAttr("initialize", app.getNoBackupFilesDir().getAbsolutePath(),
                    TimeZone.getDefault().getID(), BuildConfig.VERSION_NAME);
            module = candidate;
        }
        return module;
    }
    static String call(Context context, String method, Object... arguments) {
        return module(context).callAttr(method, arguments).toString();
    }
    static void sources(Context context) {
        Context app = context.getApplicationContext();
        if (!BotiquinWorker.online(app) || !sourcesRunning.compareAndSet(false, true)) return;
        SOURCES.execute(() -> {
            try { call(app, "check_sources");ReminderScheduler.tick(app, 0); }
            catch (Exception ignored) { }
            finally { sourcesRunning.set(false); }
        });
    }
    private RuntimeApi() { }
}
