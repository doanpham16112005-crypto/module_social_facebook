# -*- coding: utf-8 -*-

import json
import logging
import requests
import re
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
        """
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')
        
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
        """
        try:
            body = request.httprequest.get_data(as_text=True)
            data = json.loads(body)
            
            _logger.info(f'🔔 WEBHOOK RECEIVED: {json.dumps(data, indent=2)}')
            
            if data.get('object') != 'page':
                _logger.warning(f'⚠️ Unknown object type: {data.get("object")}')
                return 'OK'
            
            for entry in data.get('entry', []):
                self._process_entry(entry)
            
            return 'OK'
            
        except Exception as e:
            _logger.error(f'❌ Error processing webhook: {e}', exc_info=True)
            return 'OK'
    
    def _process_entry(self, entry):
        """Xử lý một entry từ webhook"""
        if 'messaging' in entry:
            for event in entry['messaging']:
                self._process_messaging_event(event)
        
        if 'changes' in entry:
            for change in entry['changes']:
                self._process_change_event(change)
    
    def _process_messaging_event(self, event):
        """Xử lý messaging events"""
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        if not sender_id or not recipient_id:
            _logger.warning('⚠️ Missing sender_id or recipient_id')
            return
        
        _logger.info(f'📨 Processing event from {sender_id} to {recipient_id}')
        
        conversation = self._find_or_create_conversation(sender_id, recipient_id)
        
        if not conversation:
            _logger.error(f'❌ Failed to find/create conversation')
            return
        
        if 'message' in event:
            message_data = event['message']
            
            if message_data.get('is_echo'):
                _logger.debug('⏭️ Skipping echo message')
                return
            
            if 'quick_reply' in message_data:
                payload = message_data['quick_reply'].get('payload', '')
                self._handle_quick_reply(conversation, payload, message_data.get('text', ''))
            else:
                self._handle_message(conversation, message_data, sender_id)
        
        elif 'postback' in event:
            self._handle_postback(conversation, event['postback'], sender_id)
        
        elif 'read' in event:
            self._handle_read(conversation, event['read'])
    
    def _process_change_event(self, change):
        """Xử lý change events"""
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
        """Xử lý tin nhắn mới"""
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
        
        # ✅ XỬ LÝ CHATBOT FLOW (CÓ STATE MACHINE)
        self._process_chatbot_flow(conversation, text)
    
    def _handle_quick_reply(self, conversation, payload, text):
        """Xử lý quick reply"""
        _logger.info(f'🔘 Quick Reply received - payload: {payload}, text: {text}')
        self._process_chatbot_flow(conversation, payload)
    
    def _handle_postback(self, conversation, postback_data, sender_id):
        """Xử lý postback"""
        payload = postback_data.get('payload', '')
        title = postback_data.get('title', '')
        _logger.info(f'🔘 Postback received - payload: {payload}, title: {title}')
        self._process_chatbot_flow(conversation, payload)
    
    def _handle_read(self, conversation, read_data):
        """Handle read receipts"""
        watermark = read_data.get('watermark')
        _logger.debug(f'👁️ Message read - watermark: {watermark}')
    
    # -------------------------------------------------------------------------
    # ✅ CHATBOT FLOW (STATE MACHINE ĐẦY ĐỦ)
    # -------------------------------------------------------------------------
    
    def _process_chatbot_flow(self, conversation, user_message):
        """
        Xử lý chatbot flow với state machine.
        """
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            _logger.info('⚠️ Chatbot disabled')
            return
        
        # ✅ KIỂM TRA FIELD TỒN TẠI
        if 'chatbot_state' not in conversation._fields:
            _logger.error('❌ CRITICAL: chatbot_state field does not exist in social.message!')
            _logger.error('   Solution 1: Add chatbot_state field to models/social_message.py')
            _logger.error('   Solution 2: Use social.conversation model instead')
            # GỬI TIN NHẮN LỖI CHO USER
            self._send_message(conversation, 
                'Xin lỗi, hệ thống chatbot đang gặp sự cố. Vui lòng liên hệ trực tiếp với chúng tôi. 🙏')
            return
        
        # Lấy state hiện tại
        current_state = conversation.chatbot_state or 'idle'
        _logger.info(f'🤖 Current state: {current_state}, Message: "{user_message[:50]}..."')
    
    # ... (phần còn lại giữ nguyên)
        
        # ✅ STATE: IDLE - Chờ lệnh bắt đầu
        if current_state == 'idle':
            self._chatbot_start_flow(conversation, user_message)
        
        # ✅ STATE: ASK_NAME - Đang hỏi tên
        elif current_state == 'ask_name':
            self._chatbot_save_name_ask_phone(conversation, user_message)
        
        # ✅ STATE: ASK_PHONE - Đang hỏi SĐT
        elif current_state == 'ask_phone':
            self._chatbot_save_phone_show_products(conversation, user_message)
        
        # ✅ STATE: SHOW_PRODUCTS - Đã hiển thị sản phẩm, chờ chọn
        elif current_state == 'show_products':
            self._chatbot_handle_product_selection(conversation, user_message)
        
        # ✅ STATE: CONFIRM_ORDER - Chờ xác nhận đặt hàng
        elif current_state == 'confirm_order':
            self._chatbot_confirm_order(conversation, user_message)
        
        # ✅ STATE: COMPLETED - Đã hoàn tất
        elif current_state == 'completed':
            # Reset về idle hoặc xử lý lệnh mới
            conversation.sudo().write({'chatbot_state': 'idle'})
            self._chatbot_start_flow(conversation, user_message)
    
    # -------------------------------------------------------------------------
    # ✅ CHATBOT STATE HANDLERS
    # -------------------------------------------------------------------------
    
    def _chatbot_start_flow(self, conversation, user_message):
        """
        STATE: idle → ask_name
        
        Triggers: mua, sản phẩm, giá, order, buy
        """
        trigger_keywords = ['mua', 'sản phẩm', 'giá', 'order', 'buy', 'xem hàng', 'menu']
        
        if any(kw in user_message.lower() for kw in trigger_keywords):
            _logger.info('🚀 Starting chatbot flow')
            
            # ✅ KIỂM TRA FIELD TỒN TẠI TRƯỚC KHI GHI
            try:
                if 'chatbot_state' in conversation._fields:
                    conversation.sudo().write({'chatbot_state': 'ask_name'})
                    _logger.info('✅ State updated to ask_name')
                else:
                    _logger.error('❌ Field chatbot_state does not exist in social.message!')
                    _logger.error('   Please add the field or use social.conversation model')
                    # ✅ DỪNG NGAY ĐỂ TRÁNH LẶP VÔ HẠN
                    return
            except Exception as e:
                _logger.error(f'❌ Failed to update state: {e}')
                return
            
            # Gửi tin nhắn hỏi tên
            welcome_msg = """Xin chào! Cảm ơn bạn đã quan tâm đến sản phẩm của chúng tôi! 😊

    Để phục vụ bạn tốt hơn, bạn vui lòng cho tôi biết **tên** của bạn?"""
            
            self._send_message(conversation, welcome_msg)
        
        else:
            # Không match → Gửi hướng dẫn
            self._send_message(conversation, 
                'Xin chào! Gửi "mua" hoặc "xem sản phẩm" để bắt đầu mua hàng nhé! 😊')
    
    def _chatbot_save_name_ask_phone(self, conversation, user_message):
        """
        STATE: ask_name → ask_phone
        
        Lưu tên, hỏi SĐT
        """
        name = user_message.strip()
        
        if len(name) < 2:
            self._send_message(conversation, 
                'Tên bạn có vẻ hơi ngắn. Bạn vui lòng nhập lại tên đầy đủ nhé! 😊')
            return
        
        _logger.info(f'💾 Saving customer name: {name}')
        
        # Lưu tên
        conversation.sudo().write({
            'customer_name': name,
            'chatbot_state': 'ask_phone'
        })
        
        # Hỏi SĐT
        self._send_message(conversation, 
            f'Rất vui được làm quen với {name}! 👋\n\n'
            'Để chúng tôi có thể liên hệ xác nhận đơn hàng, bạn vui lòng cung cấp **số điện thoại**?')
    
    def _chatbot_save_phone_show_products(self, conversation, user_message):
        """
        STATE: ask_phone → show_products
        
        Lưu SĐT, hiển thị sản phẩm
        """
        phone = user_message.strip()
        
        # Validate phone (10-11 số)
        phone_pattern = r'^[0-9\s\+\-\(\)]{9,15}$'
        
        if not re.match(phone_pattern, phone):
            self._send_message(conversation, 
                'Số điện thoại có vẻ không hợp lệ. Vui lòng nhập lại số điện thoại của bạn (10-11 số).')
            return
        
        _logger.info(f'💾 Saving customer phone: {phone}')
        
        # Lưu SĐT
        conversation.sudo().write({
            'customer_phone': phone,
            'chatbot_state': 'show_products'
        })
        
        # Hiển thị danh sách sản phẩm
        self._send_product_list(conversation)
    
    def _chatbot_handle_product_selection(self, conversation, user_message):
        """
        STATE: show_products → confirm_order
        
        Lưu sản phẩm đã chọn, hỏi xác nhận
        """
        # Check nếu user chọn sản phẩm (payload PRODUCT_XXX)
        if user_message.startswith('PRODUCT_'):
            try:
                product_id = int(user_message.replace('PRODUCT_', ''))
                product = request.env['social.messenger.product'].sudo().browse(product_id)
                
                if not product.exists() or not product.active:
                    self._send_message(conversation, 
                        'Xin lỗi, sản phẩm này hiện không còn bán. Vui lòng chọn sản phẩm khác.')
                    self._send_product_list(conversation)
                    return
                
                _logger.info(f'✅ Product selected: {product.product_id.name}')
                
                # Lưu sản phẩm đã chọn
                conversation.sudo().write({
                    'selected_product_ids': [(6, 0, [product.id])],
                    'chatbot_state': 'confirm_order'
                })
                
                # Build confirmation message
                price_text = f"{product.price:,.0f} {product.currency_id.symbol}" if product.price > 0 else "Liên hệ"
                
                confirm_msg = f"""✅ Bạn đã chọn:

📦 **{product.product_id.name}**
💰 Giá: {price_text}

"""
                
                if product.description:
                    confirm_msg += f"📝 {product.description}\n\n"
                
                confirm_msg += f"""📋 Thông tin đặt hàng:
👤 Tên: {conversation.customer_name}
📞 SĐT: {conversation.customer_phone}

Bạn có muốn **xác nhận đặt hàng** không?

👉 Trả lời **"Có"** để xác nhận
👉 Trả lời **"Không"** để chọn lại"""
                
                self._send_message(conversation, confirm_msg)
                
            except Exception as e:
                _logger.error(f'❌ Error handling product selection: {e}')
                self._send_message(conversation, 'Đã có lỗi xảy ra. Vui lòng thử lại.')
        
        else:
            # User gửi text thường → Nhắc chọn sản phẩm
            self._send_message(conversation, 
                'Vui lòng chọn một sản phẩm từ danh sách bên trên.')
    
    def _chatbot_confirm_order(self, conversation, user_message):
        """
        STATE: confirm_order → completed
        
        Tạo order + CRM lead khi user xác nhận "Có"
        """
        message_lower = user_message.lower().strip()
        
        # Check xác nhận
        confirm_keywords = ['có', 'yes', 'ok', 'đồng ý', 'đặt hàng', 'chốt đơn']
        cancel_keywords = ['không', 'no', 'cancel', 'hủy', 'chọn lại']
        
        if any(kw in message_lower for kw in confirm_keywords):
            _logger.info('🛒 User confirmed order')
            
            # ✅ TẠO ORDER VÀ CRM LEAD
            try:
                # 1. Tạo Messenger Order
                order = self._create_messenger_order(conversation)
                
                if order:
                    # 2. Tạo Sale Order
                    sale_order = order.create_sale_order()
                    
                    # 3. Tạo CRM Lead
                    lead = self._create_crm_lead(conversation, order, sale_order)
                    
                    # 4. Chuyển state → completed
                    conversation.sudo().write({
                        'chatbot_state': 'completed',
                        'messenger_order_id': order.id,
                        'lead_id': lead.id if lead else False
                    })
                    
                    # 5. Gửi thông báo thành công
                    success_msg = f"""🎉 **Đặt hàng thành công!**

📝 Mã đơn hàng: **{order.name}**
📝 Mã đơn bán: **{sale_order.name}**

Chúng tôi sẽ liên hệ với bạn trong thời gian sớm nhất để xác nhận và giao hàng.

Cảm ơn bạn đã tin tưởng! 🙏

---
Gửi "mua" để tiếp tục mua sắm."""
                    
                    self._send_message(conversation, success_msg)
                    
                    _logger.info(f'✅ Order created: {order.name}, Sale Order: {sale_order.name}')
                
                else:
                    raise Exception('Failed to create messenger order')
                    
            except Exception as e:
                _logger.error(f'❌ Error creating order: {e}', exc_info=True)
                
                conversation.sudo().write({'chatbot_state': 'idle'})
                
                self._send_message(conversation, 
                    'Đã có lỗi xảy ra khi tạo đơn hàng. Vui lòng liên hệ với chúng tôi qua hotline. Xin lỗi vì sự bất tiện này! 😔')
        
        elif any(kw in message_lower for kw in cancel_keywords):
            _logger.info('❌ User cancelled order')
            
            # Reset state, xóa sản phẩm đã chọn
            conversation.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)]
            })
            
            self._send_message(conversation, 
                'Đơn hàng đã được hủy. Hãy chọn lại sản phẩm bạn muốn nhé! 😊')
            
            # Re-send product list
            self._send_product_list(conversation)
        
        else:
            # User gửi text khác → Nhắc xác nhận
            self._send_message(conversation, 
                'Vui lòng trả lời **"Có"** để xác nhận hoặc **"Không"** để hủy.')
    
    # -------------------------------------------------------------------------
    # ✅ CREATE ORDER & CRM LEAD
    # -------------------------------------------------------------------------
    
    def _create_messenger_order(self, conversation):
        """
        Tạo social.messenger.order
        
        Returns:
            social.messenger.order record
        """
        try:
            order_vals = {
                'conversation_id': conversation.id,
                'facebook_user_id': conversation.facebook_user_id,
                'customer_name': conversation.customer_name,
                'customer_phone': conversation.customer_phone,
                'product_ids': [(6, 0, conversation.selected_product_ids.ids)],
                'company_id': conversation.company_id.id,
                'state': 'confirmed',
            }
            
            order = request.env['social.messenger.order'].sudo().create(order_vals)
            
            _logger.info(f'✅ Created messenger order: {order.name}')
            
            return order
            
        except Exception as e:
            _logger.error(f'❌ Failed to create messenger order: {e}')
            raise
    
    def _create_crm_lead(self, conversation, messenger_order, sale_order):
        """
        Tạo crm.lead từ order
        
        Returns:
            crm.lead record
        """
        try:
            Lead = request.env['crm.lead'].sudo()
            
            # Check nếu đã có lead
            if conversation.lead_id:
                lead = conversation.lead_id
                
                lead.message_post(
                    body=f"""<strong>🛒 Order created from Facebook Messenger</strong><br/>
                    Order: {messenger_order.name}<br/>
                    Sale Order: {sale_order.name}<br/>
                    Total: {messenger_order.total_amount:,.0f} {messenger_order.currency_id.symbol}
                    """,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment'
                )
                
                _logger.info(f'✅ Updated existing lead: {lead.id}')
                return lead
            
            # Tạo lead mới
            lead_vals = {
                'name': f'Facebook Order - {conversation.customer_name}',
                'type': 'opportunity',
                'contact_name': conversation.customer_name,
                'phone': conversation.customer_phone,
                'expected_revenue': messenger_order.total_amount,
                'description': f"""
Lead from Facebook Messenger Order

Order: {messenger_order.name}
Sale Order: {sale_order.name}
Total: {messenger_order.total_amount:,.0f} {messenger_order.currency_id.symbol}

Products:
{chr(10).join([f"- {p.product_id.name}: {p.price:,.0f} {p.currency_id.symbol}" for p in messenger_order.product_ids])}

Customer Info:
- Name: {conversation.customer_name}
- Phone: {conversation.customer_phone}
- Facebook PSID: {conversation.facebook_user_id}
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
            
            _logger.info(f'✅ Created CRM lead: {lead.id}')
            
            return lead
            
        except Exception as e:
            _logger.error(f'❌ Failed to create CRM lead: {e}')
            return None
    
    # -------------------------------------------------------------------------
    # ✅ SEND MESSAGE HELPERS
    # -------------------------------------------------------------------------
    
    def _send_message(self, conversation, text):
        """
        Gửi tin nhắn text đơn giản
        """
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': conversation.facebook_user_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': conversation.account_id.access_token}
        
        _logger.info(f'📤 Sending message to {conversation.facebook_user_id}: "{text[:50]}..."')
        
        try:
            response = requests.post(url, json=payload, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            _logger.info(f'✅ Message sent: {result}')
            
            return True
            
        except Exception as e:
            _logger.error(f'❌ Failed to send message: {e}')
            return False
    
    def _send_product_list(self, conversation):
        """
        Gửi danh sách sản phẩm với Quick Replies
        """
        # Lấy sản phẩm active
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', conversation.company_id.id)
        ], order='sequence, id')
        
        if not products:
            self._send_message(conversation, 
                'Xin lỗi, hiện tại chúng tôi chưa có sản phẩm nào. Vui lòng quay lại sau!')
            return False
        
        # Build product list text
        product_list = "📦 **Danh sách sản phẩm của chúng tôi:**\n\n"
        
        for idx, product in enumerate(products, 1):
            price_text = f"{product.price:,.0f} {product.currency_id.symbol}" if product.price > 0 else "Liên hệ"
            product_list += f"{idx}. {product.product_id.name}\n"
            product_list += f"   💰 Giá: {price_text}\n"
            if product.description:
                desc = product.description[:60] + '...' if len(product.description) > 60 else product.description
                product_list += f"   📝 {desc}\n"
            product_list += "\n"
        
        product_list += "👇 Vui lòng chọn sản phẩm bạn muốn mua:"
        
        # Build Quick Replies
        quick_replies = []
        for product in products[:11]:
            title = product.quick_reply_title or product.product_id.name[:20]
            quick_replies.append({
                'content_type': 'text',
                'title': title,
                'payload': f'PRODUCT_{product.id}'
            })
        
        # Send with Quick Replies
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': conversation.facebook_user_id},
            'message': {
                'text': product_list,
                'quick_replies': quick_replies
            },
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': conversation.account_id.access_token}
        
        try:
            response = requests.post(url, json=payload, params=params, timeout=10)
            response.raise_for_status()
            
            _logger.info(f'✅ Product list sent with {len(quick_replies)} quick replies')
            return True
            
        except Exception as e:
            _logger.error(f'❌ Failed to send product list: {e}')
            return False
    
    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    
    def _handle_leadgen_event(self, leadgen_data):
        """Xử lý lead form submissions"""
        pass
    
    def _handle_feed_event(self, feed_data):
        """Handle post events"""
        pass
    
    def _handle_comment_event(self, comment_data):
        """Handle comment events"""
        pass
    
    def _find_or_create_conversation(self, sender_id, recipient_id):
        """Tìm hoặc tạo conversation"""
        _logger.info(f'🔍 Finding conversation for user {sender_id}, page {recipient_id}')
        
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)
        ], limit=1)
        
        if not account:
            _logger.error(f'❌ No account found for page {recipient_id}')
            return None
        
        _logger.info(f'✅ Found account: {account.name} (ID: {account.id})')
        
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
            'chatbot_state': 'idle',
        }
        
        try:
            conversation = request.env['social.message'].sudo().create(conv_vals)
            _logger.info(f'✅ Created new conversation: {conversation.id}')
            return conversation
        except Exception as e:
            _logger.error(f'❌ Failed to create conversation: {e}')
            return None