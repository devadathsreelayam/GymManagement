from django import template

register = template.Library()

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def next(value, arg):
    """Get next item in list"""
    try:
        return value[int(arg) + 1]
    except (IndexError, TypeError, ValueError):
        return None
