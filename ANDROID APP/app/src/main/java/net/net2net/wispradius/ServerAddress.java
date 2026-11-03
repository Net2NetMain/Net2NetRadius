package net.net2net.wispradius;

import java.net.URI;

final class ServerAddress {
  static String normalize(String input) {
    String value = input.trim();
    if (!value.contains("://")) {
      boolean address = value.matches("[0-9.]+(?::[0-9]+)?/?") || value.startsWith("[");
      value = (address ? "http://" : "https://") + value;
    }
    URI uri = URI.create(value);
    if (!("https".equals(uri.getScheme()) || "http".equals(uri.getScheme()))
        || uri.getHost() == null
        || uri.getUserInfo() != null
        || uri.getQuery() != null
        || uri.getFragment() != null)
      throw new IllegalArgumentException(
          "Enter a server URL or IP address without login details or a query");
    String host = uri.getHost();
    boolean ip = host.matches("[0-9.]+") || host.contains(":");
    int port = uri.getPort();
    if (ip && port == -1) port = 8080;
    String path = uri.getPath() == null ? "" : uri.getPath().replaceAll("/+$", "");
    try {
      return new URI(uri.getScheme(), null, host, port, path, null, null).toString();
    } catch (Exception e) {
      throw new IllegalArgumentException("Invalid server address");
    }
  }
}
