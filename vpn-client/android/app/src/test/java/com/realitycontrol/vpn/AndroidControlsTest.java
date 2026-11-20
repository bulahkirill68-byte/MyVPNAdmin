package com.realitycontrol.vpn;

import android.app.Notification;
import android.content.ComponentName;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.ColorDrawable;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.Config;
import java.lang.reflect.Field;
import java.util.List;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35)
public class AndroidControlsTest {
    @Before public void reset() { RealityVpnService.phase = "disconnected"; RealityVpnService.error = ""; RealityVpnService.since = 0; RealityVpnService.traffic = TrafficMeter.Snapshot.empty(); }
    @After public void cleanup() { reset(); }
    @Test public void notificationIsOngoingAndContainsTotalsSpeedAndStopAction() {
        Context c = RuntimeEnvironment.getApplication();
        TrafficMeter.Snapshot stats = new TrafficMeter(0).sample("proxy,downlink,2048;proxy,uplink,1024;", 1000);
        Notification n = VpnNotification.build(c, "connected", stats, System.currentTimeMillis());
        assertTrue((n.flags & Notification.FLAG_ONGOING_EVENT) != 0); assertTrue((n.flags & Notification.FLAG_NO_CLEAR) != 0);
        assertFalse((n.flags & Notification.FLAG_AUTO_CANCEL) != 0);
        assertTrue(n.extras.getString(Notification.EXTRA_TEXT).contains("2.0 КБ"));
        assertTrue(n.extras.getString(Notification.EXTRA_BIG_TEXT).contains("Отправлено: 1.0 КБ"));
        assertTrue(n.extras.getString(Notification.EXTRA_SUB_TEXT).contains("КБ/с"));
        assertEquals("Отключить VPN", n.actions[0].title); assertNotNull(n.deleteIntent);
        // A dismiss broadcast while disconnected must never start a VPN/service.
        new NotificationDismissReceiver().onReceive(c, new android.content.Intent());
        assertNull(Shadows.shadowOf(RuntimeEnvironment.getApplication()).getNextStartedService());
    }
    @Test public void tileIsProtectedBySystemPermissionAndCanBeAddedFromSettings() throws Exception {
        Context c = RuntimeEnvironment.getApplication();
        ServiceInfo tile = c.getPackageManager().getServiceInfo(new ComponentName(c, VpnTileService.class), PackageManager.GET_META_DATA);
        assertEquals("android.permission.BIND_QUICK_SETTINGS_TILE", tile.permission); assertTrue(tile.exported);
        assertTrue(tile.metaData.getBoolean("android.service.quicksettings.ACTIVE_TILE"));
        try (var controller = Robolectric.buildActivity(MainActivity.class).setup().visible()) {
            LinearLayout nav = controller.get().findViewById(R.id.vpn_navigation); nav.getChildAt(3).performClick();
            assertNotNull(controller.get().findViewById(R.id.add_vpn_tile));
        }
    }
    @Test public void activeTileCanStopVpnWithoutOpeningTheActivity() {
        RealityVpnService.phase = "connected";
        var controller = Robolectric.buildService(VpnTileService.class).create();
        try {
            VpnTileService tile = controller.get(); tile.onStartListening();
            assertEquals(android.service.quicksettings.Tile.STATE_ACTIVE, tile.getQsTile().getState());
            tile.onClick();
            android.content.Intent stop = Shadows.shadowOf(RuntimeEnvironment.getApplication()).getNextStartedService();
            assertNotNull(stop); assertEquals("STOP", stop.getAction());
            assertEquals(RealityVpnService.class.getName(), stop.getComponent().getClassName());
        } finally {
            // Robolectric 4.16's TileService shadow is not a ShadowService; calling
            // Service.onDestroy through it raises a framework-shadow ClassCastException.
            controller.get().onStopListening();
        }
    }
    @Test public void filteringHidesLibrariesAndKeepsPreinstalledBrowsers() {
        ApplicationInfo chrome = new ApplicationInfo(); chrome.enabled = true; chrome.packageName = "com.android.chrome"; chrome.flags = ApplicationInfo.FLAG_SYSTEM;
        assertTrue(AppCatalog.visible(chrome, true, true, "com.realitycontrol.vpn"));
        ApplicationInfo overlay = new ApplicationInfo(); overlay.enabled = true; overlay.packageName = "com.android.cellbroadcast.overlay";
        assertFalse(AppCatalog.visible(overlay, false, true, "com.realitycontrol.vpn"));
        assertFalse(AppCatalog.visible(chrome, true, false, "com.realitycontrol.vpn"));
        chrome.enabled = false; assertFalse(AppCatalog.visible(chrome, true, true, "com.realitycontrol.vpn"));
    }
    @Test public void activityDisplaysActualTotalsAndAppIcons() throws Exception {
        RealityVpnService.phase = "connected"; RealityVpnService.since = System.currentTimeMillis();
        RealityVpnService.traffic = new TrafficMeter(0).sample("proxy,downlink,4096;proxy,uplink,1024;", 1000);
        try (var controller = Robolectric.buildActivity(MainActivity.class).setup().visible()) {
            MainActivity activity = controller.get();
            assertEquals("4.0 КБ", ((TextView) activity.findViewById(R.id.traffic_received)).getText().toString());
            assertEquals("1.0 КБ", ((TextView) activity.findViewById(R.id.traffic_sent)).getText().toString());
            Field entries = MainActivity.class.getDeclaredField("appEntries"); entries.setAccessible(true);
            entries.set(activity, List.of(new AppCatalog.Entry("Chrome", "com.android.chrome", new ColorDrawable(0xff5599ee))));
            LinearLayout nav = activity.findViewById(R.id.vpn_navigation); nav.getChildAt(2).performClick();
            ImageView icon = activity.findViewById(R.id.app_icon); assertNotNull(icon); assertNotNull(icon.getDrawable());
        }
    }
}
