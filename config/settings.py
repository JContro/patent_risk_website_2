"""
Django settings for config project.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-change-this-in-production'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email configuration
# Default to console backend for development; set EMAIL_BACKEND environment variable to 'smtp' to use SMTP
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'console')
if EMAIL_BACKEND == 'smtp':
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@patentrisk.com')

# Login/registration settings
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# OpenRouter API configuration
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')

# Patent analysis prompt template
# Use {risks_list} and {patent_claims} as placeholders
PATENT_ANALYSIS_PROMPT = os.environ.get('PATENT_ANALYSIS_PROMPT', '''In the following text please extract (if you find any) snippets of text that present any one of these risks:

{risks_list}

The text is:
{patent_claims}

Please output the text in this format:
[{"snippet": "example", "risk": "risk type (from the given risks)", "confidence score": (float between 0 and 1)}]

if there is no risk detected output []''')

# EU AI Act Risks List
EU_AI_RISKS = [
    # Unacceptable risks p1-p8
    'Unacceptable risk p1 (harmful AI-based manipulation and deception)',
    'Unacceptable risk p2 (harmful AI-based exploitation of vulnerabilities)',
    'Unacceptable risk p3 (social scoring)',
    'Unacceptable risk p4 (individual criminal offence risk assessment or prediction)',
    'Unacceptable risk p5 (untargeted scraping of the internet or CCTV material to create or expand facial recognition databases)',
    'Unacceptable risk p6 (emotion recognition in workplaces and education institutions)',
    'Unacceptable risk p7 (biometric categorisation to deduce certain protected characteristics)',
    'Unacceptable risk p8 (real-time remote biometric identification for law enforcement purposes in publicly accessible spaces)',

    # High risks u1-u9
    'High risk u1 (AI safety components in critical infrastructures (e.g. transport), the failure of which could put the life and health of citizens at risk)',
    'High risk u2 (AI solutions used in education institutions, that may determine the access to education and course of someones professional life (e.g. scoring of exams))',
    'High risk u3 (AI-based safety components of products (e.g. AI application in robot-assisted surgery))',
    'High risk u4 (AI tools for employment, management of workers and access to self-employment (e.g. CV-sorting software for recruitment))',
    'High risk u5 (Certain AI use-cases utilised to give access to essential private and public services (e.g. credit scoring denying citizens opportunity to obtain a loan))',
    'High risk u6 (AI systems used for remote biometric identification, emotion recognition and biometric categorisation (e.g AI system to retroactively identify a shoplifter))',
    'High risk u7 (AI use-cases in law enforcement that may interfere with peoples fundamental rights (e.g. evaluation of the reliability of evidence))',
    'High risk u8 (AI use-cases in migration, asylum and border control management (e.g. automated examination of visa applications))',
    'High risk u9 (AI solutions used in the administration of justice and democratic processes (e.g. AI solutions to prepare court rulings))',

    # General high risks
    'High risk health (risk to health)',
    'High risk safety (risk to safety)',
    'High risk fundamental rights (risk to fundamental rights)',
    'Transparency risk (risks associated with a need for transparency around the use of AI, humans are informed when necessary to preserve trust)',

    # Human rights
    'Human right to life',
    'Human right to freedom from torture (and inhuman or degrading treatment or punishment)',
    'Human right to freedom from slavery and forced labour',
    'Human right to liberty and security (lawful arrest or detention, informed why arrested in language they understand)',
    'Human right to a fair trial (assumed innocent)',
    'Human right to respect for private and family life',
    'Human right to freedom of thought, conscience and religion',
    'Human right to freedom of expression',
    'Human right to freedom of assembly and association (protest)',
    'Human right to marry',
    'Human right to an effective remedy (right to legal remedy by person whose rights have been violated)',
    'Human right to freedom of discrimination',
]
