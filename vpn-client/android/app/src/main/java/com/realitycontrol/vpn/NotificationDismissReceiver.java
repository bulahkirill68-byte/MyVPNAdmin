package com.realitycontrol.vpn;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class NotificationDismissReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        // Android 14+ permits swiping away ongoing notifications. Restore the active
        // connection's status without starting or resurrecting a stopped VPN.
        RealityVpnService.restoreNotification();
    }
}
