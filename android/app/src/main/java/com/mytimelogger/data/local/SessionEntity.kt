package com.mytimelogger.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "sessions")
data class SessionEntity(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    val startTime: String,
    val endTime: String,
    val netDurationMinutes: Double,
    val date: String,
    val dayOfWeek: String?,
    val pauseCount: Int,
    val pauseReasons: String?,
    val sessionSummary: String?,
    val categoryId: String?
)
