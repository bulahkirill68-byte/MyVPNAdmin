package com.realitycontrol.vpn;

import java.util.Locale;

/** AndroidLibXrayLite returns DELTAS and resets the counters on every query. */
final class TrafficMeter {
    static final class Snapshot {
        final long up, down, sampledAt;
        final double upRate, downRate;
        final boolean ready, stale;
        Snapshot(long up, long down, double upRate, double downRate, long sampledAt, boolean ready, boolean stale) {
            this.up = up; this.down = down; this.upRate = upRate; this.downRate = downRate;
            this.sampledAt = sampledAt; this.ready = ready; this.stale = stale;
        }
        static Snapshot empty() { return new Snapshot(0, 0, 0, 0, 0, false, false); }
        Snapshot stale() { return new Snapshot(up, down, 0, 0, sampledAt, ready, true); }
    }
    private long up, down, previousTime;
    TrafficMeter(long startedAt) { previousTime = startedAt; }
    Snapshot sample(String response, long now) {
        if (response == null) throw new IllegalArgumentException("Missing native statistics");
        long sent = 0, received = 0;
        for (String record : response.split(";")) {
            String[] fields = record.split(",", -1);
            if (fields.length != 3 || !fields[0].equals("proxy")) continue;
            try {
                long value = Long.parseLong(fields[2]); if (value < 0) continue;
                if (fields[1].equals("uplink")) sent = add(sent, value);
                else if (fields[1].equals("downlink")) received = add(received, value);
            } catch (NumberFormatException ignored) { }
        }
        double seconds = Math.max(.001, (now - previousTime) / 1000.0);
        up = add(up, sent); down = add(down, received); previousTime = now;
        return new Snapshot(up, down, sent / seconds, received / seconds, now, true, false);
    }
    private static long add(long a, long b) { return a > Long.MAX_VALUE - b ? Long.MAX_VALUE : a + b; }
    static String bytes(double value) {
        double n = Math.max(0, value); String[] units = {"Б", "КБ", "МБ", "ГБ", "ТБ"}; int unit = 0;
        while (n >= 1024 && unit < units.length - 1) { n /= 1024; unit++; }
        return unit == 0 ? String.format(Locale.ROOT, "%.0f %s", n, units[unit]) : String.format(Locale.ROOT, "%.1f %s", n, units[unit]);
    }
    static String totals(Snapshot s) { return "↓ " + bytes(s.down) + "   ↑ " + bytes(s.up); }
    static String rates(Snapshot s) { return "↓ " + bytes(s.downRate) + "/с   ↑ " + bytes(s.upRate) + "/с"; }
}
