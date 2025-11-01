from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta, datetime, date


class MembershipPlan(models.Model):
    PLAN_CHOICES = [
        ('Basic', 'Basic'),
        ('Premium', 'Premium'),
    ]

    name = models.CharField(max_length=50, choices=PLAN_CHOICES, unique=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField()
    features = models.TextField(help_text="List of features separated by commas")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - ${self.price}/month"


class Trainer(models.Model):
    SPECIALIZATION_CHOICES = [
        ('Yoga', 'Yoga'),
        ('Strength Training', 'Strength Training'),
        ('Cardio', 'Cardio'),
        ('Pilates', 'Pilates'),
        ('CrossFit', 'CrossFit'),
        ('Martial Arts', 'Martial Arts'),
        ('Dance', 'Dance'),
        ('General Fitness', 'General Fitness'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    specialization = models.CharField(max_length=50, choices=SPECIALIZATION_CHOICES)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.specialization}"


class Member(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    membership_plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT)
    membership_purchase_date = models.DateField(default=timezone.now)  # Changed from start_date
    phone = models.CharField(max_length=15, blank=True, null=True)
    alternative_contact = models.CharField(max_length=15, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=15, blank=True, null=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_date = models.DateTimeField(auto_now_add=True)

    def has_active_membership(self):
        """Membership is lifetime once purchased - just check is_active status"""
        return self.is_active

    def get_membership_duration(self):
        """Calculate how long the member has been with the gym"""
        duration = timezone.now().date() - self.membership_purchase_date
        return duration.days

    def get_membership_status(self):
        """Get membership status for display"""
        if self.is_active:
            return "Active"
        return "Inactive"

    def get_latest_progress(self):
        """Get the most recent progress entry"""
        return self.progress_entries.order_by('-recorded_date').first()

    def __str__(self):
        return f"{self.user.username} - {self.membership_plan.name}"

    class Meta:
        verbose_name = "Member"
        verbose_name_plural = "Members"


class ProgressEntry(models.Model):
    """Model to track member's progress over time"""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='progress_entries')
    height = models.DecimalField(max_digits=5, decimal_places=2, help_text="Height in cm")
    weight = models.DecimalField(max_digits=5, decimal_places=2, help_text="Weight in kg")
    bmi = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about this progress entry")
    recorded_date = models.DateTimeField(default=timezone.now)
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_date']
        verbose_name_plural = "Progress entries"

    def save(self, *args, **kwargs):
        # Calculate BMI before saving
        if self.height and self.weight:
            height_m = float(self.height) / 100  # Convert cm to meters
            self.bmi = round(float(self.weight) / (height_m * height_m), 2)
        super().save(*args, **kwargs)

    def get_bmi_category(self):
        if not self.bmi:
            return "Unknown"
        bmi = float(self.bmi)
        if bmi < 18.5:
            return "Underweight"
        elif bmi < 25:
            return "Normal Weight"
        elif bmi < 30:
            return "Overweight"
        else:
            return "Obese"

    def __str__(self):
        return f"{self.member.user.username} - {self.recorded_date.date()} - BMI: {self.bmi}"


class Course(models.Model):
    DIFFICULTY_CHOICES = [
        ('Beginner', 'Beginner'),
        ('Intermediate', 'Intermediate'),
        ('Advanced', 'Advanced'),
        ('All Levels', 'All Levels'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    capacity = models.IntegerField(default=20)
    current_enrollment = models.IntegerField(default=0)
    duration_minutes = models.IntegerField(default=60)
    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='courses')
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='All Levels')
    is_active = models.BooleanField(default=True)
    created_date = models.DateTimeField(auto_now_add=True)

    def is_available(self):
        return self.current_enrollment < self.capacity and self.is_active

    def __str__(self):
        return f"{self.name} - {self.trainer.name} - ${self.price}"


class CourseSession(models.Model):
    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')
    day_of_week = models.CharField(max_length=10, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['day_of_week', 'start_time']

    @property
    def duration_display(self):
        """Get formatted duration display"""
        start_dt = datetime.combine(date.today(), self.start_time)
        end_dt = datetime.combine(date.today(), self.end_time)
        duration_hours = (end_dt - start_dt).total_seconds() / 3600
        return f"{duration_hours:.1f} hour{'s' if duration_hours != 1 else ''}"

    def __str__(self):
        return f"{self.course.name} - {self.day_of_week} {self.start_time}"


class CourseEnrollment(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    enrolled_date = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=30)

        super().save(*args, **kwargs)

        # Update course enrollment count
        if is_new and self.is_active:
            self.course.current_enrollment += 1
            self.course.save()

    def delete(self, *args, **kwargs):
        # Decrease enrollment count when enrollment is deleted
        if self.is_active:
            self.course.current_enrollment -= 1
            self.course.save()
        super().delete(*args, **kwargs)

    def is_expired(self):
        return self.end_date < timezone.now().date()

    def is_expiring_soon(self):
        days_until_expiry = (self.end_date - timezone.now().date()).days
        return 0 <= days_until_expiry <= 7

    def __str__(self):
        status = "Active" if self.is_active else "Expired"
        return f"{self.member.user.username} - {self.course.name} ({status})"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    razorpay_payment_id = models.CharField(max_length=100, unique=True)
    razorpay_order_id = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.razorpay_payment_id} - {self.member.user.username}"


class CoursePayment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    enrollment = models.ForeignKey('CourseEnrollment', on_delete=models.CASCADE)
    razorpay_payment_id = models.CharField(max_length=100, unique=True)
    razorpay_order_id = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Course Payment {self.razorpay_payment_id} - {self.enrollment.course.name}"
