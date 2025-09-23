from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from .models import MealPlan
import requests
import json
import csv
from datetime import timedelta

# ==============================================================================
# HELPER FUNCTION
# ==============================================================================

def _fetch_from_spoonacular(endpoint, params={}):
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

# ==============================================================================
# VIEW FUNCTIONS
# ==============================================================================

@login_required
def generate_meal_plan(request):
    """
    This function has been rewritten for reliability. It now uses a two-step
    API call process to ensure nutritional data is always fetched correctly.
    """
    profile = request.user.profile
    tdee = profile.calculate_tdee()

    if profile.goal == 'lose':
        calorie_target = tdee - 500
    elif profile.goal == 'gain':
        calorie_target = tdee + 500
    else:
        calorie_target = tdee

    api_params = {'timeFrame': 'week', 'targetCalories': calorie_target}
    if profile.health_issues:
        issues = profile.health_issues.lower()
        if "gluten" in issues:
            api_params['diet'] = "Gluten Free"
        elif "vegetarian" in issues:
            api_params['diet'] = "Vegetarian"
        elif "vegan" in issues:
            api_params['diet'] = "Vegan"

    # Step 1: Get the basic meal plan with recipe IDs
    plan_data = _fetch_from_spoonacular('mealplanner/generate', params=api_params)

    if not plan_data or 'week' not in plan_data:
        messages.error(request, 'Could not generate a meal plan. The API may be unavailable or your daily quota exceeded.')
        return redirect('meal_plan')

    # Step 2: Gather all recipe IDs and fetch their details in one bulk call
    recipe_ids = []
    meal_structure = {}
    for day, data in plan_data['week'].items():
        meal_structure[day] = []
        for meal in data['meals']:
            recipe_ids.append(meal['id'])
            meal_structure[day].append(meal)

    ids_string = ','.join(map(str, recipe_ids))
    recipes_details = _fetch_from_spoonacular(
        'recipes/informationBulk',
        params={'ids': ids_string, 'includeNutrition': True}
    )

    if not recipes_details:
        messages.error(request, 'Could not fetch nutritional details for the meal plan. Please try again.')
        return redirect('meal_plan')

    # Create a mapping of recipe ID to its detailed nutrition info
    details_map = {recipe['id']: recipe for recipe in recipes_details}
    
    # Step 3: Create the MealPlan objects with accurate data
    MealPlan.objects.filter(user=request.user).delete()
    meal_types_map = {0: "Breakfast", 1: "Lunch", 2: "Dinner"}

    for day, meals in meal_structure.items():
        for i, meal_stub in enumerate(meals):
            meal_details = details_map.get(meal_stub['id'])
            if meal_details:
                # Extract nutrition safely
                nutrition = meal_details.get('nutrition', {}).get('nutrients', [])
                calories = next((n['amount'] for n in nutrition if n['name'] == 'Calories'), 0)
                protein = next((n['amount'] for n in nutrition if n['name'] == 'Protein'), 0)
                carbs = next((n['amount'] for n in nutrition if n['name'] == 'Carbohydrates'), 0)
                fats = next((n['amount'] for n in nutrition if n['name'] == 'Fat'), 0)
                
                MealPlan.objects.create(
                    user=request.user,
                    day=day.capitalize(),
                    meal_type=meal_types_map.get(i, f"Meal {i+1}"),
                    meal_name=meal_details.get('title', 'Generated Meal'),
                    spoonacular_id=meal_details.get('id'),
                    calories=round(calories),
                    protein=f"{round(protein)}g",
                    carbs=f"{round(carbs)}g",
                    fats=f"{round(fats)}g",
                    image_url=meal_details.get('image'),
                )
    
    messages.success(request, 'Your new, personalized meal plan has been generated!')
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
        
        response_data = _fetch_from_spoonacular(
            'recipes/complexSearch',
            params={'number': 1, 'targetCalories': original_meal.calories, 'addRecipeNutrition': 'true'}
        )

        if not response_data or not response_data.get('results'):
            response_data = _fetch_from_spoonacular('recipes/random', params={'number': 1, 'addRecipeNutrition': 'true'})

        if response_data and (response_data.get('results') or response_data.get('recipes')):
            new_recipe = response_data.get('results', response_data.get('recipes'))[0]
            
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
            'number': 12, 'addRecipeNutrition': 'true', 'cuisine': 'Indian',
            'diet': diet, 'intolerances': ','.join(intolerances)
        }
    )
    recipes = []
    if recipes_data and 'results' in recipes_data:
        for recipe in recipes_data['results']:
            nutrition = recipe.get('nutrition', {}).get('nutrients', [])
            calories = next((n['amount'] for n in nutrition if n['name'] == 'Calories'), 0)
            recipes.append({
                'id': recipe['id'], 'title': recipe['title'], 'image': recipe['image'],
                'readyInMinutes': recipe.get('readyInMinutes'), 'servings': recipe.get('servings'),
                'calories': round(calories),
            })
    context = {'recipes': recipes}
    return render(request, 'meals/discover.html', context)


@login_required
def grocery_list(request):
    meals = MealPlan.objects.filter(user=request.user)
    ingredient_list = set()
    
    recipe_ids = [meal.spoonacular_id for meal in meals if meal.spoonacular_id]

    if recipe_ids:
        ids_string = ','.join(map(str, recipe_ids))
        recipes_data = _fetch_from_spoonacular(
            'recipes/informationBulk',
            params={'ids': ids_string}
        )
        if recipes_data:
            for recipe in recipes_data:
                for ingredient in recipe.get('extendedIngredients', []):
                    ingredient_list.add(ingredient['name'].capitalize())

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
    today = timezone.now().date()
    seven_days_ago = today - timedelta(days=6)
    meals_last_7_days = MealPlan.objects.filter(
        user=request.user, eaten=True, eaten_at__date__gte=seven_days_ago
    ).order_by('eaten_at__date')

    dates = [(seven_days_ago + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    daily_data = {day: {'calories': 0, 'meals': 0} for day in dates}

    for meal in meals_last_7_days:
        day_str = meal.eaten_at.strftime('%Y-%m-%d')
        if day_str in daily_data:
            daily_data[day_str]['calories'] += meal.calories
            daily_data[day_str]['meals'] += 1

    calories_data = [daily_data[d]['calories'] for d in dates]
    meals_data = [daily_data[d]['meals'] for d in dates]
    
    total_calories_week = sum(calories_data)
    total_meals_week = sum(meals_data)
    days_tracked = len([c for c in calories_data if c > 0])
    avg_daily_calories = total_calories_week // days_tracked if days_tracked > 0 else 0

    best_day_calories = 0
    best_day_date = "N/A"
    if days_tracked > 0:
        tdee = request.user.profile.calculate_tdee()
        closest_diff = float('inf')
        for day_str, data in daily_data.items():
            if data['calories'] > 0:
                diff = abs(data['calories'] - tdee)
                if diff < closest_diff:
                    closest_diff = diff
                    best_day_calories = data['calories']
                    best_day_date = day_str
    
    if request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv', charset='utf-8')
        response['Content-Disposition'] = 'attachment; filename="weekly_progress_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Calories Consumed', 'Meals Eaten'])
        for date, data in daily_data.items():
            writer.writerow([date, data['calories'], data['meals']])
        return response

    context = {
        'dates_json': json.dumps(dates),
        'calories_json': json.dumps(calories_data),
        'meal_counts_json': json.dumps(meals_data),
        'total_calories_week': total_calories_week,
        'total_meals_week': total_meals_week,
        'avg_daily_calories': avg_daily_calories,
        'best_day': {'date': best_day_date, 'calories': best_day_calories},
    }
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

