from django.urls import path
from . import views


urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('payment-gateway/', views.payment_gateway_view, name='payment_gateway'),
    path('handle-registration/', views.handle_registration_after_payment, name='handle_registration_after_payment'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('customer_dashboard/', views.customer_dashboard, name='customer_dashboard'),

    # Course Catalog & Purchase
    path('courses/', views.course_catalog, name='course_catalog'),
    path('course/<int:course_id>/purchase/', views.purchase_course, name='purchase_course'),
    path('course/<int:course_id>/payment/', views.course_payment_gateway, name='course_payment_gateway'),
    path('course/payment/success/', views.handle_course_payment_success, name='handle_course_payment_success'),
    path('courses/purchase/<int:course_id>/', views.purchase_course, name='purchase_course'),
    path('timetable/', views.class_timetable, name='class_timetable'),
    path('profile/', views.profile, name='profile'),
    path('progress', views.progress_tracking, name='progress_tracking'),

    # Admin management URLs
    # Trainer management URLs
    path('admin-trainers/', views.admin_trainer_management, name='admin_trainer_management'),
    path('admin-trainers/add/', views.admin_add_trainer, name='admin_add_trainer'),
    path('admin-trainers/<int:trainer_id>/edit/', views.admin_edit_trainer, name='admin_edit_trainer'),
    path('admin-trainers/<int:trainer_id>/', views.admin_trainer_detail, name='admin_trainer_detail'),
    path('admin-trainers/<int:trainer_id>/toggle-status/', views.admin_toggle_trainer_status,
         name='admin_toggle_trainer_status'),
    path('admin-trainers/<int:trainer_id>/delete/', views.admin_delete_trainer, name='admin_delete_trainer'),


    # Admin course management
    path('admin-courses/', views.admin_course_management, name='admin_course_management'),
    path('admin-courses/add/', views.admin_add_course, name='admin_add_course'),
    path('admin-courses/<int:course_id>/edit/', views.admin_edit_course, name='admin_edit_course'),
    path('admin-courses/<int:course_id>/', views.admin_course_detail, name='admin_course_detail'),
    path('admin-courses/<int:course_id>/toggle-status/', views.admin_toggle_course_status,
         name='admin_toggle_course_status'),
    path('admin-courses/<int:course_id>/delete/', views.admin_delete_course, name='admin_delete_course'),
    path('admin-courses/<int:course_id>/sessions/', views.admin_manage_sessions, name='admin_manage_sessions'),

    # Admin member management
    path('admin-members/', views.admin_member_management, name='admin_member_management'),
    path('admin-members/<int:member_id>/', views.admin_member_detail, name='admin_member_detail'),
    path('admin-members/<int:member_id>/toggle-status/', views.admin_toggle_member_status, name='admin_toggle_member_status'),
    path('admin-members/<int:member_id>/update-plan/', views.admin_update_member_plan, name='admin_update_member_plan'),
    path('admin-reports/', views.admin_reports, name='admin_reports'),
]