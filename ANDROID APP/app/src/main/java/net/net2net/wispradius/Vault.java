package net.net2net.wispradius;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** All credentials and cached records stay encrypted with a non-exportable device key. */
final class Vault {
  private final Context context;

  Vault(Context context) {
    this.context = context;
  }

  private SecretKey key() throws Exception {
    KeyStore store = KeyStore.getInstance("AndroidKeyStore");
    store.load(null);
    if (!store.containsAlias("wisp-radius")) {
      KeyGenerator generator = KeyGenerator.getInstance("AES", "AndroidKeyStore");
      generator.init(
          new KeyGenParameterSpec.Builder(
                  "wisp-radius", KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
              .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
              .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
              .build());
      generator.generateKey();
    }
    return (SecretKey) store.getKey("wisp-radius", null);
  }

  JSONObject load() {
    try {
      String value = context.getSharedPreferences("vault", 0).getString("state", "");
      if (value.isEmpty()) return new JSONObject();
      String[] parts = value.split(":");
      Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
      cipher.init(
          Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], 0)));
      return new JSONObject(
          new String(
              cipher.doFinal(Base64.decode(parts[1], 0)), java.nio.charset.StandardCharsets.UTF_8));
    } catch (Exception ignored) {
      return new JSONObject();
    }
  }

  synchronized void save(JSONObject value) {
    try {
      Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
      cipher.init(Cipher.ENCRYPT_MODE, key());
      String encrypted =
          Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)
              + ":"
              + Base64.encodeToString(
                  cipher.doFinal(
                      value.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)),
                  Base64.NO_WRAP);
      if (!context.getSharedPreferences("vault", 0).edit().putString("state", encrypted).commit())
        throw new IllegalStateException("Could not save login on this phone");
    } catch (Exception e) {
      throw new IllegalStateException("Could not encrypt saved settings", e);
    }
  }
}
