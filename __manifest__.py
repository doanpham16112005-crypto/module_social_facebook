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
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'web',
        'crm',
        'sale_management',
        'product',
    ],
    'data': [
        # Security
        'security/social_security.xml',
        'security/ir.model.access.csv',
        
        # Data - CHỈ GIỮ FILE TỒN TẠI
        'data/ir_cron_data.xml',
        
        # Views - CHỈ GIỮ FILE TỒN TẠI
        'views/social_account_views.xml',
        'views/social_post_views.xml',
        'views/social_comment_views.xml',
        'views/social_conversation_views.xml',
        'views/social_message_views.xml',
        'views/social_messenger_product_views.xml',
        'views/social_messenger_order_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}