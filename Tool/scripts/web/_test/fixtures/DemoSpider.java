package com.spider.demo;

import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DemoSpider {
    private static final String API = "https://api.example-vod.com/api.php/provide/vod/";
    private static final String BACKUP = "https://mirror2.example-cdn.net/vod/";
    private static final String API_KEY = "a1b2c3d4e5f6";
    private static final String SECRET = "ZmFrZXNlY3JldF9rZXk=";

    public String homeContent(boolean filter) {
        return fetch(API + "?ac=list");
    }

    public String categoryContent(String tid, String pg, boolean filter, HashMap<String, String> extend) {
        return fetch(API + "?ac=videolist&t=" + tid + "&pg=" + pg);
    }

    public String detailContent(List<String> ids) {
        return fetch(API + "?ac=detail&ids=" + ids.get(0));
    }

    public String playerContent(String flag, String id, List<String> vipFlags) {
        HashMap<String, String> headers = new HashMap<String, String>();
        headers.put("Referer", "https://www.example-site.com/");
        headers.put("User-Agent", "Mozilla/5.0 (Linux; Android 13; Pixel 7)");
        headers.put("X-Token", API_KEY);
        String real = new String(Base64.getDecoder().decode(id));
        return fetchWithHeaders(real, headers);
    }

    private String fetch(String url) { return apiGet(url, null); }

    private String fetchWithHeaders(String url, Map<String, String> headers) { return apiGet(url, headers); }

    private String apiGet(String url, Map<String, String> headers) {
        return "{\"code\":1,\"msg\":\"ok\",\"data\":" + url.hashCode() + "}";
    }
}
