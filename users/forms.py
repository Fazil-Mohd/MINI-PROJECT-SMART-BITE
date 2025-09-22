from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Profile

class SignUpForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        # Add 'goal' to this list of fields
        fields = ['age', 'weight', 'height', 'gender', 'activity_level', 'goal', 'health_issues']
        widgets = {
            'health_issues': forms.Textarea(attrs={'rows': 3}),
        }