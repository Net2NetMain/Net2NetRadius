package net.net2net.wispradius;

import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import java.nio.charset.StandardCharsets;
import java.text.DateFormat;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;

/** Native Android controls throughout; no WebView or embedded website. */
public class MainActivity extends Activity {
  private final ExecutorService worker = Executors.newSingleThreadExecutor();
  private final Handler timer = new Handler(Looper.getMainLooper());
  private Vault vault;
  private JSONObject saved, identity, cache;
  private Api api;
  private LinearLayout root, content, navigation;
  private TextView status, brand;
  private String section = "Overview", query = "";
  private boolean busy, active, offline;
  private int ink, muted, background, surface, accent = Color.rgb(51, 126, 170);
  private Dialog editor;
  private byte[] download;
  private String downloadName;
  private int generation;
  private final Runnable poll =
      new Runnable() {
        @Override
        public void run() {
          if (active && identity != null && !busy && editor == null) refresh();
          timer.postDelayed(this, 15000);
        }
      };

  @Override
  public void onCreate(Bundle state) {
    boolean dark =
        (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
            == Configuration.UI_MODE_NIGHT_YES;
    setTheme(
        dark
            ? android.R.style.Theme_Material_NoActionBar
            : android.R.style.Theme_Material_Light_NoActionBar);
    super.onCreate(state);
    vault = new Vault(this);
    saved = vault.load();
    cache = saved.optJSONObject("cache");
    if (cache == null) cache = new JSONObject();
    identity = saved.optJSONObject("identity");
    if (identity != null) {
      api = new Api(saved.optString("server"));
      section = saved.optString("section", "Overview");
      offline = true;
      shell();
      render();
      refresh();
    } else loginScreen("");
  }

  @Override
  protected void onResume() {
    super.onResume();
    active = true;
    timer.removeCallbacks(poll);
    timer.postDelayed(poll, 15000);
  }

  @Override
  protected void onPause() {
    super.onPause();
    active = false;
    timer.removeCallbacks(poll);
  }

  @Override
  protected void onDestroy() {
    super.onDestroy();
    generation++;
    worker.shutdownNow();
    timer.removeCallbacks(poll);
  }

  private int dp(float value) {
    return Math.round(value * getResources().getDisplayMetrics().density);
  }

  private String pretty(String key) {
    String value =
        key.replace('_', ' ')
            .replace("mbps", "Mbps")
            .replace("uisp", "UISP")
            .replace("pppoe", "PPPoE")
            .replace("ip ", "IP ")
            .replace("api ", "API ");
    return value.isEmpty() ? value : Character.toUpperCase(value.charAt(0)) + value.substring(1);
  }

  private void colors() {
    boolean dark =
        (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
            == Configuration.UI_MODE_NIGHT_YES;
    background = Color.parseColor(dark ? "#101A25" : "#F1F5F9");
    surface = Color.parseColor(dark ? "#1B2939" : "#FFFFFF");
    ink = Color.parseColor(dark ? "#EDF5FC" : "#172C43");
    muted = Color.parseColor(dark ? "#A7B9C9" : "#586E80");
    getWindow().setStatusBarColor(background);
    getWindow().setNavigationBarColor(background);
    getWindow()
        .getDecorView()
        .setSystemUiVisibility(dark ? 0 : View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
  }

  private LinearLayout column() {
    LinearLayout box = new LinearLayout(this);
    box.setOrientation(LinearLayout.VERTICAL);
    return box;
  }

  private TextView text(String value, int size, int color) {
    TextView view = new TextView(this);
    view.setText(value);
    view.setTextSize(size);
    view.setTextColor(color);
    view.setPadding(0, dp(5), 0, dp(5));
    return view;
  }

  private GradientDrawable shape(int color) {
    GradientDrawable d = new GradientDrawable();
    d.setColor(color);
    d.setCornerRadius(dp(18));
    return d;
  }

  private LinearLayout card(String title) {
    LinearLayout box = column();
    box.setPadding(dp(18), dp(12), dp(18), dp(16));
    box.setBackground(shape(surface));
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
    params.setMargins(0, 0, 0, dp(12));
    content.addView(box, params);
    if (!title.isEmpty()) box.addView(text(title, 19, ink));
    return box;
  }

  private Button button(String label, Runnable action) {
    Button b = new Button(this);
    b.setText(label);
    b.setTextColor(accent);
    b.setAllCaps(false);
    b.setMinHeight(dp(48));
    b.setOnClickListener(v -> action.run());
    return b;
  }

  private EditText input(LinearLayout parent, String label, String value, boolean secret) {
    parent.addView(text(label, 13, muted));
    EditText edit = new EditText(this);
    edit.setText(value);
    edit.setTextColor(ink);
    edit.setHintTextColor(muted);
    edit.setSingleLine(true);
    edit.setPadding(dp(10), dp(8), dp(10), dp(8));
    edit.setInputType(
        secret
            ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
            : InputType.TYPE_CLASS_TEXT);
    edit.setMinHeight(dp(52));
    parent.addView(edit, new LinearLayout.LayoutParams(-1, -2));
    return edit;
  }

  private void base() {
    colors();
    root = column();
    root.setBackgroundColor(background);
    root.setPadding(dp(16), dp(12), dp(16), dp(6));
    setContentView(root);
    root.setOnApplyWindowInsetsListener(
        (v, insets) -> {
          v.setPadding(
              dp(16) + insets.getSystemWindowInsetLeft(),
              dp(12) + insets.getSystemWindowInsetTop(),
              dp(16) + insets.getSystemWindowInsetRight(),
              dp(6) + insets.getSystemWindowInsetBottom());
          return insets;
        });
  }

  private void loginScreen(String error) {
    identity = null;
    base();
    ScrollView scroll = new ScrollView(this);
    content = column();
    scroll.addView(content);
    root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
    ImageView logo = new ImageView(this);
    logo.setImageResource(R.drawable.net2net_logo);
    logo.setContentDescription("Net2Net");
    logo.setScaleType(ImageView.ScaleType.FIT_CENTER);
    content.addView(logo, new LinearLayout.LayoutParams(-1, dp(150)));
    content.addView(text("WISP Radius", 30, ink));
    content.addView(text("Your connection. Your network.", 16, muted));
    LinearLayout form = card("Sign in to your WISP");
    TextView companyLabel = text(object("branding").optString("company_name", ""), 18, accent);
    form.addView(companyLabel);
    EditText server = input(form, "Server URL or IP address", saved.optString("server"), false);
    server.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
    server.setOnFocusChangeListener(
        (v, focused) -> {
          if (!focused && !server.getText().toString().trim().isEmpty()) {
            String address = server.getText().toString();
            worker.execute(
                () -> {
                  try {
                    JSONObject details = new Api(address).object("/api/branding");
                    runOnUiThread(
                        () -> companyLabel.setText(details.optString("company_name", "")));
                  } catch (Exception ignored) {
                  }
                });
          }
        });
    EditText user = input(form, "Username", saved.optString("username"), false);
    EditText password = input(form, "Password", "", true);
    if (!error.isEmpty()) form.addView(text(error, 14, Color.rgb(199, 65, 65)));
    form.addView(
        button(
            "Sign in",
            () -> {
              if (busy) return;
              try {
                String address = ServerAddress.normalize(server.getText().toString());
                String username = user.getText().toString().trim(),
                    pass = password.getText().toString();
                if (username.isEmpty() || pass.isEmpty())
                  throw new IllegalArgumentException("Enter your username and password");
                busy = true;
                password.setText("");
                worker.execute(
                    () -> {
                      try {
                        Api candidate = new Api(address);
                        JSONObject who = candidate.login(username, pass);
                        runOnUiThread(
                            () -> {
                              busy = false;
                              api = candidate;
                              identity = who;
                              cache = new JSONObject();
                              section = "Overview";
                              saved = new JSONObject();
                              put(saved, "server", address);
                              put(saved, "username", username);
                              put(saved, "password", pass);
                              persist();
                              shell();
                              render();
                              refresh();
                            });
                      } catch (Exception e) {
                        runOnUiThread(
                            () -> {
                              busy = false;
                              loginScreen(message(e));
                            });
                      }
                    });
              } catch (Exception e) {
                toast(message(e));
              }
            }));
    form.addView(
        text(
            "Your existing account determines what you can access. IP addresses use port 8080. Use"
                + " HTTPS when available.",
            13,
            muted));
    content.addView(text("Powered by Net2Net", 13, muted));
  }

  private boolean admin() {
    return identity != null && !identity.optString("role").equals("client");
  }

  private boolean superAdmin() {
    return identity != null && identity.optString("role").equals("super_admin");
  }

  private void shell() {
    base();
    LinearLayout heading = new LinearLayout(this);
    heading.setGravity(Gravity.CENTER_VERTICAL);
    brand = text("WISP Radius", 24, ink);
    heading.addView(brand, new LinearLayout.LayoutParams(0, -2, 1));
    heading.addView(button("Account", this::accountDialog));
    root.addView(heading);
    status = text("Connecting…", 12, muted);
    root.addView(status);
    ScrollView scroll = new ScrollView(this);
    content = column();
    scroll.addView(content);
    root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
    HorizontalScrollView nav = new HorizontalScrollView(this);
    nav.setHorizontalScrollBarEnabled(false);
    navigation = new LinearLayout(this);
    nav.addView(navigation);
    root.addView(nav);
    root.addView(text("Powered by Net2Net", 11, muted));
    String[] sections =
        admin()
            ? new String[] {
              "Overview",
              "Subscribers",
              "Live",
              "Packages",
              "Routers",
              "IP pools",
              "Sessions",
              "Speed tests",
              "Settings"
            }
            : new String[] {"Overview", "Usage", "History"};
    for (String name : sections)
      navigation.addView(
          button(
              name,
              () -> {
                section = name;
                query = "";
                persist();
                render();
                refresh();
              }));
  }

  private void accountDialog() {
    new AlertDialog.Builder(this)
        .setTitle(identity.optString("display_name", saved.optString("username")))
        .setMessage(saved.optString("server") + "\n\n" + pretty(identity.optString("role")))
        .setPositiveButton("Close", null)
        .setNeutralButton(
            "Sign out / change server",
            (d, w) -> {
              generation++;
              saved.remove("password");
              saved.remove("identity");
              saved.remove("cache");
              cache = new JSONObject();
              vault.save(saved);
              identity = null;
              loginScreen("");
            })
        .show();
  }

  private void persist() {
    put(saved, "identity", identity);
    put(saved, "cache", cache);
    put(saved, "section", section);
    vault.save(saved);
  }

  private static void put(JSONObject object, String key, Object value) {
    try {
      object.put(key, value);
    } catch (JSONException e) {
      throw new IllegalArgumentException(e);
    }
  }

  private JSONObject object(String key) {
    JSONObject result = cache.optJSONObject(key);
    return result == null ? new JSONObject() : result;
  }

  private JSONArray array(String key) {
    JSONArray result = cache.optJSONArray(key);
    return result == null ? new JSONArray() : result;
  }

  private String pathForSection(String name) {
    return switch (name) {
      case "Subscribers" -> "/api/subscribers";
      case "Packages" -> "/api/packages";
      case "Routers" -> "/api/routers";
      case "IP pools" -> "/api/ip-pools";
      case "Sessions" -> "/api/sessions";
      case "Live" -> "/api/sessions/live-traffic";
      case "Speed tests" -> "/api/speed-tests";
      default -> "/api/dashboard";
    };
  }

  private interface Task {
    Object run() throws Exception;
  }

  private interface Done {
    void accept(Object value) throws Exception;
  }

  private void execute(Task task, Done done) {
    if (busy) {
      toast("Please wait for the current request");
      return;
    }
    busy = true;
    int stamp = generation;
    worker.execute(
        () -> {
          Object result = null;
          Exception failure = null;
          try {
            result = task.run();
          } catch (Exception e) {
            failure = e;
          }
          final Object value = result;
          final Exception problem = failure;
          runOnUiThread(
              () -> {
                busy = false;
                if (stamp != generation || isDestroyed()) return;
                if (problem != null) {
                  if (problem instanceof Api.Failure && ((Api.Failure) problem).status == 401) {
                    saved.remove("password");
                    saved.remove("identity");
                    persist();
                    identity = null;
                    saved.remove("identity");
                    vault.save(saved);
                    loginScreen("Please sign in again");
                  } else {
                    offline = true;
                    if (identity != null) {
                      render();
                      status.append(" • Server unavailable");
                    }
                    toast(message(problem));
                  }
                } else
                  try {
                    done.accept(value);
                  } catch (Exception e) {
                    toast(message(e));
                  }
              });
        });
  }

  /** Refresh one snapshot atomically. Mutations never retry automatically. */
  private void refresh() {
    if (busy || identity == null) return;
    String requested = section;
    boolean isAdmin = admin(), isSuper = superAdmin();
    execute(
        () -> {
          if (!authenticated) {
            api.login(saved.optString("username"), saved.optString("password"));
            authenticated = true;
          }
          JSONObject update = new JSONObject();
          try {
            update.put("branding", api.object("/api/branding"));
            if (!isAdmin) {
              update.put("portal", api.object("/api/client/portal"));
              try {
                update.put("usage", api.object("/api/mobile/usage"));
              } catch (Api.Failure e) {
                if (e.status != 404) throw e;
              }
            } else {
              update.put(
                  pathForSection(requested), api.call("GET", pathForSection(requested), null));
              if (requested.equals("Subscribers")) {
                update.put("/api/packages", api.call("GET", "/api/packages", null));
                update.put("/api/ip-pools", api.call("GET", "/api/ip-pools", null));
              }
              if (requested.equals("Settings")) {
                if (isSuper) {
                  update.put("configuration", api.object("/api/system/configuration"));
                  update.put("system", api.object("/api/system/status"));
                  update.put("backups", api.call("GET", "/api/mobile/backups", null));
                  update.put("admins", api.call("GET", "/api/admin/users", null));
                }
              }
              if (!cache.has("schema")) update.put("schema", api.object("/openapi.json"));
            }
          } catch (Api.Failure e) {
            if (e.status == 401) authenticated = false;
            throw e;
          }
          update.put("updated:" + requested, System.currentTimeMillis());
          return update;
        },
        value -> {
          JSONObject update = (JSONObject) value;
          for (Iterator<String> keys = update.keys(); keys.hasNext(); ) {
            String key = keys.next();
            cache.put(key, update.get(key));
          }
          offline = false;
          persist();
          render();
          if (!requested.equals(section)) refresh();
          if (object("branding").optBoolean("has_logo")) loadBrandLogo();
        });
  }

  private boolean authenticated;
  private Bitmap wispLogo;
  private boolean logoLoaded;

  private void loadBrandLogo() {
    if (logoLoaded) return;
    logoLoaded = true;
    worker.execute(
        () -> {
          try {
            byte[] bytes = api.raw("GET", "/api/branding/logo", null, "", false);
            Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            if (bitmap == null) {
              com.caverock.androidsvg.SVG svg =
                  com.caverock.androidsvg.SVG.getFromString(
                      new String(bytes, StandardCharsets.UTF_8));
              bitmap = Bitmap.createBitmap(512, 512, Bitmap.Config.ARGB_8888);
              svg.setDocumentWidth("100%");
              svg.setDocumentHeight("100%");
              svg.renderToCanvas(new Canvas(bitmap));
            }
            Bitmap loaded = bitmap;
            runOnUiThread(
                () -> {
                  wispLogo = loaded;
                });
          } catch (Exception ignored) {
            logoLoaded = false;
          }
        });
  }

  private void render() {
    if (identity == null || content == null) return;
    content.removeAllViews();
    String company = object("branding").optString("company_name", "WISP Radius");
    brand.setText(company);
    long updated = cache.optLong("updated:" + section);
    status.setText(
        updated == 0
            ? (offline ? "No saved data for this screen" : "Loading from server…")
            : (offline ? "Saved data • " : "Updated ")
                + DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.MEDIUM)
                    .format(new Date(updated)));
    if (wispLogo != null) {
      ImageView image = new ImageView(this);
      image.setImageBitmap(wispLogo);
      image.setContentDescription(company + " logo");
      image.setScaleType(ImageView.ScaleType.FIT_CENTER);
      content.addView(image, new LinearLayout.LayoutParams(-1, dp(72)));
    }
    content.addView(text(section, 28, ink));
    if (admin()) {
      if (section.equals("Overview")) adminOverview();
      else if (section.equals("Settings")) settingsScreen();
      else listScreen();
    } else customerScreen();
  }

  private void metric(LinearLayout box, String label, String value) {
    box.addView(text(label, 13, muted));
    box.addView(text(value, 24, ink));
  }

  private String bytes(double value) {
    if (!Double.isFinite(value)) return "Unavailable";
    String[] units = {"B", "KB", "MB", "GB", "TB"};
    int i = 0;
    while (value >= 1024 && i < 4) {
      value /= 1024;
      i++;
    }
    return String.format(Locale.ENGLISH, "%.2f %s", value, units[i]);
  }

  private void customerScreen() {
    JSONObject portal = object("portal"),
        subscriber = portal.optJSONObject("subscriber"),
        pack = portal.optJSONObject("package"),
        live = portal.optJSONObject("live_session");
    if (subscriber == null) {
      card("Your connection")
          .addView(text("Connect to the server to load your statistics.", 15, muted));
      return;
    }
    if (section.equals("Overview")) {
      LinearLayout summary = card(subscriber.optString("display_name"));
      summary.addView(
          text(live == null ? "Offline / live status unavailable" : "● Connected", 18, accent));
      metric(summary, "PPPoE account", subscriber.optString("username"));
      summary.addView(text("IP address: " + subscriber.optString("framed_ip_address"), 15, muted));
      if (pack != null) {
        metric(summary, "Package", pack.optString("name"));
        summary.addView(
            text(
                "↓ "
                    + pack.optString("advertised_down_mbps")
                    + " Mbps   ↑ "
                    + pack.optString("advertised_up_mbps")
                    + " Mbps",
                17,
                ink));
      }
      LinearLayout speeds = card("Live connection");
      metric(
          speeds,
          "Download",
          live == null
              ? "Unavailable"
              : String.format(
                  Locale.ENGLISH, "%.2f Mbps", live.optDouble("download_bps") / 1_000_000));
      metric(
          speeds,
          "Upload",
          live == null
              ? "Unavailable"
              : String.format(
                  Locale.ENGLISH, "%.2f Mbps", live.optDouble("upload_bps") / 1_000_000));
      if (live != null) {
        speeds.addView(text("Connected for " + live.optString("uptime"), 15, muted));
        speeds.addView(
            text(
                "This connection: ↓ "
                    + bytes(live.optDouble("download_bytes"))
                    + "  ↑ "
                    + bytes(live.optDouble("upload_bytes")),
                15,
                muted));
      }
      speeds.addView(text("Automatically refreshes every 15 seconds while open.", 12, muted));
    } else if (section.equals("Usage")) {
      JSONObject usage = object("usage");
      LinearLayout totals = card("Recorded usage");
      metric(totals, "Download", bytes(usage.optDouble("download_bytes")));
      metric(totals, "Upload", bytes(usage.optDouble("upload_bytes")));
      totals.addView(
          text(
              usage.optString(
                  "note",
                  "Usage history requires the updated server accounting collector. Missing records"
                      + " do not mean zero usage."),
              13,
              muted));
      JSONArray daily = usage.optJSONArray("daily"), monthly = usage.optJSONArray("monthly");
      usageChart("Daily usage", daily);
      usageChart("Monthly usage", monthly);
    } else {
      JSONArray sessions = portal.optJSONArray("sessions");
      if (sessions == null || sessions.length() == 0)
        card("Connection history")
            .addView(
                text(
                    "No recorded sessions yet. History is supplied by the server's RADIUS"
                        + " accounting.",
                    15,
                    muted));
      else
        for (int i = 0; i < sessions.length(); i++) {
          JSONObject row = sessions.optJSONObject(i);
          if (row == null) continue;
          LinearLayout box = card(row.optString("started_at", "Start time unavailable"));
          box.addView(
              text(
                  "Disconnected: "
                      + (row.isNull("stopped_at") ? "Still active" : row.optString("stopped_at")),
                  15,
                  ink));
          box.addView(
              text("Duration: " + row.optLong("session_seconds") / 60 + " minutes", 15, muted));
          box.addView(
              text(
                  "↓ "
                      + bytes(row.optDouble("output_bytes"))
                      + "   ↑ "
                      + bytes(row.optDouble("input_bytes")),
                  16,
                  ink));
        }
    }
  }

  private void usageChart(String title, JSONArray rows) {
    LinearLayout box = card(title);
    if (rows == null || rows.length() == 0) {
      box.addView(text("No accounting history available for this period.", 14, muted));
      return;
    }
    box.addView(new Bars(this, rows), new LinearLayout.LayoutParams(-1, dp(130)));
    for (int i = rows.length() - 1; i >= Math.max(0, rows.length() - 31); i--) {
      JSONObject row = rows.optJSONObject(i);
      if (row != null)
        box.addView(
            text(
                row.optString("period")
                    + "  ↓ "
                    + bytes(row.optDouble("download_bytes"))
                    + "  ↑ "
                    + bytes(row.optDouble("upload_bytes")),
                13,
                muted));
    }
  }

  private final class Bars extends View {
    final JSONArray rows;
    final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

    Bars(Context context, JSONArray rows) {
      super(context);
      this.rows = rows;
      setContentDescription("Usage chart; exact values are listed below");
    }

    @Override
    protected void onDraw(Canvas canvas) {
      super.onDraw(canvas);
      double max = 1;
      for (int i = 0; i < rows.length(); i++) {
        JSONObject r = rows.optJSONObject(i);
        max = Math.max(max, r.optDouble("download_bytes") + r.optDouble("upload_bytes"));
      }
      float width = (float) getWidth() / rows.length();
      for (int i = 0; i < rows.length(); i++) {
        JSONObject r = rows.optJSONObject(i);
        float down = (float) (r.optDouble("download_bytes") / max * getHeight()),
            up = (float) (r.optDouble("upload_bytes") / max * getHeight());
        paint.setColor(accent);
        canvas.drawRect(i * width + 2, getHeight() - down, (i + 1) * width - 2, getHeight(), paint);
        paint.setColor(Color.rgb(88, 187, 186));
        canvas.drawRect(
            i * width + 2, getHeight() - down - up, (i + 1) * width - 2, getHeight() - down, paint);
      }
    }
  }

  private void adminOverview() {
    JSONObject dashboard = object("/api/dashboard");
    LinearLayout box = card("Network at a glance");
    for (String key :
        new String[] {
          "subscribers", "online", "suspended", "unlinked", "routers_online", "routers_total"
        }) metric(box, pretty(key), dashboard.has(key) ? dashboard.optString(key) : "—");
    JSONArray attention = dashboard.optJSONArray("attention");
    if (attention != null)
      for (int i = 0; i < attention.length(); i++)
        card("Needs attention")
            .addView(text(attention.optJSONObject(i).optString("message"), 15, ink));
  }

  private void listScreen() {
    String path = pathForSection(section);
    LinearLayout tools = card("");
    EditText search = input(tools, "Search " + section.toLowerCase(Locale.ENGLISH), query, false);
    tools.addView(
        button(
            "Search",
            () -> {
              query = search.getText().toString().trim();
              render();
            }));
    if (Set.of("Subscribers", "Packages", "Routers", "IP pools").contains(section))
      tools.addView(
          button("+ Add " + section.toLowerCase(Locale.ENGLISH), () -> form(section, null)));
    JSONArray rows = array(path);
    int found = 0;
    for (int i = 0; i < rows.length(); i++) {
      JSONObject row = rows.optJSONObject(i);
      if (row == null
          || (!query.isEmpty()
              && !row.toString()
                  .toLowerCase(Locale.ENGLISH)
                  .contains(query.toLowerCase(Locale.ENGLISH)))) continue;
      found++;
      String title =
          row.optString("username", row.optString("name", "Record " + row.optString("id")));
      LinearLayout box = card(title);
      for (Iterator<String> keys = row.keys(); keys.hasNext(); ) {
        String key = keys.next();
        if (key.contains("password")
            || key.equals("raw_data")
            || key.equals("id")
            || key.equals("username")
            || key.equals("name")) continue;
        Object value = row.opt(key);
        if (value != null && value != JSONObject.NULL)
          box.addView(text(pretty(key) + ": " + value, 14, muted));
      }
      String current = section;
      if (Set.of("Subscribers", "Packages", "Routers", "IP pools").contains(current))
        box.addView(button("Edit", () -> form(current, row)));
      if (current.equals("Subscribers")) {
        box.addView(
            button(
                "Reconnect",
                () ->
                    confirm(
                        "Reconnect " + title + "?",
                        "The active session will disconnect so the router can reconnect it.",
                        null,
                        () ->
                            mutate(
                                "POST",
                                "/api/mobile/subscribers/" + row.optInt("id") + "/reconnect",
                                null))));
        String next = row.optString("status").equals("disabled") ? "active" : "disabled";
        box.addView(
            button(
                next.equals("active") ? "Enable" : "Disable",
                () ->
                    confirm(
                        pretty(next) + " account?",
                        title,
                        null,
                        () ->
                            mutate(
                                "PATCH",
                                path + "/" + row.optInt("id") + "/status",
                                json("status", next)))));
        box.addView(
            button(
                "Delete",
                () ->
                    confirm(
                        "Delete " + title + "?",
                        "This removes the PPPoE account. Connection history remains.",
                        "Delete",
                        () ->
                            mutate(
                                "DELETE",
                                path + "/" + row.optInt("id"),
                                json("confirmation", "Delete")))));
      }
      if (current.equals("Packages"))
        box.addView(
            button(
                "Delete",
                () ->
                    confirm(
                        "Delete package?",
                        title,
                        "Delete",
                        () -> mutate("DELETE", path + "/" + row.optInt("id"), null))));
      if (current.equals("Routers")) {
        box.addView(
            button(
                "Test connection",
                () -> mutate("POST", path + "/" + row.optInt("id") + "/test", null)));
        box.addView(
            button(
                "Enable single session per host",
                () ->
                    confirm(
                        "Apply single-session guard?",
                        "Updates PPPoE servers on this router.",
                        null,
                        () ->
                            mutate(
                                "POST",
                                path + "/" + row.optInt("id") + "/pppoe-single-session",
                                null))));
      }
      if (current.equals("Live"))
        box.addView(
            button(
                "Reconnect",
                () ->
                    confirm(
                        "Reconnect " + title + "?",
                        "The router will reconnect this session.",
                        null,
                        () ->
                            mutate(
                                "POST",
                                path
                                    + "/"
                                    + row.optInt("router_id")
                                    + "/"
                                    + Uri.encode(row.optString("username"))
                                    + "/disconnect",
                                null))));
      if (current.equals("Sessions") && row.isNull("stopped_at"))
        box.addView(
            button(
                "Reconnect",
                () ->
                    confirm(
                        "Reconnect session?",
                        title,
                        null,
                        () ->
                            mutate("POST", path + "/" + row.optInt("id") + "/disconnect", null))));
    }
    if (found == 0)
      card("No records").addView(text("No matching records in the last loaded data.", 15, muted));
  }

  private JSONObject json(String key, Object value) {
    JSONObject result = new JSONObject();
    put(result, key, value);
    return result;
  }

  private void mutate(String method, String path, JSONObject body) {
    if (offline) {
      toast("Connect to the server before making changes");
      return;
    }
    execute(
        () -> api.call(method, path, body),
        result -> {
          toast(
              result instanceof JSONObject
                  ? ((JSONObject) result).optString("message", "Saved")
                  : "Saved");
          refresh();
        });
  }

  private void confirm(String title, String description, String required, Runnable action) {
    LinearLayout box = column();
    box.setPadding(dp(24), dp(8), dp(24), dp(8));
    box.addView(text(description, 16, ink));
    EditText typed =
        required == null ? null : input(box, "Type " + required + " to confirm", "", false);
    AlertDialog dialog =
        new AlertDialog.Builder(this)
            .setTitle(title)
            .setView(box)
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Confirm", null)
            .create();
    editor = dialog;
    dialog.setOnDismissListener(d -> editor = null);
    dialog.setOnShowListener(
        d ->
            dialog
                .getButton(-1)
                .setOnClickListener(
                    v -> {
                      if (typed != null && !typed.getText().toString().equals(required)) {
                        typed.setError("Type " + required + " exactly");
                        return;
                      }
                      dialog.dismiss();
                      action.run();
                    }));
    dialog.show();
  }

  private JSONObject schema(String name) {
    JSONObject schemas = object("schema").optJSONObject("components");
    if (schemas != null) schemas = schemas.optJSONObject("schemas");
    return schemas == null ? new JSONObject() : schemas.optJSONObject(name);
  }

  private JSONObject resolve(JSONObject value) {
    if (value == null) return new JSONObject();
    String ref = value.optString("$ref");
    if (!ref.isEmpty()) return schema(ref.substring(ref.lastIndexOf('/') + 1));
    JSONArray any = value.optJSONArray("anyOf");
    if (any != null)
      for (int i = 0; i < any.length(); i++) {
        JSONObject item = any.optJSONObject(i);
        if (!item.optString("type").equals("null")) return resolve(item);
      }
    return value;
  }

  private interface FieldValue {
    Object value() throws Exception;
  }

  private void form(String type, JSONObject existing) {
    String model =
        switch (type) {
          case "Subscribers" -> "Subscriber";
          case "Packages" -> "Package";
          case "Routers" -> "Router";
          case "IP pools" -> "IpPool";
          case "Admins" -> "AppUser";
          default -> type;
        };
    JSONObject definition =
        schema(
            model
                + (model.equals("PlatformConfiguration")
                    ? "Update"
                    : existing == null ? "Create" : "Update"));
    if (definition == null || definition.optJSONObject("properties") == null) {
      toast("Load the server schema first");
      return;
    }
    String endpoint =
        switch (type) {
          case "Admins" -> "/api/admin/users";
          case "PlatformConfiguration" -> "/api/system/configuration";
          default -> pathForSection(type);
        };
    editorForm(
        (existing == null ? "Add " : "Edit ") + type,
        definition,
        existing,
        body -> {
          String method = existing == null ? "POST" : "PATCH",
              path = endpoint + (existing == null ? "" : "/" + existing.optInt("id"));
          if (type.equals("PlatformConfiguration")) {
            method = "PUT";
            path = endpoint;
          }
          String finalMethod = method, finalPath = path;
          if (type.equals("Subscribers")
              && existing != null
              && body.optString("status").equals("disabled"))
            confirm(
                "Disable account?",
                existing.optString("username"),
                null,
                () -> mutate(finalMethod, finalPath, body));
          else mutate(method, path, body);
        });
  }

  private interface BodyDone {
    void accept(JSONObject body);
  }

  private void editorForm(String title, JSONObject definition, JSONObject existing, BodyDone done) {
    LinearLayout fields = column();
    fields.setPadding(dp(20), dp(8), dp(20), dp(12));
    JSONObject properties = definition.optJSONObject("properties");
    JSONArray required = definition.optJSONArray("required");
    Set<String> must = new HashSet<>();
    if (required != null)
      for (int i = 0; i < required.length(); i++) must.add(required.optString(i));
    Map<String, FieldValue> values = new LinkedHashMap<>();
    for (Iterator<String> keys = properties.keys(); keys.hasNext(); ) {
      String key = keys.next();
      JSONObject field = resolve(properties.optJSONObject(key));
      String fieldType = field.optString("type", "string");
      Object initial = existing == null ? field.opt("default") : existing.opt(key);
      if (initial == null || initial == JSONObject.NULL) initial = "";
      if (key.equals("enabled") || key.equals("uisp_link_confirmed")) {
        CheckBox check = new CheckBox(this);
        check.setText(pretty(key));
        check.setTextColor(ink);
        check.setChecked(initial.equals(true));
        fields.addView(check);
        values.put(key, check::isChecked);
        continue;
      }
      JSONArray options = field.optJSONArray("enum");
      if (key.equals("package_id") || key.equals("pool_id")) {
        JSONArray choices = array(key.equals("package_id") ? "/api/packages" : "/api/ip-pools");
        List<String> labels = new ArrayList<>();
        List<Integer> ids = new ArrayList<>();
        labels.add("Choose " + pretty(key.replace("_id", "")));
        ids.add(-1);
        int selected = 0;
        for (int i = 0; i < choices.length(); i++) {
          JSONObject row = choices.optJSONObject(i);
          labels.add(row.optString("name"));
          ids.add(row.optInt("id"));
          if (initial.toString().equals(row.optString("id"))) selected = i + 1;
        }
        fields.addView(text(pretty(key.replace("_id", "")), 13, muted));
        Spinner spin = new Spinner(this);
        spin.setAdapter(adapter(labels));
        spin.setSelection(selected);
        fields.addView(spin);
        values.put(
            key,
            () -> {
              int id = ids.get(spin.getSelectedItemPosition());
              if (id < 0) {
                if (must.contains(key)) throw new IllegalArgumentException("Choose " + pretty(key));
                return null;
              }
              return id;
            });
        continue;
      }
      if (options != null) {
        List<String> labels = new ArrayList<>();
        if (!must.contains(key)) labels.add("Unchanged");
        for (int i = 0; i < options.length(); i++) labels.add(options.optString(i));
        fields.addView(text(pretty(key), 13, muted));
        Spinner spin = new Spinner(this);
        spin.setAdapter(adapter(labels));
        int selected = labels.indexOf(initial.toString());
        spin.setSelection(Math.max(0, selected));
        fields.addView(spin);
        values.put(
            key,
            () ->
                spin.getSelectedItem().equals("Unchanged")
                    ? null
                    : spin.getSelectedItem().toString());
        continue;
      }
      boolean secret = key.contains("password") || key.contains("secret") || key.contains("token");
      EditText edit =
          input(
              fields,
              pretty(key) + (must.contains(key) ? " *" : ""),
              secret ? "" : initial.toString(),
              secret);
      if (fieldType.equals("integer") || fieldType.equals("number"))
        edit.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
      values.put(
          key,
          () -> {
            String value = edit.getText().toString().trim();
            if (value.isEmpty()) {
              if (must.contains(key))
                throw new IllegalArgumentException(pretty(key) + " is required");
              return null;
            }
            return fieldType.equals("integer")
                ? Integer.valueOf(value)
                : fieldType.equals("number") ? Double.valueOf(value) : value;
          });
    }
    ScrollView scroll = new ScrollView(this);
    scroll.addView(fields);
    AlertDialog dialog =
        new AlertDialog.Builder(this)
            .setTitle(title)
            .setView(scroll)
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Save", null)
            .create();
    editor = dialog;
    dialog.setOnDismissListener(d -> editor = null);
    dialog.setOnShowListener(
        d ->
            dialog
                .getButton(-1)
                .setOnClickListener(
                    v -> {
                      try {
                        JSONObject body = new JSONObject();
                        for (String key : values.keySet()) {
                          Object value = values.get(key).value();
                          if (value != null) body.put(key, value);
                        }
                        dialog.dismiss();
                        done.accept(body);
                      } catch (Exception e) {
                        toast(message(e));
                      }
                    }));
    dialog.show();
  }

  private ArrayAdapter<String> adapter(List<String> items) {
    ArrayAdapter<String> adapter =
        new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, items);
    adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
    return adapter;
  }

  private void settingsScreen() {
    LinearLayout branding = card("WISP branding");
    EditText
        company = input(branding, "WISP name", object("branding").optString("company_name"), false),
        hostname =
            input(
                branding,
                "Portal hostname",
                object("branding").optString("portal_hostname"),
                false);
    branding.addView(
        button(
            "Save branding",
            () -> {
              JSONObject body = json("company_name", company.getText().toString());
              put(body, "portal_hostname", hostname.getText().toString());
              mutate("PUT", "/api/branding", body);
            }));
    branding.addView(button("Choose WISP logo", () -> chooseFile(102, "image/*")));
    branding.addView(button("Test UISP connection", () -> mutate("GET", "/api/uisp/status", null)));
    if (!superAdmin()) return;
    LinearLayout config = card("Local platform settings");
    JSONObject current = object("configuration");
    for (Iterator<String> keys = current.keys(); keys.hasNext(); ) {
      String key = keys.next();
      config.addView(text(pretty(key) + ": " + current.optString(key), 14, muted));
    }
    config.addView(button("Edit platform secrets", () -> form("PlatformConfiguration", null)));
    LinearLayout admins = card("Administrators");
    JSONArray users = array("admins");
    for (int i = 0; i < users.length(); i++) {
      JSONObject u = users.optJSONObject(i);
      admins.addView(text(u.optString("username") + " • " + pretty(u.optString("role")), 15, ink));
    }
    admins.addView(button("Add WISP administrator", () -> form("Admins", null)));
    LinearLayout backups = card("Backup and restore");
    backups.addView(
        text(
            "Database backups require the server's secret.key to recover encrypted credentials on"
                + " another server. Preserve the complete appdata folder.",
            13,
            muted));
    backups.addView(
        button("Create database backup", () -> mutate("POST", "/api/system/backups", null)));
    JSONArray files = array("backups");
    for (int i = 0; i < files.length(); i++) {
      JSONObject file = files.optJSONObject(i);
      String name = file.optString("filename");
      backups.addView(button("Download " + name, () -> downloadBackup(name)));
    }
    backups.addView(button("Restore database backup", () -> chooseFile(103, "*/*")));
    LinearLayout imports = card("MikroTik User Manager import");
    imports.addView(button("Choose RouterOS export", () -> chooseFile(104, "*/*")));
  }

  private void chooseFile(int request, String type) {
    if (offline) {
      toast("Connect to the server first");
      return;
    }
    Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
    intent.setType(type);
    intent.addCategory(Intent.CATEGORY_OPENABLE);
    startActivityForResult(intent, request);
  }

  private void downloadBackup(String name) {
    execute(
        () -> api.raw("GET", "/api/system/backups/" + Uri.encode(name), null, "", false),
        value -> {
          download = (byte[]) value;
          downloadName = name;
          Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
          intent.addCategory(Intent.CATEGORY_OPENABLE);
          intent.setType("application/octet-stream");
          intent.putExtra(Intent.EXTRA_TITLE, name);
          startActivityForResult(intent, 101);
        });
  }

  @Override
  protected void onActivityResult(int request, int result, Intent data) {
    super.onActivityResult(request, result, data);
    if (result != RESULT_OK || data == null || data.getData() == null) return;
    Uri uri = data.getData();
    if (request == 101) {
      byte[] bytes = download;
      if (bytes == null) return;
      execute(
          () -> {
            try (java.io.OutputStream out = getContentResolver().openOutputStream(uri)) {
              out.write(bytes);
            }
            return "Saved " + downloadName;
          },
          value -> {
            download = null;
            toast(value.toString());
          });
    }
    if (request == 102)
      execute(
          () -> {
            String type = getContentResolver().getType(uri);
            byte[] bytes = Api.read(getContentResolver().openInputStream(uri), 5_000_000);
            return api.raw(
                "PUT", "/api/branding/logo", bytes, type == null ? "image/png" : type, false);
          },
          value -> {
            logoLoaded = false;
            toast("Logo saved");
            refresh();
          });
    if (request == 103)
      confirm(
          "Restore database?",
          "This replaces the current server database. A safety backup is created first. Keep the"
              + " matching encryption key.",
          "RESTORE",
          () ->
              execute(
                  () -> {
                    byte[] bytes =
                        Api.read(getContentResolver().openInputStream(uri), 256 * 1024 * 1024);
                    return new String(
                        api.raw(
                            "POST", "/api/system/restore", bytes, "application/octet-stream", true),
                        StandardCharsets.UTF_8);
                  },
                  value -> {
                    toast(value.toString());
                    authenticated = false;
                    refresh();
                  }));
    if (request == 104)
      confirm(
          "Import PPPoE accounts?",
          "Existing usernames are skipped. New accounts and packages will be added.",
          null,
          () ->
              execute(
                  () -> {
                    String text =
                        new String(
                            Api.read(getContentResolver().openInputStream(uri), 10_000_000),
                            StandardCharsets.UTF_8);
                    return api.call(
                        "POST", "/api/imports/mikrotik-user-manager", json("export_text", text));
                  },
                  value -> {
                    toast(value.toString());
                    refresh();
                  }));
  }

  private String message(Exception e) {
    return e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
  }

  private void toast(String message) {
    Toast.makeText(this, message, Toast.LENGTH_LONG).show();
  }
}
