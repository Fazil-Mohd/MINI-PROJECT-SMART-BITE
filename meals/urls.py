from django.urls import path
from . import views

urlpatterns = [
    path('plan/generate/', views.generate_meal_plan, name='generate_meal_plan'),
    path('plan/', views.meal_plan_view, name='meal_plan'),
    path('grocery/', views.grocery_list, name='grocery_list'),
    path('progress/', views.progress_view, name='progress'),
    path('meal/<int:meal_id>/replace/', views.replace_meal, name='replace_meal'),
    path('discover/', views.discover_meals, name='discover_meals'),
    path('plan/add/', views.add_meal_to_plan, name='add_meal_to_plan'),
    path('meal/<int:meal_id>/toggle-eaten/', views.toggle_meal_eaten, name='toggle_meal_eaten'),
]
