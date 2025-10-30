from django.db import models
from django.contrib.auth.models import User


class Trainer(models.Model):
    SPECIALISATION_CHOICES = (
        ('zumba', 'Zumba'),
        ('yoga', 'Yoga'),
        ('strength', 'Strength'),
        ('fitness', 'Fitness'),
    )
    name = models.CharField(max_length=100)
    specialization = models.CharField(max_length=100, choices=SPECIALISATION_CHOICES)
    phone = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name + ' ' + self.get_specialization_display()


class GymClass(models.Model):
    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]

    name = models.CharField(max_length=100)
    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE)
    day = models.CharField(max_length=10, choices=DAY_CHOICES)
    time = models.TimeField()
    max_capacity = models.IntegerField()
    is_active = models.BooleanField(default=True)


class Booking(models.Model):
    member = models.ForeignKey(User, on_delete=models.CASCADE)
    gym_class = models.ForeignKey(GymClass, on_delete=models.CASCADE)
    booking_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


class ProgressLog(models.Model):
    member = models.ForeignKey(User, on_delete=models.CASCADE)
    weight = models.DecimalField(max_digits=5, decimal_places=2)
    date_logged = models.DateField(auto_now_add=True)


class Membership(models.Model):
    PLAN_CHOICES = (
        ('basic', 'Basic'),
        ('premium', 'Premium'),
    )

    member = models.OneToOneField(User, on_delete=models.CASCADE)
    plan_type = models.CharField(max_length=50, choices=PLAN_CHOICES)
    is_active = models.BooleanField(default=False)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)