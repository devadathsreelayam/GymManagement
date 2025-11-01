from django.contrib import admin
from .models import MembershipPlan, Trainer, Member, Course, CourseSession, CourseEnrollment, ProgressEntry, Payment, \
    CoursePayment


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active')
    list_editable = ('price', 'is_active')
    list_filter = ('is_active',)


@admin.register(Trainer)
class TrainerAdmin(admin.ModelAdmin):
    list_display = ('name', 'specialization', 'is_active')
    list_filter = ('is_active', 'specialization')
    search_fields = ('name', 'specialization', 'description')
    list_editable = ('is_active',)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'membership_plan', 'membership_purchase_date', 'is_active')
    list_filter = ('is_active', 'membership_plan', 'membership_purchase_date')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    list_editable = ('is_active',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'trainer', 'price', 'capacity', 'current_enrollment', 'difficulty_level', 'is_active')
    list_filter = ('is_active', 'difficulty_level', 'trainer__specialization')
    search_fields = ('name', 'trainer__name', 'description')
    list_editable = ('price', 'capacity', 'is_active')
    readonly_fields = ('current_enrollment',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "trainer":
            kwargs["queryset"] = Trainer.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(CourseSession)
class CourseSessionAdmin(admin.ModelAdmin):
    list_display = ('course', 'day_of_week', 'start_time', 'end_time', 'is_active')
    list_filter = ('is_active', 'day_of_week', 'course')
    list_editable = ('is_active',)


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('member', 'course', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'start_date', 'course')
    search_fields = ('member__user__username', 'course__name')
    readonly_fields = ('enrolled_date',)
    list_editable = ('is_active',)


@admin.register(ProgressEntry)
class ProgressEntryAdmin(admin.ModelAdmin):
    list_display = ('member', 'height', 'weight', 'bmi', 'get_bmi_category', 'recorded_date')
    list_filter = ('recorded_date', 'member')
    search_fields = ('member__user__username', 'member__user__first_name', 'member__user__last_name')
    readonly_fields = ('bmi', 'created_date')
    date_hierarchy = 'recorded_date'

    def get_bmi_category(self, obj):
        return obj.get_bmi_category()

    get_bmi_category.short_description = 'BMI Category'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('member__user')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('razorpay_payment_id', 'get_member_name', 'amount', 'status', 'payment_date')
    list_filter = ('status', 'payment_date')
    search_fields = ('razorpay_payment_id', 'razorpay_order_id', 'member__user__username', 'member__user__first_name')
    readonly_fields = ('razorpay_payment_id', 'razorpay_order_id', 'payment_date', 'created_at')
    list_per_page = 20

    def get_member_name(self, obj):
        return f"{obj.member.user.first_name} {obj.member.user.last_name}"

    get_member_name.short_description = 'Member Name'
    get_member_name.admin_order_field = 'member__user__first_name'


@admin.register(CoursePayment)
class CoursePaymentAdmin(admin.ModelAdmin):
    list_display = ('razorpay_payment_id', 'enrollment', 'amount', 'status', 'payment_date')
    list_filter = ('status', 'payment_date')
    search_fields = ('razorpay_payment_id', 'enrollment__course__name', 'enrollment__member__user__username')
    readonly_fields = ('razorpay_payment_id', 'razorpay_order_id', 'payment_date', 'created_at')

    def get_enrollment_info(self, obj):
        return f"{obj.enrollment.member.user.username} - {obj.enrollment.course.name}"

    get_enrollment_info.short_description = 'Enrollment'