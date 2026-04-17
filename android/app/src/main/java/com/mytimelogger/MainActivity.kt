package com.mytimelogger

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.mytimelogger.presentation.activity.ActivityScreen
import android.content.Intent
import androidx.hilt.navigation.compose.hiltViewModel
import com.mytimelogger.presentation.activity.ActivityViewModel
import com.mytimelogger.service.TimerService
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val viewModel: ActivityViewModel = hiltViewModel()
                    ActivityScreen(viewModel = viewModel) { activity ->
                        // Start Timer Service
                        val intent = Intent(this, TimerService::class.java)
                        startService(intent)
                    }
                }
            }
        }
    }
}
