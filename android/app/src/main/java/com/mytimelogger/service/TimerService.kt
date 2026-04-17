package com.mytimelogger.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class TimerService : Service() {

    private val serviceJob = Job()
    private val serviceScope = CoroutineScope(Dispatchers.Main + serviceJob)
    private var isTimerRunning = false
    private var timeElapsedSeconds = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action

        if (action == "STOP_SERVICE") {
            stopTimerService()
            return START_NOT_STICKY
        }

        if (!isTimerRunning) {
            startTimerService()
        }

        return START_STICKY
    }

    private fun startTimerService() {
        createNotificationChannel()

        val notificationIntent = Intent(this, Class.forName("com.mytimelogger.MainActivity"))
        val pendingIntent = PendingIntent.getActivity(
            this, 0, notificationIntent, PendingIntent.FLAG_IMMUTABLE
        )

        val stopIntent = Intent(this, TimerService::class.java).apply {
            action = "STOP_SERVICE"
        }
        val stopPendingIntent = PendingIntent.getService(
            this, 1, stopIntent, PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, "TimerChannel")
            .setContentTitle("MyTimeLogger")
            .setContentText("Focus session in progress... 00:00")
            //.setSmallIcon(android.R.drawable.ic_notification_overlay)
            .setContentIntent(pendingIntent)
            .addAction(0, "Stop", stopPendingIntent)
            .build()

        startForeground(1, notification)
        isTimerRunning = true

        serviceScope.launch {
            while (isTimerRunning) {
                delay(1000L)
                timeElapsedSeconds++
                updateNotification()
            }
        }
    }

    private fun updateNotification() {
        val notificationIntent = Intent(this, Class.forName("com.mytimelogger.MainActivity"))
        val pendingIntent = PendingIntent.getActivity(
            this, 0, notificationIntent, PendingIntent.FLAG_IMMUTABLE
        )

        val stopIntent = Intent(this, TimerService::class.java).apply {
            action = "STOP_SERVICE"
        }
        val stopPendingIntent = PendingIntent.getService(
            this, 1, stopIntent, PendingIntent.FLAG_IMMUTABLE
        )

        val minutes = timeElapsedSeconds / 60
        val seconds = timeElapsedSeconds % 60
        val timeString = String.format("%02d:%02d", minutes, seconds)

        val notification = NotificationCompat.Builder(this, "TimerChannel")
            .setContentTitle("MyTimeLogger")
            .setContentText("Focus session in progress... $timeString")
            //.setSmallIcon(android.R.drawable.ic_notification_overlay)
            .setContentIntent(pendingIntent)
            .addAction(0, "Stop", stopPendingIntent)
            .setOnlyAlertOnce(true)
            .build()

        val manager = getSystemService(NotificationManager::class.java)
        manager?.notify(1, notification)
    }

    private fun stopTimerService() {
        isTimerRunning = false
        // TODO: Save session to Room here via repository before stopping
        stopForeground(true)
        stopSelf()
    }

    override fun onDestroy() {
        super.onDestroy()
        serviceJob.cancel()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val serviceChannel = NotificationChannel(
                "TimerChannel",
                "Timer Service Channel",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(serviceChannel)
        }
    }
}
