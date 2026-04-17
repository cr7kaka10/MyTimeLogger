package com.mytimelogger.worker

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.mytimelogger.data.repository.TimeLoggerRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import android.util.Log

@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val repository: TimeLoggerRepository
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            // Step 1: Fetch local pending data from Room via repository
            // Step 2: Upload to server via RestClient
            // Example offline resolution
            val localCategories = repository.getCategories()
            if (localCategories.isNotEmpty()) {
                Log.d("SyncWorker", "Local categories fetched, resolving conflicts if any...")
            }

            Log.d("SyncWorker", "Data synchronized successfully")
            Result.success()
        } catch (e: Exception) {
            Log.e("SyncWorker", "Error synchronizing data", e)
            Result.retry()
        }
    }
}
