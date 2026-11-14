plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "app.fabricinspector"
    compileSdk = 34

    defaultConfig {
        applicationId = "app.fabricinspector"
        minSdk = 26                // Android 8+
        targetSdk = 34
        versionCode = 4
        versionName = "0.4"
        // the app's main screen: the web app (kept on the phone for offline use after the first start)
        buildConfigField("String", "APP_URL", "\"https://fabric-inspector.vercel.app/\"")
        // the analysis server (same engine as the web app and the Windows app)
        buildConfigField("String", "API_URL", "\"https://fabric-inspector.vercel.app/api/analyze\"")
    }
    buildFeatures { buildConfig = true }
    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

// No libraries: the app uses only the Android platform (small APK, nothing extra to download).
