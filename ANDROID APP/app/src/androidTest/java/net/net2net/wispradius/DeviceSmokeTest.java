package net.net2net.wispradius;

import android.app.*;
import android.content.Intent;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import java.util.*;
import org.json.JSONObject;

/** Explicit local-test-server runner; never supplies or discovers production credentials. */
public class DeviceSmokeTest extends Instrumentation {
  private Bundle arguments;
  private Activity activity;
  private boolean keepLogin;

  private void capture(String name) throws Exception {
    final android.graphics.Bitmap[] rendered = new android.graphics.Bitmap[1];
    runOnMainSync(
        () -> {
          View view = activity.getWindow().getDecorView();
          rendered[0] =
              android.graphics.Bitmap.createBitmap(
                  view.getWidth(), view.getHeight(), android.graphics.Bitmap.Config.ARGB_8888);
          view.draw(new android.graphics.Canvas(rendered[0]));
        });
    android.graphics.Bitmap bitmap = rendered[0];
    try (java.io.FileOutputStream out =
        new java.io.FileOutputStream(
            new java.io.File(getTargetContext().getExternalFilesDir(null), name + ".png"))) {
      bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, out);
    }
    bitmap.recycle();
  }

  @Override
  public void onCreate(Bundle arguments) {
    this.arguments = arguments;
    start();
  }

  private List<View> all(View view) {
    List<View> result = new ArrayList<>();
    result.add(view);
    if (view instanceof ViewGroup)
      for (int i = 0; i < ((ViewGroup) view).getChildCount(); i++)
        result.addAll(all(((ViewGroup) view).getChildAt(i)));
    return result;
  }

  private List<EditText> edits() {
    List<EditText> fields = new ArrayList<>();
    for (View v : all(activity.getWindow().getDecorView()))
      if (v instanceof EditText) fields.add((EditText) v);
    return fields;
  }

  private AlertDialog dialog() throws Exception {
    java.lang.reflect.Field field = MainActivity.class.getDeclaredField("editor");
    field.setAccessible(true);
    return (AlertDialog) field.get(activity);
  }

  private void confirm() throws Exception {
    AlertDialog dialog = dialog();
    runOnMainSync(() -> dialog.getButton(-1).performClick());
    waitForIdleSync();
  }

  private void click(String label) {
    runOnMainSync(
        () -> {
          for (View view : all(activity.getWindow().getDecorView()))
            if (view instanceof Button && ((Button) view).getText().toString().equals(label)) {
              view.performClick();
              return;
            }
          throw new AssertionError("Missing button " + label);
        });
    waitForIdleSync();
  }

  private void openRecord(String title) {
    runOnMainSync(
        () -> {
          for (View view : all(activity.getWindow().getDecorView())) {
            if (view instanceof TextView
                && !(view instanceof EditText)
                && ((TextView) view).getText().toString().equals(title)) {
              View target = view;
              while (!target.isClickable() && target.getParent() instanceof View)
                target = (View) target.getParent();
              if (target.isClickable()) {
                target.performClick();
                return;
              }
            }
          }
          throw new AssertionError("Missing compact row " + title);
        });
    waitForIdleSync();
  }

  private void assertNoListActions() {
    runOnMainSync(
        () -> {
          for (View view : all(activity.getWindow().getDecorView()))
            if (view instanceof Button
                && java.util.Set.of("Edit", "Reconnect", "Disable", "Delete")
                    .contains(((Button) view).getText().toString()))
              throw new AssertionError("Record actions must be inside details");
        });
  }

  private void await(String text) throws Exception {
    long until = System.currentTimeMillis() + 30000;
    while (System.currentTimeMillis() < until) {
      final boolean[] found = {false};
      runOnMainSync(
          () -> {
            for (View v : all(activity.getWindow().getDecorView()))
              if (v instanceof TextView && ((TextView) v).getText().toString().contains(text))
                found[0] = true;
          });
      if (found[0]) return;
      Thread.sleep(200);
    }
    StringBuilder visible = new StringBuilder();
    runOnMainSync(
        () -> {
          for (View v : all(activity.getWindow().getDecorView()))
            if (v instanceof TextView && !(v instanceof EditText))
              visible.append(((TextView) v).getText()).append(" | ");
        });
    throw new AssertionError("Timed out waiting for " + text + "; visible: " + visible);
  }

  private void login(String user, String pass) throws Exception {
    runOnMainSync(
        () -> {
          List<EditText> fields = edits();
          fields.get(0).setText(arguments.getString("server", "http://127.0.0.1:18080"));
          fields.get(1).setText(user);
          fields.get(2).setText(pass);
        });
    click("Sign in");
    await("Updated ");
  }

  @Override
  public void onStart() {
    Bundle result = new Bundle();
    Vault vault = new Vault(getTargetContext());
    JSONObject original = vault.load();
    try {
      vault.save(new JSONObject().put("probe", "device-encryption-check"));
      if (!vault.load().optString("probe").equals("device-encryption-check"))
        throw new AssertionError("Encrypted settings failed");
      vault.save(new JSONObject());
      activity =
          startActivitySync(
              new Intent(getTargetContext(), MainActivity.class)
                  .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
      await("Sign in to your WISP");
      if (arguments.getString("mode", "").equals("read-only")) {
        login(arguments.getString("username"), arguments.getString("password"));
        click("Subscribers");
        await("Updated ");
        click("Packages");
        await("Updated ");
        click("Routers");
        await("Updated ");
        click("IP pools");
        await("Updated ");
        click("Settings");
        await("Updated ");
        click(arguments.getString("finalSection", "Overview"));
        await("Updated ");
        keepLogin = arguments.getString("keepLogin", "false").equals("true");
        result.putString(
            "stream", "PASS: HTTPS native administrator login and read-only production screens\n");
        finish(Activity.RESULT_OK, result);
        return;
      }
      login("phone-customer", "Phone-test-2026!");
      await("phone-customer");
      capture("customer");
      click("Usage");
      await("Recorded usage");
      click("History");
      await("Disconnected:");
      runOnMainSync(() -> activity.finish());
      activity =
          startActivitySync(
              new Intent(getTargetContext(), MainActivity.class)
                  .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
      await("Updated ");
      runOnMainSync(() -> activity.finish());
      vault.save(new JSONObject());
      activity =
          startActivitySync(
              new Intent(getTargetContext(), MainActivity.class)
                  .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
      login("device-admin", "Phone-test-2026!");
      click("Subscribers");
      await("Updated ");
      capture("administrator");
      click("+ Add subscribers");
      AlertDialog create = dialog();
      if (create == null) throw new AssertionError("Create subscriber form not available");
      runOnMainSync(
          () -> {
            int edit = 0;
            for (View v : all(create.getWindow().getDecorView())) {
              if (v instanceof EditText)
                ((EditText) v).setText(edit++ == 0 ? "phone-created" : "Phone-create-2026!");
              if (v instanceof Spinner) ((Spinner) v).setSelection(1);
            }
          });
      confirm();
      await("phone-created");
      runOnMainSync(() -> edits().get(0).setText("phone-created"));
      click("Search");
      assertNoListActions();
      openRecord("phone-created");
      await("Edit");
      click("‹ Back to Subscribers");
      assertNoListActions();
      runOnMainSync(
          () -> {
            if (!edits().get(0).getText().toString().equals("phone-created"))
              throw new AssertionError("Search must survive returning from details");
          });
      openRecord("phone-created");
      click("Disable");
      confirm();
      await("Status: disabled");
      click("Enable");
      confirm();
      await("Status: active");
      click("Delete");
      AlertDialog delete = dialog();
      runOnMainSync(
          () -> {
            for (View v : all(delete.getWindow().getDecorView()))
              if (v instanceof EditText) ((EditText) v).setText("delete");
          });
      confirm();
      if (!delete.isShowing()) throw new AssertionError("Lowercase delete must be rejected");
      runOnMainSync(
          () -> {
            for (View v : all(delete.getWindow().getDecorView()))
              if (v instanceof EditText) ((EditText) v).setText("Delete");
          });
      confirm();
      await("No records");
      click("Packages");
      await("Updated ");
      assertNoListActions();
      openRecord("5/5 Mbps");
      await("Edit");
      runOnMainSync(() -> activity.onBackPressed());
      await("+ Add packages");
      assertNoListActions();
      click("IP pools");
      await("Updated ");
      assertNoListActions();
      openRecord("Local subscribers");
      await("Edit");
      click("‹ Back to IP pools");
      assertNoListActions();
      for (String area : new String[] {"Live", "Routers", "Sessions", "Speed tests"}) {
        click(area);
        await("Updated ");
        assertNoListActions();
        openRecord(area.equals("Routers") ? "Phone test router" : "phone-customer");
        await("‹ Back to " + area);
        click("‹ Back to " + area);
        assertNoListActions();
      }
      click("Settings");
      await("Updated ");
      click("Edit platform secrets");
      if (dialog() == null) throw new AssertionError("Platform settings form missing");
      runOnMainSync(
          () -> {
            try {
              dialog().dismiss();
            } catch (Exception e) {
              throw new RuntimeException(e);
            }
          });
      result.putString(
          "stream",
          "PASS: compact list/detail/back navigation across all admin sections; customer"
              + " statistics/history, saved login, Keystore encryption; admin"
              + " create/disable/enable/delete, exact Delete confirmation, platform settings"
              + " form\n");
      finish(Activity.RESULT_OK, result);
    } catch (Throwable e) {
      result.putString("stream", "FAIL: " + e);
      finish(Activity.RESULT_CANCELED, result);
    } finally {
      if (activity != null) runOnMainSync(() -> activity.finish());
      if (!keepLogin) vault.save(original);
    }
  }
}
