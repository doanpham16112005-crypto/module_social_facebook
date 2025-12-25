# -*- coding: utf-8 -*-

import json
import logging
import requests
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class FacebookWebhookController(http.Controller):
    """
    Controller xử lý webhook từ Facebook.
    
    Endpoint: /social/facebook/webhook
    Methods:
    - GET: Verify webhook (subscription)
    - POST: Nhận events từ Facebook
    """
    
    @http.route('/social/facebook/webhook', type='http', auth='public', 
                methods=['GET'], csrf=False)
    def webhook_verify(self, **kwargs):
        """
        Verify webhook theo Facebook requirements.
        
        Facebook sẽ gửi GET request với params:
        - hub.mode = 'subscribe'
        - hub.verify_token = token bạn set
        - hub.challenge = random string
        
        Response: echo lại hub.challenge
        """
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')
        
        # Get verify token from settings
        verify_token = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.verify_token', '16112005'
        )
        
        _logger.info(f'🔔 Webhook verify attempt - mode: {mode}, token: {token}')
        
        if mode == 'subscribe' and token == verify_token:
            _logger.info('✅ Webhook verified successfully!')
            return challenge
        else:
            _logger.warning(f'❌ Webhook verify failed - token mismatch')
            return 'Forbidden', 403
    
    @http.route('/social/facebook/webhook', type='http', auth='public', 
                methods=['POST'], csrf=False)
    def webhook_callback(self, **kwargs):
        """
        Nhận và xử lý events từ Facebook.
        
        Events types:
        - messages: Tin nhắn Messenger
        - messaging_postbacks: Postback từ buttons
        - leadgen: Lead form submissions
        - feed: Post updates
        """
        try:
            # Parse JSON body
            body = request.httprequest.get_data(as_text=True)
            data = json.loads(body)
            
            _logger.info(f'🔔 WEBHOOK RECEIVED: {json.dumps(data, indent=2)}')
            
            # Verify object type
            if data.get('object') != 'page':
                _logger.warning(f'⚠️ Unknown object type: {data.get("object")}')
                return 'OK'
            
            # Process each entry
            for entry in data.get('entry', []):
                self._process_entry(entry)
            
            return 'OK'
            
        except Exception as e:
            _logger.error(f'❌ Error processing webhook: {e}', exc_info=True)
            return 'OK'  # Always return 200 to Facebook
    
    def _process_entry(self, entry):
        """
        Xử lý một entry từ webhook.
        
        Entry có thể chứa:
        - messaging: Messenger events
        - changes: Page changes (posts, comments)
        - leadgen: Lead ads submissions
        """
        # Process messaging events
        if 'messaging' in entry:
            for event in entry['messaging']:
                self._process_messaging_event(event)
        
        # Process changes (posts, comments, etc.)
        if 'changes' in entry:
            for change in entry['changes']:
                self._process_change_event(change)
    
    def _process_messaging_event(self, event):
        """
        Xử lý messaging events.
        
        Event types:
        - message: Tin nhắn mới
        - postback: User click button
        - read: User đã đọc
        - delivery: Tin đã gửi
        """
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        if not sender_id or not recipient_id:
            _logger.warning('⚠️ Missing sender_id or recipient_id')
            return
        
        _logger.info(f'📨 Processing event from {sender_id} to {recipient_id}')
        
        # Find or create conversation
        conversation = self._find_or_create_conversation(sender_id, recipient_id)
        
        if not conversation:
            _logger.error(f'❌ Failed to find/create conversation')
            return
        
        # Handle message
        if 'message' in event:
            message_data = event['message']
            
            # Skip echo messages
            if message_data.get('is_echo'):
                _logger.debug('⏭️ Skipping echo message')
                return
            
            self._handle_message(conversation, message_data, sender_id)
        
        # Handle postback
        elif 'postback' in event:
            self._handle_postback(conversation, event['postback'], sender_id)
        
        # Handle read
        elif 'read' in event:
            self._handle_read(conversation, event['read'])
    
    def _process_change_event(self, change):
        """
        Xử lý change events (posts, comments, reactions).
        
        Change types:
        - feed: Post created/updated
        - comments: New comment
        - reactions: New reaction
        - leadgen: Lead form submission
        """
        field = change.get('field')
        value = change.get('value')
        
        if field == 'leadgen':
            self._handle_leadgen_event(value)
        
        elif field == 'feed':
            self._handle_feed_event(value)
        
        elif field == 'comments':
            self._handle_comment_event(value)
    
    # -------------------------------------------------------------------------
    # MESSAGE HANDLERS
    # -------------------------------------------------------------------------
    
    def _handle_message(self, conversation, message_data, sender_id):
        """
        Xử lý tin nhắn mới.
        
        Actions:
        1. Lưu message vào database
        2. Xử lý chatbot (GIỐNG FLASK - ĐƠN GIẢN)
        3. Check purchase intent cho CRM
        """
        mid = message_data.get('mid')
        text = message_data.get('text', '')
        attachments = message_data.get('attachments', [])
        
        _logger.info(f'📨 Processing message: "{text[:100]}..."')
        
        # Check duplicate
        existing = request.env['social.message'].sudo().search([
            ('message_id', '=', mid)
        ], limit=1)
        
        if existing:
            _logger.debug(f'⏭️ Message {mid} already exists')
            return
        
        # Create message record
        message_vals = {
            'message_id': mid,
            'message': text,
            'is_from_customer': True,
            'facebook_user_id': sender_id,
            'account_id': conversation.account_id.id,
            'company_id': conversation.company_id.id,
        }
        
        if attachments:
            message_vals['attachments'] = json.dumps(attachments)
        
        try:
            msg_record = request.env['social.message'].sudo().create(message_vals)
            _logger.info(f'✅ Created message record: {msg_record.id}')
        except Exception as e:
            _logger.error(f'❌ Failed to create message: {e}')
            return
        
        # ✅ XỬ LÝ CHATBOT - ĐƠN GIẢN THEO PHONG CÁCH FLASK
        self._process_chatbot_simple(conversation, text)
        
        # Check purchase intent for CRM lead
        self._check_purchase_intent(conversation, text)
    
    def _handle_postback(self, conversation, postback_data, sender_id):
        """
        Xử lý postback từ button clicks.
        
        Postback payload format: PRODUCT_123, CONFIRM_YES, etc.
        """
        payload = postback_data.get('payload', '')
        title = postback_data.get('title', '')
        
        _logger.info(f'🔘 Postback received - payload: {payload}, title: {title}')
        
        # Process as chatbot message (treat payload as user input)
        self._process_chatbot_simple(conversation, payload)
    
    def _handle_read(self, conversation, read_data):
        """Handle read receipts"""
        watermark = read_data.get('watermark')
        _logger.debug(f'👁️ Message read - watermark: {watermark}')
    
    # -------------------------------------------------------------------------
    # ✅ CHATBOT - ĐƠN GIẢN HÓA THEO PHONG CÁCH FLASK
    # -------------------------------------------------------------------------
    
    def _process_chatbot_simple(self, conversation, user_message):
        """
        Xử lý chatbot THEO PHONG CÁCH FLASK - ĐƠN GIẢN, TRỰC TIẾP
        
        Flow:
        1. Check enabled
        2. Tìm matching rule
        3. Gửi reply TRỰC TIẾP qua Facebook API
        """
        # 1. Check enabled
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            _logger.info('⚠️ Chatbot disabled')
            return
        
        _logger.info(f'🤖 Chatbot enabled, processing message: "{user_message[:50]}..."')
        
        # 2. Tìm matching rule
        try:
            rules = request.env['social.chatbot.automation'].sudo().search([
                ('active', '=', True),
                '|',
                ('account_id', '=', False),
                ('account_id', '=', conversation.account_id.id)
            ], order='priority desc, id')
            
            _logger.info(f'📋 Found {len(rules)} active chatbot rules')
            
            for rule in rules:
                if rule.check_match(user_message):
                    _logger.info(f'✅ Matched rule: {rule.name}')
                    
                    # 3. GỬI REPLY TRỰC TIẾP (GIỐNG FLASK)
                    success = self._send_facebook_message_direct(
                        recipient_id=conversation.facebook_user_id,
                        text=rule.response_text,
                        access_token=conversation.account_id.access_token
                    )
                    
                    if success:
                        # Mark rule as triggered
                        try:
                            rule.sudo().write({
                                'triggered_count': rule.triggered_count + 1,
                                'last_triggered_date': request.env['ir.fields'].datetime.now(),
                            })
                        except:
                            pass
                        
                        _logger.info(f'✅ Chatbot reply sent successfully')
                        return
                    else:
                        _logger.error(f'❌ Failed to send chatbot reply')
            
            _logger.info('⚠️ No matching chatbot rule found')
            
        except Exception as e:
            _logger.error(f'❌ Chatbot processing error: {e}', exc_info=True)
    
    def _send_facebook_message_direct(self, recipient_id, text, access_token):
        """
        Gửi tin nhắn TRỰC TIẾP qua Facebook API - GIỐNG FLASK
        
        Args:
            recipient_id: Facebook PSID
            text: Nội dung tin nhắn
            access_token: Page Access Token
        
        Returns:
            bool: True nếu thành công, False nếu thất bại
        """
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': recipient_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': access_token}
        
        _logger.info(f'📤 Sending message to {recipient_id}: "{text[:50]}..."')
        
        try:
            response = requests.post(url, json=payload, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            _logger.info(f'✅ Facebook API response: {result}')
            
            return True
            
        except requests.exceptions.HTTPError as e:
            try:
                error_data = e.response.json().get('error', {})
                error_msg = error_data.get('message', str(e))
            except:
                error_msg = str(e)
            _logger.error(f'❌ Facebook API HTTP error: {error_msg}')
            return False
            
        except Exception as e:
            _logger.error(f'❌ Facebook API error: {e}', exc_info=True)
            return False
    
    # -------------------------------------------------------------------------
    # PURCHASE INTENT & CRM INTEGRATION
    # -------------------------------------------------------------------------
    
    def _check_purchase_intent(self, conversation, user_message):
        """
        Tự động tạo CRM lead khi phát hiện purchase intent.
        
        Triggers:
        - Keyword: mua, đặt hàng, order, buy, muốn mua, đặt mua
        """
        message_content = (user_message or '').lower().strip()
        
        # Danh sách keyword mua hàng
        purchase_keywords = [
            'mua', 'đặt hàng', 'order', 'buy', 
            'muốn mua', 'đặt mua', 'book', 'booking',
            'đặt', 'mua luôn', 'chốt đơn'
        ]
        
        # Kiểm tra có keyword không
        has_purchase_intent = any(
            keyword in message_content 
            for keyword in purchase_keywords
        )
        
        if not has_purchase_intent:
            return
        
        _logger.info(f"🛒 Purchase intent detected in conversation {conversation.id}")
        
        # Tạo CRM lead
        try:
            self._create_lead_from_conversation(conversation, user_message)
        except Exception as e:
            _logger.error(f'❌ Failed to create lead: {e}', exc_info=True)
    
    def _create_lead_from_conversation(self, conversation, trigger_message):
        """
        Tạo hoặc cập nhật CRM lead từ conversation.
        
        Args:
            conversation: social.message record (đại diện conversation)
            trigger_message: Tin nhắn trigger việc tạo lead
        """
        Lead = request.env['crm.lead'].sudo()
        
        # Check nếu đã có lead
        if hasattr(conversation, 'lead_id') and conversation.lead_id:
            # Update existing lead
            lead = conversation.lead_id
            
            lead.message_post(
                body=f"""
                <strong>🛒 Purchase intent detected in Facebook Messenger</strong><br/>
                <em>"{trigger_message}"</em>
                """,
                message_type='comment',
                subtype_xmlid='mail.mt_comment'
            )
            
            _logger.info(f"✅ Updated existing lead {lead.id}")
            return lead
        
        # Tạo lead mới
        lead_vals = {
            'name': f'Facebook Lead - {conversation.facebook_user_id}',
            'type': 'opportunity',
            'description': f"""
Lead from Facebook Messenger Conversation

PSID: {conversation.facebook_user_id}
Trigger Message: "{trigger_message}"

Customer Info:
- Name: {getattr(conversation, 'customer_name', 'Unknown')}
- Phone: {getattr(conversation, 'customer_phone', 'Unknown')}
            """,
            'company_id': conversation.company_id.id,
        }
        
        # Tìm hoặc tạo Facebook source
        source = request.env['utm.source'].sudo().search([
            ('name', '=', 'Facebook')
        ], limit=1)
        if not source:
            source = request.env['utm.source'].sudo().create({'name': 'Facebook'})
        lead_vals['source_id'] = source.id
        
        # Tạo lead
        lead = Lead.create(lead_vals)
        
        # Link lead với conversation (nếu có field)
        if hasattr(conversation, 'lead_id'):
            try:
                conversation.sudo().write({'lead_id': lead.id})
            except:
                pass
        
        _logger.info(f"✅ Created new lead {lead.id} from conversation {conversation.id}")
        
        return lead
    
    # -------------------------------------------------------------------------
    # LEADGEN HANDLER
    # -------------------------------------------------------------------------
    
    def _handle_leadgen_event(self, leadgen_data):
        """Xử lý lead form submissions từ Facebook Lead Ads"""
        _logger.info(f'📋 Leadgen event received: {leadgen_data}')
        # TODO: Implement leadgen handling
        pass
    
    def _handle_feed_event(self, feed_data):
        """Handle post events"""
        pass
    
    def _handle_comment_event(self, comment_data):
        """Handle comment events"""
        pass
    
    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    
    def _find_or_create_conversation(self, sender_id, recipient_id):
        """
        Tìm hoặc tạo conversation.
        
        Args:
            sender_id: Facebook PSID của user
            recipient_id: Facebook Page ID
        
        Returns:
            social.message record (đại diện conversation) hoặc None
        """
        _logger.info(f'🔍 Finding conversation for user {sender_id}, page {recipient_id}')
        
        # ✅ FIX: Đổi 'facebook_id' → 'facebook_page_id'
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)
        ], limit=1)
        
        if not account:
            _logger.error(f'❌ No account found for page {recipient_id}')
            _logger.error(f'   Please add this Facebook Page in Odoo first!')
            return None
        
        _logger.info(f'✅ Found account: {account.name} (ID: {account.id})')
        
        # Find existing conversation
        conversation = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', sender_id),
            ('account_id', '=', account.id),
        ], limit=1)
        
        if conversation:
            _logger.info(f'✅ Found existing conversation: {conversation.id}')
            return conversation
        
        # Create new conversation
        conv_vals = {
            'facebook_user_id': sender_id,
            'account_id': account.id,
            'company_id': account.company_id.id,
        }
        
        # Add chatbot_state if field exists
        if 'chatbot_state' in request.env['social.message']._fields:
            conv_vals['chatbot_state'] = 'idle'
        
        try:
            conversation = request.env['social.message'].sudo().create(conv_vals)
            _logger.info(f'✅ Created new conversation: {conversation.id} for user {sender_id}')
            return conversation
        except Exception as e:
            _logger.error(f'❌ Failed to create conversation: {e}', exc_info=True)
            return None