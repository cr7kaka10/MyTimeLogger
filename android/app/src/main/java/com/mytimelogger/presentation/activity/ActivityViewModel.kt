package com.mytimelogger.presentation.activity

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mytimelogger.data.repository.TimeLoggerRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ActivityViewModel @Inject constructor(
    private val repository: TimeLoggerRepository
) : ViewModel() {

    private val _activities = MutableStateFlow<List<ActivityItem>>(emptyList())
    val activities: StateFlow<List<ActivityItem>> = _activities

    init {
        loadActivities()
    }

    private fun loadActivities() {
        viewModelScope.launch {
            // Normally fetch from repository
            // val categories = repository.getCategories()
            // Map to ActivityItem

            // For MVP mock data until fetch is complete
            _activities.value = listOf(
                ActivityItem("Reading", "📖"),
                ActivityItem("Coding", "💻"),
                ActivityItem("Listening", "🎧"),
                ActivityItem("Writing", "✍️"),
                ActivityItem("Teaching", "🎬"),
                ActivityItem("Notes", "📝"),
                ActivityItem("Workout", "🏃"),
                ActivityItem("Diet", "🍽️"),
                ActivityItem("Social", "💬")
            )
        }
    }

    fun onActivityClick(activity: ActivityItem) {
        // Trigger timer start via service/intent or update state
    }
}
