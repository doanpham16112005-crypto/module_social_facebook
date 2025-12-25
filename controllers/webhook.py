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
    
    ✅ CHATBOT FLOW:
    idle → ask_name → ask_phone → show_products → confirm_order → completed
    """
    
    @http.route('/social/facebook/webhook', type='http', auth='public', 
                methods=['GET'], csrf=False)
    def webhook_verify(self, **kwargs):
        """Verify webhook theo Facebook requirements"""
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')
        
        verify_token = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.verify_token', '16112005'
        )
        
        _logger.info(f'🔔 Webhook verify - mode: {mode}, token: {token}')
        
        if mode == 'subscribe' and token == verify_token:
            _logger.info('✅ Webhook verified!')
            return challenge
        else:
            _logger.warning(f'❌ Webhook verify failed')
            return 'Forbidden', 403
    
    @http.route('/social/facebook/webhook', type='http', auth='public', 
                methods=['POST'], csrf=False)
    def webhook_callback(self, **kwargs):
        """Nhận và xử lý events từ Facebook"""
        try:
            body = request.httprequest.get_data(as_text=True)
            data = json.loads(body)
            
            _logger.info(f'🔔 WEBHOOK RECEIVED')
            
            if data.get('object') != 'page':
                return 'OK'
            
            for entry in data.get('entry', []):
                self._process_entry(entry)
            
            return 'OK'
            
        except Exception as e:
            _logger.error(f'❌ Webhook error: {e}', exc_info=True)
            return 'OK'
    
    def _process_entry(self, entry):
        """Xử lý entry"""
        if 'messaging' in entry:
            for event in entry['messaging']:
                self._process_messaging_event(event)
    
    def _process_messaging_event(self, event):
        """Xử lý messaging event"""
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        if not sender_id or not recipient_id:
            return
        
        conversation = self._find_or_create_conversation(sender_id, recipient_id)
        
        if not conversation:
            return
        
        if 'message' in event:
            message_data = event['message']
            
            if message_data.get('is_echo'):
                return
            
            if 'quick_reply' in message_data:
                payload = message_data['quick_reply'].get('payload', '')
                text = message_data.get('text', '')
                _logger.info(f'🔘 Quick Reply: {payload}')
                self._process_chatbot_flow(conversation, payload)
            else:
                text = message_data.get('text', '')
                self._process_chatbot_flow(conversation, text)
    
    # =========================================================================
    # ✅ CHATBOT FLOW - STATE MACHINE
    # =========================================================================
    
    def _process_chatbot_flow(self, conversation, user_message):
        """
        Chatbot flow với state machine
        
        States:
        - idle: Chờ lệnh
        - ask_name: Hỏi tên
        - ask_phone: Hỏi SĐT
        - show_products: Hiển thị sản phẩm
        - confirm_order: Xác nhận
        - completed: Hoàn tất
        """
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            return
        
        current_state = conversation.chatbot_state or 'idle'
        _logger.info(f'🤖 State: {current_state} | Message: "{user_message[:30]}..."')
        
        if current_state == 'idle':
            self._state_idle(conversation, user_message)
        
        elif current_state == 'ask_name':
            self._state_ask_name(conversation, user_message)
        
        elif current_state == 'ask_phone':
            self._state_ask_phone(conversation, user_message)
        
        elif current_state == 'show_products':
            self._state_show_products(conversation, user_message)
        
        elif current_state == 'confirm_order':
            self._state_confirm_order(conversation, user_message)
        
        elif current_state == 'completed':
            conversation.sudo().write({'chatbot_state': 'idle'})
            self._state_idle(conversation, user_message)
    
    # -------------------------------------------------------------------------
    # STATE HANDLERS
    # -------------------------------------------------------------------------
    
    def _state_idle(self, conv, msg):
        """STATE: idle → ask_name"""
        triggers = ['mua', 'sản phẩm', 'giá', 'order', 'buy', 'menu', 'xem']
        
        if any(kw in msg.lower() for kw in triggers):
            _logger.info('🚀 Start chatbot flow')
            
            conv.sudo().write({'chatbot_state': 'ask_name'})
            
            self._send_text(conv, 
                "Xin chào! Cảm ơn bạn đã quan tâm đến sản phẩm! 😊\n\n"
                "Để phục vụ bạn tốt hơn, bạn vui lòng cho tôi biết **tên** của bạn?")
    
    def _state_ask_name(self, conv, msg):
        """STATE: ask_name → ask_phone"""
        name = msg.strip()
        
        if len(name) < 2:
            self._send_text(conv, "Tên có vẻ ngắn quá. Vui lòng nhập lại tên đầy đủ! 😊")
            return
        
        _logger.info(f'💾 Save name: {name}')
        
        conv.sudo().write({
            'customer_name': name,
            'chatbot_state': 'ask_phone'
        })
        
        self._send_text(conv, 
            f"Rất vui được làm quen với {name}! 👋\n\n"
            "Để liên hệ xác nhận đơn hàng, bạn vui lòng cung cấp **số điện thoại**?")
    
    def _state_ask_phone(self, conv, msg):
        """STATE: ask_phone → show_products"""
        phone = msg.strip()
        
        if not re.match(r'^[0-9\s\+\-\(\)]{9,15}$', phone):
            self._send_text(conv, "SĐT không hợp lệ. Vui lòng nhập lại (10-11 số)!")
            return
        
        _logger.info(f'💾 Save phone: {phone}')
        
        conv.sudo().write({
            'customer_phone': phone,
            'chatbot_state': 'show_products'
        })
        
        self._send_product_list(conv)
    
    def _state_show_products(self, conv, msg):
        """STATE: show_products → confirm_order"""
        if msg.startswith('PRODUCT_'):
            try:
                product_id = int(msg.replace('PRODUCT_', ''))
                product = request.env['social.messenger.product'].sudo().browse(product_id)
                
                if not product.exists() or not product.active:
                    self._send_text(conv, "Sản phẩm không còn bán. Vui lòng chọn SP khác!")
                    self._send_product_list(conv)
                    return
                
                _logger.info(f'✅ Selected: {product.product_id.name}')
                
                conv.sudo().write({
                    'selected_product_ids': [(6, 0, [product.id])],
                    'chatbot_state': 'confirm_order'
                })
                
                price_text = f"{product.price:,.0f}đ" if product.price > 0 else "Liên hệ"
                
                confirm_msg = f"""✅ Bạn đã chọn:

📦 {product.product_id.name}
💰 Giá: {price_text}

📋 Thông tin:
👤 Tên: {conv.customer_name}
📞 SĐT: {conv.customer_phone}

Xác nhận đặt hàng?
👉 "Có" để xác nhận
👉 "Không" để chọn lại"""
                
                self._send_text(conv, confirm_msg)
                
            except Exception as e:
                _logger.error(f'❌ Error: {e}')
                self._send_text(conv, "Có lỗi xảy ra. Vui lòng thử lại!")
        else:
            self._send_text(conv, "Vui lòng chọn sản phẩm từ danh sách!")
    
    def _state_confirm_order(self, conv, msg):
        """STATE: confirm_order → completed (TẠO ORDER + LEAD)"""
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['có', 'yes', 'ok', 'đồng ý', 'đặt']):
            _logger.info('🛒 User confirmed!')
            
            try:
                # 1. Tạo Messenger Order
                order = self._create_order(conv)
                
                if not order:
                    raise Exception('Failed to create order')
                
                # 2. Tạo Sale Order
                sale_order = order.create_sale_order()
                
                # 3. Tạo CRM Lead
                lead = self._create_lead(conv, order, sale_order)
                
                # 4. Update state
                conv.sudo().write({
                    'chatbot_state': 'completed',
                    'messenger_order_id': order.id,
                    'lead_id': lead.id if lead else False
                })
                
                # 5. Gửi thông báo
                success_msg = f"""🎉 **Đặt hàng thành công!**

📝 Mã đơn hàng: {order.name}
📝 Mã sale order: {sale_order.name}

Chúng tôi sẽ liên hệ sớm nhất!

Cảm ơn bạn! 🙏

---
Gửi "mua" để tiếp tục mua sắm."""
                
                self._send_text(conv, success_msg)
                
                _logger.info(f'✅ Order: {order.name} | Sale: {sale_order.name}')
                
            except Exception as e:
                _logger.error(f'❌ Create order error: {e}', exc_info=True)
                conv.sudo().write({'chatbot_state': 'idle'})
                self._send_text(conv, "Có lỗi khi tạo đơn. Vui lòng liên hệ hotline! 😔")
        
        elif any(kw in msg_lower for kw in ['không', 'no', 'hủy', 'chọn lại']):
            _logger.info('❌ User cancelled')
            
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)]
            })
            
            self._send_text(conv, "Đã hủy. Hãy chọn lại sản phẩm! 😊")
            self._send_product_list(conv)
        
        else:
            self._send_text(conv, 'Vui lòng trả lời "Có" hoặc "Không"!')
    
    # =========================================================================
    # ✅ CREATE ORDER & LEAD
    # =========================================================================
    
    def _create_order(self, conv):
        """Tạo social.messenger.order"""
        try:
            order_vals = {
                'facebook_user_id': conv.facebook_user_id,
                'customer_name': conv.customer_name,
                'customer_phone': conv.customer_phone,
                'product_ids': [(6, 0, conv.selected_product_ids.ids)],
                'company_id': conv.company_id.id,
                'state': 'confirmed',
            }
            
            order = request.env['social.messenger.order'].sudo().create(order_vals)
            _logger.info(f'✅ Created order: {order.name}')
            return order
            
        except Exception as e:
            _logger.error(f'❌ Create order failed: {e}')
            raise
    
    def _create_lead(self, conv, order, sale_order):
        """Tạo crm.lead"""
        try:
            Lead = request.env['crm.lead'].sudo()
            
            if conv.lead_id:
                lead = conv.lead_id
                lead.message_post(
                    body=f"<strong>🛒 Order: {order.name}</strong><br/>"
                         f"Sale Order: {sale_order.name}<br/>"
                         f"Total: {order.total_amount:,.0f}đ",
                    message_type='comment'
                )
                return lead
            
            lead_vals = {
                'name': f'FB Order - {conv.customer_name}',
                'type': 'opportunity',
                'contact_name': conv.customer_name,
                'phone': conv.customer_phone,
                'expected_revenue': order.total_amount,
                'description': f"""Lead from Facebook Messenger

Order: {order.name}
Sale Order: {sale_order.name}
Total: {order.total_amount:,.0f}đ

Products:
{chr(10).join([f"- {p.product_id.name}" for p in order.product_ids])}

Customer:
- Name: {conv.customer_name}
- Phone: {conv.customer_phone}
- PSID: {conv.facebook_user_id}
""",
                'company_id': conv.company_id.id,
            }
            
            source = request.env['utm.source'].sudo().search([('name', '=', 'Facebook')], limit=1)
            if not source:
                source = request.env['utm.source'].sudo().create({'name': 'Facebook'})
            lead_vals['source_id'] = source.id
            
            lead = Lead.create(lead_vals)
            _logger.info(f'✅ Created lead: {lead.id}')
            return lead
            
        except Exception as e:
            _logger.error(f'❌ Create lead failed: {e}')
            return None
    
    # =========================================================================
    # SEND MESSAGE HELPERS
    # =========================================================================
    
    def _send_text(self, conv, text):
        """Gửi tin nhắn text"""
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': conv.facebook_user_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': conv.account_id.access_token}
        
        try:
            response = requests.post(url, json=payload, params=params, timeout=10)
            response.raise_for_status()
            _logger.info(f'✅ Sent: "{text[:30]}..."')
            return True
        except Exception as e:
            _logger.error(f'❌ Send failed: {e}')
            return False
    
    def _send_product_list(self, conv):
        """Gửi danh sách sản phẩm với Quick Replies"""
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', conv.company_id.id)
        ], order='sequence, id')
        
        if not products:
            self._send_text(conv, "Xin lỗi, chưa có sản phẩm nào!")
            return
        
        product_list = "📦 **Danh sách sản phẩm:**\n\n"
        
        for idx, p in enumerate(products, 1):
            price = f"{p.price:,.0f}đ" if p.price > 0 else "Liên hệ"
            product_list += f"{idx}. {p.product_id.name}\n   💰 {price}\n"
            if p.description:
                product_list += f"   📝 {p.description[:50]}...\n"
            product_list += "\n"
        
        product_list += "👇 Chọn sản phẩm:"
        
        quick_replies = []
        for p in products[:11]:
            quick_replies.append({
                'content_type': 'text',
                'title': p.quick_reply_title or p.product_id.name[:20],
                'payload': f'PRODUCT_{p.id}'
            })
        
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': conv.facebook_user_id},
            'message': {
                'text': product_list,
                'quick_replies': quick_replies
            },
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': conv.account_id.access_token}
        
        try:
            response = requests.post(url, json=payload, params=params, timeout=10)
            response.raise_for_status()
            _logger.info(f'✅ Sent product list ({len(quick_replies)} items)')
        except Exception as e:
            _logger.error(f'❌ Send product list failed: {e}')
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _find_or_create_conversation(self, sender_id, recipient_id):
        """Tìm/tạo conversation"""
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)
        ], limit=1)
        
        if not account:
            _logger.error(f'❌ No account for page {recipient_id}')
            return None
        
        conv = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', sender_id),
            ('account_id', '=', account.id),
        ], limit=1)
        
        if conv:
            return conv
        
        conv_vals = {
            'facebook_user_id': sender_id,
            'account_id': account.id,
            'company_id': account.company_id.id,
            'chatbot_state': 'idle',
        }
        
        try:
            conv = request.env['social.message'].sudo().create(conv_vals)
            _logger.info(f'✅ Created conversation: {conv.id}')
            return conv
        except Exception as e:
            _logger.error(f'❌ Create conversation failed: {e}')
            return None