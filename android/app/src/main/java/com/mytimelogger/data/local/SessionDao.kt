package com.mytimelogger.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface SessionDao {
    @Query("SELECT * FROM sessions")
    suspend fun getAll(): List<SessionEntity>

    @Insert
    suspend fun insert(session: SessionEntity)
}
