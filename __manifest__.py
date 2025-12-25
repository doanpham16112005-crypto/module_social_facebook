# -*- coding: utf-8 -*-
{
    'name': 'Social Media - Facebook Enhanced',
    'version': '19.0.2.0.0',
    'category': 'Marketing/Social Marketing',
    'summary': 'Facebook Integration with CRM, Messenger Sales & Content Calendar',
    'description': """
Facebook Integration - Enterprise Edition
==========================================

Core Features:
--------------
* Facebook Pages Management
* Posts Publishing & Scheduling
* Comments & Reactions Tracking
* Messenger Conversations
* Analytics & Insights
* Webhook Integration

NEW Features (v2.0):
-------------------
* ✨ CRM Lead Auto-creation from Messenger & Lead Ads
* ✨ Messenger Sales Bot with Order Creation
* ✨ Content Calendar View
* ✨ Ngrok Integration for Local Development
* ✨ Webhook Configuration UI
* ✨ Messenger Product Catalog
* ✨ Sale Order Integration

Technical Requirements:
-----------------------
* Odoo 19.0+
* Python 3.10+
* Facebook Graph API v18.0+
* Ngrok (optional, for localhost webhooks)
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'web',
        'crm',              # NEW - CRM integration
        'sale_management',  # NEW - Sales integration
        'product',          # NEW - Product catalog
    ],
    'data': [
    # Security
        'security/social_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/user_groups_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        'data/facebook_post_template_data.xml',
        'data/chatbot_data.xml',  # ← ĐẢM BẢO DÒNG NÀY CÓ Ở CUỐI PHẦN DATA
        
        # Views
        'views/menu_views.xml',
        'views/dashboard_views.xml',
        'views/social_account_views.xml',
        'views/social_post_views.xml',
        'views/social_post_calendar_views.xml',
        'views/social_post_template_views.xml',
        'views/social_comment_views.xml',
        'views/social_analytics_views.xml',
        'views/social_conversation_views.xml',
        'views/social_message_views.xml',
        'views/social_messenger_product_views.xml',
        'views/social_messenger_order_views.xml',
        
        # Wizards
        'wizard/wizard_views.xml',
    ],  
    'assets': {
        'web.assets_backend': [
            'module_social_facebook/static/src/css/social_facebook.css',
            'module_social_facebook/static/src/js/social_dashboard.js',
            'module_social_facebook/static/src/js/social_conversation_list.js',
            'module_social_facebook/static/src/js/ngrok_controller.js',  # NEW
        ],
        'web.assets_qweb': [
            'module_social_facebook/static/src/xml/social_conversation_templates.xml',
        ],
    },
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}