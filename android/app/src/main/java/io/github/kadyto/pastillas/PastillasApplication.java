package io.github.kadyto.pastillas;

import android.app.Application;

public final class PastillasApplication extends Application {
    @Override public void onCreate() {
        super.onCreate();
        ReminderScheduler.install(this);
    }
}
