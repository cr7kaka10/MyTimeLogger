package com.mytimelogger.data.repository

import com.mytimelogger.data.local.CategoryDao
import com.mytimelogger.data.local.CategoryEntity
import com.mytimelogger.data.local.NoteDao
import com.mytimelogger.data.local.SessionDao
import com.mytimelogger.data.local.SessionEntity
import com.mytimelogger.data.remote.RestClient
import javax.inject.Inject

class TimeLoggerRepository @Inject constructor(
    private val categoryDao: CategoryDao,
    private val sessionDao: SessionDao,
    private val noteDao: NoteDao,
    private val restClient: RestClient
) {
    suspend fun getCategories(): List<CategoryEntity> {
        // Here we'd ideally sync with remote first, then return local
        return categoryDao.getAll()
    }

    suspend fun saveSession(session: SessionEntity) {
        // Save locally
        sessionDao.insert(session)
        // Push to server
        try {
            // Note: need to map SessionEntity to whatever RestClient expects
            restClient.postSession(session)
        } catch (e: Exception) {
            // Handle offline error: typically managed by WorkManager in Stage 5
        }
    }
}
