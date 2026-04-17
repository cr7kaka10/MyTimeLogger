package com.mytimelogger.data.repository

import com.mytimelogger.data.local.CategoryDao
import com.mytimelogger.data.local.CategoryEntity
import com.mytimelogger.data.local.NoteDao
import com.mytimelogger.data.local.SessionDao
import com.mytimelogger.data.local.SessionEntity
import com.mytimelogger.data.remote.RestClient
import com.mytimelogger.data.remote.WebSocketClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

class TimeLoggerRepository @Inject constructor(
    private val categoryDao: CategoryDao,
    private val sessionDao: SessionDao,
    private val noteDao: NoteDao,
    private val restClient: RestClient,
    private val webSocketClient: WebSocketClient
) {
    init {
        // Start listening to WebSocket events for real-time sync
        CoroutineScope(Dispatchers.IO).launch {
            webSocketClient.connectAndListen().collect { event ->
                // Example handler: parse event string and update Room db
                // if (event.contains("Update")) { syncFromRemote() }
            }
        }
    }

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
            // Broadcast event over WebSocket
            webSocketClient.sendEvent("""{"type": "session_created", "id": "${session.id}"}""")
        } catch (e: Exception) {
            // Handle offline error: typically managed by WorkManager in Stage 5
        }
    }
}
