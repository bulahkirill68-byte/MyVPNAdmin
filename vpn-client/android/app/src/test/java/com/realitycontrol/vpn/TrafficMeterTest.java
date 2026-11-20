package com.realitycontrol.vpn;

import org.junit.Test;
import static org.junit.Assert.*;

public class TrafficMeterTest {
    @Test public void nativeDeltasAccumulateAndDirectTrafficIsExcluded() {
        TrafficMeter meter = new TrafficMeter(0);
        TrafficMeter.Snapshot first = meter.sample("proxy,uplink,100;proxy,downlink,2048;direct,downlink,99999;", 1000);
        assertEquals(100, first.up); assertEquals(2048, first.down); assertEquals(2048, first.downRate, .01);
        TrafficMeter.Snapshot second = meter.sample("proxy,downlink,512;proxy,uplink,20;", 2000);
        assertEquals(120, second.up); assertEquals(2560, second.down); assertEquals(512, second.downRate, .01);
        TrafficMeter.Snapshot empty = meter.sample("", 3000);
        assertEquals(2560, empty.down); assertEquals(0, empty.downRate, .01); assertTrue(empty.ready);
    }
    @Test public void failuresKeepTotalsAndNextSampleAccountsForElapsedTime() {
        TrafficMeter meter = new TrafficMeter(0);
        TrafficMeter.Snapshot good = meter.sample("proxy,downlink,1024;", 1000);
        assertEquals(1024, good.stale().down); assertTrue(good.stale().stale);
        TrafficMeter.Snapshot recovered = meter.sample("proxy,downlink,1024;proxy,downlink,-999;bad;", 3000);
        assertEquals(2048, recovered.down); assertEquals(512, recovered.downRate, .01);
        assertEquals("2.0 КБ", TrafficMeter.bytes(recovered.down));
        assertThrows(IllegalArgumentException.class, () -> meter.sample(null, 4000));
    }
}
