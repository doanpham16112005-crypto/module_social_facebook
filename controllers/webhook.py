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
        if 'messaging' in entry:
            for event in entry['messaging']:
                self._process_messaging_event(event)
    
    def _process_messaging_event(self, event):
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
    # CHATBOT FLOW - UPGRADED
    # =========================================================================
    
    def _process_chatbot_flow(self, conversation, user_message):
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
        
        # ✅ ROUTING MỚI
        if current_state == 'idle':
            self._state_idle(conversation, user_message)
        elif current_state == 'ask_name':
            self._state_ask_name(conversation, user_message)
        elif current_state == 'ask_phone':
            self._state_ask_phone(conversation, user_message)
        elif current_state == 'ask_address':  # ✅ MỚI
            self._state_ask_address(conversation, user_message)
        elif current_state == 'show_products':
            self._state_show_products(conversation, user_message)
        elif current_state == 'ask_quantity':  # ✅ MỚI
            self._state_ask_quantity(conversation, user_message)
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
            'chatbot_state': 'ask_address'  # ✅ ĐỔI STATE
        })
        
        # ✅ HỎI ĐỊA CHỈ
        self._send_text(conv, "📍 Bạn vui lòng cung cấp địa chỉ giao hàng?")
    
    # ✅ STATE MỚI: ASK_ADDRESS
    def _state_ask_address(self, conv, msg):
        """Hỏi địa chỉ khách hàng"""
        address = msg.strip()
        
        if len(address) < 5:
            self._send_text(conv, "Địa chỉ quá ngắn. Vui lòng nhập đầy đủ địa chỉ!")
            return
        
        conv.sudo().write({
            'customer_address': address,
            'chatbot_state': 'show_products'
        })
        
        # Hiển thị sản phẩm
        self._send_product_list(conv)
    
    def _state_show_products(self, conv, msg):
        if msg.startswith('PRODUCT_'):
            product_id = self._extract_product_id(msg)
            if product_id:
                self._handle_product_selection(conv, product_id)
    
    # ✅ STATE MỚI: ASK_QUANTITY
    def _state_ask_quantity(self, conv, msg):
        """Hỏi số lượng sản phẩm"""
        try:
            quantity = int(msg.strip())
            
            if quantity < 1:
                self._send_text(conv, "❌ Số lượng phải >= 1. Vui lòng nhập lại!")
                return
            
            if quantity > 999:
                self._send_text(conv, "❌ Số lượng quá lớn (max 999). Vui lòng nhập lại!")
                return
            
            # Lưu số lượng
            conv.sudo().write({
                'product_quantity': quantity,
                'chatbot_state': 'confirm_order'
            })
            
            # Hiển thị xác nhận
            product = conv.selected_product_ids[0]  # Lấy sản phẩm đã chọn
            price_unit = product.price
            total = price_unit * quantity
            
            confirm_msg = """✅ Xác nhận đơn hàng:

📦 Sản phẩm: %s
🔢 Số lượng: %d
💰 Đơn giá: %s đ
💵 Tổng tiền: %s đ

👤 Khách hàng: %s
📞 SĐT: %s
📍 Địa chỉ: %s

Xác nhận đặt hàng?
👉 "Có" / "Không" """ % (
                product.product_id.name,
                quantity,
                "{:,.0f}".format(price_unit),
                "{:,.0f}".format(total),
                conv.customer_name,
                conv.customer_phone,
                conv.customer_address or 'Chưa có'
            )
            
            self._send_text(conv, confirm_msg)
            
        except ValueError:
            self._send_text(conv, "❌ Vui lòng nhập số lượng hợp lệ (ví dụ: 1, 2, 5...)")
    
    def _state_confirm_order(self, conv, msg):
        """✅ XÁC NHẬN VÀ TẠO ORDER + CRM LEAD"""
        msg_lower = msg.lower().strip()
        
        if any(kw in msg_lower for kw in ['có', 'yes', 'ok', 'đồng ý']):
            
            try:
                # Validate
                validation = self._validate_order_data(conv)
                if not validation['valid']:
                    self._send_text(conv, "❌ Dữ liệu không hợp lệ: %s" % validation['errors'])
                    return
                
                # ✅ TẠO PARTNER
                Partner = request.env['res.partner'].with_context(tracking_disable=True).sudo()
                
                partner = Partner.search([
                    ('phone', '=', conv.customer_phone),
                ], limit=1)
                
                if not partner:
                    # Get Facebook tag
                    Tag = request.env['res.partner.category'].sudo()
                    facebook_tag = Tag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
                    if not facebook_tag:
                        facebook_tag = Tag.create({'name': 'Facebook-Messenger', 'color': 4})
                    
                    # ✅ CREATE PARTNER VỚI ĐỊA CHỈ
                    partner = Partner.create({
                        'name': conv.customer_name,
                        'phone': conv.customer_phone,
                        'street': conv.customer_address,  # ✅ ĐỊA CHỈ
                        'company_type': 'person',
                        'category_id': [(6, 0, [facebook_tag.id])],
                    })
                else:
                    # ✅ CẬP NHẬT ĐỊA CHỈ NẾU CHƯA CÓ
                    if not partner.street and conv.customer_address:
                        partner.write({'street': conv.customer_address})
                
                # ✅ TẠO SALE ORDER
                SaleOrder = request.env['sale.order'].with_context(tracking_disable=True).sudo()
                
                order = SaleOrder.create({
                    'partner_id': partner.id,
                    'date_order': fields.Datetime.now(),
                })
                
                # ✅ THÊM PRODUCTS VỚI SỐ LƯỢNG
                OrderLine = request.env['sale.order.line'].with_context(tracking_disable=True).sudo()
                
                quantity = conv.product_quantity or 1
                
                for product in conv.selected_product_ids:
                    OrderLine.create({
                        'order_id': order.id,
                        'product_id': product.product_id.id,
                        'product_uom_qty': quantity,  # ✅ SỐ LƯỢNG
                        'price_unit': product.price,
                    })
                
                # ✅✅✅ TẠO CRM LEAD ✅✅✅
                self._create_crm_lead(conv, partner, order)
                
                # ✅ SUCCESS MESSAGE
                success_msg = """🎉 Đặt hàng thành công!

📝 Mã đơn hàng: %s
👤 Khách hàng: %s
📞 SĐT: %s
📍 Địa chỉ: %s
💰 Tổng tiền: %s đ

✅ Đơn hàng đã được ghi nhận!
✅ Thông tin đã được lưu vào hệ thống CRM!
Cảm ơn bạn! 🙏""" % (
                    order.name,
                    conv.customer_name,
                    conv.customer_phone,
                    conv.customer_address or 'Chưa cập nhật',
                    "{:,.0f}".format(order.amount_total)
                )
                
                self._send_text(conv, success_msg)
                
                conv.sudo().write({'chatbot_state': 'completed'})
                self._set_cooldown(conv)
                
            except Exception as e:
                import traceback
                _logger.error('❌ ORDER FAILED: %s', str(e))
                _logger.error(traceback.format_exc())
                
                conv.sudo().write({'chatbot_state': 'idle'})
                self._send_text(conv, "❌ Có lỗi xảy ra. Vui lòng thử lại!")
        
        elif any(kw in msg_lower for kw in ['không', 'no']):
            conv.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)],
                'product_quantity': 0,
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
    # ✅ HELPER: TẠO CRM LEAD
    # =========================================================================
    
    def _create_crm_lead(self, conv, partner, order):
        """
        Tạo CRM Lead từ order Messenger.
        
        Args:
            conv: Conversation record
            partner: res.partner record
            order: sale.order record
        """
        try:
            Lead = request.env['crm.lead'].with_context(tracking_disable=True).sudo()
            
            # Get Facebook-Messenger tag
            LeadTag = request.env['crm.tag'].sudo()
            fb_tag = LeadTag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
            if not fb_tag:
                fb_tag = LeadTag.create({
                    'name': 'Facebook-Messenger',
                    'color': 4,
                })
            
            # ✅ TẠO LEAD
            lead = Lead.create({
                'name': 'FB Lead - %s' % partner.name,
                'type': 'opportunity',
                'partner_id': partner.id,  # ✅ CONTACT
                'contact_name': partner.name,
                'phone': partner.phone,
                'street': partner.street,
                'expected_revenue': order.amount_total,  # ✅ EXPECTED REVENUE
                'tag_ids': [(6, 0, [fb_tag.id])],  # ✅ TAG
                'description': (
                    'Lead tạo từ Facebook Messenger Chatbot\n'
                    'PSID: %s\n'
                    'Đơn hàng: %s\n'
                    'Tổng tiền: %s đ'
                ) % (
                    conv.facebook_user_id,
                    order.name,
                    "{:,.0f}".format(order.amount_total)
                ),
            })
            
            _logger.info('✅ Created CRM Lead: %s (ID: %s)', lead.name, lead.id)
            
            # Gắn lead vào conversation
            conv.sudo().write({'lead_id': lead.id})
            
        except Exception as e:
            _logger.error('❌ Failed to create CRM Lead: %s', e)
    
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
                'chatbot_state': 'ask_quantity'  # ✅ ĐỔI STATE
            })
            
            # ✅ HỎI SỐ LƯỢNG
            ask_qty_msg = """✅ Bạn đã chọn: %s

🔢 Bạn muốn mua bao nhiêu?
👉 Vui lòng nhập số lượng (VD: 1, 2, 5...)""" % product.product_id.name
            
            self._send_text(conv, ask_qty_msg)
            
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
        
        product_list += "\n👇 Chọn sản phẩm:"
        
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
        if not conv.customer_address:
            errors.append("Thiếu địa chỉ")
        if not conv.selected_product_ids:
            errors.append("Chưa chọn SP")
        if not hasattr(conv, 'product_quantity') or not conv.product_quantity:
            errors.append("Thiếu số lượng")
        
        return {
            'valid': len(errors) == 0,
            'errors': ', '.join(errors)
        }
    
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
            return request.env['social.message'].sudo().create(conv_vals)
        except:
            return None