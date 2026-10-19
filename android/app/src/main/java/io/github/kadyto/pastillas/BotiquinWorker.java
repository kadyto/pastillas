package io.github.kadyto.pastillas;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

public final class BotiquinWorker extends Worker {
    public BotiquinWorker(@NonNull Context context, @NonNull WorkerParameters parameters) { super(context, parameters); }
    @NonNull @Override public Result doWork() {
        Context c = getApplicationContext();
        try {
            ReminderScheduler.tick(c, 0);
            if (online(c)) RuntimeApi.call(c, "check_sources");
            ReminderScheduler.tick(c, 0);
            return Result.success();
        } catch (Exception error) {
            // No se escriben nombres, pautas ni copias en Logcat.
            return Result.retry();
        }
    }
    static boolean online(Context c) {
        ConnectivityManager manager = c.getSystemService(ConnectivityManager.class);
        NetworkCapabilities network = manager.getNetworkCapabilities(manager.getActiveNetwork());
        return network != null && network.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
    }
}
