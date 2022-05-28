from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from elk.celery import app as celery
from market.models import Class, Subscription
from timeline.signals import class_starting_student, class_starting_teacher, classes_losing


@celery.task
def notify_15min_to_class():
    for i in Class.objects.starting_soon(timedelta(minutes=30)).filter(pre_start_notifications_sent_to_teacher=False).distinct('timeline'):
        for other_class_with_the_same_timeline in Class.objects.starting_soon(timedelta(minutes=30)).filter(timeline=i.timeline):
            """
            Set all other starting classes as notified either.
            """
            other_class_with_the_same_timeline.pre_start_notifications_sent_to_teacher = True
            other_class_with_the_same_timeline.save()
        class_starting_teacher.send(sender=notify_15min_to_class, instance=i)

    for i in Class.objects.starting_soon(timedelta(minutes=30)).filter(pre_start_notifications_sent_to_student=False):
        i.pre_start_notifications_sent_to_student = True
        i.save()
        class_starting_student.send(sender=notify_15min_to_class, instance=i)


@celery.task
def lost_classes_warning():
    # TODO Can customer schedule all future classes of subscription at once?
    for i in Subscription.objects.filter(is_fully_used=False,
                                         first_lesson_date__isnull=False,
                                         first_lesson_date__gte=timezone.now() - F('duration'),  # If subscription still not deactivated but expired
                                         ):

        last_class = i.classes.order_by('timeline__start').last()
        if not last_class:
            continue
        if timezone.now() - last_class.timeline.start > timedelta(weeks=1) or last_class.is_lost():
            classes_losing.send(lost_classes_warning, instance=i)
