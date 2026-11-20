package com.realitycontrol.vpn;

import org.json.*;
import org.junit.Test;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.List;
import static org.junit.Assert.*;

public class DnsRoutingTest {
    private final String uri = "vless://12345678-1234-1234-1234-123456789abc@203.0.113.1:443?security=reality&type=tcp&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&sid=aabb&sni=example.com#Routing%20test";
    @Test public void yandexDnsAndConnectionsUseTheSameDirectPathBeforeIpLookups() throws Exception {
        JSONObject config = new JSONObject(CoreConfig.build(Profile.parse(uri), true, List.of("192.0.2.53")));
        JSONArray servers = config.getJSONObject("dns").getJSONArray("servers");
        assertEquals("dns-direct", servers.getJSONObject(1).getString("tag"));
        assertEquals("192.0.2.53", servers.getJSONObject(1).getString("address"));
        assertTrue(servers.getJSONObject(1).getBoolean("skipFallback"));
        assertTrue(config.getJSONObject("dns").getBoolean("disableFallbackIfMatch"));
        for (String domain : new String[]{"domain:ya.ru", "domain:yandex.ru", "domain:yastatic.net"}) assertTrue(servers.getJSONObject(1).getJSONArray("domains").toString().contains("\"" + domain + "\""));
        JSONArray rules = config.getJSONObject("routing").getJSONArray("rules");
        int firstIp = Integer.MAX_VALUE, yandex = -1, ai = -1;
        for (int i = 0; i < rules.length(); i++) {
            JSONObject r = rules.getJSONObject(i); if (r.has("ip")) firstIp = Math.min(firstIp, i);
            if (r.has("domain") && r.getJSONArray("domain").toString().contains("\"domain:yandex.ru\"")) { yandex = i; assertEquals("direct", r.getString("outboundTag")); }
            if (r.has("domain") && r.getJSONArray("domain").toString().contains("\"domain:openai.com\"")) { ai = i; assertEquals("proxy", r.getString("outboundTag")); }
        }
        assertTrue(ai >= 0 && ai < yandex && yandex < firstIp);
        assertTrue(config.getJSONArray("inbounds").getJSONObject(0).getJSONObject("sniffing").getBoolean("routeOnly"));
        Path file = Paths.get("build/test-split-dns.json"); Files.createDirectories(file.getParent()); Files.write(file, config.toString().getBytes(StandardCharsets.UTF_8));
    }
    @Test public void disablingRussiaBypassKeepsYandexAndDnsOnTheProxyPath() throws Exception {
        JSONObject config = new JSONObject(CoreConfig.build(Profile.parse(uri), false, List.of("192.0.2.53")));
        assertEquals(1, config.getJSONObject("dns").getJSONArray("servers").length());
        assertEquals("dns-query", config.getJSONObject("dns").getJSONArray("servers").getJSONObject(0).getString("tag"));
        assertFalse(config.toString().contains("domain:yandex.ru"));
        assertFalse(config.toString().contains("geoip:ru"));
    }
}
