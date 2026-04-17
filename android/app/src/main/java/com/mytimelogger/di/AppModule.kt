package com.mytimelogger.di

import android.content.Context
import androidx.room.Room
import com.mytimelogger.data.local.AppDatabase
import com.mytimelogger.data.local.CategoryDao
import com.mytimelogger.data.local.NoteDao
import com.mytimelogger.data.local.SessionDao
import com.mytimelogger.data.remote.RestClient
import com.mytimelogger.data.remote.WebSocketClient
import com.mytimelogger.data.repository.TimeLoggerRepository
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideAppDatabase(@ApplicationContext context: Context): AppDatabase {
        return Room.databaseBuilder(
            context,
            AppDatabase::class.java,
            "mytimelogger.db"
        ).build()
    }

    @Provides
    fun provideCategoryDao(db: AppDatabase): CategoryDao = db.categoryDao()

    @Provides
    fun provideSessionDao(db: AppDatabase): SessionDao = db.sessionDao()

    @Provides
    fun provideNoteDao(db: AppDatabase): NoteDao = db.noteDao()

    @Provides
    @Singleton
    fun provideRestClient(): RestClient = RestClient()

    @Provides
    @Singleton
    fun provideWebSocketClient(): WebSocketClient = WebSocketClient()

    @Provides
    @Singleton
    fun provideTimeLoggerRepository(
        categoryDao: CategoryDao,
        sessionDao: SessionDao,
        noteDao: NoteDao,
        restClient: RestClient,
        webSocketClient: WebSocketClient
    ): TimeLoggerRepository {
        return TimeLoggerRepository(categoryDao, sessionDao, noteDao, restClient, webSocketClient)
    }
}
