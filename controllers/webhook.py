# -*- coding: utf-8 -*-
"""
Facebook Webhook Controller - PRODUCTION FIXED
===============================================

✅ FIX: Lỗi tạo đơn hàng
✅ FIX: Link conversation_id đúng
✅ FIX: Error handling chi tiết
"""

import json
import logging
import requests
import re
from datetime import datetime, timedelta
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class FacebookWebhookController(http.Controller):
    """
    Controller xử lý webhook từ Facebook với chatbot nâng cao.
    """
    
    # =========================================================================
    # WEBHOOK ENDPOINTS
    # =========================================================================
    
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
                self._process_chatbot_flow(conversation, payload)
            else:
                text = message_data.get('text', '')
                self._process_chatbot_flow(conversation, text)
    
    # =========================================================================
    # ✅ CHATBOT FLOW
    # =========================================================================
    
    def _process_chatbot_flow(self, conversation, user_message):
        """Chatbot flow với state machine"""
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            return
        
        # Check cooldown
        if self._is_in_cooldown(conversation):
            self._send_text(conversation, 
                "Cảm ơn bạn đã đặt hàng! Nếu cần hỗ trợ, vui lòng liên hệ hotline. 😊")
            return
        
        current_state = conversation.chatbot_state or 'idle'
        _logger.info(f'🤖 State: {current_state} | Message: "{user_message[:50]}..."')
        
        if current_state == 'idle':
            self._state_idle_smart(conversation, user_message)
        elif current_state == 'ask_name':
            self._state_ask_name_improved(conversation, user_message)
        elif current_state == 'ask_phone':
            self._state_ask_phone_improved(conversation, user_message)
        elif current_state == 'show_products':
            self._state_show_products_nlu(conversation, user_message)
        elif current_state == 'confirm_order':
            self._state_confirm_order_validated(conversation, user_message)
        elif current_state == 'completed':
            self._state_completed_smart(conversation, user_message)
    
    # =========================================================================
    # STATE HANDLERS
    # =========================================================================
    
    def _state_idle_smart(self, conv, msg):
        """STATE: idle → ask_name"""
        msg_lower = msg.lower().strip()
        
        # Chào hỏi
        greetings = ['xin chào', 'chào', 'hello', 'hi', 'hey', 'shop ơi', 'alo']
        if any(g in msg_lower for g in greetings):
            existing_customer = self._check_existing_customer(conv)
            
            if existing_customer:
                welcome_msg = f"Xin chào {existing_customer['name']}! 👋\n\nRất vui được gặp lại bạn!"
            else:
                welcome_msg = "Xin chào! Cảm ơn bạn đã nhắn tin! 😊\n\nGửi 'mua' để xem sản phẩm."
            
            self._send_text(conv, welcome_msg)
            return
        
        # Từ khóa mua hàng
        purchase_keywords = ['mua', 'sản phẩm', 'giá', 'order', 'buy', 'menu', 'xem', 'đặt hàng']
        if any(kw in msg_lower for kw in purchase_keywords):
            existing_customer = self._check_existing_customer(conv)
            
            if existing_customer:
                conv.sudo().write({
                    'customer_name': existing_customer['name'],
                    'customer_phone': existing_customer['phone'],
                    'chatbot_state': 'show_products'
                })
                self._send_text(conv, f"Xin chào {existing_customer['name']}! 😊")
                self._send_product_list(conv)
            else:
                conv.sudo().write({'chatbot_state': 'ask_name'})
                self._send_text(conv, 
                    "Xin chào! Cảm ơn bạn đã quan tâm! 😊\n\n"
                    "Bạn vui lòng cho tôi biết **tên** của bạn?")
            return
        
        self._send_text(conv, 'Gửi "mua" để xem sản phẩm! 😊')
    
    def _state_ask_name_improved(self, conv, msg):
        """STATE: ask_name → ask_phone"""
        name = msg.strip()
        
        if len(name) < 2:
            self._send_text(conv, 
                "Tên có vẻ ngắn.\n\n**Vui lòng nhập lại tên đầy đủ** (VD: Nguyễn Văn A)")
            return
        
        if not re.match(r'^[a-zA-ZÀ-ỹ\s]+$', name):
            self._send_text(conv, 
                "Tên không hợp lệ.\n\n**Vui lòng nhập lại** (VD: Nguyễn Văn A)")
            return
        
        name_normalized = ' '.join(word.capitalize() for word in name.split())
        
        conv.sudo().write({
            'customer_name': name_normalized,
            'chatbot_state': 'ask_phone'
        })
        
        self._send_text(conv, 
            f"Rất vui được làm quen với {name_normalized}! 👋\n\n"
            "Bạn vui lòng cung cấp **số điện thoại**?\n"
            "_(VD: 0912345678)_")
    
    def _state_ask_phone_improved(self, conv, msg):
        """STATE: ask_phone → show_products"""
        phone = msg.strip()
        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)
        
        if phone_clean.startswith('+84'):
            phone_clean = '0' + phone_clean[3:]
        elif phone_clean.startswith('84') and len(phone_clean) == 11:
            phone_clean = '0' + phone_clean[2:]
        
        if not re.match(r'^0\d{9,10}$', phone_clean):
            self._send_text(conv, 
                "SĐT không hợp lệ.\n\n**Vui lòng nhập lại** (10-11 số)\n_(VD: 0912345678)_")
            return
        
        conv.sudo().write({
            'customer_phone': phone_clean,
            'chatbot_state': 'show_products'
        })
        
        self._send_product_list(conv)
    
    def _state_show_products_nlu(self, conv, msg):
        """STATE: show_products → confirm_order"""
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['quay lại', 'back', 'hủy']):
            conv.sudo().write({
                'chatbot_state': 'ask_phone',
                'selected_product_ids': [(5, 0, 0)]
            })
            self._send_text(conv, "Đã quay lại.\n\n**Vui lòng nhập SĐT:**")
            return
        
        if msg.startswith('PRODUCT_'):
            product_id = self._extract_product_id(msg)
            if product_id:
                self._handle_product_selection(conv, product_id)
                return
        
        product_selection = self._parse_natural_product_selection(conv, msg)
        if product_selection:
            self._handle_product_selection(conv, product_selection)
        else:
            self._send_text(conv, 
                "Xin lỗi, tôi chưa hiểu.\n\n"
                "Vui lòng click button hoặc gửi 'sản phẩm 1', 'sản phẩm 2'...")
    
    def _state_confirm_order_validated(self, conv, msg):
        """STATE: confirm_order → completed (TẠO ĐƠN)"""
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['quay lại', 'chọn lại', 'đổi']):
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)]
            })
            self._send_text(conv, "Đã xóa lựa chọn. Hãy chọn lại! 😊")
            self._send_product_list(conv)
            return
        
        if any(kw in msg_lower for kw in ['có', 'yes', 'ok', 'đồng ý', 'đặt', 'chốt']):
            _logger.info('🛒 User confirmed order')
            
            # ✅ Validate
            validation_result = self._validate_order_data(conv)
            if not validation_result['valid']:
                _logger.error(f"❌ Validation failed: {validation_result['errors']}")
                self._send_text(conv, 
                    f"Có lỗi:\n{validation_result['errors']}\n\nVui lòng thử lại.")
                return
            
            # ✅ Tạo đơn
            try:
                order_result = self._create_order_with_validation(conv)
                
                if order_result['success']:
                    self._set_cooldown(conv)
                    
                    conv.sudo().write({
                        'chatbot_state': 'completed',
                        'messenger_order_id': order_result['order'].id,
                        'lead_id': order_result['lead'].id if order_result.get('lead') else False
                    })
                    
                    success_msg = f"""🎉 **Đặt hàng thành công!**

📝 Mã đơn: {order_result['order'].name}
📝 Sale order: {order_result['sale_order'].name}
💰 Tổng tiền: {order_result['order'].total_amount:,.0f}đ

Chúng tôi sẽ liên hệ sớm!

Cảm ơn {conv.customer_name}! 🙏"""
                    
                    self._send_text(conv, success_msg)
                    _logger.info(f"✅ Order completed: {order_result['order'].name}")
                else:
                    raise Exception(order_result.get('error', 'Unknown error'))
                    
            except Exception as e:
                _logger.error(f'❌ Order creation failed: {e}', exc_info=True)
                conv.sudo().write({'chatbot_state': 'idle'})
                self._send_text(conv, 
                    "Có lỗi xảy ra khi tạo đơn hàng.\n"
                    "Vui lòng liên hệ hotline để được hỗ trợ.\n"
                    f"Chi tiết lỗi: {str(e)[:100]}")
        
        elif any(kw in msg_lower for kw in ['không', 'no', 'hủy', 'cancel']):
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)]
            })
            self._send_text(conv, "Đã hủy. Hãy chọn lại! 😊")
            self._send_product_list(conv)
        else:
            self._send_text(conv, 
                '**Vui lòng xác nhận:**\n\n'
                '👉 "Có" để đặt hàng\n'
                '👉 "Không" để chọn lại')
    
    def _state_completed_smart(self, conv, msg):
        """STATE: completed"""
        if self._is_in_cooldown(conv):
            self._send_text(conv, "Đơn hàng đang được xử lý...")
            return
        
        conv.sudo().write({'chatbot_state': 'idle'})
        self._state_idle_smart(conv, msg)
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _parse_natural_product_selection(self, conv, msg):
        """Parse lựa chọn từ ngôn ngữ tự nhiên"""
        msg_lower = msg.lower().strip()
        
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', conv.company_id.id)
        ], order='sequence, id')
        
        if not products:
            return None
        
        # Pattern 1: "sản phẩm [số]"
        match = re.search(r'(?:sản phẩm|sp|số)\s*(\d+)', msg_lower)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(products):
                return products[index].id
        
        # Pattern 2: Tên sản phẩm
        for product in products:
            if product.product_id.name.lower() in msg_lower:
                return product.id
        
        return None
    
    def _validate_order_data(self, conv):
        """Validate dữ liệu đơn hàng"""
        errors = []
        
        if not conv.customer_name or len(conv.customer_name) < 2:
            errors.append("Thiếu tên khách hàng")
        
        if not conv.customer_phone or not re.match(r'^0\d{9,10}$', conv.customer_phone):
            errors.append("SĐT không hợp lệ")
        
        if not conv.selected_product_ids:
            errors.append("Chưa chọn sản phẩm")
        
        if conv.chatbot_state != 'confirm_order':
            errors.append(f"Trạng thái không hợp lệ: {conv.chatbot_state}")
        
        return {
            'valid': len(errors) == 0,
            'errors': '\n'.join(errors) if errors else None
        }
    
    def _check_existing_customer(self, conv):
        """Kiểm tra khách cũ"""
        old_conv = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', conv.facebook_user_id),
            ('account_id', '=', conv.account_id.id),
            ('customer_name', '!=', False),
            ('customer_phone', '!=', False),
            ('id', '!=', conv.id)
        ], limit=1, order='create_date desc')
        
        if old_conv:
            return {
                'name': old_conv.customer_name,
                'phone': old_conv.customer_phone,
            }
        
        return None
    
    def _set_cooldown(self, conv):
        """Set cooldown 5 phút"""
        cooldown_minutes = 5
        cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
        
        try:
            conv.sudo().write({'cooldown_until': cooldown_until})
            _logger.info(f'⏱️ Set cooldown until {cooldown_until}')
        except:
            _logger.warning('⚠️ Field cooldown_until not found')
    
    def _is_in_cooldown(self, conv):
        """Check cooldown"""
        if not hasattr(conv, 'cooldown_until'):
            return False
        
        if conv.cooldown_until and conv.cooldown_until > datetime.now():
            return True
        
        return False
    
    def _extract_product_id(self, payload):
        """Extract product ID từ PRODUCT_XXX"""
        try:
            return int(payload.replace('PRODUCT_', ''))
        except:
            return None
    
    # =========================================================================
    # ✅ ORDER CREATION - FIXED
    # =========================================================================
    
    def _create_order_with_validation(self, conv):
        """
        ✅ FIX: Tạo đơn với error handling đầy đủ
        """
        try:
            _logger.info('🛒 Starting order creation...')
            
            # ✅ FIX 1: Tạo messenger order với conversation_id
            order = self._create_messenger_order(conv)
            if not order:
                raise Exception('Failed to create messenger order')
            
            _logger.info(f'✅ Created messenger order: {order.name}')
            
            # ✅ FIX 2: Tạo sale order
            sale_order = order.create_sale_order()
            if not sale_order:
                raise Exception('Failed to create sale order')
            
            _logger.info(f'✅ Created sale order: {sale_order.name}')
            
            # ✅ FIX 3: Tạo CRM lead (optional)
            try:
                lead = self._create_crm_lead(conv, order, sale_order)
                _logger.info(f'✅ Created CRM lead: {lead.id}')
            except Exception as e:
                _logger.warning(f'⚠️ CRM lead creation failed: {e}')
                lead = None
            
            return {
                'success': True,
                'order': order,
                'sale_order': sale_order,
                'lead': lead
            }
            
        except Exception as e:
            _logger.error(f'❌ Order creation failed: {e}', exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_messenger_order(self, conv):
        """
        ✅ FIX: Tạo messenger order với conversation_id đúng
        """
        try:
            order_vals = {
                'facebook_user_id': conv.facebook_user_id,
                'customer_name': conv.customer_name,
                'customer_phone': conv.customer_phone,
                'product_ids': [(6, 0, conv.selected_product_ids.ids)],
                'company_id': conv.company_id.id,
                'state': 'confirmed',
                # ✅ FIX: Link conversation
                'conversation_id': conv.id,
            }
            
            _logger.info(f'📝 Creating messenger order with data: {order_vals}')
            
            order = request.env['social.messenger.order'].sudo().create(order_vals)
            
            _logger.info(f'✅ Messenger order created: ID={order.id}, Name={order.name}')
            
            return order
            
        except Exception as e:
            _logger.error(f'❌ Create messenger order failed: {e}', exc_info=True)
            raise
    
    def _create_crm_lead(self, conv, order, sale_order):
        """Tạo CRM lead"""
        try:
            Lead = request.env['crm.lead'].sudo()
            
            if conv.lead_id:
                lead = conv.lead_id
                lead.message_post(
                    body=f"<strong>🛒 New order</strong><br/>"
                         f"Order: {order.name}<br/>"
                         f"Sale: {sale_order.name}<br/>"
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
            return lead
            
        except Exception as e:
            _logger.error(f'❌ Create CRM lead failed: {e}', exc_info=True)
            return None
    
    def _handle_product_selection(self, conv, product_id):
        """Xử lý khi chọn sản phẩm"""
        try:
            product = request.env['social.messenger.product'].sudo().browse(product_id)
            
            if not product.exists() or not product.active:
                self._send_text(conv, "Sản phẩm không còn bán. Vui lòng chọn SP khác!")
                self._send_product_list(conv)
                return
            
            _logger.info(f'✅ Product selected: {product.product_id.name}')
            
            conv.sudo().write({
                'selected_product_ids': [(6, 0, [product.id])],
                'chatbot_state': 'confirm_order'
            })
            
            price_text = f"{product.price:,.0f}đ" if product.price > 0 else "Liên hệ"
            
            confirm_msg = f"""✅ Bạn đã chọn:

📦 **{product.product_id.name}**
💰 Giá: {price_text}

📋 Thông tin:
👤 Tên: {conv.customer_name}
📞 SĐT: {conv.customer_phone}

**Xác nhận đặt hàng?**

👉 "Có" để xác nhận
👉 "Không" để chọn lại"""
            
            self._send_text(conv, confirm_msg)
            
        except Exception as e:
            _logger.error(f'❌ Handle product selection error: {e}', exc_info=True)
    
    # =========================================================================
    # SEND MESSAGE
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
        """Gửi danh sách sản phẩm"""
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', conv.company_id.id)
        ], order='sequence, id')
        
        if not products:
            self._send_text(conv, "Xin lỗi, chưa có sản phẩm!")
            return
        
        product_list = "📦 **Danh sách sản phẩm:**\n\n"
        
        for idx, p in enumerate(products, 1):
            price = f"{p.price:,.0f}đ" if p.price > 0 else "Liên hệ"
            product_list += f"{idx}. {p.product_id.name}\n   💰 {price}\n\n"
        
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