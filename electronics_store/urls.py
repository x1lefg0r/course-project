"""
URL configuration for electronics_store project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token
from shop.views import register_view, profile_view, oauth_success_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("silk/", include("silk.urls", namespace="silk")),
    # OAuth2 (Google)
    path("auth/", include("social_django.urls", namespace="social")),
    path("api/auth/oauth-success/", oauth_success_view, name="oauth-success"),
    # Token auth
    path("api/auth/token/", obtain_auth_token, name="api-token-auth"),
    path("api/auth/register/", register_view, name="api-register"),
    path("api/auth/profile/", profile_view, name="api-profile"),
    path("", include("shop.urls")),
]
