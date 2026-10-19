package io.github.kadyto.pastillas;

import android.Manifest;
import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.webkit.WebViewAssetLoader;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends ComponentActivity {
    static final String ORIGIN = "https://appassets.androidplatform.net";
    private static final int EXPORT = 10, IMPORT = 11, NOTIFY = 12;
    private final ExecutorService executor = Executors.newFixedThreadPool(2);
    private final ExecutorService remote = Executors.newSingleThreadExecutor();
    private WebView web;
    private boolean destroyed;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        FrameLayout root = new FrameLayout(this);
        ViewCompat.setOnApplyWindowInsetsListener(root, (view, insets) -> {
            androidx.core.graphics.Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout() | WindowInsetsCompat.Type.ime());
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return insets;
        });
        TextView loading = new TextView(this);loading.setText(R.string.loading);loading.setGravity(android.view.Gravity.CENTER);
        root.addView(loading);setContentView(root);
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override public void handleOnBackPressed() { handleBack(); }
        });
        executor.execute(() -> {
            try {
                RuntimeApi.module(this);
                runOnUiThread(() -> { if (!destroyed) openWeb(root); });
            } catch (Exception error) {
                runOnUiThread(() -> loading.setText(R.string.storage_error));
            }
        });
    }

    private void openWeb(FrameLayout root) {
        web = new WebView(this);
        WebSettings s = web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setJavaScriptCanOpenWindowsAutomatically(false);s.setSupportMultipleWindows(false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        WebViewAssetLoader loader = new WebViewAssetLoader.Builder().addPathHandler("/", new WebViewAssetLoader.AssetsPathHandler(this)).build();
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (local(uri)) {
                    WebResourceResponse response = loader.shouldInterceptRequest(uri);
                    if (response != null) {
                        HashMap<String,String> headers = new HashMap<>();
                        headers.put("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'");
                        headers.put("Cache-Control", "no-store");headers.put("X-Content-Type-Options", "nosniff");
                        response.setResponseHeaders(headers);return response;
                    }
                }
                return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found", null, new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (local(request.getUrl())) return false;
                if (request.hasGesture()) openExternal(request.getUrl().toString());
                return true;
            }
        });
        web.addJavascriptInterface(new Bridge(), "AndroidBridge");
        root.removeAllViews();root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        String route = getIntent().getStringExtra("route");
        web.loadUrl(ORIGIN + "/index.html#" + ("alerts".equals(route) ? "alerts" : "today"));
        runMaintenance();
    }

    static boolean local(Uri uri) {
        return "https".equals(uri.getScheme()) && "appassets.androidplatform.net".equals(uri.getHost()) && uri.getPort() == -1 && uri.getUserInfo() == null;
    }
    private void openExternal(String target) {
        Uri uri = Uri.parse(target);
        if (!"https".equals(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null) return;
        runOnUiThread(() -> { try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (ActivityNotFoundException ignored) { message("No hay un navegador disponible para abrir el enlace."); } });
    }
    private void runMaintenance() {
        if (destroyed || executor.isShutdown()) return;
        executor.execute(() -> {
            try {
                ReminderScheduler.tick(this, 0);
                RuntimeApi.sources(this);
            } catch (Exception ignored) { }
        });
    }
    private void message(String value) {
        if (!destroyed) new AlertDialog.Builder(this).setMessage(value).setPositiveButton("Aceptar", null).show();
    }
    private void refreshWeb() {
        runOnUiThread(() -> { if (web != null && !destroyed) web.evaluateJavascript("window.dispatchEvent(new Event('pastillas-native-resume'))", null); });
    }
    @Override protected void onResume() {
        super.onResume();
        if (web != null) { runMaintenance();refreshWeb(); }
    }
    @Override protected void onDestroy() {
        destroyed = true;
        if (web != null) { web.removeJavascriptInterface("AndroidBridge");web.destroy();web = null; }
        executor.shutdown();remote.shutdown();super.onDestroy();
    }
    private void handleBack() {
        if (web == null) { finish();return; }
        web.evaluateJavascript("(function(){const d=document.querySelector('dialog');if(d?.open){d.close();return true;}if(location.hash!=='#today'){location.hash='today';return true;}return false;})()", handled -> { if (!"true".equals(handled)) finish(); });
    }

    public final class Bridge {
        @JavascriptInterface public void request(String identifier, String method, String path, String body) {
            if (identifier == null || !identifier.matches("[0-9]{1,12}") || destroyed) return;
            boolean network = path != null && (path.startsWith("/api/medicine-") || path.matches("/api/medications/[0-9]+/(document|equivalents).*"));
            (network ? remote : executor).execute(() -> {
                String response;
                try { response = RuntimeApi.call(MainActivity.this, "request", method, path, body); }
                catch (Exception error) { response = "{\"status\":500,\"body\":{\"error\":\"No se pudo completar la operación local.\"}}"; }
                String result = response;
                if ("/api/android/erase".equals(path) && result.contains("\"status\": 200"))
                    getSystemService(android.app.NotificationManager.class).cancelAll();
                runOnUiThread(() -> { if (web != null && !destroyed) web.evaluateJavascript("window.PastillasNative.resolve(" + JSONObject.quote(identifier) + "," + JSONObject.quote(result) + ")", null); });
                if (!"GET".equals(method)) runMaintenance();
            });
        }
        @JavascriptInterface public String status() {
            try { return new JSONObject().put("notifications", ReminderScheduler.permitted(MainActivity.this))
                .put("reminders", ReminderScheduler.enabled(MainActivity.this))
                .put("exact", ReminderScheduler.exact(MainActivity.this)).toString(); }
            catch (Exception ignored) { return "{}"; }
        }
        @JavascriptInterface public void setReminders(boolean value) {
            getSharedPreferences("device", MODE_PRIVATE).edit().putBoolean("reminders", value).apply();runMaintenance();
        }
        @JavascriptInterface public void openUrl(String target) { openExternal(target); }
        @JavascriptInterface public void action(String action) {
            runOnUiThread(() -> {
                if (destroyed) return;
                try {
                    switch (action) {
                        case "notifications":
                            if (Build.VERSION.SDK_INT >= 33 && !ReminderScheduler.permitted(MainActivity.this)) requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFY);
                            else startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName()));
                            break;
                        case "notification-settings": startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName()));break;
                        case "exact":
                            if (Build.VERSION.SDK_INT >= 31) startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:" + getPackageName())));
                            break;
                        case "export":
                            startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/json").putExtra(Intent.EXTRA_TITLE, "pastillas-export.json"), EXPORT);break;
                        case "import":
                            startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*").putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/json", "text/plain", "application/octet-stream"}), IMPORT);break;
                        default: break;
                    }
                } catch (ActivityNotFoundException ignored) { message("Esta opción no está disponible en este dispositivo."); }
            });
        }
    }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);runMaintenance();refreshWeb();
    }
    @Override protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        if (result != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if (code == EXPORT) executor.execute(() -> {
            try {
                byte[] bytes = RuntimeApi.call(this, "export_json").getBytes(StandardCharsets.UTF_8);
                try (OutputStream out = getContentResolver().openOutputStream(uri, "wt")) { if (out == null) throw new java.io.IOException();out.write(bytes); }
                runOnUiThread(() -> message("Copia guardada. El archivo contiene tus datos del botiquín; guárdalo en un lugar privado."));
            } catch (Exception error) { runOnUiThread(() -> message("No se pudo guardar la copia. Tus datos siguen en la app.")); }
        });
        if (code == IMPORT) executor.execute(() -> {
            try {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                try (InputStream in = getContentResolver().openInputStream(uri)) {
                    if (in == null) throw new java.io.IOException();
                    byte[] buffer = new byte[8192];int n;
                    while ((n = in.read(buffer)) != -1) { if (out.size() + n > 10 * 1024 * 1024) throw new java.io.IOException();out.write(buffer, 0, n); }
                }
                String raw = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(out.toByteArray())).toString();
                JSONObject parsed = new JSONObject(raw);
                if (!"pastillas".equals(parsed.optString("format")) || parsed.optJSONArray("medications") == null) throw new java.io.IOException();
                int count = parsed.getJSONArray("medications").length();
                runOnUiThread(() -> { if (!destroyed) new AlertDialog.Builder(this).setTitle("Importar botiquín")
                    .setMessage("Se añadirán " + count + " medicamentos y su historial a este teléfono. Los datos actuales se conservan. No se consultará internet para importar.")
                    .setNegativeButton("Cancelar", null).setPositiveButton("Importar", (d, which) -> executor.execute(() -> {
                        try { RuntimeApi.call(this, "import_json", raw);runMaintenance();refreshWeb();runOnUiThread(() -> message("Botiquín importado.")); }
                        catch (Exception error) { runOnUiThread(() -> message("No se ha importado la copia: ya estaba importada o contiene datos no compatibles. El botiquín anterior se conserva.")); }
                    })).show(); });
            } catch (Exception error) { runOnUiThread(() -> message("El archivo no es una copia JSON de Pastillas válida o supera 10 MB.")); }
        });
    }
}
