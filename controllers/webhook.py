import json
import logging
import requests
import re
from odoo import fields
from datetime import datetime, timedelta
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class FacebookWebhookController(http.Controller):
    
    @http.route('/social/facebook/webhook', type='http', auth='public', 
                methods=['GET'], csrf=False)
    def webhook_verify(self, **kwargs):
        """Verify webhook"""
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')
        
        verify_token = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.verify_token', '16112005'
        )
        
        if mode == 'subscribe' and token == verify_token:
            _logger.info('✅ Webhook verified')
            return challenge
        else:
            _logger.warning('❌ Webhook verify failed')
            return 'Forbidden', 403
    
    @http.route('/social/facebook/webhook', type='http', auth='public', 
                methods=['POST'], csrf=False)
    def webhook_callback(self, **kwargs):
        """Nhận events từ Facebook"""
        try:
            body = request.httprequest.get_data(as_text=True)
            data = json.loads(body)
            
            if data.get('object') != 'page':
                return 'OK'
            
            for entry in data.get('entry', []):
                self._process_entry(entry)
            
            return 'OK'
            
        except Exception as e:
            _logger.error('❌ Webhook error: %s', e, exc_info=True)
            return 'OK'
    
    def _process_entry(self, entry):
        """Xử lý entry từ webhook"""
        if 'messaging' in entry:
            for event in entry['messaging']:
                self._process_messaging_event(event)
    
    def _process_messaging_event(self, event):
        """Xử lý messaging event"""
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        if not sender_id or not recipient_id:
            return
        
        # Find or create conversation
        conversation = self._find_or_create_conversation(sender_id, recipient_id)
        if not conversation:
            return
        
        # Process message
        if 'message' in event:
            message_data = event['message']
            
            # Skip echo messages (từ page gửi đi)
            if message_data.get('is_echo'):
                return
            
            # Process chatbot flow
            if 'quick_reply' in message_data:
                payload = message_data['quick_reply'].get('payload', '')
                self._process_chatbot_flow(conversation, payload)
            else:
                text = message_data.get('text', '')
                self._process_chatbot_flow(conversation, text)
    
    # =========================================================================
    # CHATBOT FLOW - STATE MACHINE
    # =========================================================================
    
    def _process_chatbot_flow(self, conversation, user_message):
        """Main chatbot flow dispatcher"""
        # Check if chatbot is enabled
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            return
        
        # Check cooldown (after order completion)
        if self._is_in_cooldown(conversation):
            self._send_text(conversation, 
                "Cảm ơn bạn đã đặt hàng! Đơn hàng đang được xử lý. "
                "Nếu cần hỗ trợ, vui lòng liên hệ hotline.")
            return
        
        # Get current state
        current_state = conversation.chatbot_state or 'idle'
        
        _logger.info('🤖 State: %s | Message: %s', current_state, user_message)
        
        # Dispatch to state handlers
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
            self._state_completed(conversation, user_message)
    
    # =========================================================================
    # STATE HANDLERS
    # =========================================================================
    
    def _state_idle(self, conv, msg):
        """State: idle - Chờ trigger từ user"""
        msg_lower = msg.lower().strip()
        
        # Check purchase intent keywords
        if any(kw in msg_lower for kw in ['mua', 'order', 'buy', 'menu', 'đặt hàng']):
            conv.sudo().write({'chatbot_state': 'ask_name'})
            self._send_text(conv, "Xin chào! 👋\n\nBạn vui lòng cho biết tên của bạn?")
        else:
            self._send_text(conv, '👋 Gửi "mua" để xem sản phẩm và đặt hàng!')
    
    def _state_ask_name(self, conv, msg):
        """State: ask_name - Thu thập tên khách hàng"""
        name = msg.strip()
        
        # Validate name length
        if len(name) < 2:
            self._send_text(conv, "Tên quá ngắn. Vui lòng nhập lại (ít nhất 2 ký tự).")
            return
        
        # Normalize name (capitalize each word)
        name_normalized = ' '.join(word.capitalize() for word in name.split())
        
        # Update conversation
        conv.sudo().write({
            'customer_name': name_normalized,
            'chatbot_state': 'ask_phone'
        })
        
        # Ask for phone
        welcome_msg = "Xin chào %s! 😊\n\nBạn vui lòng cung cấp số điện thoại?" % name_normalized
        self._send_text(conv, welcome_msg)
    
    def _state_ask_phone(self, conv, msg):
        """State: ask_phone - Thu thập số điện thoại"""
        phone = msg.strip()
        
        # Clean phone number
        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)
        
        # Convert +84 or 84 to 0
        if phone_clean.startswith('+84'):
            phone_clean = '0' + phone_clean[3:]
        elif phone_clean.startswith('84'):
            phone_clean = '0' + phone_clean[2:]
        
        # Validate Vietnamese phone format (0XXXXXXXXX)
        if not re.match(r'^0\d{9,10}$', phone_clean):
            self._send_text(conv, 
                "📱 Số điện thoại không hợp lệ!\n\n"
                "Vui lòng nhập lại (VD: 0912345678)")
            return
        
        # Update conversation
        conv.sudo().write({
            'customer_phone': phone_clean,
            'chatbot_state': 'show_products'
        })
        
        # Show product list
        self._send_product_list(conv)
    
    def _state_show_products(self, conv, msg):
        """State: show_products - Chờ user chọn sản phẩm"""
        # Check if message is a product selection payload
        if msg.startswith('PRODUCT_'):
            product_id = self._extract_product_id(msg)
            if product_id:
                self._handle_product_selection(conv, product_id)
    
    def _state_confirm_order(self, conv, msg):
        """
        ✅ State: confirm_order - Xác nhận và TẠO SALE ORDER
        """
        msg_lower = msg.lower().strip()
        
        _logger.info('📝 CONFIRM ORDER - Message: %s', msg)
        
        # User confirms order
        if any(kw in msg_lower for kw in ['có', 'yes', 'ok', 'đồng ý', 'xác nhận']):
            _logger.info('✅ User confirmed order')
            
            try:
                # Step 1: Validate order data
                _logger.info('Step 1: Validating order data...')
                validation = self._validate_order_data(conv)
                
                if not validation['valid']:
                    error_msg = "❌ Dữ liệu không hợp lệ: %s" % validation['errors']
                    _logger.error(error_msg)
                    self._send_text(conv, error_msg)
                    return
                
                # ✅ Step 2: TẠO SALE ORDER TRỰC TIẾP
                _logger.info('Step 2: Creating Sale Order directly...')
                sale_order = self._create_sale_order_directly(conv)
                _logger.info('✅ Sale order created: %s', sale_order.name)
                
                # Step 3: Update conversation state
                conv.sudo().write({
                    'chatbot_state': 'completed',
                    # Lưu sale_order_id vào conversation (cần thêm field này)
                })
                
                # Step 4: Send success message
                _logger.info('Step 4: Sending success message...')
                
                # Calculate total
                total_amount = sale_order.amount_total
                
                success_msg = """🎉 Đặt hàng thành công!

📝 Mã đơn hàng: %s
💰 Tổng tiền: %s đ

📦 Sản phẩm:
%s

👤 Khách hàng: %s
📞 SĐT: %s

✅ Đơn hàng đã được ghi nhận!
Chúng tôi sẽ liên hệ xác nhận trong thời gian sớm nhất.

Cảm ơn bạn! 🙏""" % (
                    sale_order.name,
                    "{:,.0f}".format(total_amount),
                    self._format_order_lines(sale_order),
                    conv.customer_name,
                    conv.customer_phone
                )
                
                self._send_text(conv, success_msg)
                
                # Set cooldown
                self._set_cooldown(conv)
                
                _logger.info('✅ Order flow completed: %s', sale_order.name)
                
            except Exception as e:
                import traceback
                _logger.error('❌ ORDER FAILED: %s', str(e))
                _logger.error('Traceback:\n%s', traceback.format_exc())
                
                # Reset to idle on error
                conv.sudo().write({'chatbot_state': 'idle'})
                self._send_text(conv, 
                    "❌ Xin lỗi, có lỗi xảy ra khi tạo đơn hàng.\n\n"
                    "Vui lòng thử lại hoặc liên hệ hotline để được hỗ trợ!")
        
        # User cancels order
        elif any(kw in msg_lower for kw in ['không', 'no', 'hủy', 'cancel']):
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)]  # Clear selected products
            })
            self._send_text(conv, "Đã hủy đơn hàng. Bạn có thể chọn lại sản phẩm! 🔄")
            self._send_product_list(conv)
        
        else:
            self._send_text(conv, 
                '⚠️ Vui lòng trả lời:\n'
                '✅ "Có" - để xác nhận đặt hàng\n'
                '❌ "Không" - để hủy và chọn lại')
    
    def _state_completed(self, conv, msg):
        """State: completed - Đơn hàng đã hoàn tất"""
        if self._is_in_cooldown(conv):
            self._send_text(conv, 
                "Đơn hàng của bạn đang được xử lý. "
                "Chúng tôi sẽ liên hệ sớm nhất! 📞")
        else:
            # Cooldown expired, reset to idle
            conv.sudo().write({'chatbot_state': 'idle'})
            self._state_idle(conv, msg)
    
    # =========================================================================
    # ✅ CORE BUSINESS LOGIC - TẠO SALE ORDER TRỰC TIẾP
    # =========================================================================
    
    def _create_sale_order_directly(self, conv):
        """
        ✅ TẠO SALE ORDER TRỰC TIẾP (không qua social.messenger.order)
        
        Args:
            conv (social.message): Conversation record
        
        Returns:
            sale.order: Created sale order
        """
        # 1. Find or create partner
        partner = self._find_or_create_partner(conv)
        
        # 2. Create sale.order
        sale_vals = {
            'partner_id': partner.id,
            'company_id': conv.company_id.id,
            'date_order': fields.Datetime.now(),
            'origin': 'Facebook Messenger - %s' % conv.facebook_user_id,
            'note': 'Đơn hàng từ Facebook Messenger\nPSID: %s' % conv.facebook_user_id,
        }
        
        # Get default salesperson from settings
        default_user_id = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.lead_default_user_id'
        )
        if default_user_id:
            sale_vals['user_id'] = int(default_user_id)
        
        sale_order = request.env['sale.order'].sudo().create(sale_vals)
        
        _logger.info('✅ Created sale.order: %s for partner: %s', 
                     sale_order.name, partner.name)
        
        # 3. Add order lines
        for product in conv.selected_product_ids:
            line_vals = {
                'order_id': sale_order.id,
                'product_id': product.product_id.id,
                'product_uom_qty': 1,
                'price_unit': product.price,
            }
            request.env['sale.order.line'].sudo().create(line_vals)
            
            _logger.info('  ➕ Added product: %s - %s đ', 
                        product.product_id.name, product.price)
        
        # 4. Add note to chatter
        sale_order.message_post(
            body='Đơn hàng tạo từ Facebook Messenger chatbot\n'
                 'Khách hàng: %s\n'
                 'SĐT: %s\n'
                 'PSID: %s' % (
                     conv.customer_name,
                     conv.customer_phone,
                     conv.facebook_user_id
                 ),
            subject='Facebook Messenger Order',
            message_type='comment',
            subtype_xmlid='mail.mt_note'
        )
        
        return sale_order
    
    def _find_or_create_partner(self, conv):
        """
        Tìm hoặc tạo res.partner từ conversation data
        
        Args:
            conv (social.message): Conversation record
        
        Returns:
            res.partner: Partner record
        """
        Partner = request.env['res.partner'].sudo()
        
        # Search by phone first
        if conv.customer_phone:
            partner = Partner.search([
                ('phone', '=', conv.customer_phone),
                ('company_id', 'in', [False, conv.company_id.id]),
            ], limit=1)
            
            if partner:
                _logger.info('✅ Found existing partner: %s (by phone)', partner.name)
                return partner
        
        # Create new partner
        partner_vals = {
            'name': conv.customer_name,
            'phone': conv.customer_phone,
            'company_id': conv.company_id.id,
            'comment': 'Created from Facebook Messenger chatbot\nPSID: %s' % conv.facebook_user_id,
        }
        
        # Add facebook_user_id if field exists
        if 'facebook_user_id' in Partner._fields:
            partner_vals['facebook_user_id'] = conv.facebook_user_id
        
        partner = Partner.create(partner_vals)
        
        _logger.info('✅ Created new partner: %s (ID: %s)', partner.name, partner.id)
        
        return partner
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _handle_product_selection(self, conv, product_id):
        """Xử lý khi user chọn sản phẩm"""
        try:
            product = request.env['social.messenger.product'].sudo().browse(product_id)
            
            if not product.exists():
                self._send_text(conv, "❌ Sản phẩm không tồn tại!")
                return
            
            # Update conversation with selected product
            conv.sudo().write({
                'selected_product_ids': [(6, 0, [product.id])],
                'chatbot_state': 'confirm_order'
            })
            
            # Format price
            price_text = "{:,.0f}đ".format(product.price) if product.price > 0 else "Liên hệ"
            
            # Send confirmation message
            confirm_msg = """✅ Bạn đã chọn:

📦 Sản phẩm: %s
🔢 Số lượng: 1
💰 Giá: %s

👤 Khách hàng: %s
📞 SĐT: %s

Xác nhận đặt hàng?

👉 Gửi "Có" để xác nhận
👉 Gửi "Không" để chọn lại""" % (
                product.product_id.name,
                price_text,
                conv.customer_name,
                conv.customer_phone
            )
            
            self._send_text(conv, confirm_msg)
            
        except Exception as e:
            _logger.error('❌ Product selection error: %s', e)
            self._send_text(conv, "Có lỗi xảy ra. Vui lòng thử lại!")
    
    def _send_text(self, conv, text):
        """
        Gửi tin nhắn text qua Facebook Send API
        
        Args:
            conv (social.message): Conversation record
            text (str): Message text
        
        Returns:
            bool: True if success
        """
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': conv.facebook_user_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': conv.account_id.access_token}
        
        try:
            resp = requests.post(url, json=payload, params=params, timeout=10)
            success = resp.status_code == 200
            
            if success:
                _logger.debug('✅ Message sent to %s', conv.facebook_user_id)
            else:
                _logger.error('❌ Send failed: %s', resp.text)
            
            return success
            
        except Exception as e:
            _logger.error('❌ Send error: %s', e)
            return False
    
    def _send_product_list(self, conv):
        """Gửi danh sách sản phẩm với quick reply buttons"""
        # Get active products
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', conv.company_id.id)
        ], order='sequence, id')
        
        if not products:
            self._send_text(conv, "Xin lỗi, hiện tại chưa có sản phẩm nào!")
            return
        
        # Build product list text
        product_list = "📦 Danh sách sản phẩm:\n\n"
        
        for idx, p in enumerate(products, 1):
            price = "{:,.0f}đ".format(p.price) if p.price > 0 else "Liên hệ"
            product_list += "%s. %s - %s\n" % (idx, p.product_id.name, price)
        
        product_list += "\n👇 Vui lòng chọn sản phẩm:"
        
        # Build quick reply buttons (max 11)
        quick_replies = []
        for p in products[:11]:
            quick_replies.append({
                'content_type': 'text',
                'title': p.quick_reply_title or p.product_id.name[:20],
                'payload': 'PRODUCT_%s' % p.id
            })
        
        # Send message with quick replies
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
            resp = requests.post(url, json=payload, params=params, timeout=10)
            if resp.status_code == 200:
                _logger.info('✅ Product list sent to %s', conv.facebook_user_id)
            else:
                _logger.error('❌ Failed to send product list: %s', resp.text)
        except Exception as e:
            _logger.error('❌ Error sending product list: %s', e)
    
    def _validate_order_data(self, conv):
        """
        Validate order data before creating sale order
        
        Returns:
            dict: {'valid': bool, 'errors': str}
        """
        errors = []
        
        if not conv.customer_name:
            errors.append("Thiếu tên khách hàng")
        
        if not conv.customer_phone:
            errors.append("Thiếu số điện thoại")
        
        if not conv.selected_product_ids:
            errors.append("Chưa chọn sản phẩm")
        
        return {
            'valid': len(errors) == 0,
            'errors': ', '.join(errors)
        }
    
    def _format_order_lines(self, sale_order):
        """Format order lines for display"""
        lines = []
        for line in sale_order.order_line:
            lines.append("  • %s x%s - %s đ" % (
                line.product_id.name,
                int(line.product_uom_qty),
                "{:,.0f}".format(line.price_unit)
            ))
        return "\n".join(lines)
    
    def _set_cooldown(self, conv):
        """Set cooldown period after order completion"""
        try:
            cooldown_until = datetime.now() + timedelta(minutes=5)
            conv.sudo().write({'cooldown_until': cooldown_until})
            _logger.info('⏰ Cooldown set until %s', cooldown_until)
        except Exception as e:
            _logger.error('❌ Failed to set cooldown: %s', e)
    
    def _is_in_cooldown(self, conv):
        """Check if conversation is in cooldown period"""
        if not hasattr(conv, 'cooldown_until'):
            return False
        
        if conv.cooldown_until and conv.cooldown_until > datetime.now():
            return True
        
        return False
    
    def _extract_product_id(self, payload):
        """Extract product ID from payload string"""
        try:
            return int(payload.replace('PRODUCT_', ''))
        except:
            return None
    
    def _find_or_create_conversation(self, sender_id, recipient_id):
        """
        Find or create conversation record
        
        Args:
            sender_id (str): Facebook user PSID
            recipient_id (str): Facebook page ID
        
        Returns:
            social.message: Conversation record or None
        """
        # Find account by page ID
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)
        ], limit=1)
        
        if not account:
            _logger.warning('❌ Account not found for page: %s', recipient_id)
            return None
        
        # Find existing conversation
        conv = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', sender_id),
            ('account_id', '=', account.id),
        ], limit=1)
        
        if conv:
            _logger.debug('✅ Found existing conversation: %s', conv.id)
            return conv
        
        # Create new conversation
        conv_vals = {
            'facebook_user_id': sender_id,
            'account_id': account.id,
            'company_id': account.company_id.id,
            'chatbot_state': 'idle',
        }
        
        try:
            conv = request.env['social.message'].sudo().create(conv_vals)
            _logger.info('✅ Created new conversation: %s', conv.id)
            return conv
        except Exception as e:
            _logger.error('❌ Failed to create conversation: %s', e)
            return None