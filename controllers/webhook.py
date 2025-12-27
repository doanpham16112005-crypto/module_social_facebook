import json
import logging
import requests
import re
from datetime import datetime, timedelta
from odoo import http, fields
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
    # CHATBOT FLOW
    # =========================================================================
    
    def _process_chatbot_flow(self, conversation, user_message):
        """Main chatbot flow dispatcher"""
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            return
        
        if self._is_in_cooldown(conversation):
            self._send_text(conversation, 
                "Cảm ơn bạn đã đặt hàng! Đơn hàng đang được xử lý.")
            return
        
        current_state = conversation.chatbot_state or 'idle'
        _logger.info('🤖 State: %s | Message: %s', current_state, user_message)
        
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
    
    def _state_idle(self, conv, msg):
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['mua', 'order', 'buy', 'menu']):
            conv.sudo().write({'chatbot_state': 'ask_name'})
            self._send_text(conv, "Xin chào! 👋\n\nBạn vui lòng cho biết tên của bạn?")
        else:
            self._send_text(conv, '👋 Gửi "mua" để xem sản phẩm!')
    
    def _state_ask_name(self, conv, msg):
        name = msg.strip()
        
        if len(name) < 2:
            self._send_text(conv, "Tên quá ngắn. Vui lòng nhập lại.")
            return
        
        name_normalized = ' '.join(word.capitalize() for word in name.split())
        
        conv.sudo().write({
            'customer_name': name_normalized,
            'chatbot_state': 'ask_phone'
        })
        
        welcome_msg = "Xin chào %s! 😊\n\nBạn vui lòng cung cấp số điện thoại?" % name_normalized
        self._send_text(conv, welcome_msg)
    
    def _state_ask_phone(self, conv, msg):
        phone = msg.strip()
        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)
        
        if phone_clean.startswith('+84'):
            phone_clean = '0' + phone_clean[3:]
        elif phone_clean.startswith('84'):
            phone_clean = '0' + phone_clean[2:]
        
        if not re.match(r'^0\d{9,10}$', phone_clean):
            self._send_text(conv, 
                "📱 Số điện thoại không hợp lệ!\n\nVui lòng nhập lại (VD: 0912345678)")
            return
        
        conv.sudo().write({
            'customer_phone': phone_clean,
            'chatbot_state': 'show_products'
        })
        
        self._send_product_list(conv)
    
    def _state_show_products(self, conv, msg):
        if msg.startswith('PRODUCT_'):
            product_id = self._extract_product_id(msg)
            if product_id:
                self._handle_product_selection(conv, product_id)
    
    def _state_confirm_order(self, conv, msg):
        """✅ XÁC NHẬN VÀ TẠO SALE ORDER VỚI PARTNER"""
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['có', 'yes', 'ok', 'đồng ý']):
            _logger.info('=' * 80)
            _logger.info('📝 CREATING ORDER WITH PARTNER')
            _logger.info('=' * 80)
            
            try:
                # STEP 1: Validate
                validation = self._validate_order_data(conv)
                if not validation['valid']:
                    self._send_text(conv, "❌ Dữ liệu không hợp lệ: %s" % validation['errors'])
                    return
                
                # STEP 2: Create/Find Partner (QUAN TRỌNG!)
                _logger.info('Creating partner: %s - %s', conv.customer_name, conv.customer_phone)
                
                partner = self._odoo_create_partner(
                    name=conv.customer_name,
                    phone=conv.customer_phone,
                    company_id=conv.company_id.id
                )
                
                _logger.info('✅ Partner created/found: %s (ID: %s)', partner.name, partner.id)
                
                # STEP 3: Create Sale Order WITH partner_id
                _logger.info('Creating sale order with partner_id=%s', partner.id)
                
                sale_order = self._odoo_create_sale_order(
                    partner_id=partner.id,
                    company_id=conv.company_id.id,
                    origin='Facebook Messenger - %s' % conv.facebook_user_id,
                    note='Đơn từ Messenger\nKhách: %s\nSĐT: %s' % (
                        conv.customer_name, conv.customer_phone
                    )
                )
                
                _logger.info('✅ Sale order created: %s', sale_order.name)
                _logger.info('  Partner: %s', sale_order.partner_id.name)
                
                # STEP 4: Add order lines
                for product in conv.selected_product_ids:
                    self._odoo_add_order_line(
                        order_id=sale_order.id,
                        product_id=product.product_id.id,
                        quantity=1,
                        price=product.price
                    )
                
                # STEP 5: Send success message
                success_msg = """🎉 Đặt hàng thành công!

📝 Mã đơn hàng: %s
💰 Tổng tiền: %s đ

📦 Sản phẩm:
%s

👤 Khách hàng: %s
📞 SĐT: %s

✅ Đơn hàng đã được ghi nhận!
Chúng tôi sẽ liên hệ xác nhận sớm nhất.

Cảm ơn bạn! 🙏""" % (
                    sale_order.name,
                    "{:,.0f}".format(sale_order.amount_total),
                    self._format_order_lines(sale_order),
                    conv.customer_name,
                    conv.customer_phone
                )
                
                self._send_text(conv, success_msg)
                
                conv.sudo().write({'chatbot_state': 'completed'})
                self._set_cooldown(conv)
                
                _logger.info('=' * 80)
                _logger.info('✅✅✅ ORDER COMPLETED ✅✅✅')
                _logger.info('=' * 80)
                
            except Exception as e:
                import traceback
                _logger.error('❌ ORDER FAILED: %s', str(e))
                _logger.error(traceback.format_exc())
                
                conv.sudo().write({'chatbot_state': 'idle'})
                self._send_text(conv, "❌ Có lỗi xảy ra. Vui lòng thử lại!")
        
        elif any(kw in msg_lower for kw in ['không', 'no']):
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)]
            })
            self._send_text(conv, "Đã hủy. Chọn lại!")
            self._send_product_list(conv)
        else:
            self._send_text(conv, 'Vui lòng gửi "Có" hoặc "Không"')
    
    def _state_completed(self, conv, msg):
        if self._is_in_cooldown(conv):
            self._send_text(conv, "Đơn hàng đang xử lý...")
        else:
            conv.sudo().write({'chatbot_state': 'idle'})
            self._state_idle(conv, msg)
    
    # =========================================================================
    # ✅✅✅ ODOO INTEGRATION METHODS (GIỐNG app.py) ✅✅✅
    # =========================================================================
    
    def _odoo_create_partner(self, name, phone, company_id):
        """
        ✅ TẠO PARTNER (tương tự app.py nhưng dùng ORM thay vì JSON-RPC)
        
        Returns:
            res.partner: Partner record
        """
        Partner = request.env['res.partner'].sudo()
        
        # 1. TÌM PARTNER THEO SĐT
        partner = Partner.search([
            ('phone', '=', phone),
            '|',
            ('company_id', '=', False),
            ('company_id', '=', company_id),
        ], limit=1)
        
        if partner:
            _logger.info('Found existing partner: %s', partner.name)
            
            # Ensure Facebook tag
            self._ensure_facebook_tag(partner)
            
            return partner
        
        # 2. TẠO PARTNER MỚI (giống contact_data trong app.py)
        _logger.info('Creating new partner: %s', name)
        
        facebook_tag = self._get_or_create_facebook_tag()
        
        partner_data = {
            'name': name,           # Giống app.py
            'phone': phone,         # Giống app.py
            'company_id': company_id,
            'company_type': 'person',  # ✅ QUAN TRỌNG
            'category_id': [(6, 0, [facebook_tag.id])],  # ✅ TAG FACEBOOK
        }
        
        partner = Partner.create(partner_data)
        
        # ✅ CRITICAL: COMMIT
        request.env.cr.commit()
        
        _logger.info('✅ Partner created: %s (ID: %s)', partner.name, partner.id)
        
        return partner
    
    def _odoo_create_sale_order(self, partner_id, company_id, origin, note):
        """
        ✅ TẠO SALE ORDER với partner_id
        
        Returns:
            sale.order: Sale order record
        """
        SaleOrder = request.env['sale.order'].sudo()
        
        order_data = {
            'partner_id': partner_id,  # ✅✅✅ QUAN TRỌNG NHẤT
            'company_id': company_id,
            'date_order': fields.Datetime.now(),
            'origin': origin,
            'note': note,
        }
        
        # Get default salesperson
        default_user_id = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.lead_default_user_id'
        )
        if default_user_id:
            try:
                order_data['user_id'] = int(default_user_id)
            except:
                pass
        
        order = SaleOrder.create(order_data)
        
        # ✅ COMMIT
        request.env.cr.commit()
        
        return order
    
    def _odoo_add_order_line(self, order_id, product_id, quantity, price):
        """
        ✅ THÊM ORDER LINE
        """
        OrderLine = request.env['sale.order.line'].sudo()
        
        line_data = {
            'order_id': order_id,
            'product_id': product_id,
            'product_uom_qty': quantity,
            'price_unit': price,
        }
        
        line = OrderLine.create(line_data)
        
        # ✅ COMMIT
        request.env.cr.commit()
        
        return line
    
    def _get_or_create_facebook_tag(self):
        """Get or create Facebook tag"""
        Tag = request.env['res.partner.category'].sudo()
        
        tag = Tag.search([('name', '=ilike', 'Facebook')], limit=1)
        
        if tag:
            return tag
        
        tag = Tag.create({'name': 'Facebook', 'color': 1})
        request.env.cr.commit()
        
        _logger.info('Created Facebook tag')
        
        return tag
    
    def _ensure_facebook_tag(self, partner):
        """Ensure partner has Facebook tag"""
        facebook_tag = self._get_or_create_facebook_tag()
        
        if facebook_tag in partner.category_id:
            return
        
        partner.write({
            'category_id': [(4, facebook_tag.id)]
        })
        
        request.env.cr.commit()
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _handle_product_selection(self, conv, product_id):
        try:
            product = request.env['social.messenger.product'].sudo().browse(product_id)
            
            if not product.exists():
                self._send_text(conv, "❌ Sản phẩm không tồn tại!")
                return
            
            conv.sudo().write({
                'selected_product_ids': [(6, 0, [product.id])],
                'chatbot_state': 'confirm_order'
            })
            
            price_text = "{:,.0f}đ".format(product.price) if product.price > 0 else "Liên hệ"
            
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
    
    def _send_text(self, conv, text):
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': conv.facebook_user_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': conv.account_id.access_token}
        
        try:
            resp = requests.post(url, json=payload, params=params, timeout=10)
            return resp.status_code == 200
        except:
            return False
    
    def _send_product_list(self, conv):
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', conv.company_id.id)
        ], order='sequence, id')
        
        if not products:
            self._send_text(conv, "Xin lỗi, chưa có sản phẩm!")
            return
        
        product_list = "📦 Danh sách sản phẩm:\n\n"
        
        for idx, p in enumerate(products, 1):
            price = "{:,.0f}đ".format(p.price) if p.price > 0 else "Liên hệ"
            product_list += "%s. %s - %s\n" % (idx, p.product_id.name, price)
        
        product_list += "\n👇 Vui lòng chọn sản phẩm:"
        
        quick_replies = []
        for p in products[:11]:
            quick_replies.append({
                'content_type': 'text',
                'title': p.quick_reply_title or p.product_id.name[:20],
                'payload': 'PRODUCT_%s' % p.id
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
            requests.post(url, json=payload, params=params, timeout=10)
        except:
            pass
    
    def _validate_order_data(self, conv):
        errors = []
        
        if not conv.customer_name:
            errors.append("Thiếu tên")
        if not conv.customer_phone:
            errors.append("Thiếu SĐT")
        if not conv.selected_product_ids:
            errors.append("Chưa chọn SP")
        
        return {
            'valid': len(errors) == 0,
            'errors': ', '.join(errors)
        }
    
    def _format_order_lines(self, sale_order):
        lines = []
        for line in sale_order.order_line:
            lines.append("  • %s x%s - %s đ" % (
                line.product_id.name,
                int(line.product_uom_qty),
                "{:,.0f}".format(line.price_unit)
            ))
        return "\n".join(lines)
    
    def _set_cooldown(self, conv):
        try:
            cooldown_until = datetime.now() + timedelta(minutes=5)
            conv.sudo().write({'cooldown_until': cooldown_until})
        except:
            pass
    
    def _is_in_cooldown(self, conv):
        if not hasattr(conv, 'cooldown_until'):
            return False
        return conv.cooldown_until and conv.cooldown_until > datetime.now()
    
    def _extract_product_id(self, payload):
        try:
            return int(payload.replace('PRODUCT_', ''))
        except:
            return None
    
    def _find_or_create_conversation(self, sender_id, recipient_id):
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)
        ], limit=1)
        
        if not account:
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
            request.env.cr.commit()
            return conv
        except:
            return None