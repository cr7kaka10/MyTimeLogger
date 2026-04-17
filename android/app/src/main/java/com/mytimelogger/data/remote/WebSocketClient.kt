package com.mytimelogger.data.remote

import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.plugins.websocket.*
import io.ktor.http.*
import io.ktor.websocket.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.isActive

class WebSocketClient {
    private val client = HttpClient(CIO) {
        install(WebSockets) {
            pingInterval = 20_000
        }
    }

    private val wsUrl = "ws://10.0.2.2:8000/ws/sync"
    private var session: DefaultClientWebSocketSession? = null

    suspend fun connectAndListen(): Flow<String> = flow {
        try {
            client.webSocket(wsUrl) {
                session = this
                while (isActive) {
                    when (val frame = incoming.receive()) {
                        is Frame.Text -> {
                            emit(frame.readText())
                        }
                        else -> {} // ignore other frame types for now
                    }
                }
            }
        } finally {
            session = null
        }
    }.catch { e ->
        // Handle reconnection logic or logging here
        emit("Error: ${e.message}")
    }

    suspend fun sendEvent(eventJson: String) {
        session?.send(Frame.Text(eventJson))
    }

    fun close() {
        client.close()
    }
}
