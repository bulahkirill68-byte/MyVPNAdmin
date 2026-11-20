package com.realitycontrol.vpn;

import android.content.Context;
import android.content.Intent;
import android.content.pm.*;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import java.util.*;

final class AppCatalog {
    static final class Entry {
        final String name, packageName;
        final Drawable icon;
        Entry(String name, String packageName, Drawable icon) { this.name = name; this.packageName = packageName; this.icon = icon; }
    }
    static boolean visible(ApplicationInfo app, boolean launchable, boolean internet, String ownPackage) {
        // Keep Chrome/other preinstalled user-facing apps; hide overlays, providers,
        // shared libraries and services which have no launcher activity.
        return app.enabled && launchable && internet && !app.packageName.equals(ownPackage);
    }
    static List<Entry> load(Context context) {
        PackageManager pm = context.getPackageManager(); Set<String> packages = new HashSet<>();
        for (ResolveInfo item : pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0)) if (item.activityInfo != null) packages.add(item.activityInfo.packageName);
        List<Entry> result = new ArrayList<>();
        int size = Math.round(40 * context.getResources().getDisplayMetrics().density);
        for (String pkg : packages) try {
            ApplicationInfo app = pm.getApplicationInfo(pkg, 0);
            if (!visible(app, true, pm.checkPermission(android.Manifest.permission.INTERNET, pkg) == PackageManager.PERMISSION_GRANTED, context.getPackageName())) continue;
            Drawable icon;
            try { icon = pm.getApplicationIcon(app); } catch (RuntimeException e) { icon = pm.getDefaultActivityIcon(); }
            Bitmap image = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888); icon.setBounds(0, 0, size, size); icon.draw(new Canvas(image));
            result.add(new Entry(pm.getApplicationLabel(app).toString(), pkg, new BitmapDrawable(context.getResources(), image)));
        } catch (PackageManager.NameNotFoundException ignored) { }
        result.sort(Comparator.comparing(e -> e.name.toLowerCase(Locale.ROOT)));
        return result;
    }
}
