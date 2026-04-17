from django.urls import path
from django.contrib.auth.views import LogoutView, PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('register/', views.register, name='register'),
    path('login/', views.custom_login, name='login'),
    path('logout/', LogoutView.as_view(next_page='landing'), name='logout'),
    path('password-reset/', PasswordResetView.as_view(template_name='accounts/password_reset.html', email_template_name='accounts/password_reset_email.html', subject_template_name='accounts/password_reset_subject.txt', success_url='/accounts/password-reset-done/'), name='password_reset'),
    path('password-reset-done/', PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html', success_url='/accounts/password-reset-complete/'), name='password_reset_confirm'),
    path('password-reset-complete/', PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),
    path('profile/', views.profile, name='profile'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('patents/', views.patent_list, name='patent_list'),
    path('patents/<int:patent_id>/', views.patent_detail, name='patent_detail'),
    path('patents/<int:patent_id>/analyse/', views.analyse_patent, name='analyse_patent'),
    path('verify/<uidb64>/<token>/', views.verify_email, name='verify_email'),
    path('resend-verification/', views.resend_verification, name='resend_verification'),
    # Autocomplete and search URLs
    path('autocomplete/entities/', views.autocomplete_entities, name='autocomplete_entities'),
    path('search/', views.search_patents, name='search_patents'),
    path('search/save/', views.save_search, name='save_search'),
    path('search/delete/<int:search_id>/', views.delete_saved_search, name='delete_saved_search'),
    path('search/analyse-all/', views.analyse_all_patents, name='analyse_all_patents'),
]