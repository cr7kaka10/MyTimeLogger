package com.mytimelogger

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class MyTimeLoggerApp : Application() {
    override fun onCreate() {
        super.onCreate()
    }
}
