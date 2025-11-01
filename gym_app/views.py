import json
from datetime import datetime, timedelta, time as time_class

import razorpay
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from razorpay import Payment

from GymManagement import settings
from gym_app.models import CourseEnrollment, Course, Member, Trainer, CourseSession, MembershipPlan, ProgressEntry, \
    CoursePayment, Payment
from gym_app.forms import CustomUserCreationForm


def index(request):
    context = {}
    return render(request, 'home.html', context)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('login')


# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        # Handle the actual registration after payment
        return handle_registration_after_payment(request)
    else:
        form = UserCreationForm()

    # Pass Razorpay key to template
    context = {
        'form': form,
        'RAZORPAY_KEY_ID': settings.RAZORPAY_KEY_ID,
    }
    return render(request, 'register.html', context)


def create_payment_order(request, amount, membership_type):
    """Create Razorpay order for payment - using the working approach"""
    try:
        # Convert amount to paisa (Razorpay expects amount in smallest currency unit)
        amount_in_paisa = int(float(amount) * 100)

        # Create a Razorpay order
        order_data = {
            'amount': amount_in_paisa,
            'currency': 'INR',  # Changed to INR as per working example
            'receipt': f'membership_{membership_type.lower()}_{timezone.now().strftime("%Y%m%d%H%M%S")}',
            'payment_capture': '1',  # Auto-capture payment
            'notes': {
                'membership_type': membership_type,
                'description': f"FitPro Gym {membership_type} Membership"
            }
        }

        # Create an order
        order = razorpay_client.order.create(data=order_data)

        return {
            'success': True,
            'order_id': order['id'],
            'amount': order_data['amount'],
            'currency': order_data['currency'],
            'razorpay_api_key': settings.RAZORPAY_KEY_ID,
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def payment_gateway_view(request):
    """Handle payment gateway rendering"""
    if request.method == 'POST':
        # Get form data from registration
        membership_type = request.POST.get('membership_type', 'Basic')

        # Validate required fields
        required_fields = ['username', 'password1', 'password2', 'first_name', 'last_name', 'email', 'phone']
        for field in required_fields:
            if not request.POST.get(field):
                messages.error(request, f'Missing required field: {field}')
                return redirect('register')

        # Define membership prices
        membership_prices = {
            'Basic': 500,  # ₹500
            'Premium': 1000,  # ₹1000
        }

        amount = membership_prices.get(membership_type, 500)

        # Store ALL form data in session for after payment
        request.session['registration_data'] = {
            'username': request.POST.get('username'),
            'password1': request.POST.get('password1'),
            'password2': request.POST.get('password2'),
            'first_name': request.POST.get('first_name'),
            'last_name': request.POST.get('last_name'),
            'email': request.POST.get('email'),
            'date_of_birth': request.POST.get('date_of_birth'),
            'address': request.POST.get('address'),
            'phone': request.POST.get('phone'),
            'contact': request.POST.get('contact'),
            'membership_type': membership_type,
            'amount': amount,
        }

        # Save the session
        request.session.modified = True

        # Create payment order
        payment_result = create_payment_order(request, amount, membership_type)

        if payment_result['success']:
            context = {
                'razorpay_api_key': payment_result['razorpay_api_key'],
                'amount': payment_result['amount'],
                'currency': payment_result['currency'],
                'order_id': payment_result['order_id'],
                'membership_type': membership_type,
                'amount_display': amount,
            }
            return render(request, 'payment_gateway.html', context)
        else:
            messages.error(request, f'Payment initialization failed: {payment_result["error"]}')
            return redirect('register')

    # If not POST, redirect to registration
    return redirect('register')


def handle_registration_after_payment(request):
    """Handle registration after successful payment"""
    if request.method == 'POST':
        # Get registration data from session
        registration_data = request.session.get('registration_data')

        if not registration_data:
            messages.error(request, 'Session expired or invalid. Please start registration again.')
            return redirect('register')

        try:
            # Verify payment signature
            params_dict = {
                'razorpay_payment_id': request.POST.get('razorpay_payment_id'),
                'razorpay_order_id': request.POST.get('razorpay_order_id'),
                'razorpay_signature': request.POST.get('razorpay_signature')
            }

            # Verify payment signature
            razorpay_client.utility.verify_payment_signature(params_dict)

            # Payment verified successfully, now create user and member
            form_data = {
                'username': registration_data['username'],
                'password1': registration_data['password1'],
                'password2': registration_data['password2'],
            }

            form = UserCreationForm(form_data)
            if form.is_valid():
                # Create user
                user = form.save(commit=False)
                user.email = registration_data['email']
                user.first_name = registration_data['first_name']
                user.last_name = registration_data['last_name']
                user.save()

                # Get or create membership plan
                membership_type = registration_data['membership_type']
                membership_plan, created = MembershipPlan.objects.get_or_create(
                    name=membership_type,
                    defaults={
                        'price': 500.00 if membership_type == 'Basic' else 1000.00,
                        'description': f'{membership_type} membership plan',
                        'features': 'Gym Access, Equipment Usage',
                        'is_active': True
                    }
                )

                # Create member profile
                member = Member.objects.create(
                    user=user,
                    membership_plan=membership_plan,
                    phone=registration_data['phone'],
                    alternative_contact=registration_data.get('contact', ''),
                    date_of_birth=registration_data.get('date_of_birth'),
                    address=registration_data.get('address', ''),
                    membership_purchase_date=timezone.now().date(),
                    is_active=True
                )

                # Store payment information - with error handling
                try:
                    # Check if Payment model exists and has objects manager
                    from .models import Payment  # Replace your_app_name with your actual app name

                    Payment.objects.create(
                        member=member,
                        razorpay_payment_id=params_dict['razorpay_payment_id'],
                        razorpay_order_id=params_dict['razorpay_order_id'],
                        amount=membership_plan.price,
                        status='completed',
                        payment_date=timezone.now()
                    )
                    payment_saved = True
                except Exception as e:
                    print(f"Payment record creation failed: {e}")
                    payment_saved = False
                    # Don't fail the entire registration if payment record fails

                # Clear session data
                if 'registration_data' in request.session:
                    del request.session['registration_data']

                # Auto-login after registration
                login(request, user)

                if payment_saved:
                    messages.success(request, f'Registration successful! Welcome to FitPro Gym, {user.first_name}!')
                else:
                    messages.success(request,
                                     f'Registration successful! Welcome to FitPro Gym, {user.first_name}! (Payment record not saved)')

                return redirect('dashboard')
            else:
                # Form validation failed
                error_message = ' '.join([f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()])
                messages.error(request, f'Registration failed: {error_message}')
                return redirect('register')

        except razorpay.errors.SignatureVerificationError:
            messages.error(request, 'Payment verification failed. Please try again.')
            return redirect('register')
        except Exception as e:
            messages.error(request, f'Registration failed: {str(e)}')
            import traceback
            print(traceback.format_exc())  # This will help debug
            return redirect('register')

    messages.error(request, 'Invalid request method.')
    return redirect('register')


@login_required
def dashboard(request):
    """Redirect to appropriate dashboard based on user type"""
    if request.user.is_staff:
        return redirect('admin_dashboard')
    else:
        return redirect('customer_dashboard')


@login_required
def admin_dashboard(request):
    """Admin-specific dashboard"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    # Basic counts
    total_members = Member.objects.filter(is_active=True).count()
    total_all_members = Member.objects.count()
    total_trainers = Trainer.objects.filter(is_active=True).count()
    total_all_trainers = Trainer.objects.count()
    total_courses = Course.objects.filter(is_active=True).count()
    total_all_courses = Course.objects.count()

    # Today's data
    today = timezone.now().date()
    today_enrollments = CourseEnrollment.objects.filter(
        enrolled_date__date=today
    ).count()

    # Calculate today's revenue
    today_payments = CoursePayment.objects.filter(
        payment_date__date=today,
        status='completed'
    )
    today_revenue = sum(float(payment.amount) for payment in today_payments)

    # Recent members (last 7 days)
    recent_members = Member.objects.filter(
        created_date__date__gte=today - timedelta(days=7)
    ).select_related('user', 'membership_plan').order_by('-created_date')[:5]

    # Recent enrollments
    recent_enrollments = CourseEnrollment.objects.filter(
        enrolled_date__date__gte=today - timedelta(days=7)
    ).select_related('member__user', 'course').order_by('-enrolled_date')[:5]

    # Revenue and transaction data
    total_revenue = sum(
        float(payment.amount)
        for payment in CoursePayment.objects.filter(status='completed')
    ) + sum(
        float(payment.amount)
        for payment in Payment.objects.filter(status='completed')
    )

    total_transactions = (CoursePayment.objects.filter(status='completed').count() +
                          Payment.objects.filter(status='completed').count())

    # Popular courses
    from django.db.models import Count
    popular_courses = Course.objects.annotate(
        enrollment_count=Count('enrollments')
    ).filter(
        enrollments__is_active=True
    ).order_by('-enrollment_count')[:5]

    # Membership distribution
    membership_distribution = []
    total_active_members = Member.objects.filter(is_active=True).count()

    for plan in MembershipPlan.objects.all():
        member_count = Member.objects.filter(
            membership_plan=plan,
            is_active=True
        ).count()
        percentage = (member_count / total_active_members * 100) if total_active_members > 0 else 0

        membership_distribution.append({
            'name': plan.name,
            'member_count': member_count,
            'percentage': round(percentage, 1)
        })

    # Active trainers for management section
    active_trainers = Trainer.objects.filter(is_active=True).prefetch_related('courses')[:10]

    context = {
        'total_members': total_members,
        'total_all_members': total_all_members,
        'total_trainers': total_trainers,
        'total_all_trainers': total_all_trainers,
        'total_courses': total_courses,
        'total_all_courses': total_all_courses,
        'today_enrollments': today_enrollments,
        'today_revenue': round(today_revenue, 2),
        'recent_members': recent_members,
        'recent_enrollments': recent_enrollments,
        'total_revenue': round(total_revenue, 2),
        'total_transactions': total_transactions,
        'popular_courses': popular_courses,
        'membership_distribution': membership_distribution,
        'active_trainers': active_trainers,
    }

    return render(request, 'admin_dashboard.html', context)


@login_required
def customer_dashboard(request):
    """Customer-specific dashboard with timetable"""
    if request.user.is_staff:
        return redirect('admin_dashboard')

    context = {}

    try:
        member = Member.objects.get(user=request.user)
        context['member'] = member
        context['has_active_membership'] = member.has_active_membership()
        context['latest_progress'] = member.get_latest_progress()

        # Active enrollments
        active_enrollments = CourseEnrollment.objects.filter(
            member=member,
            is_active=True,
            end_date__gte=timezone.now().date()
        ).select_related('course', 'course__trainer')
        context['active_enrollments'] = active_enrollments

        # Weekly sessions count
        context['weekly_sessions'] = active_enrollments.count() * 2  # Placeholder calculation

        # Days since joined
        if member.has_active_membership():
            days_joined = (timezone.now().date() - member.membership_purchase_date).days
            context['days_joined'] = max(0, days_joined)
        else:
            context['days_until_renewal'] = 0

        # Get timetable data for enrolled courses
        enrolled_course_ids = active_enrollments.values_list('course_id', flat=True)

        # Get all sessions for enrolled courses
        sessions = CourseSession.objects.filter(
            course_id__in=enrolled_course_ids,
            is_active=True
        ).select_related('course', 'course__trainer')

        # Separate sessions by day
        context['sunday_sessions'] = sessions.filter(day_of_week='Sunday').order_by('start_time')
        context['monday_sessions'] = sessions.filter(day_of_week='Monday').order_by('start_time')
        context['tuesday_sessions'] = sessions.filter(day_of_week='Tuesday').order_by('start_time')
        context['wednesday_sessions'] = sessions.filter(day_of_week='Wednesday').order_by('start_time')
        context['thursday_sessions'] = sessions.filter(day_of_week='Thursday').order_by('start_time')
        context['friday_sessions'] = sessions.filter(day_of_week='Friday').order_by('start_time')
        context['saturday_sessions'] = sessions.filter(day_of_week='Saturday').order_by('start_time')

        # Check if there's any timetable data
        context['has_timetable_data'] = sessions.exists()

    except Member.DoesNotExist:
        context['member'] = None
        context['has_active_membership'] = False
        context['latest_progress'] = None
        context['active_enrollments'] = []
        context['weekly_sessions'] = 0
        context['days_until_renewal'] = 0
        context['has_timetable_data'] = False
        # Initialize empty session lists
        for day in ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']:
            context[f'{day}_sessions'] = []

    return render(request, 'customer_dashboard.html', context)


@login_required
def course_catalog(request):
    # Get all available courses
    courses = Course.objects.filter(is_active=True)

    # Get filter parameters
    search_query = request.GET.get('search', '')
    level_filter = request.GET.get('level', '')
    price_filter = request.GET.get('price', '')
    trainer_filter = request.GET.get('trainer', '')
    specialization_filter = request.GET.get('specialization', '')

    # Apply filters
    if search_query:
        courses = courses.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(trainer__name__icontains=search_query)
        )

    if level_filter:
        courses = courses.filter(difficulty_level=level_filter)

    if price_filter:
        if price_filter == 'under_50':
            courses = courses.filter(price__lt=50)
        elif price_filter == '50_100':
            courses = courses.filter(price__gte=50, price__lte=100)
        elif price_filter == 'over_100':
            courses = courses.filter(price__gt=100)

    if trainer_filter:
        courses = courses.filter(trainer_id=trainer_filter)

    if specialization_filter:
        courses = courses.filter(trainer__specialization=specialization_filter)

    # Get trainers and specializations for filter
    trainers = Trainer.objects.filter(is_active=True)
    specializations = Trainer.SPECIALIZATION_CHOICES

    # Check if user has active membership and get member object
    try:
        member = Member.objects.get(user=request.user)
        has_active_membership = member.has_active_membership()
    except Member.DoesNotExist:
        has_active_membership = False
        member = None

    # Check which courses user is already enrolled in
    enrolled_course_ids = []
    if member:
        enrolled_course_ids = CourseEnrollment.objects.filter(
            member=member,
            is_active=True,
            end_date__gte=timezone.now().date()
        ).values_list('course_id', flat=True)

    context = {
        'courses': courses,
        'trainers': trainers,
        'specializations': specializations,
        'has_active_membership': has_active_membership,
        'enrolled_course_ids': list(enrolled_course_ids),
        'search_query': search_query,
        'selected_level': level_filter,
        'selected_price': price_filter,
        'selected_trainer': trainer_filter,
        'selected_specialization': specialization_filter,
    }

    return render(request, 'course_catalog.html', context)


@login_required
def purchase_course(request, course_id):
    # Check if user has member profile
    try:
        member = Member.objects.get(user=request.user)
    except Member.DoesNotExist:
        messages.error(request, 'Please complete your member profile first.')
        return redirect('profile')

    # Check active membership
    if not member.has_active_membership():
        messages.error(request, 'Your membership is not active. Please renew your membership to purchase courses.')
        return redirect('course_catalog')

    # Get course
    course = get_object_or_404(Course, id=course_id, is_active=True)

    # Check if course is available
    if not course.is_available():
        messages.error(request, 'This course is currently full. Please try another course.')
        return redirect('course_catalog')

    # Check if already enrolled
    existing_enrollment = CourseEnrollment.objects.filter(
        member=member,
        course=course,
        is_active=True,
        end_date__gte=timezone.now().date()
    ).exists()

    if existing_enrollment:
        messages.warning(request, f'You are already enrolled in {course.name}')
        return redirect('course_catalog')

    # Store course enrollment data in session for payment
    request.session['course_enrollment_data'] = {
        'course_id': course.id,
        'course_name': course.name,
        'course_price': str(course.price),
        'member_id': member.id,
    }
    request.session.modified = True

    # Redirect to payment gateway
    return redirect('course_payment_gateway', course_id=course.id)


def course_payment_gateway(request, course_id):
    """Handle course payment gateway"""
    course = get_object_or_404(Course, id=course_id, is_active=True)

    # Get enrollment data from session
    enrollment_data = request.session.get('course_enrollment_data', {})

    if not enrollment_data or str(course.id) != str(enrollment_data.get('course_id')):
        messages.error(request, 'Invalid course enrollment session. Please try again.')
        return redirect('course_catalog')

    # Create payment order
    amount = enrollment_data['course_price']
    payment_result = create_course_payment_order(request, amount, course.name)

    if payment_result['success']:
        context = {
            'razorpay_api_key': payment_result['razorpay_api_key'],
            'amount': payment_result['amount'],
            'currency': payment_result['currency'],
            'order_id': payment_result['order_id'],
            'course': course,
            'amount_display': amount,
        }
        return render(request, 'course_payment_gateway.html', context)
    else:
        messages.error(request, f'Payment initialization failed: {payment_result["error"]}')
        return redirect('course_catalog')


def create_course_payment_order(request, amount, course_name):
    """Create Razorpay order for course payment"""
    try:
        # Convert amount to paisa (INR)
        amount_in_paisa = int(float(amount) * 100)

        # Create a Razorpay order
        order_data = {
            'amount': amount_in_paisa,
            'currency': 'INR',
            'receipt': f'course_{course_name.lower().replace(" ", "_")}_{timezone.now().strftime("%Y%m%d%H%M%S")}',
            'payment_capture': '1',
            'notes': {
                'course_name': course_name,
                'description': f"FitPro Gym Course: {course_name}"
            }
        }

        # Create an order
        order = razorpay_client.order.create(data=order_data)

        return {
            'success': True,
            'order_id': order['id'],
            'amount': order_data['amount'],
            'currency': order_data['currency'],
            'razorpay_api_key': settings.RAZORPAY_KEY_ID,
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@login_required
def handle_course_payment_success(request):
    """Handle course enrollment after successful payment"""
    if request.method == 'POST':
        # Get enrollment data from session
        enrollment_data = request.session.get('course_enrollment_data', {})

        if not enrollment_data:
            messages.error(request, 'Session expired. Please start enrollment again.')
            return redirect('course_catalog')

        try:
            # Verify payment signature
            params_dict = {
                'razorpay_payment_id': request.POST.get('razorpay_payment_id'),
                'razorpay_order_id': request.POST.get('razorpay_order_id'),
                'razorpay_signature': request.POST.get('razorpay_signature')
            }

            # Verify payment signature
            razorpay_client.utility.verify_payment_signature(params_dict)

            # Payment verified successfully, now create enrollment
            course = Course.objects.get(id=enrollment_data['course_id'])
            member = Member.objects.get(id=enrollment_data['member_id'])

            # Create enrollment
            enrollment = CourseEnrollment.objects.create(
                member=member,
                course=course,
                start_date=timezone.now().date(),
                end_date=timezone.now().date() + timedelta(days=30),
                is_active=True
            )

            # Store payment information
            CoursePayment.objects.create(
                enrollment=enrollment,
                razorpay_payment_id=params_dict['razorpay_payment_id'],
                razorpay_order_id=params_dict['razorpay_order_id'],
                amount=course.price,
                status='completed',
                payment_date=timezone.now()
            )

            # Clear session data
            if 'course_enrollment_data' in request.session:
                del request.session['course_enrollment_data']

            messages.success(request, f'Successfully enrolled in {course.name}! Access valid for 30 days.')
            return redirect('course_catalog')

        except razorpay.errors.SignatureVerificationError:
            messages.error(request, 'Payment verification failed. Please try again.')
            return redirect('course_catalog')
        except Exception as e:
            messages.error(request, f'Enrollment failed: {str(e)}')
            return redirect('course_catalog')

    messages.error(request, 'Invalid request method.')
    return redirect('course_catalog')


@login_required
def class_timetable(request):
    # Get all active courses with their sessions
    courses = Course.objects.filter(is_active=True)

    # Get filter parameters
    day_filter = request.GET.get('day', '')
    trainer_filter = request.GET.get('trainer', '')
    specialization_filter = request.GET.get('specialization', '')

    # Get user's enrolled courses
    try:
        member = Member.objects.get(user=request.user)
        enrolled_courses = CourseEnrollment.objects.filter(
            member=member,
            is_active=True,
            end_date__gte=timezone.now().date()
        ).values_list('course_id', flat=True)
    except Member.DoesNotExist:
        enrolled_courses = []

    # Get all sessions for active courses
    sessions = CourseSession.objects.filter(
        course__in=courses,
        is_active=True
    ).select_related('course', 'course__trainer')

    # Apply filters
    if day_filter:
        sessions = sessions.filter(day_of_week=day_filter)

    if trainer_filter:
        sessions = sessions.filter(course__trainer_id=trainer_filter)

    if specialization_filter:
        sessions = sessions.filter(course__trainer__specialization=specialization_filter)

    # Group sessions by day and time for timetable display
    timetable = {}
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Also collect unique times for the table rows
    unique_times = set()

    for session in sessions:
        day = session.day_of_week
        time_slot = f"{session.start_time.strftime('%H:%M')}-{session.end_time.strftime('%H:%M')}"
        unique_times.add(time_slot)

        if day not in timetable:
            timetable[day] = {}

        if time_slot not in timetable[day]:
            timetable[day][time_slot] = []

        timetable[day][time_slot].append(session)

    # Sort timetable by day order and time
    sorted_timetable = {}
    for day in days_order:
        if day in timetable:
            sorted_timetable[day] = dict(sorted(timetable[day].items()))

    # Sort unique times
    sorted_unique_times = sorted(unique_times)

    # Get filters data
    trainers = Trainer.objects.filter(is_active=True)
    specializations = Trainer.SPECIALIZATION_CHOICES

    context = {
        'timetable': sorted_timetable,
        'days_order': days_order,
        'unique_times': sorted_unique_times,
        'trainers': trainers,
        'specializations': specializations,
        'enrolled_courses': list(enrolled_courses),
        'selected_day': day_filter,
        'selected_trainer': trainer_filter,
        'selected_specialization': specialization_filter,
    }

    return render(request, 'class_timetable.html', context)


@login_required
def profile(request):
    try:
        member = Member.objects.get(user=request.user)
        latest_progress = member.get_latest_progress()
    except Member.DoesNotExist:
        member = None
        latest_progress = None

    # Get active enrollments for the member
    active_enrollments = []
    if member:
        active_enrollments = CourseEnrollment.objects.filter(
            member=member,
            is_active=True,
            end_date__gte=timezone.now().date()
        ).select_related('course', 'course__trainer')

    if request.method == 'POST':
        # Check if this is a profile update or progress update
        if 'update_stats' in request.POST:
            # Handle progress update
            height = request.POST.get('height')
            weight = request.POST.get('weight')
            notes = request.POST.get('progress_notes', '')

            if height and weight:
                # Create new progress entry
                progress_entry = ProgressEntry.objects.create(
                    member=member,
                    height=height,
                    weight=weight,
                    notes=notes
                )
                messages.success(request, 'Progress updated successfully!')
            else:
                messages.error(request, 'Please provide both height and weight.')

            return redirect('profile')

        else:
            # Handle profile update
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            email = request.POST.get('email')
            phone = request.POST.get('phone')
            date_of_birth = request.POST.get('date_of_birth')
            address = request.POST.get('address')
            alternative_contact = request.POST.get('contact')
            emergency_contact_name = request.POST.get('emergency_contact_name')
            emergency_contact_phone = request.POST.get('emergency_contact_phone')
            emergency_contact_relationship = request.POST.get('emergency_contact_relationship')

            # Update User model
            user = request.user
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.save()

            if not member:
                # Create member profile with Basic membership as default
                membership_plan = MembershipPlan.objects.filter(name='Basic').first()
                if not membership_plan:
                    # Create a basic plan if it doesn't exist
                    membership_plan = MembershipPlan.objects.create(
                        name='Basic',
                        price=29.99,
                        description='Basic gym membership',
                        features='Gym Access,Basic Equipment',
                        is_active=True
                    )

                member = Member.objects.create(
                    user=user,
                    membership_plan=membership_plan,
                    phone=phone,
                    alternative_contact=alternative_contact,
                    date_of_birth=date_of_birth if date_of_birth else None,
                    address=address,
                    emergency_contact_name=emergency_contact_name,
                    emergency_contact_phone=emergency_contact_phone,
                    emergency_contact_relationship=emergency_contact_relationship,
                    membership_start_date=timezone.now().date(),
                    membership_end_date=timezone.now().date() + timedelta(days=30)
                )
                messages.success(request, 'Profile created successfully!')
            else:
                # Update existing profile
                member.phone = phone
                member.alternative_contact = alternative_contact
                member.date_of_birth = date_of_birth if date_of_birth else None
                member.address = address
                member.emergency_contact_name = emergency_contact_name
                member.emergency_contact_phone = emergency_contact_phone
                member.emergency_contact_relationship = emergency_contact_relationship
                member.save()
                messages.success(request, 'Profile updated successfully!')

            return redirect('profile')

    # Get progress history for chart
    progress_history = []
    if member:
        progress_history = member.progress_entries.all()[:10]  # Last 10 entries

    context = {
        'member': member,
        'latest_progress': latest_progress,
        'active_enrollments': active_enrollments,
        'progress_history': progress_history,
    }

    # Days since joined
    if member.has_active_membership():
        days_joined = (timezone.now().date() - member.membership_purchase_date).days
        context['days_joined'] = max(0, days_joined)
    else:
        context['days_joined'] = 0

    return render(request, 'profile.html', context)


@login_required
def progress_tracking(request):
    """Detailed progress tracking page with charts and history"""
    try:
        member = Member.objects.get(user=request.user)
        latest_progress = member.get_latest_progress()
        progress_entries = member.progress_entries.all()[:20]
    except Member.DoesNotExist:
        member = None
        latest_progress = None
        progress_entries = []

    # Prepare progress data with calculated changes
    progress_data = []
    for i, entry in enumerate(progress_entries):
        weight_change = None
        weight_change_display = None
        change_type = None

        if i < len(progress_entries) - 1:  # If there's a next entry
            next_entry = progress_entries[i + 1]
            weight_change = float(entry.weight) - float(next_entry.weight)

            # Determine change type and format display
            if weight_change > 0:
                weight_change_display = f"+{weight_change:.1f}"
                change_type = 'increase'
            elif weight_change < 0:
                weight_change_display = f"{weight_change:.1f}"  # Already negative
                change_type = 'decrease'
            else:
                weight_change_display = "0.0"
                change_type = 'same'

        progress_data.append({
            'entry': entry,
            'weight_change': weight_change,
            'weight_change_display': weight_change_display,
            'change_type': change_type,
            'is_current': i == 0  # First entry is current
        })

    # Calculate progress insights
    progress_insights = []
    if progress_entries and len(progress_entries) > 1:
        current = progress_entries[0]  # Latest entry
        previous = progress_entries[1]  # Previous entry

        weight_change = float(current.weight) - float(previous.weight)
        bmi_change = float(current.bmi) - float(previous.bmi)

        if weight_change < -1:
            progress_insights.append({
                'type': 'success',
                'icon': 'trophy',
                'message': f'Great job! You lost {abs(weight_change):.1f} kg since your last measurement.'
            })
        elif weight_change > 1:
            progress_insights.append({
                'type': 'warning',
                'icon': 'exclamation-triangle',
                'message': f'You gained {weight_change:.1f} kg since your last measurement.'
            })

        if bmi_change < -0.5:
            progress_insights.append({
                'type': 'success',
                'icon': 'arrow-down',
                'message': f'Your BMI improved by {abs(bmi_change):.1f} points!'
            })
        elif bmi_change > 0.5:
            progress_insights.append({
                'type': 'warning',
                'icon': 'arrow-up',
                'message': f'Your BMI increased by {bmi_change:.1f} points.'
            })

        # Goal tracking insight
        if current.get_bmi_category() == 'Normal Weight':
            progress_insights.append({
                'type': 'info',
                'icon': 'check-circle',
                'message': 'You are in the healthy BMI range! Keep up the good work.'
            })
        elif current.get_bmi_category() in ['Overweight', 'Obese']:
            target_weight = (24.9 * (float(current.height) / 100) ** 2)
            weight_to_lose = float(current.weight) - target_weight
            if weight_to_lose > 0:
                progress_insights.append({
                    'type': 'info',
                    'icon': 'bullseye',
                    'message': f'Target: Lose {weight_to_lose:.1f} kg to reach healthy BMI range.'
                })

    if request.method == 'POST':
        # Handle progress update
        height = request.POST.get('height')
        weight = request.POST.get('weight')
        notes = request.POST.get('progress_notes', '')

        if height and weight and member:
            # Create new progress entry
            progress_entry = ProgressEntry.objects.create(
                member=member,
                height=height,
                weight=weight,
                notes=notes
            )
            messages.success(request, 'Progress updated successfully!')
            return redirect('progress_tracking')
        else:
            messages.error(request, 'Please provide both height and weight.')

        return redirect('progress_tracking')

    context = {
        'member': member,
        'latest_progress': latest_progress,
        'progress_data': progress_data,  # Use the prepared data
        'progress_entries': progress_entries,  # Add this line - the raw entries for charts
        'progress_insights': progress_insights,
    }
    return render(request, 'progress.html', context)


@login_required
def admin_trainer_management(request):
    """Admin trainer management with search and filtering"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    # Get filter parameters
    search_query = request.GET.get('search', '')
    specialization_filter = request.GET.get('specialization', '')
    status_filter = request.GET.get('status', '')
    sort_by = request.GET.get('sort', 'name')

    # Start with all trainers
    trainers = Trainer.objects.all()

    # Apply filters
    if search_query:
        trainers = trainers.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if specialization_filter:
        trainers = trainers.filter(specialization=specialization_filter)

    if status_filter:
        if status_filter == 'active':
            trainers = trainers.filter(is_active=True)
        elif status_filter == 'inactive':
            trainers = trainers.filter(is_active=False)

    # Apply sorting
    trainers = trainers.order_by(sort_by)

    # Calculate statistics
    total_trainers = trainers.count()
    active_trainers = trainers.filter(is_active=True).count()
    inactive_trainers = trainers.filter(is_active=False).count()

    context = {
        'trainers': trainers,
        'specializations': Trainer.SPECIALIZATION_CHOICES,
        'search_query': search_query,
        'specialization_filter': specialization_filter,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'total_trainers': total_trainers,
        'active_trainers': active_trainers,
        'inactive_trainers': inactive_trainers,
    }

    return render(request, 'admin_trainer_management.html', context)


@login_required
def admin_add_trainer(request):
    """Add new trainer"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        specialization = request.POST.get('specialization')
        is_active = request.POST.get('is_active') == 'on'

        # Validate required fields
        if not name or not specialization:
            messages.error(request, 'Name and specialization are required fields.')
            return redirect('admin_add_trainer')

        try:
            # Create new trainer
            trainer = Trainer.objects.create(
                name=name,
                description=description,
                specialization=specialization,
                is_active=is_active
            )

            messages.success(request, f'Trainer "{trainer.name}" has been added successfully!')
            return redirect('admin_trainer_management')

        except Exception as e:
            messages.error(request, f'Error creating trainer: {str(e)}')

    context = {
        'specializations': Trainer.SPECIALIZATION_CHOICES,
    }

    return render(request, 'admin_trainer_form.html', context)


@login_required
def admin_edit_trainer(request, trainer_id):
    """Edit existing trainer"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    trainer = get_object_or_404(Trainer, id=trainer_id)

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        specialization = request.POST.get('specialization')
        is_active = request.POST.get('is_active') == 'on'

        # Validate required fields
        if not name or not specialization:
            messages.error(request, 'Name and specialization are required fields.')
            return redirect('admin_edit_trainer', trainer_id=trainer_id)

        try:
            # Update trainer
            trainer.name = name
            trainer.description = description
            trainer.specialization = specialization
            trainer.is_active = is_active
            trainer.save()

            messages.success(request, f'Trainer "{trainer.name}" has been updated successfully!')
            return redirect('admin_trainer_management')

        except Exception as e:
            messages.error(request, f'Error updating trainer: {str(e)}')

    context = {
        'trainer': trainer,
        'specializations': Trainer.SPECIALIZATION_CHOICES,
    }

    return render(request, 'admin_trainer_form.html', context)


@login_required
def admin_toggle_trainer_status(request, trainer_id):
    """Toggle trainer active/inactive status (soft delete)"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    if request.method == 'POST':
        trainer = get_object_or_404(Trainer, id=trainer_id)
        trainer.is_active = not trainer.is_active
        trainer.save()

        action = "activated" if trainer.is_active else "deactivated"
        messages.success(request, f'Trainer "{trainer.name}" has been {action}.')

    return redirect('admin_trainer_management')


@login_required
def admin_trainer_detail(request, trainer_id):
    """Detailed view of a specific trainer"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    trainer = get_object_or_404(Trainer, id=trainer_id)

    # Get trainer's courses
    courses = Course.objects.filter(
        trainer=trainer
    ).select_related('trainer').prefetch_related('sessions')

    # Get active enrollments for each course
    for course in courses:
        course.active_enrollments = CourseEnrollment.objects.filter(
            course=course,
            is_active=True
        ).count()

    context = {
        'trainer': trainer,
        'courses': courses,
    }

    return render(request, 'admin_trainer_detail.html', context)


@login_required
def admin_delete_trainer(request, trainer_id):
    """Delete trainer (soft delete)"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    if request.method == 'POST':
        trainer = get_object_or_404(Trainer, id=trainer_id)
        trainer_name = trainer.name
        trainer.is_active = False
        trainer.save()

        messages.success(request, f'Trainer "{trainer_name}" has been deactivated.')

    return redirect('admin_trainer_management')


@login_required
def admin_member_management(request):
    """Admin member management with search and filtering"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    # Get filter parameters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    membership_filter = request.GET.get('membership', '')
    sort_by = request.GET.get('sort', '-created_date')

    # Start with all members
    members = Member.objects.all().select_related('user', 'membership_plan')

    # Apply filters
    if search_query:
        members = members.filter(
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    if status_filter:
        if status_filter == 'active':
            members = members.filter(is_active=True)
        elif status_filter == 'inactive':
            members = members.filter(is_active=False)

    if membership_filter:
        members = members.filter(membership_plan__name=membership_filter)

    # Apply sorting
    members = members.order_by(sort_by)

    # Get available membership plans for filter
    membership_plans = MembershipPlan.objects.all()

    # Calculate additional member statistics
    total_members = members.count()
    active_members = members.filter(is_active=True).count()
    inactive_members = members.filter(is_active=False).count()

    context = {
        'members': members,
        'membership_plans': membership_plans,
        'search_query': search_query,
        'status_filter': status_filter,
        'membership_filter': membership_filter,
        'sort_by': sort_by,
        'total_members': total_members,
        'active_members': active_members,
        'inactive_members': inactive_members,
    }

    return render(request, 'admin_member_management.html', context)


@login_required
def admin_member_detail(request, member_id):
    """Detailed view of a specific member"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    member = get_object_or_404(Member, id=member_id)

    # Get member's enrollments
    enrollments = CourseEnrollment.objects.filter(
        member=member
    ).select_related('course', 'course__trainer').order_by('-enrolled_date')

    # Get member's payments
    payments = Payment.objects.filter(
        member=member
    ).order_by('-payment_date')

    # Get member's course payments
    course_payments = CoursePayment.objects.filter(
        enrollment__member=member
    ).select_related('enrollment__course').order_by('-payment_date')

    # Get progress history
    progress_entries = ProgressEntry.objects.filter(
        member=member
    ).order_by('-recorded_date')[:10]

    context = {
        'member': member,
        'enrollments': enrollments,
        'payments': payments,
        'course_payments': course_payments,
        'progress_entries': progress_entries,
    }

    return render(request, 'admin_member_detail.html', context)


@login_required
def admin_toggle_member_status(request, member_id):
    """Toggle member active/inactive status"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    if request.method == 'POST':
        member = get_object_or_404(Member, id=member_id)
        member.is_active = not member.is_active
        member.save()

        action = "activated" if member.is_active else "deactivated"
        messages.success(request, f'Member {member.user.get_full_name()} has been {action}.')

    return redirect('admin_member_management')


@login_required
def admin_update_member_plan(request, member_id):
    """Update member's membership plan"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    if request.method == 'POST':
        member = get_object_or_404(Member, id=member_id)
        new_plan_id = request.POST.get('membership_plan')

        try:
            new_plan = MembershipPlan.objects.get(id=new_plan_id)
            old_plan = member.membership_plan
            member.membership_plan = new_plan
            member.save()

            messages.success(request,
                             f'Membership plan updated from {old_plan.name} to {new_plan.name} for {member.user.get_full_name()}.')

        except MembershipPlan.DoesNotExist:
            messages.error(request, 'Invalid membership plan selected.')

    return redirect('admin_member_detail', member_id=member_id)


@login_required
def admin_course_management(request):
    """Admin course management with search and filtering"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    # Get filter parameters
    search_query = request.GET.get('search', '')
    trainer_filter = request.GET.get('trainer', '')
    difficulty_filter = request.GET.get('difficulty', '')
    status_filter = request.GET.get('status', '')
    sort_by = request.GET.get('sort', '-created_date')

    # Start with all courses
    courses = Course.objects.all().select_related('trainer').prefetch_related('sessions')

    # Apply filters
    if search_query:
        courses = courses.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if trainer_filter:
        courses = courses.filter(trainer_id=trainer_filter)

    if difficulty_filter:
        courses = courses.filter(difficulty_level=difficulty_filter)

    if status_filter:
        if status_filter == 'active':
            courses = courses.filter(is_active=True)
        elif status_filter == 'inactive':
            courses = courses.filter(is_active=False)

    # Apply sorting
    courses = courses.order_by(sort_by)

    # Get available trainers and difficulties for filters
    trainers = Trainer.objects.filter(is_active=True)
    difficulties = Course.DIFFICULTY_CHOICES

    # Calculate statistics
    total_courses = courses.count()
    active_courses = courses.filter(is_active=True).count()
    inactive_courses = courses.filter(is_active=False).count()

    # Calculate enrollment statistics for each course
    for course in courses:
        course.active_enrollments = CourseEnrollment.objects.filter(
            course=course,
            is_active=True
        ).count()

        # Calculate enrollment percentage
        if course.capacity > 0:
            course.enrollment_percentage = (course.current_enrollment / course.capacity) * 100
        else:
            course.enrollment_percentage = 0

    context = {
        'courses': courses,
        'trainers': trainers,
        'difficulties': difficulties,
        'search_query': search_query,
        'trainer_filter': trainer_filter,
        'difficulty_filter': difficulty_filter,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'total_courses': total_courses,
        'active_courses': active_courses,
        'inactive_courses': inactive_courses,
    }

    return render(request, 'admin_course_management.html', context)


@login_required
def admin_add_course(request):
    """Add new course"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        capacity = request.POST.get('capacity')
        duration_minutes = request.POST.get('duration_minutes')
        trainer_id = request.POST.get('trainer')
        difficulty_level = request.POST.get('difficulty_level')
        is_active = request.POST.get('is_active') == 'on'

        # Validate required fields
        if not name or not price or not trainer_id:
            messages.error(request, 'Name, price, and trainer are required fields.')
            return redirect('admin_add_course')

        try:
            # Get trainer
            trainer = Trainer.objects.get(id=trainer_id)

            # Create new course
            course = Course.objects.create(
                name=name,
                description=description,
                price=price,
                capacity=capacity or 20,
                duration_minutes=duration_minutes or 60,
                trainer=trainer,
                difficulty_level=difficulty_level or 'All Levels',
                is_active=is_active
            )

            messages.success(request, f'Course "{course.name}" has been created successfully!')
            return redirect('admin_course_management')

        except Trainer.DoesNotExist:
            messages.error(request, 'Selected trainer does not exist.')
        except Exception as e:
            messages.error(request, f'Error creating course: {str(e)}')

    context = {
        'trainers': Trainer.objects.filter(is_active=True),
        'difficulties': Course.DIFFICULTY_CHOICES,
    }

    return render(request, 'admin_course_form.html', context)


@login_required
def admin_edit_course(request, course_id):
    """Edit existing course"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    course = get_object_or_404(Course, id=course_id)

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        capacity = request.POST.get('capacity')
        duration_minutes = request.POST.get('duration_minutes')
        trainer_id = request.POST.get('trainer')
        difficulty_level = request.POST.get('difficulty_level')
        is_active = request.POST.get('is_active') == 'on'

        # Validate required fields
        if not name or not price or not trainer_id:
            messages.error(request, 'Name, price, and trainer are required fields.')
            return redirect('admin_edit_course', course_id=course_id)

        try:
            # Get trainer
            trainer = Trainer.objects.get(id=trainer_id)

            # Update course
            course.name = name
            course.description = description
            course.price = price
            course.capacity = capacity or 20
            course.duration_minutes = duration_minutes or 60
            course.trainer = trainer
            course.difficulty_level = difficulty_level or 'All Levels'
            course.is_active = is_active
            course.save()

            messages.success(request, f'Course "{course.name}" has been updated successfully!')
            return redirect('admin_course_management')

        except Trainer.DoesNotExist:
            messages.error(request, 'Selected trainer does not exist.')
        except Exception as e:
            messages.error(request, f'Error updating course: {str(e)}')

    context = {
        'course': course,
        'trainers': Trainer.objects.filter(is_active=True),
        'difficulties': Course.DIFFICULTY_CHOICES,
    }

    return render(request, 'admin_course_form.html', context)


@login_required
def admin_toggle_course_status(request, course_id):
    """Toggle course active/inactive status"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    if request.method == 'POST':
        course = get_object_or_404(Course, id=course_id)

        # Check if course has active enrollments before deactivating
        active_enrollments = CourseEnrollment.objects.filter(
            course=course,
            is_active=True
        ).exists()

        if not course.is_active and active_enrollments:
            messages.warning(request, f'Cannot deactivate course "{course.name}" - it has active enrollments.')
            return redirect('admin_course_management')

        course.is_active = not course.is_active
        course.save()

        action = "activated" if course.is_active else "deactivated"
        messages.success(request, f'Course "{course.name}" has been {action}.')

    return redirect('admin_course_management')


@login_required
def admin_course_detail(request, course_id):
    """Detailed view of a specific course"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    course = get_object_or_404(Course, id=course_id)

    # Get course sessions
    sessions = CourseSession.objects.filter(course=course).order_by('day_of_week', 'start_time')

    # Get active enrollments
    active_enrollments = CourseEnrollment.objects.filter(
        course=course,
        is_active=True
    ).select_related('member__user')

    # Get enrollment history
    all_enrollments = CourseEnrollment.objects.filter(
        course=course
    ).select_related('member__user').order_by('-enrolled_date')

    # Calculate revenue from this course
    course_revenue = sum(
        float(payment.amount)
        for payment in CoursePayment.objects.filter(enrollment__course=course, status='completed')
    )

    context = {
        'course': course,
        'sessions': sessions,
        'active_enrollments': active_enrollments,
        'all_enrollments': all_enrollments,
        'course_revenue': course_revenue,
    }

    return render(request, 'admin_course_detail.html', context)


@login_required
def admin_delete_course(request, course_id):
    """Delete course (only if no active enrollments)"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    if request.method == 'POST':
        course = get_object_or_404(Course, id=course_id)

        # Check if course has any enrollments
        has_enrollments = CourseEnrollment.objects.filter(course=course).exists()

        if has_enrollments:
            messages.error(request,
                           f'Cannot delete course "{course.name}" - it has enrollment history. You can deactivate it instead.')
        else:
            course_name = course.name
            course.delete()
            messages.success(request, f'Course "{course_name}" has been deleted successfully.')

    return redirect('admin_course_management')


@login_required
def admin_manage_sessions(request, course_id):
    """Manage course sessions"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    course = get_object_or_404(Course, id=course_id)

    if request.method == 'POST':
        # Handle session creation/updates
        if 'add_session' in request.POST:
            day_of_week = request.POST.get('day_of_week')
            start_time = request.POST.get('start_time')

            if day_of_week and start_time:
                # Calculate end time based on start time and course duration
                start_dt = datetime.strptime(start_time, '%H:%M')
                end_dt = start_dt + timedelta(minutes=course.duration_minutes)
                end_time = end_dt.time()

                CourseSession.objects.create(
                    course=course,
                    day_of_week=day_of_week,
                    start_time=start_time,
                    end_time=end_time
                )
                messages.success(request, 'Session added successfully!')

        # Handle session deletion
        elif 'delete_session' in request.POST:
            session_id = request.POST.get('session_id')
            session = get_object_or_404(CourseSession, id=session_id, course=course)
            session.delete()
            messages.success(request, 'Session deleted successfully!')

    sessions = CourseSession.objects.filter(course=course).order_by('day_of_week', 'start_time')

    sessions_by_day = {}
    for session_day in CourseSession.DAY_CHOICES:
        sessions_by_day[session_day[0]] = sessions.filter(day_of_week=session_day[0])

    context = {
        'course': course,
        'sessions': sessions,
        'sessions_by_day': sessions_by_day,
        'days': CourseSession.DAY_CHOICES,
    }

    return render(request, 'admin_course_sessions.html', context)

@login_required
def admin_reports(request):
    """Admin reports with payment statistics and charts"""
    if not request.user.is_staff:
        return redirect('customer_dashboard')

    # Get filter parameters
    report_type = request.GET.get('report_type', 'revenue')
    date_range = request.GET.get('date_range', '30days')
    payment_type = request.GET.get('payment_type', 'all')

    # Calculate date range
    end_date = timezone.now().date()
    if date_range == '7days':
        start_date = end_date - timedelta(days=7)
    elif date_range == '90days':
        start_date = end_date - timedelta(days=90)
    elif date_range == '1year':
        start_date = end_date - timedelta(days=365)
    else:  # 30 days default
        start_date = end_date - timedelta(days=30)

    # Base querysets
    membership_payments = Payment.objects.filter(
        status='completed',
        payment_date__date__range=[start_date, end_date]
    )

    course_payments = CoursePayment.objects.filter(
        status='completed',
        payment_date__date__range=[start_date, end_date]
    )

    # Apply payment type filter
    if payment_type == 'membership':
        course_payments = course_payments.none()
    elif payment_type == 'course':
        membership_payments = membership_payments.none()

    # Calculate statistics
    total_revenue = sum(float(p.amount) for p in membership_payments) + sum(float(p.amount) for p in course_payments)
    total_transactions = membership_payments.count() + course_payments.count()
    avg_transaction_value = total_revenue / total_transactions if total_transactions > 0 else 0

    # Revenue by type
    membership_revenue = sum(float(p.amount) for p in membership_payments)
    course_revenue = sum(float(p.amount) for p in course_payments)

    # Daily revenue data for charts
    daily_revenue = []
    current_date = start_date
    while current_date <= end_date:
        day_membership = sum(
            float(p.amount) for p in membership_payments.filter(payment_date__date=current_date)
        )
        day_course = sum(
            float(p.amount) for p in course_payments.filter(payment_date__date=current_date)
        )
        daily_revenue.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'membership': float(day_membership),
            'course': float(day_course),
            'total': float(day_membership + day_course)
        })
        current_date += timedelta(days=1)

    # Top courses by revenue
    top_courses = CoursePayment.objects.filter(
        status='completed',
        payment_date__date__range=[start_date, end_date]
    ).values(
        'enrollment__course__name'
    ).annotate(
        total_revenue=Sum('amount'),
        enrollment_count=Count('id')
    ).order_by('-total_revenue')[:10]

    # Membership plan distribution
    membership_distribution = Payment.objects.filter(
        status='completed',
        payment_date__date__range=[start_date, end_date]
    ).values(
        'member__membership_plan__name'
    ).annotate(
        total_revenue=Sum('amount'),
        payment_count=Count('id')
    ).order_by('-total_revenue')

    # Payment methods summary (simulated - you can enhance this with actual payment method data)
    payment_methods = [
        {'name': 'Razorpay', 'count': total_transactions, 'revenue': total_revenue}
    ]

    # Get recent payments for the table (add this section)
    recent_membership_payments = Payment.objects.filter(
        status='completed',
        payment_date__date__range=[start_date, end_date]
    ).select_related('member__user', 'member__membership_plan').order_by('-payment_date')[:10]

    recent_course_payments = CoursePayment.objects.filter(
        status='completed',
        payment_date__date__range=[start_date, end_date]
    ).select_related('enrollment__member__user', 'enrollment__course').order_by('-payment_date')[:10]

    context = {
        'report_type': report_type,
        'date_range': date_range,
        'payment_type': payment_type,
        'start_date': start_date,
        'end_date': end_date,

        # Statistics
        'total_revenue': round(total_revenue, 2),
        'total_transactions': total_transactions,
        'avg_transaction_value': round(avg_transaction_value, 2),
        'membership_revenue': round(membership_revenue, 2),
        'course_revenue': round(course_revenue, 2),

        # Chart data
        'daily_revenue_json': json.dumps(daily_revenue),
        'top_courses': top_courses,
        'membership_distribution': membership_distribution,
        'payment_methods': payment_methods,

        # Recent payments (ADD THESE)
        'recent_membership_payments': recent_membership_payments,
        'recent_course_payments': recent_course_payments,

        # Filter options
        'date_ranges': [
            ('7days', 'Last 7 Days'),
            ('30days', 'Last 30 Days'),
            ('90days', 'Last 90 Days'),
            ('1year', 'Last Year'),
        ],
        'payment_types': [
            ('all', 'All Payments'),
            ('membership', 'Membership Only'),
            ('course', 'Course Only'),
        ],
    }

    return render(request, 'admin_reports.html', context)
