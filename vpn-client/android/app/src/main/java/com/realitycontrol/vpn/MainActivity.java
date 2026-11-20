package com.realitycontrol.vpn;

import android.Manifest;
import android.app.*;
import android.animation.*;
import android.content.*;
import android.content.pm.ApplicationInfo;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.Icon;
import android.net.VpnService;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.util.*;
import java.util.concurrent.*;

public final class MainActivity extends Activity {
    private static final int BG = 0xff10131c, CARD = 0xff1a1f2e, MUTED = 0xff8290ab, TEXT = 0xffe9ecf5, ACCENT = 0xffad9af1;
    private Store store;
    private LinearLayout root, content, nav;
    private TextView status, duration;
    private Button power;
    private ImageButton powerIcon;
    private PowerHaloView halo;
    private TextView received, sent, receiveRate, sendRate, statsNote;
    private ValueAnimator counters;
    private long lastTrafficSample = -1;
    private double displayedUp, displayedDown;
    private String paintedPhase = "";
    private boolean resumed, waitingForNotificationPermission;
    private int renderVersion;
    private List<AppCatalog.Entry> appEntries;
    private final ExecutorService appLoader = Executors.newSingleThreadExecutor();
    private String page = "home";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable clock = new Runnable() { @Override public void run() { updateStatus(); handler.postDelayed(this, 1000); } };
    private final BroadcastReceiver receiver = new BroadcastReceiver() { @Override public void onReceive(Context c, Intent i) { updateStatus(); } };
    private boolean receiverRegistered;
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(BG); getWindow().setNavigationBarColor(BG);
        try { store = new Store(this); render(); handleConnectIntent(); }
        catch (Exception e) { new AlertDialog.Builder(this).setTitle("Ошибка хранилища").setMessage("Не удалось открыть зашифрованные профили. Данные сохранены без изменений.").setPositiveButton("Закрыть", (d, w) -> finish()).show(); }
    }
    @Override protected void onResume() {
        super.onResume();
        resumed = true; if (halo != null) halo.setMotionAllowed(true);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, new IntentFilter(getPackageName() + ".STATE"), Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(receiver, new IntentFilter(getPackageName() + ".STATE"));
        receiverRegistered = true; handler.post(clock);
    }
    @Override protected void onPause() { super.onPause(); resumed = false; handler.removeCallbacks(clock); if (halo != null) halo.setMotionAllowed(false); if (counters != null) counters.cancel(); lastTrafficSample = -1; if (receiverRegistered) { unregisterReceiver(receiver); receiverRegistered = false; } }
    @Override protected void onDestroy() { appLoader.shutdownNow(); if (counters != null) counters.cancel(); super.onDestroy(); }
    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); handleConnectIntent(); }
    private void handleConnectIntent() { if (VpnTileService.CONNECT.equals(getIntent().getAction())) { getIntent().setAction(null); handler.post(() -> { if (idle() && store != null) requestConnection(); }); } }
    private int dp(float n) { return (int) (n * getResources().getDisplayMetrics().density + .5f); }
    private GradientDrawable background(int color, int radius) { GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(radius)); return d; }
    private TextView text(String value, int size, int color) { TextView t = new TextView(this); t.setText(value); t.setTextSize(size); t.setTextColor(color); t.setPadding(0, dp(5), 0, dp(5)); return t; }
    private Button button(String value, boolean primary, Runnable click) { Button b = new Button(this); b.setText(value); b.setTextSize(13); b.setAllCaps(false); b.setTextColor(primary ? 0xff211a3a : TEXT); b.setBackground(background(primary ? ACCENT : 0xff2b3146, 12)); b.setPadding(dp(15), dp(4), dp(15), dp(4)); b.setMinHeight(dp(46)); b.setOnClickListener(v -> click.run()); pressAnimation(b); return b; }
    private void pressAnimation(View view) { StateListAnimator states = new StateListAnimator(); AnimatorSet down = new AnimatorSet(); down.playTogether(ObjectAnimator.ofFloat(view, "scaleX", .97f), ObjectAnimator.ofFloat(view, "scaleY", .97f)); down.setDuration(110); AnimatorSet up = new AnimatorSet(); up.playTogether(ObjectAnimator.ofFloat(view, "scaleX", 1f), ObjectAnimator.ofFloat(view, "scaleY", 1f)); up.setDuration(160); states.addState(new int[]{android.R.attr.state_pressed}, down); states.addState(new int[]{}, up); view.setStateListAnimator(states); }
    private LinearLayout column() { LinearLayout l = new LinearLayout(this); l.setOrientation(LinearLayout.VERTICAL); return l; }
    private LinearLayout card() { LinearLayout l = column(); l.setPadding(dp(20), dp(18), dp(20), dp(18)); l.setBackground(background(CARD, 20)); LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.bottomMargin = dp(16); l.setLayoutParams(p); return l; }
    private void gap(LinearLayout l, int height) { l.addView(new android.view.View(this), new LinearLayout.LayoutParams(1, dp(height))); }
    private void title(String eyebrow, String title, String note) { TextView e = text(eyebrow, 10, ACCENT); e.setLetterSpacing(.17f); content.addView(e); TextView h = text(title, 30, TEXT); h.setTypeface(null, Typeface.BOLD); content.addView(h); content.addView(text(note, 13, MUTED)); gap(content, 22); }
    private void render() {
        ++renderVersion; if (counters != null) counters.cancel();
        status = null; duration = null; power = null; powerIcon = null; halo = null; received = null; sent = null; lastTrafficSample = -1; paintedPhase = "";
        root = column(); root.setBackgroundColor(BG); setContentView(root);
        root.setOnApplyWindowInsetsListener((v, insets) -> { if (Build.VERSION.SDK_INT >= 30) { var bars = insets.getInsets(WindowInsets.Type.systemBars()); root.setPadding(bars.left, bars.top, bars.right, bars.bottom); } else root.setPadding(0, insets.getSystemWindowInsetTop(), 0, insets.getSystemWindowInsetBottom()); return insets; });
        root.requestApplyInsets();
        TextView brand = text("◈  REALITY VPN", 16, TEXT); brand.setLetterSpacing(.12f); brand.setPadding(dp(24), dp(18), dp(24), dp(18)); root.addView(brand);
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        content = column(); content.setPadding(dp(24), dp(8), dp(24), dp(16)); scroll.addView(content);
        try { if (page.equals("profiles")) profiles(); else if (page.equals("apps")) apps(); else if (page.equals("settings")) settings(); else home(); }
        catch (Exception e) { showError(e); }
        nav = new LinearLayout(this); nav.setId(R.id.vpn_navigation); nav.setPadding(dp(8), dp(10), dp(8), dp(12)); nav.setBackgroundColor(0xff141925); root.addView(nav);
        String[][] tabs = {{"home", "VPN"}, {"profiles", "Серверы"}, {"apps", "Приложения"}, {"settings", "Настройки"}};
        int[] icons = {R.drawable.ic_shield, R.drawable.ic_servers, R.drawable.ic_apps, R.drawable.ic_settings};
        for (int i = 0; i < tabs.length; i++) {
            String destination = tabs[i][0], label = tabs[i][1];
            boolean selected = page.equals(destination);
            LinearLayout tab = column(); tab.setGravity(Gravity.CENTER); tab.setPadding(dp(2), dp(8), dp(2), dp(8)); tab.setMinimumHeight(dp(64));
            tab.setBackground(background(selected ? 0xff302943 : 0xff141925, 12));
            tab.setContentDescription(label); tab.setClickable(true); tab.setFocusable(true); tab.setSelected(selected);
            tab.setOnClickListener(v -> { page = destination; render(); });
            ImageView icon = new ImageView(this); icon.setImageResource(icons[i]); icon.setColorFilter(selected ? ACCENT : MUTED); icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            tab.addView(icon, new LinearLayout.LayoutParams(dp(22), dp(22)));
            TextView caption = text(label, 11, selected ? ACCENT : MUTED); caption.setGravity(Gravity.CENTER); caption.setSingleLine(true); caption.setPadding(0, dp(5), 0, 0); caption.setEllipsize(android.text.TextUtils.TruncateAt.END); caption.setAutoSizeTextTypeUniformWithConfiguration(8, 11, 1, android.util.TypedValue.COMPLEX_UNIT_SP); caption.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            tab.addView(caption, new LinearLayout.LayoutParams(-1, dp(22)));
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, -2, 1); p.setMargins(dp(2), 0, dp(2), 0); nav.addView(tab, p);
        }
        updateStatus();
        if (resumed && ValueAnimator.areAnimatorsEnabled()) { content.setAlpha(0); content.setTranslationY(dp(5)); content.animate().alpha(1).translationY(0).setDuration(180).start(); }
    }
    private boolean idle() { return "disconnected".equals(RealityVpnService.phase); }
    private void edit(Runnable action) { if (!idle()) toast("Сначала отключите VPN"); else action.run(); }
    private void save() { try { store.save(); } catch (Exception e) { showError(e); } }
    private void home() throws Exception {
        title("БЕЗОПАСНЫЙ ИНТЕРНЕТ", "Свобода подключения.", "Приватный доступ под вашим контролем.");
        LinearLayout c = card(); c.setGravity(Gravity.CENTER_HORIZONTAL);
        status = text("Готов к подключению", 12, MUTED); status.setGravity(Gravity.CENTER); c.addView(status); gap(c, 16);
        powerIcon = new ImageButton(this); powerIcon.setImageResource(R.drawable.ic_power); powerIcon.setColorFilter(0xff211a3a); powerIcon.setPadding(dp(28), dp(28), dp(28), dp(28)); powerIcon.setScaleType(ImageView.ScaleType.FIT_CENTER); powerIcon.setBackground(background(ACCENT, 90)); powerIcon.setContentDescription("Подключить VPN"); powerIcon.setOnClickListener(v -> toggle());
        pressAnimation(powerIcon);
        FrameLayout orb = new FrameLayout(this); halo = new PowerHaloView(this); orb.addView(halo, new FrameLayout.LayoutParams(-1, -1)); orb.addView(powerIcon, new FrameLayout.LayoutParams(dp(112), dp(112), Gravity.CENTER)); c.addView(orb, new LinearLayout.LayoutParams(dp(136), dp(136))); gap(c, 12);
        power = button("Подключить VPN", true, this::toggle); power.setId(R.id.vpn_connect); power.setSingleLine(true); power.setMinWidth(0); power.setMinimumWidth(0); power.setPadding(dp(8), dp(10), dp(8), dp(10));
        c.addView(power, new LinearLayout.LayoutParams(-1, -2)); gap(c, 12);
        TextView heading = text("Ваше личное соединение", 20, TEXT); heading.setGravity(Gravity.CENTER); c.addView(heading);
        duration = text("VLESS + REALITY · XTLS Vision", 12, MUTED); c.addView(duration); gap(c, 12);
        TextView badge = text("VPN / TUN · IPv4 + IPv6", 11, ACCENT); c.addView(badge); content.addView(c);
        LinearLayout trafficCard = card(); LinearLayout columns = new LinearLayout(this);
        LinearLayout download = column(), upload = column(); download.addView(text("↓  Получено", 12, MUTED)); upload.addView(text("↑  Отправлено", 12, MUTED));
        received = text("0 Б", 23, TEXT); received.setId(R.id.traffic_received); sent = text("0 Б", 23, TEXT); sent.setId(R.id.traffic_sent); download.addView(received); upload.addView(sent);
        receiveRate = text("—", 11, MUTED); sendRate = text("—", 11, MUTED); download.addView(receiveRate); upload.addView(sendRate);
        columns.addView(download, new LinearLayout.LayoutParams(0, -2, 1)); columns.addView(upload, new LinearLayout.LayoutParams(0, -2, 1)); trafficCard.addView(columns);
        statsNote = text("Трафик через VPN-сервер", 10, MUTED); statsNote.setId(R.id.traffic_status); trafficCard.addView(statsNote); content.addView(trafficCard);
        LinearLayout server = card(); server.addView(text("ТЕКУЩИЙ СЕРВЕР", 10, MUTED));
        try { JSONObject p = store.selected(); server.addView(text(p.getString("name"), 19, TEXT)); server.addView(text(p.getString("host") + ":" + p.getInt("port") + " · " + p.getString("fingerprint"), 12, MUTED)); }
        catch (Exception e) { server.addView(text("Добавьте ваш сервер  →", 18, TEXT)); }
        server.setOnClickListener(v -> { page = "profiles"; render(); }); content.addView(server);
        String mode = store.data.optString("appMode", "all");
        content.addView(text("↗  " + (mode.equals("all") ? "VPN для всех приложений" : mode.equals("allow") ? "VPN только для выбранных приложений" : "Выбранные приложения обходят VPN"), 12, MUTED));
        content.addView(text(store.data.optBoolean("ruDirect", true) ? "Российские сайты — напрямую" : "Внешний трафик — через сервер", 12, MUTED));
        content.addView(text("Профили защищены Android Keystore", 10, 0xff59647e));
    }
    private void updateStatus() {
        if (status == null) return;
        String phase = RealityVpnService.phase;
        boolean connected = phase.equals("connected"), idle = phase.equals("disconnected");
        status.setText(connected ? "●  Туннель включён" : phase.equals("connecting") ? "Подключение…" : phase.equals("disconnecting") ? "Отключение…" : RealityVpnService.error.isEmpty() ? "Готов к подключению" : RealityVpnService.error);
        status.setTextColor(connected ? 0xff8ed9ba : MUTED);
        String action = connected ? "Отключить VPN" : idle ? "Подключить VPN" : phase.equals("connecting") ? "Подключение…" : "Отключение…";
        power.setText(action); power.setEnabled(connected || idle);
        powerIcon.setContentDescription(action); powerIcon.setEnabled(connected || idle);
        if (!paintedPhase.equals(phase)) { paintedPhase = phase; power.setBackground(background(connected ? 0xff85d9b7 : ACCENT, 12)); powerIcon.setBackground(background(connected ? 0xff85d9b7 : ACCENT, 90)); halo.setPhase(phase); }
        halo.setMotionAllowed(resumed);
        long s = connected ? (System.currentTimeMillis() - RealityVpnService.since) / 1000 : 0;
        duration.setText(connected ? String.format(Locale.ROOT, "%02d:%02d:%02d", s / 3600, s / 60 % 60, s % 60) : "VLESS + REALITY · XTLS Vision");
        updateTraffic(connected);
    }
    private void updateTraffic(boolean connected) {
        TrafficMeter.Snapshot snapshot = RealityVpnService.traffic;
        receiveRate.setText(connected && snapshot.ready && !snapshot.stale ? TrafficMeter.bytes(snapshot.downRate) + "/с" : "—");
        sendRate.setText(connected && snapshot.ready && !snapshot.stale ? TrafficMeter.bytes(snapshot.upRate) + "/с" : "—");
        if (connected && snapshot.stale) { long age = snapshot.sampledAt > 0 ? Math.max(0, (SystemClock.elapsedRealtime() - snapshot.sampledAt) / 1000) : 0; statsNote.setText("Статистика задерживается" + (age > 0 ? " · " + age + " с" : "") + ". Значения сохранены."); statsNote.setTextColor(0xffdfb17c); }
        else { statsNote.setText(connected && !snapshot.ready ? "Ожидание счётчиков…" : "Трафик через VPN-сервер · обновление раз в секунду"); statsNote.setTextColor(MUTED); }
        if (lastTrafficSample == snapshot.sampledAt) return;
        if (counters != null) counters.cancel();
        if (lastTrafficSample >= 0 && resumed && ValueAnimator.areAnimatorsEnabled() && (displayedDown != snapshot.down || displayedUp != snapshot.up)) {
            double fromUp = displayedUp, fromDown = displayedDown;
            counters = ValueAnimator.ofFloat(0, 1); counters.setDuration(280);
            counters.addUpdateListener(a -> { float fraction = (float) a.getAnimatedValue(); showTotals(fromUp + (snapshot.up - fromUp) * fraction, fromDown + (snapshot.down - fromDown) * fraction); }); counters.start();
        } else showTotals(snapshot.up, snapshot.down);
        if (resumed && ValueAnimator.areAnimatorsEnabled() && connected) { if (snapshot.downRate > 0) { receiveRate.setAlpha(.45f); receiveRate.animate().alpha(1).setDuration(450).start(); } if (snapshot.upRate > 0) { sendRate.setAlpha(.45f); sendRate.animate().alpha(1).setDuration(450).start(); } }
        lastTrafficSample = snapshot.sampledAt;
    }
    private void showTotals(double up, double down) { displayedUp = up; displayedDown = down; received.setText(TrafficMeter.bytes(down)); sent.setText(TrafficMeter.bytes(up)); }
    private void toggle() {
        if (!idle()) { startService(new Intent(this, RealityVpnService.class).setAction("STOP")); return; }
        requestConnection();
    }
    private void requestConnection() {
        try { store.selected(); if (store.data.optString("appMode").equals("allow") && store.data.getJSONArray("apps").length() == 0) throw new Exception("Выберите хотя бы одно приложение"); }
        catch (Exception e) { showError(e); return; }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) { waitingForNotificationPermission = true; requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 2); return; }
        prepareVpn();
    }
    private void prepareVpn() {
        Intent consent = VpnService.prepare(this);
        if (consent != null) startActivityForResult(consent, 1); else startVpn();
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) { super.onRequestPermissionsResult(request, permissions, results); if (request == 2 && waitingForNotificationPermission) { waitingForNotificationPermission = false; prepareVpn(); } }
    private void startVpn() { startForegroundService(new Intent(this, RealityVpnService.class).setAction("START")); handler.postDelayed(this::updateStatus, 200); }
    @Override protected void onActivityResult(int request, int result, Intent data) { super.onActivityResult(request, result, data); if (request == 1 && result == RESULT_OK) startVpn(); }
    private void profiles() throws Exception {
        title("ВАШИ МАРШРУТЫ", "Мои серверы.", "Импортируйте ссылку из VPN-панели.");
        content.addView(button("＋  Добавить сервер", true, () -> edit(this::importDialog))); gap(content, 20);
        JSONArray profiles = store.data.getJSONArray("profiles");
        for (int i = 0; i < profiles.length(); i++) {
            final int index = i; JSONObject p = profiles.getJSONObject(i); String id = p.getString("id");
            LinearLayout c = card(); c.addView(text(p.getString("name"), 19, TEXT)); c.addView(text(p.getString("host") + ":" + p.getInt("port") + " · " + p.getString("fingerprint"), 12, MUTED)); c.addView(text(p.getString("sni"), 11, MUTED)); gap(c, 10);
            c.addView(button(id.equals(store.data.optString("selected")) ? "✓  Выбран" : "Выбрать", id.equals(store.data.optString("selected")), () -> edit(() -> { try { store.data.put("selected", id); save(); render(); } catch (Exception e) { showError(e); } })));
            TextView actions = text("Скопировать ссылку  ·  Удалить", 12, MUTED); actions.setPadding(0, dp(17), 0, 0); actions.setOnClickListener(v -> new AlertDialog.Builder(this).setItems(new String[]{"Скопировать ссылку", "Удалить профиль"}, (d, which) -> {
                if (which == 0) { ClipboardManager clipboard = getSystemService(ClipboardManager.class); ClipData clip = ClipData.newPlainText("VLESS", p.optString("uri")); if (Build.VERSION.SDK_INT >= 33) { PersistableBundle extras = new PersistableBundle(); extras.putBoolean("android.content.extra.IS_SENSITIVE", true); clip.getDescription().setExtras(extras); } clipboard.setPrimaryClip(clip); toast("Ссылка скопирована"); }
                else edit(() -> { profiles.remove(index); if (id.equals(store.data.optString("selected"))) try { store.data.put("selected", profiles.length() > 0 ? profiles.getJSONObject(0).getString("id") : ""); } catch (Exception e) { showError(e); } save(); render(); });
            }).show()); c.addView(actions); content.addView(c);
        }
    }
    private void importDialog() {
        EditText input = new EditText(this); input.setHint("vless://…"); input.setTextSize(12); input.setMinLines(3); input.setMaxLines(6); input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        LinearLayout wrap = column(); wrap.setPadding(dp(20), dp(12), dp(20), 0); wrap.addView(input);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Новый сервер").setView(wrap).setNeutralButton("Вставить", null).setNegativeButton("Отмена", null).setPositiveButton("Добавить", null).create();
        dialog.setOnShowListener(d -> {
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v -> { ClipboardManager cb = getSystemService(ClipboardManager.class); if (cb.hasPrimaryClip()) input.setText(cb.getPrimaryClip().getItemAt(0).coerceToText(this)); });
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                try { JSONObject p = Profile.parse(input.getText().toString()); JSONArray all = store.data.getJSONArray("profiles"); if (all.length() >= 100) throw new Exception("Максимум 100 профилей"); all.put(p); store.data.put("selected", p.getString("id")); store.save(); dialog.dismiss(); render(); }
                catch (Exception e) { input.setError(e.getMessage()); }
            });
        }); dialog.show();
    }
    private void apps() throws Exception {
        title("SPLIT TUNNELING", "Ваши приложения.", "Выберите, какой трафик пойдёт через VPN.");
        String mode = store.data.optString("appMode", "all");
        String[][] choices = {{"all", "Все приложения"}, {"allow", "Только выбранные — через VPN"}, {"bypass", "Выбранные — без VPN"}};
        LinearLayout modes = card();
        for (String[] choice : choices) {
            RadioButton b = new RadioButton(this); b.setText(choice[1]); b.setTextColor(TEXT); b.setTextSize(13); b.setChecked(mode.equals(choice[0])); b.setOnClickListener(v -> edit(() -> { try { store.data.put("appMode", choice[0]); save(); render(); } catch (Exception e) { showError(e); } })); b.setEnabled(idle()); modes.addView(b);
        }
        content.addView(modes);
        content.addView(text("Приложения с доступом к интернету и значком в меню. Служебные пакеты и библиотеки скрыты. Изменения — после переподключения.", 11, MUTED));
        EditText search = new EditText(this); search.setSingleLine(true); search.setHint("Поиск приложений"); search.setTextSize(13); content.addView(search); gap(content, 10);
        LinearLayout list = column(); content.addView(list);
        Set<String> selected = new HashSet<>(); JSONArray stored = store.data.getJSONArray("apps"); for (int i = 0; i < stored.length(); i++) selected.add(stored.getString(i));
        TextView loading = text("Загрузка приложений…", 12, MUTED); list.addView(loading);
        int version = renderVersion;
        if (appEntries != null) showApps(list, search, appEntries, selected);
        else appLoader.execute(() -> {
            try {
                List<AppCatalog.Entry> entries = AppCatalog.load(this);
                runOnUiThread(() -> { appEntries = entries; if (page.equals("apps") && renderVersion == version && !isFinishing() && !isDestroyed()) showApps(list, search, entries, selected); });
            } catch (Exception e) { runOnUiThread(() -> { if (renderVersion == version && !isDestroyed()) { list.removeAllViews(); list.addView(text("Не удалось загрузить приложения", 12, MUTED)); } }); }
        });
    }
    private void showApps(LinearLayout list, EditText search, List<AppCatalog.Entry> entries, Set<String> selected) {
        Set<String> visible = new HashSet<>(); for (AppCatalog.Entry entry : entries) visible.add(entry.packageName);
        Set<String> hidden = new HashSet<>(selected); hidden.removeAll(visible);
        Runnable populate = () -> {
            list.removeAllViews(); String term = search.getText().toString().trim().toLowerCase(Locale.ROOT);
            if (!hidden.isEmpty()) {
                list.addView(text("В старом выборе есть скрытые пакеты: " + hidden.size(), 11, MUTED));
                Button clean = button("Убрать скрытые из выбора", false, () -> edit(() -> { selected.removeAll(hidden); try { store.data.put("apps", new JSONArray(selected)); store.save(); render(); } catch (Exception e) { showError(e); } })); clean.setEnabled(idle()); list.addView(clean);
            }
            int count = 0;
            for (AppCatalog.Entry app : entries) {
                if (!(app.name + " " + app.packageName).toLowerCase(Locale.ROOT).contains(term)) continue;
                count++;
                LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(0, dp(12), 0, dp(12)); row.setMinimumHeight(dp(64));
                ImageView icon = new ImageView(this); icon.setId(R.id.app_icon); icon.setImageDrawable(app.icon); icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
                LinearLayout.LayoutParams iconParams = new LinearLayout.LayoutParams(dp(40), dp(40)); iconParams.setMarginEnd(dp(12)); row.addView(icon, iconParams);
                LinearLayout info = column(); TextView name = text(app.name, 14, TEXT); name.setSingleLine(true); name.setEllipsize(android.text.TextUtils.TruncateAt.END); info.addView(name);
                TextView pkg = text(app.packageName, 10, MUTED); pkg.setSingleLine(true); pkg.setEllipsize(android.text.TextUtils.TruncateAt.END); info.addView(pkg); row.addView(info, new LinearLayout.LayoutParams(0, -2, 1));
                CheckBox check = new CheckBox(this); check.setContentDescription("VPN для " + app.name); check.setChecked(selected.contains(app.packageName)); check.setEnabled(idle() && !store.data.optString("appMode", "all").equals("all"));
                check.setOnCheckedChangeListener((b, checked) -> { if (checked) selected.add(app.packageName); else selected.remove(app.packageName); try { store.data.put("apps", new JSONArray(selected)); save(); } catch (Exception e) { showError(e); } });
                row.addView(check); row.setOnClickListener(v -> { if (check.isEnabled() && idle()) check.toggle(); }); list.addView(row);
            }
            if (count == 0) list.addView(text("Приложения не найдены", 12, MUTED));
        };
        search.addTextChangedListener(new android.text.TextWatcher() { public void beforeTextChanged(CharSequence s, int start, int count, int after) {} public void onTextChanged(CharSequence s, int start, int before, int count) { populate.run(); } public void afterTextChanged(android.text.Editable e) {} }); populate.run();
    }
    private void settings() {
        title("ПОД ВАШИМ КОНТРОЛЕМ", "Настройки.", "Маршрутизация и приватность.");
        LinearLayout shortcuts = card(); shortcuts.addView(text("Быстрое управление", 16, TEXT)); shortcuts.addView(text("Включайте и выключайте VPN плиткой Reality VPN в шторке быстрых настроек.", 12, MUTED)); Button tile = button("Добавить плитку VPN в шторку", true, this::addTile); tile.setId(R.id.add_vpn_tile); shortcuts.addView(tile); content.addView(shortcuts);
        LinearLayout c = card(); Switch ru = new Switch(this); ru.setText("Российские сайты напрямую"); ru.setTextColor(TEXT); ru.setTextSize(13); ru.setChecked(store.data.optBoolean("ruDirect", true)); ru.setEnabled(idle()); ru.setOnCheckedChangeListener((b, checked) -> { try { store.data.put("ruDirect", checked); save(); } catch (Exception e) { showError(e); } }); c.addView(ru); c.addView(text("Российские домены и IP обходят VPN. OpenAI и OpenCode направляются через сервер.", 12, MUTED)); content.addView(c);
        LinearLayout about = card(); about.addView(text("Reality VPN " + BuildConfig.VERSION_NAME, 19, TEXT)); about.addView(text("Xray 26.11.9 · VLESS REALITY · XTLS Vision", 12, MUTED)); about.addView(text("Профили зашифрованы AES-GCM, ключ хранится в Android Keystore. Приложение не отправляет телеметрию.", 12, MUTED)); about.addView(text("VPN блокирует обычные DNS-запросы от ухода напрямую, обрабатывая их через Xray DoH. При остановке VPN системное соединение восстанавливается.", 12, MUTED)); content.addView(about);
    }
    private void addTile() {
        if (Build.VERSION.SDK_INT >= 33) getSystemService(StatusBarManager.class).requestAddTileService(new ComponentName(this, VpnTileService.class), "Reality VPN", Icon.createWithResource(this, R.drawable.ic_shield), getMainExecutor(), result -> toast(result == StatusBarManager.TILE_ADD_REQUEST_RESULT_TILE_ADDED || result == StatusBarManager.TILE_ADD_REQUEST_RESULT_TILE_ALREADY_ADDED ? "Плитка Reality VPN доступна в шторке" : "Плитку можно добавить через редактирование шторки"));
        else new AlertDialog.Builder(this).setTitle("Плитка Reality VPN").setMessage("Откройте шторку быстрых настроек → редактирование (карандаш) → перетащите Reality VPN к активным кнопкам.").setPositiveButton("Понятно", null).show();
    }
    private void toast(String value) { Toast.makeText(this, value, Toast.LENGTH_SHORT).show(); }
    private void showError(Exception e) { new AlertDialog.Builder(this).setTitle("Reality VPN").setMessage(e.getMessage() == null ? "Ошибка операции" : e.getMessage()).setPositiveButton("Понятно", null).show(); }
}
