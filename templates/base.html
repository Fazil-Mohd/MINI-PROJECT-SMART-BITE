from django.db import models
from django.contrib.auth.models import User

class MealPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    day = models.CharField(max_length=10)
    meal_type = models.CharField(max_length=50)
    meal_name = models.CharField(max_length=200)

    spoonacular_id = models.PositiveIntegerField(null=True, blank=True)

    calories = models.PositiveIntegerField()
    protein = models.CharField(max_length=10, default="0g")
    carbs = models.CharField(max_length=10, default="0g")
    fats = models.CharField(max_length=10, default="0g")

    image_url = models.URLField(max_length=500, null=True, blank=True) 

    # Tracking
    eaten = models.BooleanField(default=False)
    eaten_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}'s {self.meal_type} on {self.day}"
