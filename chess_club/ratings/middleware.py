from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
import time


class PasscodeMiddleware:
    """Simple middleware that requires a session flag to access the site.

    If the session key 'access_granted' is not present and the request path
    isn't the passcode page or static/admin paths, the user is redirected to
    the passcode entry view.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # allowed paths that don't require passcode
        self.allowed_prefixes = [
            settings.STATIC_URL,
            '/admin/',
            '/passcode/',
            '/favicon.ico',
        ]

    def __call__(self, request):
        # if sessions aren't available yet, allow request through (SessionMiddleware should be before this middleware)
        if not hasattr(request, 'session'):
            return self.get_response(request)

        # if already granted, check expiry
        if request.session.get('access_granted'):
            granted_at = request.session.get('access_granted_at')
            if granted_at:
                try:
                    # granted_at stored as epoch seconds (float)
                    if (time.time() - float(granted_at)) > 60 * 60:
                        # expired - remove keys and force passcode again
                        request.session.pop('access_granted', None)
                        request.session.pop('access_granted_at', None)
                        return redirect(reverse('passcode'))
                except Exception:
                    # if anything odd, remove keys and require passcode
                    request.session.pop('access_granted', None)
                    request.session.pop('access_granted_at', None)
                    return redirect(reverse('passcode'))
            # still valid
            return self.get_response(request)

        path = request.path
        # allow allowed prefixes
        for p in self.allowed_prefixes:
            if path.startswith(p):
                return self.get_response(request)

        # allow AJAX to pass through (optional)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return self.get_response(request)

        # otherwise redirect to passcode entry
        return redirect(reverse('passcode'))
