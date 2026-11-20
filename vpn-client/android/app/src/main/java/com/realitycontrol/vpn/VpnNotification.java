package com.realitycontrol.vpn;

import android.app.*;
import android.content.*;
import android.os.Build;

final class VpnNotification {
    static final int ID = 1;
    static final String CHANNEL = "vpn";
    static PendingIntent open(Context c) {
        return PendingIntent.getActivity(c, 0, new Intent(c, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
    static Notification build(Context c, String phase, TrafficMeter.Snapshot traffic, long since) {
        c.getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel(CHANNEL, "VPN-подключение и трафик", NotificationManager.IMPORTANCE_LOW));
        PendingIntent stop = PendingIntent.getService(c, 1, new Intent(c, RealityVpnService.class).setAction("STOP"), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent dismissed = PendingIntent.getBroadcast(c, 2, new Intent(c, NotificationDismissReceiver.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        String status = phase.equals("connected") ? "VPN подключён" : phase.equals("connecting") ? "Подключение VPN…" : "Отключение VPN…";
        String totals = traffic.ready ? TrafficMeter.totals(traffic) : "Ожидание счётчиков…";
        String rates = traffic.stale ? "Статистика задерживается · последние значения сохранены" : TrafficMeter.rates(traffic);
        Notification.Builder b = new Notification.Builder(c, CHANNEL).setSmallIcon(R.drawable.ic_shield)
            .setContentTitle("Reality VPN · " + status).setContentText(totals).setSubText(rates)
            .setStyle(new Notification.BigTextStyle().bigText("Получено: " + TrafficMeter.bytes(traffic.down) + "\nОтправлено: " + TrafficMeter.bytes(traffic.up) + "\n" + rates))
            .setContentIntent(open(c)).setDeleteIntent(dismissed).setOngoing(true).setAutoCancel(false)
            .setOnlyAlertOnce(true).setShowWhen(false).setCategory(Notification.CATEGORY_SERVICE)
            .setVisibility(Notification.VISIBILITY_PUBLIC).setColor(0xffad9af1)
            .addAction(new Notification.Action.Builder(null, "Отключить VPN", stop).build());
        if (since > 0 && phase.equals("connected")) b.setWhen(since).setShowWhen(true).setUsesChronometer(true);
        if (Build.VERSION.SDK_INT >= 31) b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        Notification n = b.build(); n.flags |= Notification.FLAG_ONGOING_EVENT | Notification.FLAG_NO_CLEAR;
        return n;
    }
}
