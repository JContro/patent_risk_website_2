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

# vLLM API configuration
VLLM_API_URL = os.environ.get('VLLM_API_URL', 'http://vllm-api-server:8000')

# Patent analysis prompt template
# Use {risks_list} and {patent_claims} as placeholders
PATENT_ANALYSIS_PROMPT = os.environ.get('PATENT_ANALYSIS_PROMPT', '''Analyze the following patent text and extract any risks related to EU AI Act concerns.

Risks to check for:
{risks_list}

Patent text to analyze:
{patent_claims}

INSTRUCTIONS:
1. Output ONLY valid JSON - no additional text, explanations, or markdown formatting
2. The response must be a JSON array of objects with exactly these keys:
   - "snippet": The exact text from the patent that contains the risk (string)
   - "risk": The exact risk category from the list above (string)
   - "explanation": A brief explanation of why this is a risk (1-2 sentences max)
   - "confidence_score": A float between 0 and 1 (number, not string)
3. If no risks are found, output an empty array: []
4. Do not include any keys other than "snippet", "risk", "explanation", and "confidence_score"
5. Do not add any commentary or explanation outside the JSON - output ONLY the JSON array''')

# EU AI Act Risks - Structured JSON format
# Categories: Unacceptable, High Risk, General High Risks, Human Rights, Online Manipulation
EU_AI_RISKS_STRUCTURE = {
    "Unacceptable": [
        "harmful AI-based manipulation and deception",
        "harmful AI-based exploitation of vulnerabilities",
        "social scoring",
        "individual criminal offence risk assessment or prediction",
        "untargeted scraping of the internet or CCTV material to create or expand facial recognition databases",
        "emotion recognition in workplaces and education institutions",
        "biometric categorisation to deduce certain protected characteristics",
        "real-time remote biometric identification for law enforcement purposes in publicly accessible spaces"
    ],
    "High Risk": [
        "AI safety components in critical infrastructures (e.g. transport), the failure of which could put the life and health of citizens at risk",
        "AI solutions used in education institutions, that may determine the access to education and course of someones professional life (e.g. scoring of exams)",
        "AI-based safety components of products (e.g. AI application in robot-assisted surgery)",
        "AI tools for employment, management of workers and access to self-employment (e.g. CV-sorting software for recruitment)",
        "Certain AI use-cases utilised to give access to essential private and public services (e.g. credit scoring denying citizens opportunity to obtain a loan)",
        "AI systems used for remote biometric identification, emotion recognition and biometric categorisation (e.g AI system to retroactively identify a shoplifter)",
        "AI use-cases in law enforcement that may interfere with peoples fundamental rights (e.g. evaluation of the reliability of evidence)",
        "AI use-cases in migration, asylum and border control management (e.g. automated examination of visa applications)",
        "AI solutions used in the administration of justice and democratic processes (e.g. AI solutions to prepare court rulings)"
    ],
    "General High Risks": [
        "risk to health",
        "risk to safety",
        "risk to fundamental rights",
        "risks associated with a need for transparency around the use of AI, humans are informed when necessary to preserve trust"
    ],
    "Human Rights": [
        "human right to life",
        "human right to freedom from torture (and inhuman or degrading treatment or punishment)",
        "human right to freedom from slavery and forced labour",
        "human right to liberty and security (lawful arrest or detention, informed why arrested in language they understand)",
        "human right to a fair trial (assumed innocent)",
        "human right to respect for private and family life",
        "human right to freedom of thought, conscience and religion",
        "human right to freedom of expression",
        "human right to freedom of assembly and association (protest)",
        "human right to marry",
        "human right to an effective remedy (right to legal remedy by person whose rights have been violated)",
        "human right to freedom of discrimination"
    ],
    "Online Manipulation": [
        # Vulnerabilities - Ontological: Universal human traits making everyone susceptible to influence (cognitive biases, emotional vulnerabilities, habitual behaviors, loss aversion, sunk cost fallacy)",
        "Online Manipulation: Ontological Vulnerabilities - Universal human traits making everyone susceptible to influence (cognitive biases, emotional vulnerabilities, habitual behaviors, loss aversion, sunk cost fallacy)",
        # Vulnerabilities - Contingent Structural: Susceptibilities from social position or systemic disadvantages (demographic targeting, economic hardship, polarization, social isolation, historical trauma, educational disparities)",
        "Online Manipulation: Contingent-Structural Vulnerabilities - Susceptibilities from social position or systemic disadvantages (demographic targeting, economic hardship, polarization, social isolation, historical trauma, educational disparities)",
        # Vulnerabilities - Contingent Individual: Personal traits unique to individuals (behavioral profiling, preference exploitation, life event targeting, psychological inference, personality assessment, addiction tendencies)",
        "Online Manipulation: Contingent-Individual Vulnerabilities - Personal traits unique to individuals (behavioral profiling, preference exploitation, life event targeting, psychological inference, personality assessment, addiction tendencies)",
        # Characteristics - Hidden/Covert Influence: Influence operating outside conscious awareness (unaware influence, no transparency, obscured mechanisms, concealed sources, misrepresented motivations)",
        "Online Manipulation: Hidden/Covert Influence - Influence operating outside conscious awareness (unaware influence, no transparency, obscured mechanisms, concealed sources, misrepresented motivations)",
        # Characteristics - Exploitation of Vulnerabilities: Deliberate targeting of decision-making weaknesses (cognitive biases, emotional states, impulse control, creating wants, addictive behaviors)",
        "Online Manipulation: Exploitation of Vulnerabilities - Deliberate targeting of decision-making weaknesses (cognitive biases, emotional states, impulse control, creating wants, addictive behaviors)",
        # Characteristics - Targeted Delivery: Influence directed at specific individuals (personalized messaging, microtargeting, individual adaptation, psychographic segmentation, real-time personalization)",
        "Online Manipulation: Targeted Delivery - Influence directed at specific individuals (personalized messaging, microtargeting, individual adaptation, psychographic segmentation, real-time personalization)",
        # Context - Commercial/Consumer: Manipulation driving purchasing decisions (emotional targeting, personalized pricing, urgency tactics, insecurity exploitation, predatory advertising, subliminal techniques)",
        "Online Manipulation: Commercial/Consumer Context - Manipulation driving purchasing decisions (emotional targeting, personalized pricing, urgency tactics, insecurity exploitation, predatory advertising, subliminal techniques)",
        # Context - Workplace/Labor: Manipulation of workers through algorithmic management (push notifications, gamification, psychological goal-setting, automatic queuing, misleading metrics, behavioral nudges)",
        "Online Manipulation: Workplace/Labor Context - Manipulation of workers through algorithmic management (push notifications, gamification, psychological goal-setting, automatic queuing, misleading metrics, behavioral nudges)",
        # Context - Political: Manipulation influencing voting, public opinion, or political processes (voter psychographic targeting, emotional political advertising, disinformation, microtargeted messaging, ideological bias exploitation, division amplification)",
        "Online Manipulation: Political Context - Manipulation influencing voting, public opinion, or political processes (voter psychographic targeting, emotional political advertising, disinformation, microtargeted messaging, ideological bias exploitation, division amplification)"
    ]
}

# Flat list for backwards compatibility (format: "Category: description")
EU_AI_RISKS = [
    "Unacceptable: harmful AI-based manipulation and deception",
    "Unacceptable: harmful AI-based exploitation of vulnerabilities",
    "Unacceptable: social scoring",
    "Unacceptable: individual criminal offence risk assessment or prediction",
    "Unacceptable: untargeted scraping of the internet or CCTV material to create or expand facial recognition databases",
    "Unacceptable: emotion recognition in workplaces and education institutions",
    "Unacceptable: biometric categorisation to deduce certain protected characteristics",
    "Unacceptable: real-time remote biometric identification for law enforcement purposes in publicly accessible spaces",
    "High Risk: AI safety components in critical infrastructures (e.g. transport), the failure of which could put the life and health of citizens at risk",
    "High Risk: AI solutions used in education institutions, that may determine the access to education and course of someones professional life (e.g. scoring of exams)",
    "High Risk: AI-based safety components of products (e.g. AI application in robot-assisted surgery)",
    "High Risk: AI tools for employment, management of workers and access to self-employment (e.g. CV-sorting software for recruitment)",
    "High Risk: Certain AI use-cases utilised to give access to essential private and public services (e.g. credit scoring denying citizens opportunity to obtain a loan)",
    "High Risk: AI systems used for remote biometric identification, emotion recognition and biometric categorisation (e.g AI system to retroactively identify a shoplifter)",
    "High Risk: AI use-cases in law enforcement that may interfere with peoples fundamental rights (e.g. evaluation of the reliability of evidence)",
    "High Risk: AI use-cases in migration, asylum and border control management (e.g. automated examination of visa applications)",
    "High Risk: AI solutions used in the administration of justice and democratic processes (e.g. AI solutions to prepare court rulings)",
    "General High Risks: risk to health",
    "General High Risks: risk to safety",
    "General High Risks: risk to fundamental rights",
    "General High Risks: risks associated with a need for transparency around the use of AI, humans are informed when necessary to preserve trust",
    "Human Rights: human right to life",
    "Human Rights: human right to freedom from torture (and inhuman or degrading treatment or punishment)",
    "Human Rights: human right to freedom from slavery and forced labour",
    "Human Rights: human right to liberty and security (lawful arrest or detention, informed why arrested in language they understand)",
    "Human Rights: human right to a fair trial (assumed innocent)",
    "Human Rights: human right to respect for private and family life",
    "Human Rights: human right to freedom of thought, conscience and religion",
    "Human Rights: human right to freedom of expression",
    "Human Rights: human right to freedom of assembly and association (protest)",
    "Human Rights: human right to marry",
    "Human Rights: human right to an effective remedy (right to legal remedy by person whose rights have been violated)",
    "Human Rights: human right to freedom of discrimination",
    "Online Manipulation: Ontological Vulnerabilities - Universal human traits making everyone susceptible to influence (cognitive biases, emotional vulnerabilities, habitual behaviors, loss aversion, sunk cost fallacy)",
    "Online Manipulation: Contingent-Structural Vulnerabilities - Susceptibilities from social position or systemic disadvantages (demographic targeting, economic hardship, polarization, social isolation, historical trauma, educational disparities)",
    "Online Manipulation: Contingent-Individual Vulnerabilities - Personal traits unique to individuals (behavioral profiling, preference exploitation, life event targeting, psychological inference, personality assessment, addiction tendencies)",
    "Online Manipulation: Hidden/Covert Influence - Influence operating outside conscious awareness (unaware influence, no transparency, obscured mechanisms, concealed sources, misrepresented motivations)",
    "Online Manipulation: Exploitation of Vulnerabilities - Deliberate targeting of decision-making weaknesses (cognitive biases, emotional states, impulse control, creating wants, addictive behaviors)",
    "Online Manipulation: Targeted Delivery - Influence directed at specific individuals (personalized messaging, microtargeting, individual adaptation, psychographic segmentation, real-time personalization)",
    "Online Manipulation: Commercial/Consumer Context - Manipulation driving purchasing decisions (emotional targeting, personalized pricing, urgency tactics, insecurity exploitation, predatory advertising, subliminal techniques)",
    "Online Manipulation: Workplace/Labor Context - Manipulation of workers through algorithmic management (push notifications, gamification, psychological goal-setting, automatic queuing, misleading metrics, behavioral nudges)",
    "Online Manipulation: Political Context - Manipulation influencing voting, public opinion, or political processes (voter psychographic targeting, emotional political advertising, disinformation, microtargeted messaging, ideological bias exploitation, division amplification)",
]
