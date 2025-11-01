from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.simple_tag
def get_unique_times(timetable):
    unique_times = set()
    for day_sessions in timetable.values():
        for time_slot in day_sessions.keys():
            unique_times.add(time_slot)
    return sorted(unique_times)