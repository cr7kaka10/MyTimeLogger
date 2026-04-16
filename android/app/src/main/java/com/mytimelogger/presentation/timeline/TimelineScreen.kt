package com.mytimelogger.presentation.timeline

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

data class TimelineEvent(val time: String, val description: String, val duration: String? = null)

@Composable
fun TimelineScreen(events: List<TimelineEvent>) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text(
            text = "Timeline",
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.padding(bottom = 16.dp)
        )

        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(events) { event ->
                TimelineItem(event)
            }
        }
    }
}

@Composable
fun TimelineItem(event: TimelineEvent) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.padding(16.dp)) {
            Text(
                text = event.time,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.width(60.dp)
            )
            Spacer(modifier = Modifier.width(16.dp))
            Column {
                Text(text = event.description, style = MaterialTheme.typography.bodyLarge)
                if (event.duration != null) {
                    Text(
                        text = event.duration,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}
