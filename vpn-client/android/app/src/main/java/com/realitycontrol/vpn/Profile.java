package com.realitycontrol.vpn;

import org.json.JSONObject;
import java.net.URI;
import java.net.URLDecoder;
import java.util.HashMap;
import java.util.UUID;

final class Profile {
    static JSONObject parse(String input) throws Exception {
        if (input == null || input.length() > 4096) throw new Exception("Некорректная VLESS-ссылка");
        URI u = new URI(input.trim());
        String uuid = u.getUserInfo();
        if (!"vless".equals(u.getScheme()) || uuid == null || !uuid.matches("(?i)[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")) throw new Exception("Проверьте VLESS UUID");
        String host = u.getHost();
        if (host == null || host.isEmpty()) throw new Exception("Проверьте адрес сервера");
        host = host.replace("[", "").replace("]", "");
        int port = u.getPort() == -1 ? 443 : u.getPort();
        if (port < 1 || port > 65535) throw new Exception("Проверьте порт сервера");
        HashMap<String, String> q = new HashMap<>();
        for (String part : (u.getRawQuery() == null ? "" : u.getRawQuery()).split("&")) {
            String[] kv = part.split("=", 2);
            if (kv.length == 2) q.put(decode(kv[0]), decode(kv[1]));
        }
        if (!"reality".equals(q.get("security")) || !q.getOrDefault("type", "tcp").matches("tcp|raw") || !"xtls-rprx-vision".equals(q.getOrDefault("flow", "xtls-rprx-vision"))) throw new Exception("Нужен VLESS TCP + REALITY + XTLS Vision");
        String pbk = q.getOrDefault("pbk", ""), sid = q.getOrDefault("sid", ""), sni = q.getOrDefault("sni", ""), fp = q.getOrDefault("fp", "firefox");
        if (!pbk.matches("[A-Za-z0-9_-]{43}") || !sid.matches("(?i)([0-9a-f]{2}){0,8}") || !sni.matches("(?i)(?=.{1,253}$)[a-z0-9]([a-z0-9.-]*[a-z0-9])?")) throw new Exception("Проверьте REALITY public key, Short ID и SNI");
        if (!fp.matches("firefox|chrome|safari|edge|randomized")) throw new Exception("Неподдерживаемый fingerprint");
        String name = u.getRawFragment() == null ? host : decode(u.getRawFragment());
        if (name.isEmpty()) name = host;
        return new JSONObject().put("id", UUID.randomUUID().toString()).put("name", name.substring(0, Math.min(80, name.length()))).put("host", host).put("port", port).put("uuid", uuid).put("publicKey", pbk).put("shortId", sid).put("sni", sni).put("fingerprint", fp).put("uri", input.trim());
    }
    private static String decode(String value) throws java.io.UnsupportedEncodingException { return URLDecoder.decode(value.replace("+", "%2B"), "UTF-8"); }
}
