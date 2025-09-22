import re
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from .forms import SignUpForm, ProfileForm
from .models import Profile
from meals.models import MealPlan

def home(request):
    return render(request, 'users/home.html')

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if hasattr(user, 'profile'):
                return redirect('dashboard')
            else:
                return redirect('create_profile')
        else:
            messages.error(request, "Invalid username or password")
    return render(request, "users/login.html")

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('create_profile')
    else:
        form = SignUpForm()
    return render(request, 'users/signup.html', {'form': form})

@login_required
def create_profile(request):
    # Redirect if a profile already exists
    if hasattr(request.user, 'profile'):
        return redirect('dashboard') 

    if request.method == 'POST':
        form = ProfileForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            return redirect('dashboard')
    else:
        form = ProfileForm()

    return render(request, 'users/create_profile.html', {'form': form})

@login_required
def profile_view(request):
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        return redirect('create_profile')

    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('profile')
    else:
        form = ProfileForm(instance=profile)

    context = {
        'form': form,
        'user': request.user
    }
    return render(request, 'users/profile.html', context)

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Profile
from meals.models import MealPlan
import re

@login_required
def dashboard(request):
    """
    Displays the user's dashboard with goal-adjusted calorie intake.
    """
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        return redirect('create_profile')

    # Step 1: Calculate base maintenance calories (TDEE)
    tdee = profile.calculate_tdee()

    # Step 2: Adjust the TDEE based on the user's selected goal
    if profile.goal == 'lose':
        daily_calorie_goal = tdee - 500  # Create a 500 calorie deficit
    elif profile.goal == 'gain':
        daily_calorie_goal = tdee + 500  # Create a 500 calorie surplus
    else:  # 'maintain'
        daily_calorie_goal = tdee

    # Step 3: Calculate today's consumption
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timezone.timedelta(days=1)
    
    today_meals = MealPlan.objects.filter(
        user=request.user,
        eaten=True,
        eaten_at__gte=today_start,
        eaten_at__lt=today_end
    )
    
    calories_consumed = sum(meal.calories for meal in today_meals)
    
    # Safely parse macros from string fields
    total_protein = sum(int(re.search(r'\d+', meal.protein).group()) for meal in today_meals if re.search(r'\d+', meal.protein))
    total_carbs = sum(int(re.search(r'\d+', meal.carbs).group()) for meal in today_meals if re.search(r'\d+', meal.carbs))
    total_fats = sum(int(re.search(r'\d+', meal.fats).group()) for meal in today_meals if re.search(r'\d+', meal.fats))

    # Step 4: Calculate progress percentage using the adjusted goal
    progress_percent = int((calories_consumed / daily_calorie_goal) * 100) if daily_calorie_goal > 0 else 0

    context = {
        'profile': profile,
        'daily_calorie_goal': daily_calorie_goal,
        'calories_consumed': calories_consumed,
        'progress_percent': min(progress_percent, 100),
        'protein': total_protein,
        'carbs': total_carbs,
        'fats': total_fats,
    }
    return render(request, 'users/dashboard.html', context)




def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('home')

