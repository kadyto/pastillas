package io.github.kadyto.pastillas;

import android.Manifest;
import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.TimeUnit;

final class ReminderScheduler {
    static final String CHANNEL = "pastillas-recordatorios";
    static final String ALARM_ACTION = "io.github.kadyto.pastillas.REMIND";
    static boolean enabled(Context c) {
        return c.getSharedPreferences("device", Context.MODE_PRIVATE).getBoolean("reminders", true);
    }
    static boolean permitted(Context c) {
        return NotificationManagerCompat.from(c).areNotificationsEnabled() &&
            (Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(c, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED);
    }
    static boolean exact(Context c) {
        return Build.VERSION.SDK_INT < 31 || c.getSystemService(AlarmManager.class).canScheduleExactAlarms();
    }
    static void install(Context c) {
        NotificationChannel channel = new NotificationChannel(CHANNEL, "Tomas y botiquín", NotificationManager.IMPORTANCE_HIGH);
        channel.setDescription("Recordatorios locales de tomas, existencias, recetas y avisos de medicamentos");
        channel.setLockscreenVisibility(android.app.Notification.VISIBILITY_PRIVATE);
        c.getSystemService(NotificationManager.class).createNotificationChannel(channel);
        PeriodicWorkRequest work = new PeriodicWorkRequest.Builder(BotiquinWorker.class, 15, TimeUnit.MINUTES).build();
        WorkManager.getInstance(c).enqueueUniquePeriodicWork("pastillas-local", ExistingPeriodicWorkPolicy.KEEP, work);
    }
    static void reconcile(Context c) {
        AlarmManager manager = c.getSystemService(AlarmManager.class);
        long at = Long.parseLong(RuntimeApi.call(c, "next_alarm"));
        Intent intent = new Intent(c, ReminderReceiver.class).setAction(ALARM_ACTION).putExtra("scheduled_at", at);
        PendingIntent pending = PendingIntent.getBroadcast(c, 1, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        manager.cancel(pending);
        if (!enabled(c) || !permitted(c) || at <= 0) return;
        long when = Math.max(System.currentTimeMillis() + 1000, at * 1000);
        try {
            if (exact(c)) manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, when, pending);
            else manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, when, pending);
        } catch (SecurityException revoked) {
            manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, when, pending);
        }
    }
    static void tick(Context c, long alarmAt) throws Exception {
        JSONArray alerts = new JSONArray(RuntimeApi.call(c, "tick", alarmAt));
        if (enabled(c) && permitted(c)) {
            JSONArray delivered = new JSONArray();
            Intent intent = new Intent(c, MainActivity.class).putExtra("route", "alerts");
            PendingIntent open = PendingIntent.getActivity(c, 2, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            for (int i = 0; i < alerts.length(); i++) {
                JSONObject alert = alerts.getJSONObject(i);
                NotificationCompat.Builder notification = new NotificationCompat.Builder(c, CHANNEL)
                    .setSmallIcon(R.drawable.ic_notification).setContentTitle(alert.getString("title"))
                    .setContentText(alert.getString("message"))
                    .setStyle(new NotificationCompat.BigTextStyle().bigText(alert.getString("message")))
                    .setContentIntent(open).setAutoCancel(true).setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
                    .setCategory(NotificationCompat.CATEGORY_REMINDER).setOnlyAlertOnce(true);
                try {
                    NotificationManagerCompat.from(c).notify(alert.getInt("id"), notification.build());
                    delivered.put(alert.getInt("id"));
                } catch (SecurityException permissionRevoked) {
                    // El permiso puede revocarse después de comprobarlo. No marcar como entregado.
                    break;
                }
            }
            RuntimeApi.call(c, "mark_notified", delivered.toString());
        }
        reconcile(c);
    }
    private ReminderScheduler() { }
}
