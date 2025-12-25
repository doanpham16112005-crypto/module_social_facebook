# -*- coding: utf-8 -*-
"""
PATCH FOR: controllers/webhook.py

HƯỚNG DẪN:
1. Mở file controllers/webhook.py
2. Tìm method _handle_message() (khoảng dòng 101-139)
3. SAU dòng tạo msg_record, THÊM 2 dòng xử lý chatbot
4. THÊM 3 method mới vào cuối class FacebookWebhookController

HOẶC sử dụng code đầy đủ bên dưới để thay thế toàn bộ file.
"""

import json
import logging
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
            'social_facebook.webhook_verify_token', '16112005'
        )
        
        _logger.info(f'Webhook verify attempt - mode: {mode}, token: {token}')
        
        if mode == 'subscribe' and token == verify_token:
            _logger.info('Webhook verified successfully!')
            return challenge
        else:
            _logger.warning(f'Webhook verify failed - token mismatch')
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
            
            _logger.info(f'Received webhook data: {json.dumps(data, indent=2)}')
            
            # Verify object type
            if data.get('object') != 'page':
                _logger.warning(f'Unknown object type: {data.get("object")}')
                return 'OK'
            
            # Process each entry
            for entry in data.get('entry', []):
                self._process_entry(entry)
            
            return 'OK'
            
        except Exception as e:
            _logger.error(f'Error processing webhook: {e}', exc_info=True)
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
            return
        
        # Find or create conversation
        conversation = self._find_or_create_conversation(sender_id, recipient_id)
        
        # Handle message
        if 'message' in event:
            self._handle_message(conversation, event['message'], sender_id)
        
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
        2. Check chatbot flow
        3. Auto-reply nếu cần
        4. Check purchase intent cho CRM
        """
        mid = message_data.get('mid')
        text = message_data.get('text', '')
        attachments = message_data.get('attachments', [])
        
        # Check duplicate
        existing = request.env['social.message'].sudo().search([
            ('message_id', '=', mid)
        ], limit=1)
        
        if existing:
            _logger.debug(f'Message {mid} already exists')
            return
        
        # Create message record
        message_vals = {
            'conversation_id': conversation.id if hasattr(conversation, 'conversation_id') else False,
            'message_id': mid,
            'message': text,
            'is_from_customer': True,
            'facebook_user_id': sender_id,
            'account_id': conversation.account_id.id,
            'company_id': conversation.company_id.id,
        }
        
        if attachments:
            message_vals['attachments'] = json.dumps(attachments)
        
        msg_record = request.env['social.message'].sudo().create(message_vals)
        
        _logger.info(f'Created message {msg_record.id} for conversation {conversation.id}')
        
        # ✅ THÊM MỚI: Process chatbot flow
        self._process_chatbot(conversation, text)
        
        # ✅ THÊM MỚI: Check purchase intent for CRM lead
        self._check_purchase_intent(conversation, text)
        
        # Auto-create lead if enabled (legacy support)
        self._auto_create_lead(conversation)
    
    def _handle_postback(self, conversation, postback_data, sender_id):
        """
        Xử lý postback từ button clicks.
        
        Postback payload format: PRODUCT_123, CONFIRM_YES, etc.
        """
        payload = postback_data.get('payload', '')
        title = postback_data.get('title', '')
        
        _logger.info(f'Postback received - payload: {payload}, title: {title}')
        
        # Process as chatbot message (treat payload as user input)
        self._process_chatbot(conversation, payload)
    
    def _handle_read(self, conversation, read_data):
        """Handle read receipts"""
        watermark = read_data.get('watermark')
        _logger.debug(f'Message read - watermark: {watermark}')
        # Optional: Update message read status
    
    # -------------------------------------------------------------------------
    # ✅ THÊM MỚI: CHATBOT FLOW PROCESSING
    # -------------------------------------------------------------------------
    
    def _process_chatbot(self, conversation, user_message):
        """
        Xử lý chatbot flow.
        
        Gọi conversation.process_chatbot_flow() và gửi reply.
        """
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            return
        
        try:
            # Process chatbot logic
            response = conversation.process_chatbot_flow(user_message)
            
            if response:
                # Send message
                conversation.send_chatbot_message(response)
                _logger.info(f'✅ Chatbot response sent for conversation {conversation.id}')
                
        except Exception as e:
            _logger.error(f'❌ Chatbot error: {e}', exc_info=True)
    
    # -------------------------------------------------------------------------
    # ✅ THÊM MỚI: PURCHASE INTENT & CRM INTEGRATION
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
        if conversation.lead_id:
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
            
            # Update stage nếu chưa won/lost
            if lead.probability < 100 and lead.probability != 0:
                qualified_stage = request.env['crm.stage'].sudo().search([
                    '|',
                    ('name', 'ilike', 'qualified'),
                    ('name', 'ilike', 'qualification')
                ], limit=1)
                
                if qualified_stage:
                    lead.write({
                        'stage_id': qualified_stage.id,
                        'probability': 60,
                    })
            
            _logger.info(f"✅ Updated existing lead {lead.id}")
            return lead
        
        # Tạo lead mới
        lead_vals = {
            'name': f'Facebook Lead - {conversation.customer_name or conversation.facebook_user_id}',
            'type': 'opportunity',
            'contact_name': conversation.customer_name,
            'phone': conversation.customer_phone,
            'description': f"""
Lead from Facebook Messenger Conversation

PSID: {conversation.facebook_user_id}
Trigger Message: "{trigger_message}"
Created at: {request.env.cr.now()}

Customer Info:
- Name: {conversation.customer_name or 'Unknown'}
- Phone: {conversation.customer_phone or 'Unknown'}
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
        
        # Tìm stage "Qualified"
        qualified_stage = request.env['crm.stage'].sudo().search([
            '|',
            ('name', 'ilike', 'qualified'),
            ('name', 'ilike', 'new')
        ], limit=1)
        
        if qualified_stage:
            lead_vals['stage_id'] = qualified_stage.id
            lead_vals['probability'] = 60 if 'qualified' in qualified_stage.name.lower() else 20
        
        # Tạo lead
        lead = Lead.create(lead_vals)
        
        # Link lead với conversation
        conversation.sudo().write({'lead_id': lead.id})
        
        _logger.info(f"✅ Created new lead {lead.id} from conversation {conversation.id}")
        
        return lead
    
    # -------------------------------------------------------------------------
    # LEADGEN HANDLER
    # -------------------------------------------------------------------------
    
    def _handle_leadgen_event(self, leadgen_data):
        """
        Xử lý lead form submissions từ Facebook Lead Ads.
        """
        leadgen_id = leadgen_data.get('leadgen_id')
        page_id = leadgen_data.get('page_id')
        
        if not leadgen_id or not page_id:
            _logger.warning('Missing leadgen_id or page_id')
            return
        
        # Find Facebook account
        account = request.env['social.account'].sudo().search([
            ('facebook_id', '=', page_id)
        ], limit=1)
        
        if not account or not account.access_token:
            _logger.error(f'No account found for page {page_id}')
            return
        
        # Fetch lead data from Graph API
        try:
            from odoo.addons.module_social_facebook.lib import facebook_api
            api = facebook_api.FacebookAPI(account.access_token)
            
            lead_data = api.get_leadgen_data(leadgen_id)
            
            # Parse field data
            field_data = {}
            for field in lead_data.get('field_data', []):
                field_name = field.get('name')
                field_value = field.get('values', [None])[0]
                field_data[field_name] = field_value
            
            # Extract common fields
            name = field_data.get('full_name') or field_data.get('first_name', 'Unknown')
            phone = field_data.get('phone_number') or field_data.get('phone')
            email = field_data.get('email')
            
            # Check duplicate
            existing_lead = request.env['crm.lead'].sudo().search([
                ('phone', '=', phone),
                ('type', '=', 'lead'),
            ], limit=1)
            
            if existing_lead:
                _logger.info(f'Lead already exists for phone {phone}')
                existing_lead.message_post(
                    body=f'Duplicate lead form submission from Facebook: {leadgen_id}'
                )
                return
            
            # Create crm.lead
            lead_vals = {
                'name': f'Facebook Lead: {name}',
                'contact_name': name,
                'phone': phone,
                'email_from': email,
                'type': 'lead',
                'source_id': self._get_facebook_source(),
                'description': f'Lead from Facebook Lead Ads\nForm ID: {leadgen_data.get("form_id")}\nLead ID: {leadgen_id}\n\nFields:\n{json.dumps(field_data, indent=2)}',
                'company_id': account.company_id.id,
            }
            
            lead = request.env['crm.lead'].sudo().create(lead_vals)
            
            _logger.info(f'Created lead {lead.id} from Facebook leadgen {leadgen_id}')
            
        except Exception as e:
            _logger.error(f'Failed to process leadgen {leadgen_id}: {e}', exc_info=True)
    
    def _get_facebook_source(self):
        """Get or create Facebook source"""
        Source = request.env['utm.source'].sudo()
        source = Source.search([('name', '=', 'Facebook')], limit=1)
        if not source:
            source = Source.create({'name': 'Facebook'})
        return source.id
    
    # -------------------------------------------------------------------------
    # AUTO LEAD CREATION (LEGACY)
    # -------------------------------------------------------------------------
    
    def _auto_create_lead(self, conversation):
        """
        Tự động tạo lead từ conversation nếu enabled.
        
        Conditions:
        - auto_create_lead = True
        - Conversation chưa có lead_id
        - Có đủ thông tin (name, phone)
        """
        auto_create = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.auto_create_lead', 'False'
        )
        
        if auto_create != 'True':
            return
        
        if conversation.lead_id:
            return  # Already has lead
        
        if not conversation.customer_name or not conversation.customer_phone:
            return  # Not enough info
        
        try:
            lead = conversation.create_lead_from_conversation()
            if lead:
                _logger.info(f'Auto-created lead {lead.id} from conversation {conversation.id}')
        except Exception as e:
            _logger.error(f'Failed to auto-create lead: {e}')
    
    # -------------------------------------------------------------------------
    # FEED/COMMENT HANDLERS
    # -------------------------------------------------------------------------
    
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
        """
        # ✅ SỬA: Đổi 'facebook_id' → 'facebook_page_id'
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)  # ← DÒNG NÀY
        ], limit=1)
        
        if not account:
            _logger.error(f'No account found for page {recipient_id}')
            return None
        
        # Find existing conversation
        conversation = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', sender_id),
            ('account_id', '=', account.id),
        ], limit=1)
        
        if conversation:
            return conversation
        
        # Create new conversation
        conv_vals = {
            'facebook_user_id': sender_id,
            'account_id': account.id,
            'company_id': account.company_id.id,
            'chatbot_state': 'idle',
        }
        
        conversation = request.env['social.message'].sudo().create(conv_vals)
        
        _logger.info(f'Created new conversation {conversation.id} for user {sender_id}')
        
        return conversation