# OnboardHub mobile builds

This is an **initial Capacitor wrapper for the existing hosted Django portal**, not a native mobile API rewrite. It requires a working HTTPS Django deployment; no HR data is bundled in the app.

Set the repository Actions **variable** `PORTAL_URL` to the full HTTPS portal origin (example: `https://onboarding.example.com`). Do not use localhost or a LAN address. The portal must have valid TLS, mobile-friendly pages and correct host/CSRF configuration.

After merge to `main`, GitHub Actions tests Django and produces a debug Android APK and **iOS simulator app**. The iOS simulator app is not installable on physical iPhones. **Distributable IPA needs Apple Developer signing/provisioning** and a separate signed archive/export workflow. Android debug APK isn't a production release either. Future pushes create new downloadable artifacts; they do **not** silently update installed apps. For automatic employee deployment, configure managed distribution (MDM, Play internal track/TestFlight) with signing and release approval.

This wrapper may not satisfy App Store review's minimum-functionality guidelines without native device features. Long-term recommended architecture: Django REST API, OIDC/SSO, native app navigation, secure local credential storage, privacy-first notifications, and role-scoped data caching. Never embed production credentials or employee data inside a mobile binary.
