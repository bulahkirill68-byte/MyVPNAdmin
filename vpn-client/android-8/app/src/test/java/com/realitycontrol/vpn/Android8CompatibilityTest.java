package com.realitycontrol.vpn;

import android.app.Notification;
import android.content.Intent;
import android.graphics.Rect;
import android.os.Build;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowAlertDialog;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 26, qualifiers = "w360dp-h640dp-mdpi")
public class Android8CompatibilityTest {
    @Before public void reset() { RealityVpnService.phase = "disconnected"; RealityVpnService.error = ""; RealityVpnService.since = 0; RealityVpnService.traffic = TrafficMeter.Snapshot.empty(); }
    @After public void cleanup() { reset(); }

    @Test public void api26ActivityStartsWithVisibleConnectButtonAndFourTabs() {
        assertEquals(26, Build.VERSION.SDK_INT);
        assertEquals(26, RuntimeEnvironment.getApplication().getApplicationInfo().targetSdkVersion);
        try (var controller = Robolectric.buildActivity(MainActivity.class).setup().visible()) {
            MainActivity activity = controller.get();
            View decor = activity.getWindow().getDecorView();
            decor.measure(View.MeasureSpec.makeMeasureSpec(360, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(640, View.MeasureSpec.EXACTLY)); decor.layout(0, 0, 360, 640);
            Button button = activity.findViewById(R.id.vpn_connect);
            assertEquals("Подключить VPN", button.getText().toString()); assertTrue(button.isEnabled());
            Rect rectangle = new Rect(); assertTrue(button.getGlobalVisibleRect(rectangle)); assertTrue(rectangle.height() >= 48);
            LinearLayout nav = activity.findViewById(R.id.vpn_navigation); assertEquals(4, nav.getChildCount());
        }
    }
    @Test public void api26NotificationUsesChannelOngoingFlagsTrafficAndStopAction() {
        TrafficMeter.Snapshot traffic = new TrafficMeter(0).sample("proxy,uplink,1024;proxy,downlink,2048;", 1000);
        Notification n = VpnNotification.build(RuntimeEnvironment.getApplication(), "connected", traffic, System.currentTimeMillis());
        assertEquals("vpn", n.getChannelId());
        assertTrue((n.flags & Notification.FLAG_ONGOING_EVENT) != 0); assertTrue((n.flags & Notification.FLAG_NO_CLEAR) != 0);
        assertTrue(n.extras.getString(Notification.EXTRA_TEXT).contains("2.0 КБ"));
        assertEquals("Отключить VPN", n.actions[0].title);
    }
    @Test public void api26QuickTileOpensSetupThroughLegacyIntentApi() {
        var controller = Robolectric.buildService(VpnTileService.class).create();
        try {
            VpnTileService tile = controller.get(); tile.onStartListening(); tile.onClick();
            Intent launched = Shadows.shadowOf(RuntimeEnvironment.getApplication()).getNextStartedActivity();
            assertNotNull(launched); assertEquals(MainActivity.class.getName(), launched.getComponent().getClassName());
            assertEquals(VpnTileService.CONNECT, launched.getAction());
        } finally { controller.get().onStopListening(); }
    }
    @Test public void api26TileSettingsShowManualAddInstructions() {
        try (var controller = Robolectric.buildActivity(MainActivity.class).setup().visible()) {
            LinearLayout nav = controller.get().findViewById(R.id.vpn_navigation); nav.getChildAt(3).performClick();
            controller.get().findViewById(R.id.add_vpn_tile).performClick();
            assertNotNull(ShadowAlertDialog.getLatestAlertDialog());
            assertTrue(Shadows.shadowOf(ShadowAlertDialog.getLatestAlertDialog()).getMessage().toString().contains("шторку"));
        }
    }
}
