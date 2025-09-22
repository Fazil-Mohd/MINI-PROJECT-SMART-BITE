import requests
import csv
import json
from datetime import timedelta
from django.conf import settings
from django.contrib import messages 
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import MealPlan
from users.models import Profile


def _fetch_from_spoonacular(endpoint, params={}):
    """
    A helper function to make requests to the Spoonacular API.
    """
    params['apiKey'] = settings.SPOONACULAR_API_KEY
    base_url = "https://api.spoonacular.com/"
    url = f"{base_url}{endpoint}"
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return None


@login_required
def generate_meal_plan(request):
    """
    Generates a 7-day meal plan based on the user's profile and goal.
    """
    profile = request.user.profile
    tdee = profile.calculate_tdee()
    
    if profile.goal == 'lose':
        calorie_target = tdee - 500
    elif profile.goal == 'gain':
        calorie_target = tdee + 500
    else:
        calorie_target = tdee

    health_issues = profile.health_issues.lower() if profile.health_issues else ''
    diet = 'low glycemic' if 'diabetes' in health_issues else None
    
    response_data = _fetch_from_spoonacular(
        'mealplanner/generate',
        params={
            'timeFrame': 'week',
            'targetCalories': calorie_target,
            'diet': diet,
        }
    )

    if response_data and 'week' in response_data:
        MealPlan.objects.filter(user=request.user).delete()
        
        for day, data in response_data['week'].items():
            for meal_data in data['meals']:
                MealPlan.objects.create(
                    user=request.user,
                    day=day.capitalize(),
                    meal_type=meal_data.get('title', 'Meal'),
                    meal_name=meal_data.get('title', 'Generated Meal'),
                    spoonacular_id=meal_data['id'],
                    calories=meal_data.get('calories', 0),
                    protein=meal_data.get('protein', '0g'),
                    fats=meal_data.get('fat', '0g'), # Corrected from fat to fats
                    carbs=meal_data.get('carbohydrates', '0g'),
                    image_url=f"https://spoonacular.com/recipeImages/{meal_data['id']}-556x370.{meal_data.get('imageType', 'jpg')}",
                )
        return redirect('meal_plan')

    messages.error(request, "Could not generate a meal plan. The API might be temporarily unavailable or your daily quota may have been reached.")
    return redirect('meal_plan')


@login_required
def meal_plan_view(request):
    meals = MealPlan.objects.filter(user=request.user).order_by('pk')
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    grouped_meals = {day: [] for day in days_order}
    for meal in meals:
        if meal.day in grouped_meals:
            grouped_meals[meal.day].append(meal)
            
    context = {'grouped_meals': grouped_meals}
    return render(request, 'meals/meal_plan.html', context)


@login_required
def replace_meal(request, meal_id):
    if request.method == 'POST':
        original_meal = get_object_or_404(MealPlan, id=meal_id, user=request.user)
        profile = request.user.profile
        
        params = {
            'number': 1,
            'addRecipeNutrition': 'true',
            'targetCalories': original_meal.calories,
        }
        
        response_data = _fetch_from_spoonacular('recipes/complexSearch', params=params)
        
        if not response_data or not response_data.get('results'):
             # If first attempt fails, try a broader search
            del params['targetCalories']
            response_data = _fetch_from_spoonacular('recipes/complexSearch', params=params)

        if response_data and response_data.get('results'):
            new_recipe = response_data['results'][0]
            
            nutrition_data = new_recipe.get('nutrition', {}).get('nutrients', [])
            calories = next((n['amount'] for n in nutrition_data if n['name'] == 'Calories'), original_meal.calories)

            original_meal.meal_name = new_recipe['title']
            original_meal.spoonacular_id = new_recipe['id']
            original_meal.calories = round(calories)
            original_meal.image_url = new_recipe.get('image')
            original_meal.save()
            
            return JsonResponse({
                'success': True,
                'meal_name': original_meal.meal_name,
                'calories': original_meal.calories,
                'image_url': original_meal.image_url
            })
            
    return JsonResponse({'success': False, 'error': 'Could not find a replacement meal. Please try again later or check your API quota.'})


@login_required
def toggle_meal_eaten(request, meal_id):
    if request.method == 'POST':
        meal = get_object_or_404(MealPlan, id=meal_id, user=request.user)
        meal.eaten = not meal.eaten
        if meal.eaten:
            meal.eaten_at = timezone.now()
        else:
            meal.eaten_at = None
        meal.save()
        return JsonResponse({'success': True, 'eaten': meal.eaten})
    return JsonResponse({'success': False, 'error': 'Invalid request'})


@login_required
def discover_meals(request):
    profile = request.user.profile
    health_issues = profile.health_issues.lower() if profile.health_issues else ''
    
    diet = 'low glycemic' if 'diabetes' in health_issues else None
    intolerances = []
    if 'gluten' in health_issues:
        intolerances.append('gluten')
    if 'dairy' in health_issues or 'lactose' in health_issues:
        intolerances.append('dairy')

    recipes_data = _fetch_from_spoonacular(
        'recipes/complexSearch',
        params={
            'number': 12,
            'addRecipeNutrition': 'true',
            'cuisine': 'Indian',
            'diet': diet,
            'intolerances': ','.join(intolerances)
        }
    )

    recipes = []
    if recipes_data and 'results' in recipes_data:
        for recipe in recipes_data['results']:
            nutrition = recipe.get('nutrition', {}).get('nutrients', [])
            calories = next((n['amount'] for n in nutrition if n['name'] == 'Calories'), 0)
            
            recipes.append({
                'id': recipe['id'],
                'title': recipe['title'],
                'image': recipe['image'],
                'readyInMinutes': recipe.get('readyInMinutes'),
                'servings': recipe.get('servings'),
                'calories': round(calories),
            })
            
    context = {'recipes': recipes}
    return render(request, 'meals/discover.html', context)


@login_required
def grocery_list(request):
    meals = MealPlan.objects.filter(user=request.user)
    ingredient_list = set()
    
    for meal in meals:
        if not meal.spoonacular_id:
            continue
        ingredients_data = _fetch_from_spoonacular(f'recipes/{meal.spoonacular_id}/ingredientWidget.json')
        if ingredients_data and 'ingredients' in ingredients_data:
            for item in ingredients_data['ingredients']:
                ingredient_list.add(item['name'].capitalize())

    if request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="grocery_list.csv"'
        writer = csv.writer(response)
        writer.writerow(['Ingredient'])
        for item in sorted(list(ingredient_list)):
            writer.writerow([item])
        return response
        
    context = {'shopping_list': sorted(list(ingredient_list))}
    return render(request, 'meals/grocery_list.html', context)


@login_required
def progress_view(request):
    """
    Calculates and displays the user's progress over the last 7 days,
    including summary stats and data for charts.
    """
    profile = request.user.profile
    today = timezone.now().date()
    seven_days_ago = today - timedelta(days=6)

    meals_last_7_days = MealPlan.objects.filter(
        user=request.user,
        eaten=True,
        eaten_at__date__gte=seven_days_ago,
        eaten_at__date__lte=today
    ).order_by('eaten_at__date')

    daily_data = {}
    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        day_str = day.strftime('%b %d')
        daily_data[day_str] = {'calories': 0, 'meals': 0}

    for meal in meals_last_7_days:
        day_str = meal.eaten_at.strftime('%b %d')
        if day_str in daily_data:
            daily_data[day_str]['calories'] += meal.calories
            daily_data[day_str]['meals'] += 1

    total_calories_week = sum(d['calories'] for d in daily_data.values())
    total_meals_week = sum(d['meals'] for d in daily_data.values())

    days_tracked = len([d for d in daily_data.values() if d['calories'] > 0])
    avg_daily_calories = total_calories_week // days_tracked if days_tracked > 0 else 0

    tdee = profile.calculate_tdee()
    best_day = {'date': 'N/A', 'calories': 0}
    min_diff = float('inf')

    if days_tracked > 0:
        for date, data in daily_data.items():
            if data['calories'] > 0:
                diff = abs(data['calories'] - tdee)
                if diff < min_diff:
                    min_diff = diff
                    best_day['date'] = date
                    best_day['calories'] = data['calories']

    dates_list = list(daily_data.keys())
    calories_list = [d['calories'] for d in daily_data.values()]
    meal_counts_list = [d['meals'] for d in daily_data.values()]

    context = {
        'total_calories_week': total_calories_week,
        'total_meals_week': total_meals_week,
        'avg_daily_calories': avg_daily_calories,
        'best_day': best_day,
        'dates_json': json.dumps(dates_list),
        'calories_json': json.dumps(calories_list),
        'meal_counts_json': json.dumps(meal_counts_list),
    }

    if request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="weekly_progress_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Calories Consumed', 'Meals Eaten'])
        for date, data in daily_data.items():
            writer.writerow([date, data['calories'], data['meals']])
        return response

    return render(request, 'meals/progress.html', context)


@login_required
def add_meal_to_plan(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            MealPlan.objects.create(
                user=request.user,
                day=data['day'],
                meal_type=data['meal_type'],
                meal_name=data['name'],
                spoonacular_id=data['recipe_id'],
                calories=int(data.get('calories', 0)),
                image_url=data.get('image')
            )
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

