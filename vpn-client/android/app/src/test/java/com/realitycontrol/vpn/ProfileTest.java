package com.realitycontrol.vpn;

import org.json.*;
import org.junit.Test;
import static org.junit.Assert.*;
import java.nio.file.*;

public class ProfileTest {
    private final String uri = "vless://12345678-1234-1234-1234-123456789abc@203.0.113.1:443?security=reality&type=tcp&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&sid=aabb&sni=example.com#Test%20server";
    @Test public void parseAndValidate() throws Exception {
        JSONObject p = Profile.parse(uri);
        assertEquals("firefox", p.getString("fingerprint")); assertEquals("Test server", p.getString("name"));
        assertEquals(443, p.getInt("port"));
        for (String bad : new String[]{uri.replace("reality", "tls"), uri.replace("type=tcp", "type=ws"), uri.replace("sid=aabb", "sid=a"), uri.replace("vless://", "https://"), uri.replace("sni=example.com", "sni=invalid/path")}) {
            assertThrows(Exception.class, () -> Profile.parse(bad));
        }
    }
    @Test public void androidConfigDnsAndRules() throws Exception {
        JSONObject config = new JSONObject(CoreConfig.build(Profile.parse(uri), true));
        assertEquals("tun", config.getJSONArray("inbounds").getJSONObject(0).getString("protocol"));
        assertFalse(config.getJSONArray("inbounds").getJSONObject(0).getJSONObject("settings").has("autoSystemRoutingTable"));
        JSONArray rules = config.getJSONObject("routing").getJSONArray("rules");
        assertEquals("direct", rules.getJSONObject(0).getString("outboundTag"));
        assertTrue(rules.getJSONObject(3).getJSONArray("domain").toString().contains("domain:openai.com"));
        assertFalse(CoreConfig.build(Profile.parse(uri), false).contains("geoip:ru"));
        Path target = Paths.get("build/test-config.json"); Files.createDirectories(target.getParent()); Files.write(target, config.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
}
