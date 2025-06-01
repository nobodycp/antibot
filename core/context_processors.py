from django.utils.timezone import now

def inject_now(request):
    return {'now': now()}
