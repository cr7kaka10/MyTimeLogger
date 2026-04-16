package com.mytimelogger.data.remote

import io.ktor.client.*
import io.ktor.client.engine.android.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.json.Json
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*

class RestClient {
    private val client = HttpClient(Android) {
        install(ContentNegotiation) {
            json(Json {
                prettyPrint = true
                isLenient = true
                ignoreUnknownKeys = true
            })
        }
    }

    private var token: String? = null
    val baseUrl = "http://10.0.2.2:8000/api" // Emulator localhost

    fun setToken(newToken: String) {
        token = newToken
    }

    suspend fun postSession(sessionData: Any): HttpResponse {
        return client.post("$baseUrl/sessions/start") {
            contentType(ContentType.Application.Json)
            token?.let { header(HttpHeaders.Authorization, "Bearer $it") }
            setBody(sessionData)
        }
    }

    // Add other REST methods (login, getCategories, etc.) as needed
}
