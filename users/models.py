from django.db import models
from django.contrib.auth.models import User

ACTIVITY_LEVELS = [
    ('sedentary', 'Sedentary (little or no exercise)'),
    ('light', 'Lightly active (light exercise 1-3 days/week)'),
    ('moderate', 'Moderately active (moderate exercise 3-5 days/week)'),
    ('active', 'Very active (hard exercise 6-7 days/week)'),
    ('extra', 'Extra active (very hard exercise & physical job)'),
]

GOALS = [
    ('lose', 'Lose Weight'),
    ('gain', 'Gain Weight'),
    ('maintain', 'Maintain Weight'),
]

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    age = models.PositiveIntegerField()
    weight = models.FloatField(help_text="in kg")
    height = models.FloatField(help_text="in cm")
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')])
    activity_level = models.CharField(max_length=20, choices=ACTIVITY_LEVELS)
    health_issues = models.TextField(blank=True, null=True, help_text="e.g., diabetes, gluten intolerance")
    goal = models.CharField(max_length=10, choices=GOALS)

    def calculate_bmr(self):
        """
        Calculates Basal Metabolic Rate (BMR) using the Harris-Benedict equation.
        BMR is the number of calories required to keep your body functioning at rest.
        """
        if self.gender == 'male':
            # Formula for men
            return 10 * self.weight + 6.25 * self.height - 5 * self.age + 5
        else:
            # Formula for women
            return 10 * self.weight + 6.25 * self.height - 5 * self.age - 161

    def calculate_tdee(self):
        """
        Calculates Total Daily Energy Expenditure (TDEE).
        TDEE is the total calories burned in a day, including all activities.
        """
        bmr = self.calculate_bmr()
        # Activity level multipliers
        multipliers = {
            'sedentary': 1.2,
            'light': 1.375,
            'moderate': 1.55,
            'active': 1.725,
            'extra': 1.9,
        }
        # Multiply BMR by the activity multiplier to get TDEE
        return round(bmr * multipliers[self.activity_level])

    def __str__(self):
        return f"{self.user.username}'s Profile"