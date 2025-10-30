from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import Trainer, GymClass, Booking, ProgressLog, Membership


# Unregister default User admin if you want to customize it
# admin.site.unregister(User)

# Custom User Admin (Optional but recommended)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')


# Register User with custom admin (optional)
# admin.site.register(User, CustomUserAdmin)

# Trainer Admin
@admin.register(Trainer)
class TrainerAdmin(admin.ModelAdmin):
    list_display = ('name', 'specialization', 'phone', 'is_active')
    list_filter = ('is_active', 'specialization')
    search_fields = ('name', 'specialization')
    list_editable = ('is_active',)


# GymClass Admin
@admin.register(GymClass)
class GymClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'trainer', 'day', 'time', 'max_capacity', 'is_active')
    list_filter = ('day', 'is_active', 'trainer')
    search_fields = ('name', 'trainer__name')
    list_editable = ('is_active', 'max_capacity')

    # Optional: Filter trainers to only active ones
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "trainer":
            kwargs["queryset"] = Trainer.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# Booking Admin
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('member', 'gym_class', 'booking_date', 'is_active')
    list_filter = ('is_active', 'booking_date', 'gym_class__day')
    search_fields = ('member__username', 'member__first_name', 'gym_class__name')
    list_editable = ('is_active',)
    date_hierarchy = 'booking_date'

    # Optional: Filter to active classes and members
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "gym_class":
            kwargs["queryset"] = GymClass.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ProgressLog Admin
@admin.register(ProgressLog)
class ProgressLogAdmin(admin.ModelAdmin):
    list_display = ('member', 'weight', 'date_logged')
    list_filter = ('date_logged',)
    search_fields = ('member__username', 'member__first_name')
    date_hierarchy = 'date_logged'


# Membership Admin
@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('member', 'plan_type', 'is_active', 'start_date', 'end_date')
    list_filter = ('is_active', 'plan_type', 'start_date')
    search_fields = ('member__username', 'member__first_name', 'plan_type')
    list_editable = ('is_active', 'plan_type')
    date_hierarchy = 'start_date'