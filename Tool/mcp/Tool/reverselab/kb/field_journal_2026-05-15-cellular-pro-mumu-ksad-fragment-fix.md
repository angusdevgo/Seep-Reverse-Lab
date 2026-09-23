---
name: cellular-pro-mumu-ksad-fragment-fix
description: Cellular-Pro rebuilt APK on MuMu crashed first in Kuaishou/KSAd anti-fraud paths, then in app fragments whose lifecycle methods had been stubbed without calling Fragment super methods.
metadata:
  type: project
---
Cellular-Pro rebuilt APK on MuMu 12 required a two-layer fix: first short-circuit Kuaishou/KSAd device-fingerprint and ad-network paths that crashed under emulator translation, then restore Fragment lifecycle super-calls for app fragments that had been stubbed into no-ops.

**Why:** The privacy-consent crash was not a single issue. After the first native crash was removed, later startup phases exposed additional KSAd emulator incompatibilities and finally an app-side `SuperNotCalledException` from fragments whose `onResume()` had been emptied.

**How to apply:** For rebuilt Android APKs that still crash only on MuMu/Android emulators after consent or splash, verify whether third-party ad SDK device-info collectors (`com.yxcorp.kuaishou.addfp`, `com.kwad.sdk.utils.bc`, `com.kwad.sdk.core.network`) need to be stubbed, then check app fragments for lifecycle methods replaced with `return-void` and restore direct `androidx.fragment.app.Fragment` super calls. Related: [[apk-reverse]], [[cellular-pro-reporting]].
