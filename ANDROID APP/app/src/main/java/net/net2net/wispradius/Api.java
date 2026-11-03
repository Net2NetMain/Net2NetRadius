package net.net2net.wispradius;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import org.json.*;

/** Server-scoped native HTTP client. Never follows redirects with a user's credentials. */
final class Api {
  final String base;
  private String cookie = "";
  private String username = "", password = "";

  Api(String base) {
    this.base = ServerAddress.normalize(base);
  }

  static final class Failure extends IOException {
    final int status;

    Failure(int status, String message) {
      super(message);
      this.status = status;
    }
  }

  byte[] raw(String method, String path, byte[] body, String contentType, boolean restore)
      throws Exception {
    HttpURLConnection connection = (HttpURLConnection) new URL(base + path).openConnection();
    connection.setInstanceFollowRedirects(false);
    connection.setConnectTimeout(10000);
    connection.setReadTimeout(45000);
    connection.setRequestMethod(method);
    connection.setRequestProperty("Accept", "application/json");
    if (!cookie.isEmpty()) connection.setRequestProperty("Cookie", cookie);
    if (restore) connection.setRequestProperty("X-Net2Net-Restore-Confirm", "RESTORE");
    try {
      if (body != null) {
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", contentType);
        connection.setFixedLengthStreamingMode(body.length);
        try (OutputStream out = connection.getOutputStream()) {
          out.write(body);
        }
      }
      int status = connection.getResponseCode();
      String setCookie = connection.getHeaderField("Set-Cookie");
      if (setCookie != null && path.equals("/api/auth/login")) cookie = setCookie.split(";", 2)[0];
      InputStream stream =
          status >= 400 ? connection.getErrorStream() : connection.getInputStream();
      byte[] bytes = stream == null ? new byte[0] : read(stream, 270 * 1024 * 1024);
      if (status < 200 || status >= 300) {
        String message = "Server returned " + status;
        try {
          message =
              new JSONObject(new String(bytes, StandardCharsets.UTF_8)).opt("detail").toString();
        } catch (Exception ignored) {
        }
        if (status >= 300 && status < 400)
          message = "Use the final server URL (redirects are not followed)";
        throw new Failure(status, message);
      }
      return bytes;
    } finally {
      connection.disconnect();
    }
  }

  static byte[] read(InputStream input, int limit) throws IOException {
    try (InputStream in = input;
        ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] buffer = new byte[16384];
      int count;
      while ((count = in.read(buffer)) != -1) {
        if (out.size() + count > limit) throw new IOException("File exceeds the supported size");
        out.write(buffer, 0, count);
      }
      return out.toByteArray();
    }
  }

  Object call(String method, String path, JSONObject data) throws Exception {
    byte[] result;
    try {
      result =
          raw(
              method,
              path,
              data == null ? null : data.toString().getBytes(StandardCharsets.UTF_8),
              "application/json",
              false);
    } catch (Failure e) {
      if (e.status != 401 || !method.equals("GET") || username.isEmpty()) throw e;
      login(username, password);
      result = raw(method, path, null, "application/json", false);
    }
    return result.length == 0
        ? new JSONObject()
        : new JSONTokener(new String(result, StandardCharsets.UTF_8)).nextValue();
  }

  JSONObject object(String path) throws Exception {
    return (JSONObject) call("GET", path, null);
  }

  JSONObject login(String user, String password) throws Exception {
    JSONObject identity =
        (JSONObject)
            call(
                "POST",
                "/api/auth/login",
                new JSONObject().put("username", user).put("password", password));
    this.username = user;
    this.password = password;
    return identity;
  }
}
