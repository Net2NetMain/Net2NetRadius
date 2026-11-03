package net.net2net.wispradius;

import static org.junit.Assert.*;

import org.junit.Test;

public class ServerAddressTest {
  @Test
  public void ipUsesDefaultPort() {
    assertEquals("http://192.168.1.2:8080", ServerAddress.normalize("192.168.1.2"));
  }

  @Test
  public void explicitPortIsRetained() {
    assertEquals("http://10.0.0.2:9090", ServerAddress.normalize("10.0.0.2:9090/"));
  }

  @Test
  public void hostnameUsesHttps() {
    assertEquals("https://radius.example.com", ServerAddress.normalize("radius.example.com/"));
  }

  @Test
  public void httpsIsRetained() {
    assertEquals(
        "https://radius.example.com", ServerAddress.normalize("https://radius.example.com"));
  }

  @Test(expected = IllegalArgumentException.class)
  public void rejectsEmbeddedCredentials() {
    ServerAddress.normalize("https://user:password@example.com");
  }

  @Test(expected = IllegalArgumentException.class)
  public void rejectsQuery() {
    ServerAddress.normalize("https://example.com?token=secret");
  }

  @Test(expected = IllegalArgumentException.class)
  public void rejectsOtherProtocols() {
    ServerAddress.normalize("ftp://example.com");
  }
}
