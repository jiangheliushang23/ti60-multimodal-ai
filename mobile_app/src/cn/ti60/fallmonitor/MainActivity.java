package cn.ti60.fallmonitor;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONObject;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private WebView web;
    private TextView message;
    private String base = "";
    private SharedPreferences prefs;
    private boolean pageFailed = false;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = getSharedPreferences("server", MODE_PRIVATE);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setOnApplyWindowInsetsListener((v, insets) -> { v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom()); return insets; });
        root.setBackgroundColor(Color.rgb(14, 53, 68));
        LinearLayout bar = new LinearLayout(this);
        bar.setBackgroundColor(Color.rgb(14, 53, 68));
        bar.setPadding(dp(16), dp(12), dp(12), dp(12));
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setMinimumHeight(dp(76));

        LinearLayout brand = new LinearLayout(this);
        brand.setGravity(Gravity.CENTER_VERTICAL);
        ImageView shield = new ImageView(this);
        shield.setImageResource(drawable("toolbar_shield"));
        shield.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        LinearLayout.LayoutParams iconLayout = new LinearLayout.LayoutParams(dp(32), dp(36));
        iconLayout.setMarginEnd(dp(10));
        brand.addView(shield, iconLayout);

        LinearLayout labels = new LinearLayout(this); labels.setOrientation(LinearLayout.VERTICAL);
        TextView title = new TextView(this);
        title.setText("安护 · Ti60"); title.setTextSize(18); title.setTextColor(Color.WHITE);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        title.setSingleLine(true); title.setEllipsize(TextUtils.TruncateAt.END);
        title.setIncludeFontPadding(false);
        labels.addView(title, new LinearLayout.LayoutParams(-1, -2));
        TextView subtitle = new TextView(this);
        subtitle.setText("人体跌倒监测"); subtitle.setTextSize(11); subtitle.setTextColor(Color.rgb(164, 205, 208));
        subtitle.setSingleLine(true); subtitle.setEllipsize(TextUtils.TruncateAt.END);
        subtitle.setIncludeFontPadding(false);
        LinearLayout.LayoutParams subtitleLayout = new LinearLayout.LayoutParams(-1, -2);
        subtitleLayout.topMargin = dp(4);
        labels.addView(subtitle, subtitleLayout);
        brand.addView(labels, new LinearLayout.LayoutParams(0, -2, 1));
        LinearLayout.LayoutParams brandLayout = new LinearLayout.LayoutParams(0, -2, 1);
        brandLayout.setMarginEnd(dp(12));
        bar.addView(brand, brandLayout);

        ImageButton refresh = new ImageButton(this);
        refresh.setImageResource(drawable("toolbar_refresh"));
        refresh.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
        refresh.setPadding(dp(12), dp(12), dp(12), dp(12));
        refresh.setBackground(actionBackground());
        refresh.setBackgroundTintList(null);
        refresh.setImageTintList(null);
        refresh.setContentDescription("刷新监控画面");
        refresh.setOnClickListener(v -> { if (!base.isEmpty()) connect(base); else settings(); });
        bar.addView(refresh, new LinearLayout.LayoutParams(dp(44), dp(44)));

        Button setup = new Button(this);
        setup.setText("连接设置"); setup.setTextSize(13); setup.setAllCaps(false);
        setup.setTextColor(Color.rgb(216, 242, 237));
        setup.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        setup.setPadding(dp(12), dp(10), dp(12), dp(10));
        setup.setMinWidth(0); setup.setMinimumWidth(0); setup.setMinHeight(dp(44)); setup.setMinimumHeight(dp(44));
        setup.setStateListAnimator(null); setup.setBackground(actionBackground()); setup.setBackgroundTintList(null);
        setup.setOnClickListener(v -> settings());
        LinearLayout.LayoutParams setupLayout = new LinearLayout.LayoutParams(-2, -2);
        setupLayout.setMarginStart(dp(8));
        bar.addView(setup, setupLayout);
        root.addView(bar, new LinearLayout.LayoutParams(-1, -2));

        View divider = new View(this); divider.setBackgroundColor(Color.rgb(38, 81, 95));
        root.addView(divider, new LinearLayout.LayoutParams(-1, dp(1)));
        message = new TextView(this);
        message.setTextColor(Color.rgb(216, 237, 236)); message.setBackgroundColor(Color.rgb(20, 66, 81));
        message.setPadding(dp(16), dp(12), dp(16), dp(12)); message.setTextSize(13);
        root.addView(message, new LinearLayout.LayoutParams(-1, -2));
        web = new WebView(this); root.addView(web, new LinearLayout.LayoutParams(-1, 0, 1)); setContentView(root);
        WebSettings s = web.getSettings(); s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false); s.setAllowContentAccess(false); s.setSupportMultipleWindows(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW); s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        web.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) { pageFailed = false; }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl(), server = Uri.parse(base);
                return !(target.getScheme().equals(server.getScheme()) && target.getHost() != null && target.getHost().equals(server.getHost()) && target.getPort() == server.getPort());
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) { pageFailed = true; show("连接中断。请确认电脑监控服务运行、手机与电脑连接同一热点，并允许防火墙 TCP 8002；可点刷新重试。"); }
            }
            @Override public void onPageFinished(WebView view, String url) { if (!pageFailed && url.startsWith(base + "/")) { message.setVisibility(View.GONE); } }
        });
        web.setDownloadListener((url, userAgent, disposition, mime, size) -> {
            Uri target = Uri.parse(url), server = Uri.parse(base);
            if (target.getHost() != null && target.getHost().equals(server.getHost())) {
                try { startActivity(new Intent(Intent.ACTION_VIEW, target)); } catch (Exception e) { show("请在手机浏览器打开该服务器地址下载录像。"); }
            }
        });
        base = prefs.getString("base", "");
        if (base.isEmpty()) { show("首次使用请设置电脑服务器地址。电脑与手机须连接同一热点。不要填写 127.0.0.1。"); settings(); }
        else connect(base);
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private int drawable(String name) { return getResources().getIdentifier(name, "drawable", getPackageName()); }
    private RippleDrawable actionBackground() {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(Color.rgb(22, 70, 85)); shape.setCornerRadius(dp(12));
        shape.setStroke(dp(1), Color.rgb(53, 104, 117));
        return new RippleDrawable(ColorStateList.valueOf(Color.rgb(47, 107, 118)), shape, null);
    }
    private void show(String text) { message.setText(text); message.setVisibility(View.VISIBLE); }

    private void settings() {
        EditText input = new EditText(this); input.setSingleLine(true); input.setInputType(17);
        input.setHint("http://电脑的热点IP:8002"); input.setText(base);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("连接监控服务器")
            .setMessage("填写电脑在同一热点下的 IPv4 地址，例如 http://192.168.28.146:8002。无需填写 monitor.html。")
            .setView(input).setNegativeButton("取消", null).setPositiveButton("连接", null).create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            try {
                Uri uri = Uri.parse(input.getText().toString().trim());
                if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) || uri.getHost() == null || uri.getUserInfo() != null
                    || uri.getQuery() != null || uri.getFragment() != null || "127.0.0.1".equals(uri.getHost()) || "localhost".equals(uri.getHost())) throw new IllegalArgumentException();
                base = uri.buildUpon().path("").clearQuery().fragment(null).build().toString();
                dialog.dismiss(); connect(base);
            } catch (Exception e) { input.setError("请填写完整电脑地址，例如 http://192.168.28.146:8002"); }
        }));
        dialog.show();
    }

    private void connect(final String address) {
        show("正在连接 " + address + " …");
        new Thread(() -> {
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(address + "/api/health").openConnection(); c.setConnectTimeout(5000); c.setReadTimeout(5000); c.setInstanceFollowRedirects(false);
                if (c.getResponseCode() != 200) throw new Exception("HTTP " + c.getResponseCode());
                byte[] data = new byte[8192]; int total = 0;
                try (InputStream in = c.getInputStream()) { int n; while (total < data.length && (n = in.read(data, total, data.length - total)) > 0) total += n; }
                JSONObject health = new JSONObject(new String(data, 0, total, "UTF-8"));
                if (!"best-test-ethernet-monitor".equals(health.optString("service")) || !"smart_assist_v1".equals(health.optString("smart_assist"))) throw new Exception("电脑监控服务需要更新");
                runOnUiThread(() -> { if (!address.equals(base)) return; prefs.edit().putString("base", address).apply(); web.loadUrl(address + "/mobile.html"); });
            } catch (Exception e) { runOnUiThread(() -> { if (address.equals(base)) show("连接失败：" + e.getMessage() + "\n请保持电脑服务开启，确认同一热点、IP 和 TCP 8002 防火墙设置，然后点刷新。"); }); }
            finally { if (c != null) c.disconnect(); }
        }, "monitor-connect").start();
    }

    @Override public void onBackPressed() { if (web.canGoBack()) web.goBack(); else super.onBackPressed(); }
    @Override protected void onDestroy() { web.stopLoading(); web.destroy(); super.onDestroy(); }
}
