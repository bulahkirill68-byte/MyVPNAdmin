package com.realitycontrol.vpn;

import android.Manifest;
import android.app.PendingIntent;
import android.content.*;
import android.content.pm.PackageManager;
import android.net.VpnService;
import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

public final class VpnTileService extends TileService {
    static final String CONNECT = "com.realitycontrol.vpn.CONNECT";
    static void refresh(Context context) { TileService.requestListeningState(context, new ComponentName(context, VpnTileService.class)); }
    @Override public void onStartListening() { super.onStartListening(); update(); }
    @Override public void onTileAdded() { super.onTileAdded(); update(); }
    private void update() {
        Tile tile = getQsTile(); if (tile == null) return;
        String phase = RealityVpnService.phase;
        boolean busy = phase.equals("connecting") || phase.equals("disconnecting");
        tile.setLabel("Reality VPN");
        tile.setState(busy ? Tile.STATE_UNAVAILABLE : phase.equals("connected") ? Tile.STATE_ACTIVE : Tile.STATE_INACTIVE);
        String description = phase.equals("connected") ? "Подключён" : phase.equals("connecting") ? "Подключение…" : phase.equals("disconnecting") ? "Отключение…" : "Отключён";
        tile.setContentDescription("Reality VPN · " + description);
        if (Build.VERSION.SDK_INT >= 29) tile.setSubtitle(description);
        tile.updateTile();
    }
    @Override public void onClick() { super.onClick(); if (isLocked()) unlockAndRun(this::toggle); else toggle(); }
    private void toggle() {
        try {
            if (RealityVpnService.phase.equals("connected")) { startService(new Intent(this, RealityVpnService.class).setAction("STOP")); return; }
            if (!RealityVpnService.phase.equals("disconnected")) return;
            new Store(this).selected();
            if (VpnService.prepare(this) != null || (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)) { openApp(); return; }
            startForegroundService(new Intent(this, RealityVpnService.class).setAction("START"));
        } catch (Exception e) { openApp(); }
        finally { update(); }
    }
    private void openApp() {
        Intent intent = new Intent(this, MainActivity.class).setAction(CONNECT).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (Build.VERSION.SDK_INT >= 34) startActivityAndCollapse(PendingIntent.getActivity(this, 3, intent, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        else openLegacy(intent);
    }
    // PendingIntent overload was introduced in API 34. This branch only runs on older OS versions.
    @android.annotation.SuppressLint("StartActivityAndCollapseDeprecated")
    private void openLegacy(Intent intent) { startActivityAndCollapse(intent); }
}
