package com.realitycontrol.vpn;

import android.content.Context;
import android.net.*;
import java.net.InetAddress;
import java.util.*;

final class UnderlyingDns {
    static List<String> read(Context context) {
        ConnectivityManager cm = context.getSystemService(ConnectivityManager.class);
        if (cm == null) return Collections.emptyList();
        List<Network> candidates = new ArrayList<>();
        Network active = cm.getActiveNetwork(); if (active != null) candidates.add(active);
        for (Network network : cm.getAllNetworks()) if (!candidates.contains(network)) candidates.add(network);
        for (Network network : candidates) {
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps == null || caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) || !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) continue;
            LinkProperties links = cm.getLinkProperties(network); if (links == null) continue;
            List<String> result = new ArrayList<>();
            for (InetAddress address : links.getDnsServers()) {
                if (address.isAnyLocalAddress() || address.isLoopbackAddress() || address.isLinkLocalAddress() || address.isMulticastAddress()) continue;
                result.add(address.getHostAddress()); if (result.size() == 2) break;
            }
            if (!result.isEmpty()) return result;
        }
        return Collections.emptyList();
    }
}
