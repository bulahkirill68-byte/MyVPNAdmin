package com.realitycontrol.vpn;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.net.VpnService;
import android.os.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.file.Files;
import java.util.concurrent.*;
import go.Seq;
import libv2ray.*;

public final class RealityVpnService extends VpnService {
    static volatile String phase = "disconnected", error = "";
    static volatile long since;
    static volatile TrafficMeter.Snapshot traffic = TrafficMeter.Snapshot.empty();
    private static volatile RealityVpnService instance;
    private final ScheduledExecutorService worker = Executors.newSingleThreadScheduledExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private ScheduledFuture<?> statistics;
    private TrafficMeter meter;
    private volatile boolean stopRequested, destroyed;
    private ParcelFileDescriptor tunnel;
    private CoreController core;
    private void broadcast() { sendBroadcast(new Intent(getPackageName() + ".STATE").setPackage(getPackageName())); }
    private void status(String value) { phase = value; broadcast(); VpnTileService.refresh(this); }
    @Override public void onCreate() { super.onCreate(); instance = this; Seq.setContext(getApplicationContext()); }
    static void restoreNotification() {
        RealityVpnService service = instance;
        if (service != null && !service.destroyed) service.main.postDelayed(service::updateNotification, 150);
    }
    private void updateNotification() {
        if (destroyed || phase.equals("disconnected")) return;
        getSystemService(NotificationManager.class).notify(VpnNotification.ID, VpnNotification.build(this, phase, traffic, since));
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || "STOP".equals(intent.getAction())) { stopRequested = true; status("disconnecting"); worker.execute(() -> { stopCore(); stopSelf(); }); return START_NOT_STICKY; }
        if (!"disconnected".equals(phase)) return START_NOT_STICKY;
        stopRequested = false; error = ""; since = 0; traffic = TrafficMeter.Snapshot.empty(); status("connecting");
        PendingIntent open = VpnNotification.open(this);
        Notification notification = VpnNotification.build(this, phase, traffic, 0);
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED); else startForeground(1, notification);
        worker.execute(() -> {
            try {
                if (stopRequested || destroyed) throw new CancellationException();
                Store store = new Store(this); JSONObject profile = store.selected();
                // Capture physical-network DNS before establish() makes our VPN the active network.
                java.util.List<String> underlyingDns = UnderlyingDns.read(this);
                Builder b = new Builder().setSession("Reality VPN · " + profile.getString("name")).setMtu(1400)
                    .addAddress("172.28.64.2", 30).addAddress("fd66:7265:616c::2", 126)
                    .addRoute("0.0.0.0", 0).addRoute("::", 0).addDnsServer("1.1.1.1").setBlocking(false).setConfigureIntent(open);
                if (Build.VERSION.SDK_INT >= 29) b.setMetered(false);
                JSONArray apps = store.data.optJSONArray("apps"); String mode = store.data.optString("appMode", "all");
                if ("allow".equals(mode)) {
                    int count = 0;
                    for (int i = 0; apps != null && i < apps.length(); i++) { String pkg = apps.getString(i); if (!pkg.equals(getPackageName())) { b.addAllowedApplication(pkg); count++; } }
                    if (count == 0) throw new Exception("Выберите хотя бы одно приложение для VPN");
                } else {
                    // Xray sockets originate from our UID, which must remain outside the VPN.
                    b.addDisallowedApplication(getPackageName());
                    if ("bypass".equals(mode)) for (int i = 0; apps != null && i < apps.length(); i++) if (!apps.getString(i).equals(getPackageName())) b.addDisallowedApplication(apps.getString(i));
                }
                File assets = new File(getFilesDir(), "core"); if (!assets.exists() && !assets.mkdirs()) throw new Exception("Не удалось создать каталог ядра");
                for (String name : new String[]{"geoip.dat", "geosite.dat"}) {
                    File target = new File(assets, name);
                    if (!target.exists()) try (var input = getAssets().open(name)) { Files.copy(input, target.toPath()); }
                }
                Libv2ray.initCoreEnv(assets.getAbsolutePath(), "");
                if (stopRequested || destroyed) throw new CancellationException();
                tunnel = b.establish(); if (tunnel == null) throw new Exception("Разрешение VPN отозвано");
                core = Libv2ray.newCoreController(new CoreCallbackHandler() {
                    @Override public long startup() { return 0; }
                    @Override public long shutdown() { return 0; }
                    @Override public long onEmitStatus(long code, String message) { return 0; }
                });
                core.startLoop(CoreConfig.build(profile, store.data.optBoolean("ruDirect", true), underlyingDns), tunnel.getFd());
                if (!core.getIsRunning()) throw new Exception("Ядро Xray не запустилось");
                if (stopRequested || destroyed) throw new CancellationException();
                since = System.currentTimeMillis(); meter = new TrafficMeter(SystemClock.elapsedRealtime()); status("connected");
                main.post(this::updateNotification);
                statistics = worker.scheduleWithFixedDelay(this::sampleTraffic, 1, 1, TimeUnit.SECONDS);
            } catch (Exception e) { if (!(e instanceof CancellationException)) error = "Не удалось подключиться: " + (e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage().replaceAll("(?i)[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}", "[UUID]")); stopCore(); stopSelf(); }
        });
        return START_NOT_STICKY;
    }
    private void sampleTraffic() {
        if (stopRequested || destroyed || core == null || !phase.equals("connected")) return;
        try {
            if (!core.getIsRunning()) { error = "Ядро VPN остановлено"; stopCore(); stopSelf(); return; }
            // This is the only reader: the library resets counters after querying them.
            traffic = meter.sample(core.queryAllOutboundTrafficStats(), SystemClock.elapsedRealtime());
        } catch (Exception e) { traffic = traffic.stale(); }
        broadcast(); main.post(this::updateNotification);
    }
    private void stopCore() {
        stopRequested = true;
        if (statistics != null) { statistics.cancel(false); statistics = null; }
        status("disconnecting");
        if (core != null) { try { core.stopLoop(); } catch (Exception ignored) {} core = null; }
        if (tunnel != null) { try { tunnel.close(); } catch (Exception ignored) {} tunnel = null; }
        since = 0; stopForeground(STOP_FOREGROUND_REMOVE); status("disconnected");
    }
    @Override public void onRevoke() { stopRequested = true; worker.execute(() -> { stopCore(); stopSelf(); }); }
    @Override public void onDestroy() { destroyed = true; stopRequested = true; if (instance == this) instance = null; main.removeCallbacksAndMessages(null); worker.execute(() -> { if (core != null || tunnel != null) stopCore(); }); worker.shutdown(); super.onDestroy(); }
}
