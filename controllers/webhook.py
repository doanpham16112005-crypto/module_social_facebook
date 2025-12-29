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
        """
        ✅ FIX CRITICAL: Reset state NGAY từ đầu
        """
        sender_id = event.get('sender', {}).get('id')
        recipient_id = event.get('recipient', {}).get('id')
        
        if not sender_id or not recipient_id:
            return
        
        msg = self._find_or_create_message_record(sender_id, recipient_id)
        if not msg:
            return
        
        if 'message' in event:
            message_data = event['message']
            
            if message_data.get('is_echo'):
                return
            
            # ✅ FIX CRITICAL: Reset state completed TRƯỚC KHI xử lý
            if msg.chatbot_state == 'completed':
                msg.sudo().write({
                    'chatbot_state': 'idle',
                    'cooldown_until': False,
                    'selected_product_ids': [(5, 0, 0)],
                    'product_quantity': 0,
                    'customer_name': False,
                    'customer_phone': False,
                    'customer_address': False,
                })
                _logger.info(f"✅ Reset completed → idle for PSID: {sender_id}")
            
            # Process message
            if 'quick_reply' in message_data:
                payload = message_data['quick_reply'].get('payload', '')
                self._process_chatbot_flow(msg, payload)
            else:
                text = message_data.get('text', '')
                self._process_chatbot_flow(msg, text)
    
    def _find_or_create_message_record(self, sender_id, recipient_id):
        """Tìm/tạo message record"""
        account = request.env['social.account'].sudo().search([
            ('facebook_page_id', '=', recipient_id)
        ], limit=1)
        
        if not account:
            return None
        
        msg = request.env['social.message'].sudo().search([
            ('facebook_user_id', '=', sender_id),
            ('account_id', '=', account.id),
        ], limit=1)
        
        if msg:
            return msg
        
        try:
            return request.env['social.message'].sudo().create({
                'facebook_user_id': sender_id,
                'account_id': account.id,
                'company_id': account.company_id.id,
                'chatbot_state': 'idle',
            })
        except:
            return None
    
    def _find_existing_customer(self, psid):
        """Tìm customer có 2 tag"""
        try:
            Partner = request.env['res.partner'].sudo()
            Tag = request.env['res.partner.category'].sudo()
            
            psid_tag = Tag.search([('name', '=', f"facebook_psid:{psid}")], limit=1)
            if not psid_tag:
                return None
            
            fb_tag = Tag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
            if not fb_tag:
                return None
            
            partners = Partner.search([
                ('category_id', 'in', [psid_tag.id, fb_tag.id]),
            ])
            
            for partner in partners:
                if psid_tag.id in partner.category_id.ids and fb_tag.id in partner.category_id.ids:
                    return partner
            
            return None
        except:
            return None
    
    def _get_or_create_psid_tag(self, psid):
        Tag = request.env['res.partner.category'].sudo()
        tag = Tag.search([('name', '=', f"facebook_psid:{psid}")], limit=1)
        if not tag:
            tag = Tag.create({'name': f"facebook_psid:{psid}", 'color': 5})
        return tag
    
    def _get_or_create_fb_messenger_tag(self):
        Tag = request.env['res.partner.category'].sudo()
        tag = Tag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
        if not tag:
            tag = Tag.create({'name': 'Facebook-Messenger', 'color': 4})
        return tag
    
    def _process_chatbot_flow(self, msg, user_message):
        """Process chatbot flow"""
        chatbot_enabled = request.env['ir.config_parameter'].sudo().get_param(
            'module_social_facebook.chatbot_enabled', 'False'
        )
        
        if chatbot_enabled != 'True':
            return
        
        state = msg.chatbot_state or 'idle'
        
        # ✅ FIX: Không còn state completed nữa - đã reset ở trên
        if state == 'idle':
            self._state_idle(msg, user_message)
        elif state == 'ask_update':
            self._state_ask_update(msg, user_message)
        elif state == 'ask_name':
            self._state_ask_name(msg, user_message)
        elif state == 'ask_phone':
            self._state_ask_phone(msg, user_message)
        elif state == 'ask_address':
            self._state_ask_address(msg, user_message)
        elif state == 'show_products':
            self._state_show_products(msg, user_message)
        elif state == 'ask_quantity':
            self._state_ask_quantity(msg, user_message)
        elif state == 'confirm_order':
            self._state_confirm_order(msg, user_message)
    
    def _state_idle(self, msg, text):
        """State: idle"""
        text_lower = text.lower().strip()
        
        if any(kw in text_lower for kw in ['mua', 'order', 'buy', 'menu', 'sản phẩm']):
            customer = self._find_existing_customer(msg.facebook_user_id)
            
            if customer:
                msg.sudo().write({
                    'chatbot_state': 'ask_update',
                    'customer_name': customer.name,
                    'customer_phone': customer.phone,
                    'customer_address': customer.street,
                })
                
                self._send_text(msg, f"""👋 Xin chào {customer.name}!

📞 SĐT: {customer.phone or 'Chưa có'}
📍 Địa chỉ: {customer.street or 'Chưa có'}

Bạn có muốn cập nhật thông tin không?
👉 Gửi "Có" để cập nhật
👉 Gửi "Không" để tiếp tục mua hàng""")
            else:
                msg.sudo().write({'chatbot_state': 'ask_name'})
                
                welcome_msg = request.env['ir.config_parameter'].sudo().get_param(
                    'module_social_facebook.chatbot_welcome_message',
                    'Xin chào! 👋\n\nBạn vui lòng cho biết tên của bạn?'
                )
                
                self._send_text(msg, welcome_msg)
        else:
            self._send_text(msg, '👋 Gửi "mua" để xem sản phẩm!')
    
    def _state_ask_update(self, msg, text):
        """State: ask_update"""
        text_lower = text.lower().strip()
        
        if any(kw in text_lower for kw in ['có', 'yes', 'ok', 'update', 'cập nhật']):
            msg.sudo().write({'chatbot_state': 'ask_name'})
            self._send_text(msg, "Bạn muốn cập nhật tên mới?\n(hoặc gửi '.' để giữ nguyên)")
        elif any(kw in text_lower for kw in ['không', 'no', 'skip', 'bỏ qua']):
            msg.sudo().write({'chatbot_state': 'show_products'})
            self._send_product_list(msg)
        else:
            self._send_text(msg, '❓ Vui lòng gửi "Có" hoặc "Không"')
    
    def _state_ask_name(self, msg, text):
        """State: ask_name"""
        name = text.strip()
        
        if name == '.':
            if msg.customer_name:
                msg.sudo().write({'chatbot_state': 'ask_phone'})
                self._send_text(msg, "✅ Giữ nguyên tên.\n\nBạn muốn cập nhật SĐT?\n(hoặc gửi '.' để giữ nguyên)")
                return
            else:
                self._send_text(msg, "❌ Bạn chưa có tên. Vui lòng nhập tên!")
                return
        
        if len(name) < 2:
            self._send_text(msg, "❌ Tên quá ngắn. Vui lòng nhập lại.")
            return
        
        name_normalized = ' '.join(word.capitalize() for word in name.split())
        
        msg.sudo().write({
            'customer_name': name_normalized,
            'chatbot_state': 'ask_phone'
        })
        
        self._send_text(msg, f"✅ Xin chào {name_normalized}! 😊\n\nBạn vui lòng cung cấp số điện thoại?\n(hoặc gửi '.' để giữ nguyên)")
    
    def _state_ask_phone(self, msg, text):
        """State: ask_phone"""
        phone = text.strip()
        
        if phone == '.':
            if msg.customer_phone:
                msg.sudo().write({'chatbot_state': 'ask_address'})
                self._send_text(msg, "✅ Giữ nguyên SĐT.\n\nBạn muốn cập nhật địa chỉ?\n(hoặc gửi '.' để giữ nguyên)")
                return
            else:
                self._send_text(msg, "❌ Bạn chưa có SĐT. Vui lòng nhập SĐT!")
                return
        
        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)
        
        if phone_clean.startswith('+84'):
            phone_clean = '0' + phone_clean[3:]
        elif phone_clean.startswith('84'):
            phone_clean = '0' + phone_clean[2:]
        
        if not re.match(r'^0\d{9,10}$', phone_clean):
            self._send_text(msg, "📱 Số điện thoại không hợp lệ!\n\nVui lòng nhập lại (VD: 0912345678)")
            return
        
        msg.sudo().write({
            'customer_phone': phone_clean,
            'chatbot_state': 'ask_address'
        })
        
        self._send_text(msg, "📍 Bạn vui lòng cung cấp địa chỉ giao hàng?\n(hoặc gửi '.' để giữ nguyên)")
    
    def _state_ask_address(self, msg, text):
        """State: ask_address"""
        address = text.strip()
        
        if address == '.':
            if msg.customer_address:
                msg.sudo().write({'chatbot_state': 'show_products'})
                self._send_text(msg, "✅ Giữ nguyên địa chỉ.")
                self._send_product_list(msg)
                return
            else:
                self._send_text(msg, "❌ Bạn chưa có địa chỉ. Vui lòng nhập địa chỉ!")
                return
        
        if len(address) < 5:
            self._send_text(msg, "❌ Địa chỉ quá ngắn. Vui lòng nhập đầy đủ địa chỉ!")
            return
        
        msg.sudo().write({
            'customer_address': address,
            'chatbot_state': 'show_products'
        })
        
        self._send_product_list(msg)
    
    def _state_show_products(self, msg, text):
        """State: show_products"""
        if text.startswith('PRODUCT_'):
            product_id = self._extract_product_id(text)
            if product_id:
                self._handle_product_selection(msg, product_id)
    
    def _state_ask_quantity(self, msg, text):
        """State: ask_quantity"""
        try:
            quantity = int(text.strip())
            
            if quantity < 1:
                self._send_text(msg, "❌ Số lượng phải >= 1. Vui lòng nhập lại!")
                return
            
            if quantity > 999:
                self._send_text(msg, "❌ Số lượng quá lớn (max 999). Vui lòng nhập lại!")
                return
            
            msg.sudo().write({
                'product_quantity': quantity,
                'chatbot_state': 'confirm_order'
            })
            
            product = msg.selected_product_ids[0]
            price_unit = product.price
            total = price_unit * quantity
            
            self._send_text(msg, f"""✅ Xác nhận đơn hàng:

📦 Sản phẩm: {product.product_id.name}
🔢 Số lượng: {quantity}
💰 Đơn giá: {price_unit:,.0f} đ
💵 Tổng tiền: {total:,.0f} đ

👤 Khách hàng: {msg.customer_name}
📞 SĐT: {msg.customer_phone}
📍 Địa chỉ: {msg.customer_address or 'Chưa có'}

Xác nhận đặt hàng?
👉 "Có" / "Không" """)
            
        except ValueError:
            self._send_text(msg, "❌ Vui lòng nhập số lượng hợp lệ (ví dụ: 1, 2, 5...)")
    
    def _state_confirm_order(self, msg, text):
        """
        ✅ FIX CRITICAL: Reset về idle SAU KHI order thành công
        """
        text_lower = text.lower().strip()
        
        if any(kw in text_lower for kw in ['có', 'yes', 'ok', 'đồng ý', 'xác nhận']):
            try:
                validation = self._validate_order_data(msg)
                if not validation['valid']:
                    self._send_text(msg, f"❌ Dữ liệu không hợp lệ: {validation['errors']}")
                    return
                
                partner = self._find_or_create_partner_with_tags(msg)
                order = self._create_sale_order(msg, partner)
                lead = self._create_or_update_crm_lead(msg, partner, order)
                
                self._send_text(msg, f"""🎉 Đặt hàng thành công!

📝 Mã đơn hàng: {order.name}
👤 Khách hàng: {msg.customer_name}
📞 SĐT: {msg.customer_phone}
📍 Địa chỉ: {msg.customer_address or 'Chưa cập nhật'}
💰 Tổng tiền: {order.amount_total:,.0f} đ

✅ Đơn hàng đã được ghi nhận!
✅ Thông tin đã được lưu vào hệ thống CRM!

Cảm ơn bạn! 🙏

👉 Gửi "mua" để tiếp tục đặt hàng""")
                
                # ✅ FIX CRITICAL: Reset HOÀN TOÀN về idle
                msg.sudo().write({
                    'chatbot_state': 'idle',
                    'cooldown_until': False,
                    'selected_product_ids': [(5, 0, 0)],
                    'product_quantity': 0,
                })
                
                _logger.info(f"✅ Order success - Reset to idle for PSID: {msg.facebook_user_id}")
                
            except Exception as e:
                _logger.error(f'Order failed: {e}')
                msg.sudo().write({'chatbot_state': 'idle'})
                self._send_text(msg, "❌ Có lỗi xảy ra khi tạo đơn hàng. Vui lòng thử lại!")
        
        elif any(kw in text_lower for kw in ['không', 'no', 'hủy']):
            msg.sudo().write({
                'chatbot_state': 'show_products',
                'selected_product_ids': [(5, 0, 0)],
                'product_quantity': 0,
            })
            self._send_text(msg, "❌ Đã hủy. Bạn có thể chọn lại sản phẩm!")
            self._send_product_list(msg)
        else:
            self._send_text(msg, '❓ Vui lòng gửi "Có" hoặc "Không"')
    
    def _find_or_create_partner_with_tags(self, msg):
        """Tạo/cập nhật partner"""
        Partner = request.env['res.partner'].with_context(tracking_disable=True).sudo()
        
        existing = self._find_existing_customer(msg.facebook_user_id)
        
        if existing:
            update_vals = {}
            if msg.customer_name and existing.name != msg.customer_name:
                update_vals['name'] = msg.customer_name
            if msg.customer_phone and existing.phone != msg.customer_phone:
                update_vals['phone'] = msg.customer_phone
            if msg.customer_address and existing.street != msg.customer_address:
                update_vals['street'] = msg.customer_address
            
            if update_vals:
                existing.write(update_vals)
            
            return existing
        else:
            fb_tag = self._get_or_create_fb_messenger_tag()
            psid_tag = self._get_or_create_psid_tag(msg.facebook_user_id)
            
            return Partner.create({
                'name': msg.customer_name,
                'phone': msg.customer_phone,
                'street': msg.customer_address,
                'company_type': 'person',
                'category_id': [(6, 0, [fb_tag.id, psid_tag.id])],
            })
    
    def _create_sale_order(self, msg, partner):
        """Tạo sale order"""
        SaleOrder = request.env['sale.order'].with_context(tracking_disable=True).sudo()
        OrderLine = request.env['sale.order.line'].with_context(tracking_disable=True).sudo()
        
        order = SaleOrder.create({
            'partner_id': partner.id,
            'date_order': fields.Datetime.now(),
        })
        
        quantity = msg.product_quantity or 1
        
        for product in msg.selected_product_ids:
            OrderLine.create({
                'order_id': order.id,
                'product_id': product.product_id.id,
                'product_uom_qty': quantity,
                'price_unit': product.price,
            })
        
        return order
    
    def _create_or_update_crm_lead(self, msg, partner, order):
        """Tạo/cập nhật CRM Lead"""
        try:
            Lead = request.env['crm.lead'].with_context(tracking_disable=True).sudo()
            LeadTag = request.env['crm.tag'].sudo()
            
            fb_tag = LeadTag.search([('name', '=ilike', 'Facebook-Messenger')], limit=1)
            if not fb_tag:
                fb_tag = LeadTag.create({'name': 'Facebook-Messenger', 'color': 4})
            
            psid_tag = LeadTag.search([('name', '=', f"facebook_psid:{msg.facebook_user_id}")], limit=1)
            if not psid_tag:
                psid_tag = LeadTag.create({'name': f"facebook_psid:{msg.facebook_user_id}", 'color': 5})
            
            existing_lead = Lead.search([
                ('tag_ids', 'in', [psid_tag.id]),
                ('partner_id', '=', partner.id),
            ], limit=1)
            
            if existing_lead:
                old_revenue = existing_lead.expected_revenue or 0
                new_revenue = old_revenue + order.amount_total
                
                existing_lead.write({
                    'expected_revenue': new_revenue,
                    'description': (existing_lead.description or '') + f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆕 ĐƠN HÀNG MỚI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Mã đơn: {order.name}
📅 Ngày: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
💰 Giá trị đơn: {order.amount_total:,.0f} đ
💵 Tổng tích lũy: {new_revenue:,.0f} đ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                })
                
                msg.sudo().write({'lead_id': existing_lead.id})
                return existing_lead
            else:
                lead = Lead.create({
                    'name': f'FB Lead - {partner.name}',
                    'type': 'opportunity',
                    'partner_id': partner.id,
                    'contact_name': partner.name,
                    'phone': partner.phone,
                    'street': partner.street,
                    'expected_revenue': order.amount_total,
                    'tag_ids': [(6, 0, [fb_tag.id, psid_tag.id])],
                    'description': f"""Lead tạo từ Facebook Messenger Chatbot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 THÔNG TIN KHÁCH HÀNG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 Tên: {partner.name}
📞 SĐT: {partner.phone}
📍 Địa chỉ: {partner.street or 'Chưa có'}
🔑 PSID: {msg.facebook_user_id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 ĐƠN HÀNG ĐẦU TIÊN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Mã đơn: {order.name}
💰 Tổng tiền: {order.amount_total:,.0f} đ
📅 Ngày tạo: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
                })
                
                msg.sudo().write({'lead_id': lead.id})
                return lead
        except:
            return None
    
    def _handle_product_selection(self, msg, product_id):
        """Handle product selection"""
        try:
            product = request.env['social.messenger.product'].sudo().browse(product_id)
            
            if not product.exists():
                self._send_text(msg, "❌ Sản phẩm không tồn tại!")
                return
            
            msg.sudo().write({
                'selected_product_ids': [(6, 0, [product.id])],
                'chatbot_state': 'ask_quantity'
            })
            
            self._send_text(msg, f"""✅ Bạn đã chọn: {product.product_id.name}

💰 Giá: {product.price:,.0f} đ

🔢 Bạn muốn mua bao nhiêu?
👉 Vui lòng nhập số lượng (VD: 1, 2, 5...)""")
        except:
            pass
    
    def _send_text(self, msg, text):
        """Send text message"""
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': msg.facebook_user_id},
            'message': {'text': text},
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': msg.account_id.access_token}
        
        try:
            requests.post(url, json=payload, params=params, timeout=10)
        except:
            pass
    
    def _send_product_list(self, msg):
        """Send product list"""
        products = request.env['social.messenger.product'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', msg.company_id.id)
        ], order='sequence, id')
        
        if not products:
            self._send_text(msg, "❌ Xin lỗi, hiện tại chưa có sản phẩm!")
            return
        
        product_list = "📦 DANH SÁCH SẢN PHẨM\n\n"
        
        for idx, p in enumerate(products, 1):
            price = f"{p.price:,.0f} đ" if p.price > 0 else "Liên hệ"
            product_list += f"{idx}. {p.product_id.name}\n   💰 {price}\n\n"
        
        product_list += "👇 Chọn sản phẩm bạn muốn mua:"
        
        quick_replies = []
        for p in products[:11]:
            quick_replies.append({
                'content_type': 'text',
                'title': p.quick_reply_title or p.product_id.name[:20],
                'payload': f'PRODUCT_{p.id}'
            })
        
        url = 'https://graph.facebook.com/v18.0/me/messages'
        
        payload = {
            'recipient': {'id': msg.facebook_user_id},
            'message': {
                'text': product_list,
                'quick_replies': quick_replies
            },
            'messaging_type': 'RESPONSE'
        }
        
        params = {'access_token': msg.account_id.access_token}
        
        try:
            requests.post(url, json=payload, params=params, timeout=10)
        except:
            pass
    
    def _validate_order_data(self, msg):
        """Validate order data"""
        errors = []
        
        if not msg.customer_name:
            errors.append("Thiếu tên")
        if not msg.customer_phone:
            errors.append("Thiếu SĐT")
        if not msg.customer_address:
            errors.append("Thiếu địa chỉ")
        if not msg.selected_product_ids:
            errors.append("Chưa chọn SP")
        if not hasattr(msg, 'product_quantity') or not msg.product_quantity:
            errors.append("Thiếu số lượng")
        
        return {
            'valid': len(errors) == 0,
            'errors': ', '.join(errors)
        }
    
    def _extract_product_id(self, payload):
        """Extract product ID"""
        try:
            return int(payload.replace('PRODUCT_', ''))
        except:
            return None