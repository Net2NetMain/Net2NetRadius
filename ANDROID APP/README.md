# WISP Radius for Android

Native Android application for the Net2NetRadius appliance. Uses Android views and
controls, not a WebView. Supports Android 8.0 and later. The theme follows the phone.

## Open and run in Android Studio

Open this **ANDROID APP** directory as a project. Select the connected phone and run
the `app` configuration. The Gradle wrapper downloads Gradle 8.9. Use JDK 17 and SDK 35.

On this laptop Android Studio is installed under `C:\Program Files\Android\Android Studio1`.
SDK and signing locations are machine-local and excluded from Git. If Windows Java
reports `Unable to establish loopback connection`, use a JDK with working local
socket support, or set `JAVA_TOOL_OPTIONS=-Djdk.net.unixdomain.tmpdir=C:/net2net-no-unix-sockets`
to make its internal pipe fall back to TCP. Do not create that fallback directory.

This laptop sets `wisp.buildRoot` in the ignored `local.properties` to
`C:/Users/Chris G Nortje/.codex/builds/wisp-radius`, avoiding OneDrive locks on
generated files. Its APKs are under `app/outputs/apk/` in that directory. Other
checkouts and GitHub Actions use the standard `app/build/outputs/apk/` location.

```powershell
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

## Server and accounts

Enter a URL or IP. Bare IPs default to HTTP port 8080; bare hostnames use HTTPS.
Explicit ports and URL prefixes are retained. TLS certificates are validated normally.
HTTP is supported for local appliances; use HTTPS when going through a public proxy.
The app stores one server, credentials, account identity and cached statistics in
AES-GCM encrypted storage using Android Keystore. It signs in again when reopened
and renews expired sessions for read requests. It never automatically retries a write.
Sign out clears saved credentials and cached records; a server change requires sign-in.
Android backup and device transfer of private state are disabled.

Customers see only their own PPPoE account: package, connection status, instantaneous
upload/download rates, usage and session history. They cannot edit records. A server
failure displays the last cached data and its update time. Screens refresh every
15 seconds while the app is foregrounded; forms are not overwritten by refresh.

Admins use the same role permissions as the website. Native forms cover subscribers,
packages, routers, pools, branding, UISP checks, admin account creation, local settings,
backups/download/restore, and User Manager imports. Reconnect and disable require a
confirmation. Subscriber deletion requires exactly `Delete`, checked by both app and
server. Restore separately requires `RESTORE`. Files use Android's document picker.
WISP logos display using Android's bitmap loader or AndroidSVG for SVG logos.

## API 1.1.0

Update the Docker image with the backend in this repository. The added endpoints are:

* `GET /api/mobile/usage` (customer's own statistics)
* `GET /api/mobile/backups` (Super Admin)
* `POST /api/mobile/subscribers/{id}/reconnect` (administrator)
* `DELETE /api/subscribers/{id}` with `{"confirmation":"Delete"}` (administrator)

Daily and monthly graphs use **recorded RADIUS accounting**, not fabricated usage.
The appliance imports its persistent FreeRADIUS detail journal every five seconds.
Interim deltas are attributed to their UTC sample day; intervals crossing midnight
are not exact daily billing boundaries. Existing sessions without interval history
contribute to totals, but cannot reconstruct missing daily detail. Routers must send
accounting/interim updates to UDP 1813. Existing database tables, key and backups
stay in the mapped `/data` directory; new collector tables are additive.

## Phone tests with disposable data

From the repository root run `apps/api/.venv/Scripts/python.exe scripts/run-android-test-server.py`.
It uses a temporary SQLite database and listens only on localhost port 18080.

```powershell
adb reverse tcp:18080 tcp:18080
.\gradlew.bat :app:assembleDebug :app:assembleDebugAndroidTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell am instrument -w net.net2net.wispradius.test/net.net2net.wispradius.DeviceSmokeTest
```

Test-only credentials in that disposable server: `phone-customer` / `Phone-test-2026!`
and `device-admin` / `Phone-test-2026!`. These are never created in the Docker image
or in a production database. Stop the test server after use.

## Signed APKs

The first signed release uses the Net2Net key kept outside this repository at
`%USERPROFILE%\.codex\signing\wisp-radius\wisp-radius.jks`. The companion
`signing.properties` and the local project copy contain private signing settings;
neither is committed. Preserve these files to sign compatible future updates.

Build with `gradlew.bat :app:assembleRelease`. The result is
`app/build/outputs/apk/release/app-release.apk`. GitHub Releases distributes the
signed APK. GitHub Actions builds and checks a debug APK on commits; release
signing stays local until a separate CI signing setup is explicitly configured.
