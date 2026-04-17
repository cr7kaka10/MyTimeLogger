package com.mytimelogger.presentation.activity

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel

data class ActivityItem(val name: String, val icon: String)

@Composable
fun ActivityScreen(
    viewModel: ActivityViewModel = viewModel(),
    onActivityClick: (ActivityItem) -> Unit
) {
    val activities by viewModel.activities.collectAsState()

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text(text = "Lyubishchev Activity Tracker", modifier = Modifier.padding(bottom = 16.dp))

        LazyVerticalGrid(
            columns = GridCells.Fixed(3),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(activities) { activity ->
                ActivityCard(activity = activity, onClick = {
                    viewModel.onActivityClick(activity)
                    onActivityClick(activity)
                })
            }
        }
    }
}

@Composable
fun ActivityCard(activity: ActivityItem, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().aspectRatio(1f)) {
        Column(
            modifier = Modifier.fillMaxSize().padding(8.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally
        ) {
            Text(text = activity.icon)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = activity.name)
            Button(onClick = onClick) {
                Text("Start")
            }
        }
    }
}
