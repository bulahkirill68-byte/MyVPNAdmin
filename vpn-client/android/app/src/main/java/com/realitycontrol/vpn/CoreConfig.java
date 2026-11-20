package com.realitycontrol.vpn;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.*;

final class CoreConfig {
    static final String[] AI = {"domain:chatgpt.com", "domain:openai.com", "domain:oaistatic.com", "domain:oaiusercontent.com", "domain:opencode.ai"};
    static final String[] RU = {"geosite:category-ru", "geosite:yandex", "domain:ru", "domain:su", "domain:xn--p1ai", "domain:ya.ru", "domain:yandex.ru", "domain:yandex.com", "domain:yandex.net", "domain:yandex.by", "domain:yandex.kz", "domain:yastatic.net", "domain:vk.com", "domain:vk.me", "domain:userapi.com", "domain:mail.ru", "domain:ok.ru", "domain:ozon.ru", "domain:wildberries.ru"};
    static JSONObject obj(Object... pairs) throws Exception { JSONObject o = new JSONObject(); for (int i = 0; i < pairs.length; i += 2) o.put((String) pairs[i], pairs[i + 1]); return o; }
    static JSONArray arr(Object... values) { JSONArray a = new JSONArray(); for (Object v : values) a.put(v); return a; }
    static JSONObject rule(String key, JSONArray values, String outbound) throws Exception { return obj("type", "field", key, values, "outboundTag", outbound); }
    static String build(JSONObject p, boolean ruDirect) throws Exception { return build(p, ruDirect, Collections.emptyList()); }
    static String build(JSONObject p, boolean ruDirect, List<String> underlyingDns) throws Exception {
        JSONArray rules = arr(
            rule("inboundTag", arr("dns-direct"), "direct"),
            rule("inboundTag", arr("dns-query"), "proxy"),
            obj("type", "field", "inboundTag", arr("tun"), "port", "53", "outboundTag", "dns-out"),
            rule("domain", arr((Object[]) AI), "proxy"),
            rule("domain", arr("full:localhost", "domain:lan", "domain:local", "domain:home.arpa"), "direct")
        );
        // Domain matches must happen before IPOnDemand rules, which can trigger DNS.
        if (ruDirect) rules.put(rule("domain", arr((Object[]) RU), "direct"));
        rules.put(rule("ip", arr("geoip:private"), "direct"));
        if (ruDirect) rules.put(rule("ip", arr("geoip:ru"), "direct"));
        rules.put(obj("type", "field", "network", "tcp,udp", "outboundTag", "proxy"));

        JSONArray servers = arr(obj("address", "https://1.1.1.1/dns-query", "tag", "dns-query", "domains", arr((Object[]) AI)));
        if (ruDirect) {
            Set<String> directServers = new LinkedHashSet<>(underlyingDns);
            // Public Russian resolvers are a fallback when DHCP DNS is unavailable.
            directServers.add("77.88.8.8"); directServers.add("77.88.8.1");
            for (String server : directServers) servers.put(obj("address", server, "tag", "dns-direct", "domains", arr((Object[]) RU), "skipFallback", true, "timeoutMs", 2000));
        }
        JSONObject proxy = obj("tag", "proxy", "protocol", "vless", "settings", obj("vnext", arr(obj("address", p.getString("host"), "port", p.getInt("port"), "users", arr(obj("id", p.getString("uuid"), "encryption", "none", "flow", "xtls-rprx-vision"))))), "streamSettings", obj("network", "tcp", "security", "reality", "realitySettings", obj("serverName", p.getString("sni"), "fingerprint", p.getString("fingerprint"), "publicKey", p.getString("publicKey"), "shortId", p.getString("shortId"), "spiderX", "/")));
        JSONObject direct = obj("tag", "direct", "protocol", "freedom", "settings", obj(), "streamSettings", obj("sockopt", obj("domainStrategy", "UseIP")));
        return obj("log", obj("loglevel", "warning"), "stats", obj(), "policy", obj("system", obj("statsOutboundUplink", true, "statsOutboundDownlink", true)),
            "dns", obj("tag", "dns-query", "servers", servers, "queryStrategy", "UseIPv4", "disableFallbackIfMatch", true),
            "inbounds", arr(obj("tag", "tun", "protocol", "tun", "settings", obj("name", "RealityVPN", "mtu", 1400), "sniffing", obj("enabled", true, "destOverride", arr("http", "tls", "quic"), "routeOnly", true))),
            "outbounds", arr(proxy, direct, obj("tag", "dns-out", "protocol", "dns", "settings", obj())), "routing", obj("domainStrategy", "IPOnDemand", "rules", rules)).toString();
    }
}
