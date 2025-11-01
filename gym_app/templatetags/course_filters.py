from django import template

register = template.Library()

@register.filter
def filter_day(sessions, day):
    return [session for session in sessions if session.day_of_week == day]