package com.realitycontrol.vpn;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class Store {
    private final Context context;
    JSONObject data;
    Store(Context context) throws Exception {
        this.context = context;
        String value = context.getSharedPreferences("vault", 0).getString("encrypted", "");
        if (value.isEmpty()) data = new JSONObject().put("profiles", new JSONArray()).put("selected", "").put("appMode", "all").put("apps", new JSONArray()).put("ruDirect", true);
        else {
            byte[] bytes = Base64.decode(value, Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, bytes, 0, 12));
            data = new JSONObject(new String(cipher.doFinal(bytes, 12, bytes.length - 12), java.nio.charset.StandardCharsets.UTF_8));
        }
    }
    private SecretKey key() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore"); ks.load(null);
        if (!ks.containsAlias("RealityVPNVault")) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder("RealityVPNVault", KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey) ks.getKey("RealityVPNVault", null);
    }
    synchronized void save() throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] encrypted = cipher.doFinal(data.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
        byte[] result = new byte[12 + encrypted.length];
        System.arraycopy(cipher.getIV(), 0, result, 0, 12); System.arraycopy(encrypted, 0, result, 12, encrypted.length);
        if (!context.getSharedPreferences("vault", 0).edit().putString("encrypted", Base64.encodeToString(result, Base64.NO_WRAP)).commit()) throw new Exception("Не удалось сохранить настройки");
    }
    JSONObject selected() throws Exception {
        JSONArray profiles = data.getJSONArray("profiles");
        for (int i = 0; i < profiles.length(); i++) if (profiles.getJSONObject(i).getString("id").equals(data.optString("selected"))) return profiles.getJSONObject(i);
        throw new Exception("Добавьте и выберите сервер");
    }
}
