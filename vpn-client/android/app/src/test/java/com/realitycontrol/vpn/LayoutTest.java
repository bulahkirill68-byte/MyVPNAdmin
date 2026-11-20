package com.realitycontrol.vpn;

import android.graphics.Rect;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.robolectric.RobolectricTestRunner;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35, qualifiers = "w320dp-h640dp-mdpi")
public class LayoutTest {
    @Test public void connectActionAndFourEvenTabsOnNarrowScreen() { verifyLayout(320, 640, 1f); }
    @Test public void connectActionAndLabelsWithLargeFont() { verifyLayout(360, 720, 1.3f); }

    private void verifyLayout(int width, int height, float fontScale) {
        RuntimeEnvironment.setFontScale(fontScale);
        try (var controller = Robolectric.buildActivity(MainActivity.class).setup().visible()) {
            MainActivity activity = controller.get();
            View decor = activity.getWindow().getDecorView();
            decor.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
            decor.layout(0, 0, width, height);
            Button connect = activity.findViewById(R.id.vpn_connect);
            assertNotNull(connect); assertEquals("Подключить VPN", connect.getText().toString());
            assertTrue(connect.isEnabled()); assertTrue(connect.isClickable());
            Rect action = new Rect(); assertTrue("Connect button must be visible without scrolling", connect.getGlobalVisibleRect(action));
            assertTrue("Connect button needs a usable touch target", action.height() >= 48);
            LinearLayout nav = activity.findViewById(R.id.vpn_navigation);
            assertEquals(4, nav.getChildCount());
            int firstWidth = nav.getChildAt(0).getWidth();
            Rect navigation = new Rect(); assertTrue(nav.getGlobalVisibleRect(navigation)); assertTrue(action.bottom <= navigation.top);
            String[] labels = {"VPN", "Серверы", "Приложения", "Настройки"};
            for (int i = 0; i < labels.length; i++) {
                LinearLayout tab = (LinearLayout) nav.getChildAt(i);
                assertTrue(Math.abs(firstWidth - tab.getWidth()) <= 1);
                assertTrue(tab.getHeight() >= 48);
                TextView label = (TextView) tab.getChildAt(1);
                assertEquals(labels[i], label.getText().toString());
                assertTrue("Tab text should not wrap", label.getLineCount() <= 1);
                assertTrue("Tab label must fit inside the tab", label.getBottom() <= tab.getHeight());
                assertTrue("Tab must remain inside navigation bounds", tab.getRight() <= nav.getWidth());
            }
        }
    }
}
