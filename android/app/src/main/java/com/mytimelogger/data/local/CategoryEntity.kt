package com.mytimelogger.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "categories")
data class CategoryEntity(
    @PrimaryKey val id: String,
    val name: String,
    val icon: String,
    val color: String,
    val groupName: String,
    val sortOrder: Int,
    val isActive: Int,
    val createdAt: String
)
