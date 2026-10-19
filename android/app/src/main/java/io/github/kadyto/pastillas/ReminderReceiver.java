package io.github.kadyto.pastillas;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class ReminderReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (!java.util.Arrays.asList(ReminderScheduler.ALARM_ACTION, Intent.ACTION_BOOT_COMPLETED,
                Intent.ACTION_MY_PACKAGE_REPLACED, Intent.ACTION_TIME_CHANGED, Intent.ACTION_TIMEZONE_CHANGED,
                "android.app.action.SCHEDULE_EXACT_ALARM_PERMISSION_STATE_CHANGED").contains(action == null ? "" : action)) return;
        long scheduled = ReminderScheduler.ALARM_ACTION.equals(action) ? intent.getLongExtra("scheduled_at", 0) : 0;
        PendingResult pending = goAsync();
        new Thread(() -> {
            try { ReminderScheduler.tick(context.getApplicationContext(), scheduled); }
            catch (Exception ignored) { /* El trabajo periódico y la siguiente apertura recuperan el estado. */ }
            finally { pending.finish(); }
        }, "pastillas-alarma").start();
    }
}
