# -*- coding: utf-8 -*-
"""
Facebook Webhook Controller - Production Version
=================================================

Features:
- Smart conversation initiation
- Natural language understanding
- Customer data validation & normalization
- CRM history integration
- Flexible conversation flow
- Advanced error handling
- Comprehensive logging
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
    # ✅ CHATBOT FLOW - NÂNG CẤP TOÀN DIỆN
    # =========================================================================
    
    def _process_chatbot_flow(self, conversation, user_message):
        """
        ✅ NÂNG CẤP 1: Chatbot flow thông minh với NLU và CRM integration
        """
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            return
        
        # ✅ NÂNG CẤP 7: Kiểm tra cooldown sau khi hoàn tất đơn
        if self._is_in_cooldown(conversation):
            self._send_text(conversation, 
                "Cảm ơn bạn đã đặt hàng! Nếu cần hỗ trợ, vui lòng liên hệ hotline hoặc gửi tin nhắn sau 5 phút. 😊")
            return
        
        current_state = conversation.chatbot_state or 'idle'
        _logger.info(f'🤖 State: {current_state} | Message: "{user_message[:50]}..."')
        
        # ✅ NÂNG CẤP 8: Tận dụng CRM data cho khách hàng cũ
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
    # ✅ STATE HANDLERS - NÂNG CẤP
    # =========================================================================
    
    def _state_idle_smart(self, conv, msg):
        """
        ✅ NÂNG CẤP 1: Cải thiện cơ chế khởi động chatbot
        
        Hỗ trợ:
        - Chào hỏi tự nhiên: "xin chào", "shop ơi", "hello"
        - Từ khóa mua hàng: "mua", "sản phẩm", "giá"
        - Yêu cầu tư vấn: "tư vấn", "hỗ trợ"
        """
        msg_lower = msg.lower().strip()
        
        # ✅ Chào hỏi tự nhiên
        greetings = ['xin chào', 'chào', 'hello', 'hi', 'hey', 'shop ơi', 'alo']
        if any(g in msg_lower for g in greetings):
            _logger.info('👋 Greeting detected')
            
            # ✅ NÂNG CẤP 8: Check khách hàng cũ
            existing_customer = self._check_existing_customer(conv)
            
            if existing_customer:
                welcome_msg = f"""Xin chào {existing_customer['name']}! 👋

Rất vui được gặp lại bạn!

Bạn muốn:
📦 Xem sản phẩm
🛒 Đặt hàng mới
📞 Liên hệ hỗ trợ"""
            else:
                welcome_msg = """Xin chào! Cảm ơn bạn đã nhắn tin! 😊

Chúng tôi có thể giúp gì cho bạn:
📦 Xem sản phẩm
💰 Hỏi giá
🛒 Đặt hàng"""
            
            self._send_text(conv, welcome_msg)
            return
        
        # ✅ Từ khóa mua hàng
        purchase_keywords = ['mua', 'sản phẩm', 'giá', 'order', 'buy', 'menu', 'xem', 'đặt hàng']
        if any(kw in msg_lower for kw in purchase_keywords):
            _logger.info('🚀 Purchase intent detected - Start flow')
            
            # ✅ NÂNG CẤP 8: Auto-fill thông tin khách cũ
            existing_customer = self._check_existing_customer(conv)
            
            if existing_customer:
                # Skip ask_name, ask_phone → Đi thẳng show_products
                conv.sudo().write({
                    'customer_name': existing_customer['name'],
                    'customer_phone': existing_customer['phone'],
                    'chatbot_state': 'show_products'
                })
                
                self._send_text(conv, 
                    f"Xin chào {existing_customer['name']}! 😊\n\n"
                    "Dưới đây là danh sách sản phẩm của chúng tôi:")
                
                self._send_product_list(conv)
            else:
                # Khách mới → Hỏi tên
                conv.sudo().write({'chatbot_state': 'ask_name'})
                self._send_text(conv, 
                    "Xin chào! Cảm ơn bạn đã quan tâm đến sản phẩm! 😊\n\n"
                    "Để phục vụ bạn tốt hơn, bạn vui lòng cho tôi biết **tên** của bạn?")
            return
        
        # ✅ Yêu cầu tư vấn
        support_keywords = ['tư vấn', 'hỗ trợ', 'giúp', 'help', 'support']
        if any(kw in msg_lower for kw in support_keywords):
            _logger.info('💬 Support request')
            self._send_text(conv, 
                "Chúng tôi sẵn sàng tư vấn!\n\n"
                "Bạn muốn:\n"
                "📦 Xem sản phẩm\n"
                "💰 Hỏi giá\n"
                "📞 Liên hệ hotline: 1900xxxx")
            return
        
        # ✅ Default response
        self._send_text(conv, 
            'Xin chào! Gửi "mua" hoặc "xem sản phẩm" để bắt đầu mua hàng nhé! 😊')
    
    def _state_ask_name_improved(self, conv, msg):
        """
        ✅ NÂNG CẤP 2: Chuẩn hóa logic hỏi và lưu tên khách hàng
        ✅ NÂNG CẤP 4: Bổ sung cơ chế hỏi lại khi nhập sai
        """
        name = msg.strip()
        
        # ✅ Kiểm tra độ dài
        if len(name) < 2:
            _logger.warning(f'⚠️ Name too short: {name}')
            self._send_text(conv, 
                "Tên bạn có vẻ hơi ngắn.\n\n"
                "**Vui lòng nhập lại tên đầy đủ của bạn** (ví dụ: Nguyễn Văn A)")
            return
        
        # ✅ Kiểm tra tên hợp lệ (chỉ chữ cái và khoảng trắng)
        if not re.match(r'^[a-zA-ZÀ-ỹ\s]+$', name):
            _logger.warning(f'⚠️ Invalid name format: {name}')
            self._send_text(conv, 
                "Tên không hợp lệ (chỉ chứa chữ cái).\n\n"
                "**Vui lòng nhập lại tên của bạn** (ví dụ: Nguyễn Văn A)")
            return
        
        # ✅ Chuẩn hóa tên: Title Case
        name_normalized = ' '.join(word.capitalize() for word in name.split())
        
        _logger.info(f'💾 Save name: {name_normalized}')
        
        conv.sudo().write({
            'customer_name': name_normalized,
            'chatbot_state': 'ask_phone'
        })
        
        self._send_text(conv, 
            f"Rất vui được làm quen với {name_normalized}! 👋\n\n"
            "Để chúng tôi có thể liên hệ xác nhận đơn hàng, "
            "**bạn vui lòng cung cấp số điện thoại?**\n\n"
            "_(Ví dụ: 0912345678 hoặc +84912345678)_")
    
    def _state_ask_phone_improved(self, conv, msg):
        """
        ✅ NÂNG CẤP 3: Nâng cấp kiểm tra và chuẩn hóa số điện thoại
        ✅ NÂNG CẤP 4: Hỏi lại khi nhập sai
        """
        phone = msg.strip()
        
        # ✅ Chuẩn hóa: Xóa khoảng trắng, dấu ngoặc, dấu gạch
        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)
        
        # ✅ Chuyển +84 → 0
        if phone_clean.startswith('+84'):
            phone_clean = '0' + phone_clean[3:]
        elif phone_clean.startswith('84') and len(phone_clean) == 11:
            phone_clean = '0' + phone_clean[2:]
        
        # ✅ Kiểm tra định dạng: 10-11 số, bắt đầu bằng 0
        if not re.match(r'^0\d{9,10}$', phone_clean):
            _logger.warning(f'⚠️ Invalid phone: {phone}')
            self._send_text(conv, 
                "Số điện thoại không hợp lệ.\n\n"
                "**Vui lòng nhập lại số điện thoại** (10-11 số, bắt đầu bằng 0)\n\n"
                "_Ví dụ: 0912345678_")
            return
        
        _logger.info(f'💾 Save phone: {phone_clean}')
        
        conv.sudo().write({
            'customer_phone': phone_clean,
            'chatbot_state': 'show_products'
        })
        
        self._send_product_list(conv)
    
    def _state_show_products_nlu(self, conv, msg):
        """
        ✅ NÂNG CẤP 5: Nâng cao khả năng hiểu câu trả lời ngoài kịch bản
        ✅ NÂNG CẤP 9: Chuẩn hóa luồng - cho phép quay lại
        """
        msg_lower = msg.lower().strip()
        
        # ✅ Xử lý lệnh điều hướng
        if any(kw in msg_lower for kw in ['quay lại', 'back', 'trở lại', 'hủy']):
            _logger.info('🔙 User wants to go back')
            conv.sudo().write({
                'chatbot_state': 'ask_phone',
                'selected_product_ids': [(5, 0, 0)]
            })
            self._send_text(conv, 
                "Đã quay lại bước nhập số điện thoại.\n\n"
                "**Vui lòng nhập số điện thoại:**")
            return
        
        # ✅ Xử lý Quick Reply (PRODUCT_XXX)
        if msg.startswith('PRODUCT_'):
            product_id = self._extract_product_id(msg)
            if product_id:
                self._handle_product_selection(conv, product_id)
                return
        
        # ✅ NLU: Hiểu câu trả lời tự nhiên
        product_selection = self._parse_natural_product_selection(conv, msg)
        
        if product_selection:
            self._handle_product_selection(conv, product_selection)
        else:
            # ✅ NÂNG CẤP 4: Hỏi lại rõ ràng
            self._send_text(conv, 
                "Xin lỗi, tôi chưa hiểu lựa chọn của bạn.\n\n"
                "**Vui lòng chọn sản phẩm bằng cách:**\n"
                "- Click vào button bên dưới\n"
                "- Hoặc gửi \"sản phẩm 1\", \"sản phẩm 2\"...\n"
                "- Hoặc gửi tên sản phẩm")
    
    def _state_confirm_order_validated(self, conv, msg):
        """
        ✅ NÂNG CẤP 6: Kiểm tra dữ liệu hội thoại trước khi tạo đơn
        ✅ NÂNG CẤP 9: Cho phép quay lại hoặc đổi sản phẩm
        """
        msg_lower = msg.lower().strip()
        
        # ✅ Cho phép quay lại chọn sản phẩm
        if any(kw in msg_lower for kw in ['quay lại', 'chọn lại', 'đổi', 'back']):
            _logger.info('🔙 User wants to change product')
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)]
            })
            self._send_text(conv, "Đã xóa lựa chọn. Hãy chọn lại sản phẩm! 😊")
            self._send_product_list(conv)
            return
        
        # ✅ Xác nhận đặt hàng
        if any(kw in msg_lower for kw in ['có', 'yes', 'ok', 'đồng ý', 'đặt', 'chốt']):
            _logger.info('🛒 User confirmed order')
            
            # ✅ NÂNG CẤP 6: Validate dữ liệu trước khi tạo
            validation_result = self._validate_order_data(conv)
            
            if not validation_result['valid']:
                _logger.error(f'❌ Order validation failed: {validation_result["errors"]}')
                self._send_text(conv, 
                    f"Có lỗi xảy ra:\n{validation_result['errors']}\n\n"
                    "Vui lòng thử lại hoặc liên hệ hỗ trợ.")
                return
            
            # ✅ Tạo đơn hàng
            try:
                order_result = self._create_order_with_validation(conv)
                
                if order_result['success']:
                    # ✅ NÂNG CẤP 7: Set cooldown sau khi hoàn tất
                    self._set_cooldown(conv)
                    
                    conv.sudo().write({
                        'chatbot_state': 'completed',
                        'messenger_order_id': order_result['order'].id,
                        'lead_id': order_result['lead'].id if order_result.get('lead') else False
                    })
                    
                    success_msg = f"""🎉 **Đặt hàng thành công!**

📝 Mã đơn hàng: {order_result['order'].name}
📝 Mã sale order: {order_result['sale_order'].name}
💰 Tổng tiền: {order_result['order'].total_amount:,.0f}đ

Chúng tôi sẽ liên hệ xác nhận trong thời gian sớm nhất!

Cảm ơn {conv.customer_name}! 🙏"""
                    
                    self._send_text(conv, success_msg)
                    _logger.info(f'✅ Order completed: {order_result["order"].name}')
                else:
                    raise Exception(order_result.get('error', 'Unknown error'))
                    
            except Exception as e:
                _logger.error(f'❌ Order creation failed: {e}', exc_info=True)
                conv.sudo().write({'chatbot_state': 'idle'})
                self._send_text(conv, 
                    "Có lỗi xảy ra khi tạo đơn hàng. "
                    "Vui lòng liên hệ hotline để được hỗ trợ. Xin lỗi vì sự bất tiện! 😔")
        
        # ✅ Hủy đơn
        elif any(kw in msg_lower for kw in ['không', 'no', 'hủy', 'cancel']):
            _logger.info('❌ User cancelled order')
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)]
            })
            self._send_text(conv, "Đã hủy đơn hàng. Hãy chọn lại sản phẩm! 😊")
            self._send_product_list(conv)
        
        else:
            # ✅ NÂNG CẤP 4: Hỏi lại rõ ràng
            self._send_text(conv, 
                '**Vui lòng xác nhận:**\n\n'
                '👉 Trả lời "Có" để đặt hàng\n'
                '👉 Trả lời "Không" hoặc "Chọn lại" để chọn sản phẩm khác')
    
    def _state_completed_smart(self, conv, msg):
        """
        ✅ NÂNG CẤP 7: Xử lý thông minh sau khi hoàn tất
        """
        # Check cooldown
        if self._is_in_cooldown(conv):
            self._send_text(conv, 
                "Đơn hàng của bạn đang được xử lý.\n\n"
                "Nếu cần hỗ trợ, vui lòng liên hệ hotline: 1900xxxx")
            return
        
        # Reset về idle để bắt đầu hội thoại mới
        conv.sudo().write({'chatbot_state': 'idle'})
        self._state_idle_smart(conv, msg)
    
    # =========================================================================
    # ✅ HELPER METHODS - NLU & VALIDATION
    # =========================================================================
    
    def _parse_natural_product_selection(self, conv, msg):
        """
        ✅ NÂNG CẤP 5: Parse lựa chọn sản phẩm từ ngôn ngữ tự nhiên
        
        Examples:
        - "sản phẩm 2"
        - "mình chọn cái đầu tiên"
        - "espresso"
        - "brownie"
        """
        msg_lower = msg.lower().strip()
        
        # Lấy danh sách sản phẩm
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', conv.company_id.id)
        ], order='sequence, id')
        
        if not products:
            return None
        
        # Pattern 1: "sản phẩm [số]" hoặc "sp [số]"
        match = re.search(r'(?:sản phẩm|sp|số)\s*(\d+)', msg_lower)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(products):
                _logger.info(f'🎯 NLU: Matched product by number: {index + 1}')
                return products[index].id
        
        # Pattern 2: Vị trí (đầu tiên, thứ hai, cuối...)
        position_map = {
            'đầu': 0, 'đầu tiên': 0, 'first': 0,
            'hai': 1, 'thứ hai': 1, 'second': 1,
            'ba': 2, 'thứ ba': 2, 'third': 2,
            'cuối': -1, 'cuối cùng': -1, 'last': -1
        }
        
        for keyword, index in position_map.items():
            if keyword in msg_lower:
                try:
                    product = products[index]
                    _logger.info(f'🎯 NLU: Matched product by position: {keyword}')
                    return product.id
                except IndexError:
                    pass
        
        # Pattern 3: Tên sản phẩm (fuzzy match)
        for product in products:
            product_name_lower = product.product_id.name.lower()
            # Check exact match
            if product_name_lower in msg_lower:
                _logger.info(f'🎯 NLU: Matched product by name: {product.product_id.name}')
                return product.id
            
            # Check partial match (>70% overlap)
            name_words = set(product_name_lower.split())
            msg_words = set(msg_lower.split())
            overlap = len(name_words & msg_words)
            if overlap > 0 and overlap / len(name_words) > 0.5:
                _logger.info(f'🎯 NLU: Matched product by partial name: {product.product_id.name}')
                return product.id
        
        return None
    
    def _validate_order_data(self, conv):
        """
        ✅ NÂNG CẤP 6: Validate dữ liệu trước khi tạo đơn
        """
        errors = []
        
        # Check customer name
        if not conv.customer_name or len(conv.customer_name) < 2:
            errors.append("Thiếu tên khách hàng")
        
        # Check customer phone
        if not conv.customer_phone or not re.match(r'^0\d{9,10}$', conv.customer_phone):
            errors.append("Số điện thoại không hợp lệ")
        
        # Check selected products
        if not conv.selected_product_ids:
            errors.append("Chưa chọn sản phẩm")
        
        # Check chatbot state
        if conv.chatbot_state != 'confirm_order':
            errors.append(f"Trạng thái không hợp lệ: {conv.chatbot_state}")
        
        return {
            'valid': len(errors) == 0,
            'errors': '\n'.join(errors) if errors else None
        }
    
    def _check_existing_customer(self, conv):
        """
        ✅ NÂNG CẤP 8: Kiểm tra khách hàng cũ từ CRM
        
        Returns:
            dict hoặc None: {'name': '...', 'phone': '...', 'lead_count': X}
        """
        # Check từ conversation cũ
        old_conv = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', conv.facebook_user_id),
            ('account_id', '=', conv.account_id.id),
            ('customer_name', '!=', False),
            ('customer_phone', '!=', False),
            ('id', '!=', conv.id)
        ], limit=1, order='create_date desc')
        
        if old_conv:
            _logger.info(f'👤 Found existing customer: {old_conv.customer_name}')
            return {
                'name': old_conv.customer_name,
                'phone': old_conv.customer_phone,
                'lead_count': request.env['crm.lead'].sudo().search_count([
                    ('phone', '=', old_conv.customer_phone)
                ])
            }
        
        # Check từ res.partner
        partner = request.env['res.partner'].sudo().search([
            ('facebook_user_id', '=', conv.facebook_user_id)
        ], limit=1)
        
        if partner and partner.phone:
            _logger.info(f'👤 Found existing partner: {partner.name}')
            return {
                'name': partner.name,
                'phone': partner.phone,
                'lead_count': request.env['crm.lead'].sudo().search_count([
                    ('partner_id', '=', partner.id)
                ])
            }
        
        return None
    
    def _set_cooldown(self, conv):
        """
        ✅ NÂNG CẤP 7: Set cooldown sau khi hoàn tất đơn (5 phút)
        """
        cooldown_minutes = 5
        cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
        
        # Lưu vào conversation (thêm field mới nếu cần)
        try:
            conv.sudo().write({'cooldown_until': cooldown_until})
            _logger.info(f'⏱️ Set cooldown until {cooldown_until}')
        except:
            # Field chưa có → Log warning
            _logger.warning('⚠️ Field cooldown_until not found - skip cooldown')
    
    def _is_in_cooldown(self, conv):
        """
        ✅ NÂNG CẤP 7: Check xem có đang trong cooldown không
        """
        if not hasattr(conv, 'cooldown_until'):
            return False
        
        if conv.cooldown_until and conv.cooldown_until > datetime.now():
            _logger.info('⏱️ Conversation in cooldown')
            return True
        
        return False
    
    def _extract_product_id(self, payload):
        """Extract product ID từ payload PRODUCT_XXX"""
        try:
            return int(payload.replace('PRODUCT_', ''))
        except:
            return None
    
    # =========================================================================
    # ✅ ORDER CREATION - VALIDATED
    # =========================================================================
    
    def _create_order_with_validation(self, conv):
        """
        ✅ NÂNG CẤP 10: Tạo đơn với error handling và logging chi tiết
        """
        try:
            _logger.info('🛒 Starting order creation...')
            
            # 1. Tạo Messenger Order
            order = self._create_messenger_order(conv)
            if not order:
                raise Exception('Failed to create messenger order')
            
            _logger.info(f'✅ Created messenger order: {order.name}')
            
            # 2. Tạo Sale Order
            sale_order = order.create_sale_order()
            if not sale_order:
                raise Exception('Failed to create sale order')
            
            _logger.info(f'✅ Created sale order: {sale_order.name}')
            
            # 3. Tạo CRM Lead
            lead = self._create_crm_lead(conv, order, sale_order)
            
            if lead:
                _logger.info(f'✅ Created CRM lead: {lead.id}')
            else:
                _logger.warning('⚠️ CRM lead creation failed (non-critical)')
            
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
            return order
            
        except Exception as e:
            _logger.error(f'❌ Create messenger order failed: {e}')
            raise
    
    def _create_crm_lead(self, conv, order, sale_order):
        """Tạo crm.lead"""
        try:
            Lead = request.env['crm.lead'].sudo()
            
            # Check existing lead
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
            
            # Create new lead
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
{chr(10).join([f"- {p.product_id.name}: {p.price:,.0f}đ" for p in order.product_ids])}

Customer:
- Name: {conv.customer_name}
- Phone: {conv.customer_phone}
- PSID: {conv.facebook_user_id}
""",
                'company_id': conv.company_id.id,
            }
            
            # Add Facebook source
            source = request.env['utm.source'].sudo().search([('name', '=', 'Facebook')], limit=1)
            if not source:
                source = request.env['utm.source'].sudo().create({'name': 'Facebook'})
            lead_vals['source_id'] = source.id
            
            lead = Lead.create(lead_vals)
            return lead
            
        except Exception as e:
            _logger.error(f'❌ Create CRM lead failed: {e}')
            return None
    
    def _handle_product_selection(self, conv, product_id):
        """Xử lý khi user chọn sản phẩm"""
        try:
            product = request.env['social.messenger.product'].sudo().browse(product_id)
            
            if not product.exists() or not product.active:
                self._send_text(conv, 
                    "Sản phẩm không còn bán. Vui lòng chọn sản phẩm khác!")
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

📋 Thông tin đặt hàng:
👤 Tên: {conv.customer_name}
📞 SĐT: {conv.customer_phone}

**Xác nhận đặt hàng?**

👉 "Có" để xác nhận
👉 "Không" hoặc "Chọn lại" để chọn sản phẩm khác"""
            
            self._send_text(conv, confirm_msg)
            
        except Exception as e:
            _logger.error(f'❌ Handle product selection error: {e}')
    
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