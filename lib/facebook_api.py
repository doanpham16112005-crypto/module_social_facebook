# -*- coding: utf-8 -*-

import requests
import logging

_logger = logging.getLogger(__name__)


class FacebookAPI:
    """
    Wrapper for Facebook Graph API.
    Version: v18.0
    """
    
    API_VERSION = 'v18.0'
    BASE_URL = f'https://graph.facebook.com/{API_VERSION}'
    
    def __init__(self, access_token):
        """
        Initialize API wrapper.
        
        Args:
            access_token (str): Page Access Token
        """
        self.access_token = access_token
    
    # -------------------------------------------------------------------------
    # PAGE METHODS
    # -------------------------------------------------------------------------
    
    def get_page_info(self, page_id):
        """Get page information"""
        url = f"{self.BASE_URL}/{page_id}"
        params = {
            'access_token': self.access_token,
            'fields': 'id,name,category,picture,fan_count,link'
        }
        response = requests.get(url, params=params)
        return response.json()
    
    def publish_post(self, page_id, message, **kwargs):
        """Publish a post to page"""
        url = f"{self.BASE_URL}/{page_id}/feed"
        data = {
            'access_token': self.access_token,
            'message': message,
        }
        data.update(kwargs)
        response = requests.post(url, data=data)
        return response.json()
    
    # -------------------------------------------------------------------------
    # ✅ MESSENGER SEND API - FIXED
    # -------------------------------------------------------------------------
    
    def send_message(self, recipient_id, message_text):
        """
        ✅ FIX: Send text message via Messenger Send API.
        
        Args:
            recipient_id (str): PSID of recipient
            message_text (str): Text message to send
        
        Returns:
            dict: API response with message_id
            
        Example:
            >>> api = FacebookAPI('token123')
            >>> api.send_message('user456', 'Hello!')
            {'recipient_id': 'user456', 'message_id': 'mid.xxx'}
        """
        url = f"{self.BASE_URL}/me/messages"
        
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': message_text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': self.access_token}
        
        try:
            response = requests.post(url, json=payload, params=params, timeout=30)
            response.raise_for_status()
            
            # ✅ FIX: Parse JSON an toàn
            try:
                result = response.json()
                
                # ✅ Check result là dict
                if isinstance(result, dict):
                    message_id = result.get('message_id', 'N/A')
                    _logger.info(f"✅ Message sent to {recipient_id}: {message_id}")
                else:
                    # Result là list hoặc kiểu khác
                    _logger.info(f"✅ Message sent to {recipient_id}")
                    result = {'success': True}
                
                return result
                
            except Exception as json_error:
                _logger.warning(f"⚠️ JSON parse warning: {json_error}")
                return {'success': True}
            
        except requests.exceptions.HTTPError as e:
            # ✅ FIX: Handle HTTP errors
            try:
                error_data = e.response.json()
                
                # ✅ Check error_data type
                if isinstance(error_data, dict):
                    error_msg = error_data.get('error', {}).get('message', str(e))
                else:
                    error_msg = str(e)
            except:
                error_msg = str(e)
            
            _logger.error(f"❌ Facebook API Error: {error_msg}")
            raise Exception(f"Facebook API Error: {error_msg}")
            
        except requests.exceptions.RequestException as e:
            _logger.error(f"❌ Request failed: {e}")
            raise Exception(f"Failed to send message: {str(e)}")
    
    # -------------------------------------------------------------------------
    # CONVERSATION METHODS
    # -------------------------------------------------------------------------
    
    def get_conversation_messages(self, conversation_id, limit=25):
        """Get messages from a conversation"""
        url = f"{self.BASE_URL}/{conversation_id}"
        params = {
            'access_token': self.access_token,
            'fields': f'messages.limit({limit}){{id,created_time,from,to,message}}'
        }
        response = requests.get(url, params=params)
        return response.json()
    
    # -------------------------------------------------------------------------
    # LEADGEN API
    # -------------------------------------------------------------------------
    
    def get_leadgen_data(self, leadgen_id):
        """
        Lấy dữ liệu lead form từ Facebook.
        
        Endpoint: /{leadgen_id}
        Fields: field_data (contains name, phone, email, etc.)
        
        Args:
            leadgen_id (str): Lead generation ID from webhook
        
        Returns:
            dict: Lead data
                {
                    'id': '123',
                    'created_time': '2025-01-01T10:00:00+0000',
                    'field_data': [
                        {'name': 'full_name', 'values': ['John Doe']},
                        {'name': 'phone_number', 'values': ['+1234567890']},
                        {'name': 'email', 'values': ['john@example.com']},
                    ]
                }
        """
        url = f"{self.BASE_URL}/{leadgen_id}"
        params = {
            'access_token': self.access_token,
            'fields': 'id,created_time,field_data'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            _logger.info(f'Successfully fetched leadgen data for {leadgen_id}')
            return data
            
        except requests.exceptions.RequestException as e:
            _logger.error(f'Failed to fetch leadgen {leadgen_id}: {e}')
            raise
    
    def get_leadgen_forms(self, page_id):
        """
        Lấy danh sách lead forms của page.
        
        Args:
            page_id (str): Facebook Page ID
        
        Returns:
            list: List of lead forms
        """
        url = f"{self.BASE_URL}/{page_id}/leadgen_forms"
        params = {
            'access_token': self.access_token,
            'fields': 'id,name,status,questions'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return data.get('data', [])
            
        except requests.exceptions.RequestException as e:
            _logger.error(f'Failed to fetch leadgen forms: {e}')
            return []
    
    # -------------------------------------------------------------------------
    # MESSENGER PROFILE API
    # -------------------------------------------------------------------------
    
    def set_get_started_button(self, payload='GET_STARTED'):
        """
        Set Get Started button for Messenger.
        
        Args:
            payload (str): Postback payload when button clicked
        """
        url = f"{self.BASE_URL}/me/messenger_profile"
        data = {
            'access_token': self.access_token,
            'get_started': {'payload': payload}
        }
        response = requests.post(url, json=data)
        return response.json()
    
    def set_greeting_text(self, greeting_text):
        """
        Set greeting text for Messenger.
        
        Args:
            greeting_text (str): Greeting message
        """
        url = f"{self.BASE_URL}/me/messenger_profile"
        data = {
            'access_token': self.access_token,
            'greeting': [
                {
                    'locale': 'default',
                    'text': greeting_text
                }
            ]
        }
        response = requests.post(url, json=data)
        return response.json()