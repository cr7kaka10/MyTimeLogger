package com.mytimelogger

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Scaffold
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.material3.Icon
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Home
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.mytimelogger.presentation.activity.ActivityScreen
import com.mytimelogger.presentation.timeline.TimelineScreen
import com.mytimelogger.presentation.timeline.TimelineEvent
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
                    MainAppScreen(
                        onStartTimer = {
                            val intent = Intent(this, TimerService::class.java)
                            startService(intent)
                        }
                    )
                }
            }
        }
    }
}

@Composable
fun MainAppScreen(onStartTimer: () -> Unit) {
    var selectedTab by remember { mutableStateOf("Activity") }

    Scaffold(
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    icon = { Icon(Icons.Filled.Home, contentDescription = "Activity") },
                    label = { Text("Activity") },
                    selected = selectedTab == "Activity",
                    onClick = { selectedTab = "Activity" }
                )
                NavigationBarItem(
                    icon = { Icon(Icons.Filled.List, contentDescription = "Timeline") },
                    label = { Text("Timeline") },
                    selected = selectedTab == "Timeline",
                    onClick = { selectedTab = "Timeline" }
                )
            }
        }
    ) { innerPadding ->
        Modifier.padding(innerPadding).let { _ ->
            if (selectedTab == "Activity") {
                val viewModel: ActivityViewModel = hiltViewModel()
                ActivityScreen(viewModel = viewModel) { activity ->
                    onStartTimer()
                }
            } else {
                // Dummy Data for Timeline
                TimelineScreen(
                    events = listOf(
                        TimelineEvent("08:30", "📖 Reading", "25min"),
                        TimelineEvent("09:00", "💻 Coding", "45min")
                    )
                )
            }
        }
    }
}
